"""The last results you delivered (replaced, pasted or copied), newest first.

Kept as JSON in $XDG_STATE_HOME/ai-toolbox/history.json, readable only by
you (it holds whatever text you worked on), and rewritten atomically so a
crash never leaves half a file."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from pathlib import Path

STATE_DIR = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "ai-toolbox"
HISTORY_FILE = STATE_DIR / "history.json"
PREVIEW_CHARS = 80


@dataclass(frozen=True)
class Entry:
    time: str  # ISO 8601, local time, to the second
    source: str  # command id, "translate", "reply" or "dictate"
    name: str  # what the user saw, e.g. "Fix spelling"
    input: str
    output: str


def entry(source: str, name: str, text: str, output: str, now: datetime | None = None) -> Entry:
    stamp = (now or datetime.now()).replace(microsecond=0).isoformat()
    return Entry(stamp, source, name, text, output)


def _parse(item) -> Entry | None:
    names = [f.name for f in fields(Entry)]
    if not isinstance(item, dict) or not all(isinstance(item.get(n), str) for n in names):
        return None
    return Entry(**{n: item[n] for n in names})


def load(path: Path | None = None) -> list[Entry]:
    """Newest first. A missing or unreadable file is an empty history."""
    try:
        raw = json.loads((path or HISTORY_FILE).read_text())
    except (OSError, ValueError):
        return []
    if not isinstance(raw, list):
        return []
    return [e for e in map(_parse, raw) if e is not None]


def save(entries: list[Entry], path: Path | None = None) -> None:
    path = path or HISTORY_FILE
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".history-", suffix=".json")  # 0600
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump([asdict(e) for e in entries], fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def trim(entries: list[Entry], max_entries: int) -> list[Entry]:
    return entries[:max(0, max_entries)]


def add(item: Entry, max_entries: int, path: Path | None = None) -> list[Entry]:
    entries = trim([item, *load(path)], max_entries)
    save(entries, path)
    return entries


def clear(path: Path | None = None) -> None:
    (path or HISTORY_FILE).unlink(missing_ok=True)


def matches(item: Entry, query: str) -> bool:
    """Search box: every word appears somewhere (output, input, name, source)."""
    haystack = f"{item.output} {item.input} {item.name} {item.source}".lower()
    return all(word in haystack for word in query.lower().split())


def preview(text: str, width: int = PREVIEW_CHARS) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= width else flat[:width - 1] + "…"


def short_time(item: Entry) -> str:
    """'2026-10-21T14:05:09' → '2026-10-21 14:05'."""
    return item.time.replace("T", " ")[:16]


def summary(item: Entry) -> str:
    """One line for `ai-toolbox history`."""
    return f"{short_time(item)}  {item.source:<16} {preview(item.output)}"
