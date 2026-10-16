"""Model backends. Text streams back chunk by chunk.

- claude: Claude Code CLI, using its logged-in subscription.
- codex:  Codex CLI, using its logged-in ChatGPT subscription.
- openai: any OpenAI-compatible endpoint (Ollama, LM Studio, llama.cpp, vLLM...).
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from pathlib import Path

from .config import Model

WORKDIR = Path.home() / ".cache" / "ai-toolbox"


class ProviderError(Exception):
    pass


# ── CLI providers ──────────────────────────────────────────────────────────

def _claude_argv(model: Model, system: str) -> list[str]:
    # Fresh, tool-less session: no MCP, settings, hooks or saved history,
    # so it starts fast and only ever returns text.
    return [
        "claude", "-p",
        "--model", model.model,
        "--system-prompt", system,
        "--tools", "",
        "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
        "--setting-sources", "",
        "--disable-slash-commands",
        "--no-session-persistence",
        "--exclude-dynamic-system-prompt-sections",
        "--output-format", "stream-json", "--include-partial-messages", "--verbose",
    ]


def _codex_argv(model: Model) -> list[str]:
    argv = [
        "codex", "exec", "--skip-git-repo-check", "--ephemeral",
        "-s", "read-only", "-m", model.model,
    ]
    if model.reasoning:
        argv += ["-c", f"model_reasoning_effort={model.reasoning}"]
    return argv + ["-"]


def _claude_chunks(lines: Iterator[str]) -> Iterator[str]:
    for line in lines:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "stream_event":
            delta = event["event"].get("delta", {})
            if delta.get("type") == "text_delta":
                yield delta["text"]
        elif event.get("type") == "result" and event.get("is_error"):
            raise ProviderError(event.get("result") or "Claude returned an error")


class CliRun:
    def __init__(self, model: Model, system: str, user: str):
        WORKDIR.mkdir(parents=True, exist_ok=True)
        if model.type == "claude":
            argv, stdin = _claude_argv(model, system), user
        else:
            # codex exec has no system prompt flag: instructions go first.
            argv, stdin = _codex_argv(model), f"{system}\n\n{user}"
        self.model = model
        self.cancelled = False
        try:
            self._proc = subprocess.Popen(
                argv, cwd=WORKDIR, text=True,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        except FileNotFoundError as err:
            raise ProviderError(f"'{argv[0]}' is not installed") from err
        self._proc.stdin.write(stdin)
        self._proc.stdin.close()

    def chunks(self) -> Iterator[str]:
        out = self._proc.stdout
        if self.model.type == "claude":
            yield from _claude_chunks(out)
        else:
            yield out.read().strip()
        code = self._proc.wait()
        if code != 0 and not self.cancelled:
            err = self._proc.stderr.read().strip().splitlines()
            raise ProviderError(err[-1] if err else f"{self.model.provider} exited {code}")

    def cancel(self) -> None:
        self.cancelled = True
        if self._proc.poll() is None:
            self._proc.kill()


# ── OpenAI-compatible HTTP ─────────────────────────────────────────────────

def _sse_chunks(lines: Iterator[bytes]) -> Iterator[str]:
    for raw in lines:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            return
        try:
            event = json.loads(data)
        except json.JSONDecodeError:
            continue
        if "error" in event:
            raise ProviderError(str(event["error"].get("message", event["error"])))
        for choice in event.get("choices", []):
            text = (choice.get("delta") or {}).get("content")
            if text:
                yield text


class HttpRun:
    def __init__(self, model: Model, system: str, user: str):
        self.model = model
        self.cancelled = False
        headers = {"Content-Type": "application/json"}
        key = os.environ.get(model.api_key_env or "", "")
        if key:
            headers["Authorization"] = f"Bearer {key}"
        body = {
            "model": model.model,
            "stream": True,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
        }
        request = urllib.request.Request(
            model.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(body).encode(), headers=headers, method="POST",
        )
        try:
            self._response = urllib.request.urlopen(request, timeout=120)
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", "replace")[:300]
            raise ProviderError(f"{model.provider}: HTTP {err.code} {detail}") from err
        except (urllib.error.URLError, OSError) as err:
            raise ProviderError(f"{model.provider}: {getattr(err, 'reason', err)}") from err

    def chunks(self) -> Iterator[str]:
        try:
            yield from _sse_chunks(self._response)
        except (OSError, ValueError) as err:
            if not self.cancelled:
                raise ProviderError(f"{self.model.provider}: {err}") from err
        finally:
            self._response.close()

    def cancel(self) -> None:
        self.cancelled = True
        try:
            self._response.close()
        except OSError:
            pass


# ── Entry points ───────────────────────────────────────────────────────────

def start(model: Model, system: str, user: str) -> CliRun | HttpRun:
    if model.type in ("claude", "codex"):
        return CliRun(model, system, user)
    if model.type == "openai":
        return HttpRun(model, system, user)
    raise ProviderError(f"unknown provider type '{model.type}'")


def complete(model: Model, system: str, user: str) -> str:
    return "".join(start(model, system, user).chunks()).strip()


def stream_in_thread(
    model: Model,
    system: str,
    user: str,
    on_chunk: Callable[[str], None],
    on_done: Callable[[str | None], None],
):
    """Start a request on a worker thread; on_done gets an error message or None.
    Callbacks run on the worker thread: GTK callers wrap them in GLib.idle_add.
    Connecting happens on the worker too, so the UI never blocks."""

    class Handle:
        run = None
        cancelled = False

        def cancel(self) -> None:
            self.cancelled = True
            if self.run:
                self.run.cancel()

    handle = Handle()

    def work() -> None:
        try:
            handle.run = start(model, system, user)
            if handle.cancelled:
                handle.run.cancel()
                return
            for chunk in handle.run.chunks():
                if handle.cancelled:
                    return
                on_chunk(chunk)
        except ProviderError as err:
            if not handle.cancelled:
                on_done(str(err))
            return
        if not handle.cancelled:
            on_done(None)

    threading.Thread(target=work, daemon=True).start()
    return handle
