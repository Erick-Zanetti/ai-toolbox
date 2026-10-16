"""Read and write the config files as plain dicts (what the settings window edits).

Files are rewritten in place, so a config.toml symlinked from a dotfiles repo
stays a symlink."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

from .config import CONFIG_DIR, ensure_user_config


# ── Minimal TOML writer for this config's shape ───────────────────────────

def _scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        if "\n" in value and "'''" not in value:
            return "'''\n" + value + "'''"  # exact round trip
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_scalar(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{_key(k)} = {_scalar(v)}" for k, v in value.items()) + " }"
    raise TypeError(f"cannot write {type(value).__name__} to TOML")


def _key(key: str) -> str:
    return key if re.fullmatch(r"[A-Za-z0-9_-]+", key) else json.dumps(key)


def _is_table_of_tables(value) -> bool:
    return isinstance(value, dict) and bool(value) and all(isinstance(v, dict) for v in value.values())


def dumps(data: dict, header: str = "") -> str:
    """Scalars first; a dict of dicts becomes [a.b] tables, any other dict
    becomes [a] with nested dicts written inline."""
    lines = [header.rstrip()] if header else []
    for key, value in data.items():
        if not isinstance(value, dict):
            lines.append(f"{_key(key)} = {_scalar(value)}")
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        sections = value.items() if _is_table_of_tables(value) else [(None, value)]
        for sub, table in sections:
            name = _key(key) if sub is None else f"{_key(key)}.{_key(sub)}"
            lines += ["", f"[{name}]"]
            lines += [f"{_key(k)} = {_scalar(v)}" for k, v in table.items()]
    return "\n".join(lines).lstrip("\n") + "\n"


# ── Files ──────────────────────────────────────────────────────────────────

CONFIG_HEADER = """\
# ai-toolbox config. Edited by `ai-toolbox settings`; hand edits are fine too.
# Provider types: claude (Claude Code CLI), codex (Codex CLI),
# openai (OpenAI-compatible endpoint: Ollama, LM Studio...)."""


class Store:
    def __init__(self, config_dir: Path = CONFIG_DIR):
        self.dir = config_dir
        if config_dir == CONFIG_DIR:
            ensure_user_config(config_dir)

    @property
    def commands_dir(self) -> Path:
        return self.dir / "commands"

    def _write(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as fh:  # in place: keeps symlinks
            fh.write(text)

    def config(self) -> dict:
        with (self.dir / "config.toml").open("rb") as fh:
            return tomllib.load(fh)

    def save_config(self, data: dict) -> None:
        self._write(self.dir / "config.toml", dumps(data, CONFIG_HEADER))

    def commands(self) -> dict[str, dict]:
        out = {}
        for path in sorted(self.commands_dir.glob("*.toml")):
            with path.open("rb") as fh:
                out[path.stem] = tomllib.load(fh)
        return out

    def save_command(self, command_id: str, data: dict) -> None:
        self._write(self.commands_dir / f"{command_id}.toml", dumps(data))

    def delete_command(self, command_id: str) -> None:
        (self.commands_dir / f"{command_id}.toml").unlink(missing_ok=True)

    def new_command_id(self, name: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "command"
        candidate, n = base, 2
        while (self.commands_dir / f"{candidate}.toml").exists():
            candidate, n = f"{base}-{n}", n + 1
        return candidate

    def context(self) -> str:
        path = self.dir / "context.md"
        return path.read_text() if path.exists() else ""

    def save_context(self, text: str) -> None:
        self._write(self.dir / "context.md", text)
