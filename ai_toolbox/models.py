"""Which models each provider kind offers, for the Settings dropdowns.

- claude:    the aliases the Claude Code CLI accepts.
- codex:     the Codex CLI's own model cache (~/.codex/models_cache.json).
- openai:    GET {base_url}/models on the server (slow: use Catalog off the UI thread).
- dictation: the faster-whisper model sizes.
Nothing here raises: an unreadable source just offers no models."""

from __future__ import annotations

import json
import os
import threading
import urllib.request
from collections.abc import Callable, Iterable
from pathlib import Path

CLAUDE_MODELS = ("haiku", "sonnet", "opus")
WHISPER_MODELS = ("tiny", "base", "small", "medium", "large-v3", "large-v3-turbo")
REASONING_LEVELS = ("low", "medium", "high", "xhigh")
CODEX_CACHE = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "models_cache.json"
FETCH_TIMEOUT = 2.0


def options(current: str | None, known: Iterable[str]) -> list[str]:
    """`known` without duplicates, plus the configured value even when unknown,
    so opening Settings never loses or silently changes it."""
    return list(dict.fromkeys([*known, *([current] if current else [])]))


# ── codex ──────────────────────────────────────────────────────────────────

def _codex_listed(path: Path | None) -> list[dict]:
    try:
        raw = json.loads((path or CODEX_CACHE).read_text())
    except (OSError, ValueError):
        return []
    entries = raw.get("models") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        return []
    listed = [m for m in entries if isinstance(m, dict) and isinstance(m.get("slug"), str)
              and m.get("visibility") == "list"]

    def priority(entry: dict) -> float:
        value = entry.get("priority")
        is_number = isinstance(value, int | float) and not isinstance(value, bool)
        return value if is_number else float("inf")

    return sorted(listed, key=priority)  # stable: unranked keep the cache order


def _levels(entry: dict) -> list[str]:
    levels = entry.get("supported_reasoning_levels")
    if not isinstance(levels, list):
        return []
    return [lv["effort"] for lv in levels if isinstance(lv, dict) and isinstance(lv.get("effort"), str)]


def codex_models(path: Path | None = None) -> list[str]:
    return list(dict.fromkeys(m["slug"] for m in _codex_listed(path)))


def codex_reasoning(model: str, path: Path | None = None) -> list[str]:
    """Reasoning efforts `model` supports; for an unknown model, every level a
    listed model supports; without a cache, the common levels."""
    listed = _codex_listed(path)
    chosen = [m for m in listed if m["slug"] == model] or listed
    levels = list(dict.fromkeys(level for m in chosen for level in _levels(m)))
    return levels or list(REASONING_LEVELS)


# ── openai-compatible ──────────────────────────────────────────────────────

def openai_models(base_url: str, api_key_env: str | None = None,
                  timeout: float = FETCH_TIMEOUT) -> list[str]:
    """Model ids from the server's /models. Blocks up to `timeout` seconds."""
    if not base_url or not base_url.startswith(("http://", "https://")):
        return []
    headers = {}
    key = os.environ.get(api_key_env or "", "")
    if key:
        headers["Authorization"] = f"Bearer {key}"
    request = urllib.request.Request(base_url.rstrip("/") + "/models", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read()).get("data")
    except (OSError, ValueError, AttributeError):  # URLError/HTTPError/timeouts are OSError
        return []
    if not isinstance(data, list):
        return []
    return list(dict.fromkeys(m["id"] for m in data if isinstance(m, dict) and isinstance(m.get("id"), str)))


# ── by kind ────────────────────────────────────────────────────────────────

def known(kind: str, codex_cache: Path | None = None) -> list[str]:
    """Models for the kinds that answer at once (everything but openai)."""
    if kind == "claude":
        return list(CLAUDE_MODELS)
    if kind == "codex":
        return codex_models(codex_cache)
    if kind == "dictation":
        return list(WHISPER_MODELS)
    return []


class Catalog:
    """Answers "which models does this provider offer?". Server lists are fetched
    once, on a worker thread; `post` runs the answer where the caller wants it
    (GTK: on the main loop)."""

    def __init__(self, post: Callable[[Callable[[], None]], None],
                 fetch: Callable[..., list[str]] = openai_models, codex_cache: Path | None = None):
        self._post = post
        self._fetch = fetch
        self._codex_cache = codex_cache
        self._servers: dict[tuple, list[str]] = {}
        self._waiting: dict[tuple, list[Callable[[list[str]], None]]] = {}
        self._lock = threading.Lock()

    def request(self, name: str, provider: dict, answer: Callable[[list[str]], None]) -> None:
        kind = provider.get("type", name)
        if kind != "openai":
            answer(known(kind, self._codex_cache))
            return
        key = (provider.get("base_url", ""), provider.get("api_key_env"))
        with self._lock:
            if key in self._servers:
                cached = self._servers[key]
            else:
                cached = None
                first = key not in self._waiting
                self._waiting.setdefault(key, []).append(answer)
        if cached is not None:
            answer(list(cached))
        elif first:
            threading.Thread(target=self._load, args=(key,), daemon=True).start()

    def _load(self, key: tuple) -> None:
        found = self._fetch(*key)
        with self._lock:
            self._servers[key] = found
            waiting = self._waiting.pop(key, [])

        def deliver() -> None:
            for answer in waiting:
                answer(list(found))

        self._post(deliver)
