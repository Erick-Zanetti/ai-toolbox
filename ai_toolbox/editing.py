"""Pure text-editing logic behind the result window (no GTK)."""

from __future__ import annotations

import difflib
import re

_TOKENS = re.compile(r"\s+|\w+|[^\w\s]", re.UNICODE)


def word_diff(before: str, after: str) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Character spans removed from `before` and added in `after`, word by word."""
    old, new = _TOKENS.findall(before), _TOKENS.findall(after)

    def offsets(tokens: list[str]) -> list[int]:
        out, pos = [], 0
        for token in tokens:
            out.append(pos)
            pos += len(token)
        return out + [pos]

    old_at, new_at = offsets(old), offsets(new)
    removed, added = [], []
    matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op in ("replace", "delete") and i1 < i2:
            removed.append((old_at[i1], old_at[i2]))
        if op in ("replace", "insert") and j1 < j2:
            added.append((new_at[j1], new_at[j2]))
    return removed, added


def next_input(original: str, result: str, original_edited: bool, result_edited: bool) -> str:
    """What a retry runs on: the result (with any edits), unless only the
    original was edited since the last run, or there is no result yet."""
    if not result.strip():
        return original
    if original_edited and not result_edited:
        return original
    return result
