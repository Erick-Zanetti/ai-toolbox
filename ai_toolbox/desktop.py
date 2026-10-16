"""Desktop glue for Wayland: read the selection, remember the focused window,
paste the result back into it, notify.

Window tracking uses the compositor's IPC (Hyprland, Sway, niri). Pasting uses
the compositor when it can send keys itself (Hyprland), else wtype (wlroots)
or ydotool (any desktop, needs ydotoold). Without any of them the result stays
on the clipboard and the user is told to paste it."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass

APP_NAME = "AI Toolbox"


@dataclass(frozen=True)
class Target:
    """The window the text came from. `id` is None when the desktop has no IPC."""

    id: str | None
    app_id: str


def _run(argv: list[str], **kw) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(argv, text=True, capture_output=True, **kw)
    except FileNotFoundError:
        return subprocess.CompletedProcess(argv, 127, "", f"{argv[0]}: not found")


def _json(argv: list[str]):
    result = _run(argv)
    try:
        return json.loads(result.stdout) if result.returncode == 0 else None
    except json.JSONDecodeError:
        return None


# ── Key injection ──────────────────────────────────────────────────────────

# Linux input keycodes for ydotool.
_KEYCODES = {"c": 46, "v": 47}


def _inject_shortcut(key: str, terminal: bool) -> bool:
    """Ctrl+<key> (Ctrl+Shift+<key> in terminals) through wtype or ydotool."""
    if shutil.which("wtype"):
        mods = ["-M", "ctrl"] + (["-M", "shift"] if terminal else [])
        if _run(["wtype", *mods, "-k", key]).returncode == 0:
            return True
    if shutil.which("ydotool"):
        code = _KEYCODES[key]
        keys = ["29:1"] + (["42:1"] if terminal else []) + [f"{code}:1", f"{code}:0"]
        keys += (["42:0"] if terminal else []) + ["29:0"]
        if _run(["ydotool", "key", *keys]).returncode == 0:
            return True
    return False


# ── Compositors ────────────────────────────────────────────────────────────

class Desktop:
    name = "generic"

    def focused(self) -> Target | None:
        return Target(id=None, app_id="")

    def focus(self, target: Target) -> None:
        pass

    def send_shortcut(self, target: Target, key: str, terminal: bool) -> bool:
        return _inject_shortcut(key, terminal)

    def paste(self, target: Target, terminal_classes: tuple[str, ...]) -> bool:
        self.focus(target)
        time.sleep(0.12)  # let focus land before the keys
        return self.send_shortcut(target, "v", target.app_id in terminal_classes)

    def copy_selection(self, target: Target, terminal_classes: tuple[str, ...]) -> str:
        """Fallback for apps without a primary selection: press Ctrl+C in the
        window and read what landed on the clipboard."""
        before = clipboard()
        if not self.send_shortcut(target, "c", target.app_id in terminal_classes):
            return ""
        for _ in range(10):
            time.sleep(0.04)
            now = clipboard()
            if now != before:
                return now
        return ""


class Hyprland(Desktop):
    name = "hyprland"

    def focused(self) -> Target | None:
        data = _json(["hyprctl", "activewindow", "-j"]) or {}
        return Target(data["address"], data.get("class", "")) if data.get("address") else None

    def _dispatch(self, lua: str) -> bool:
        return _run(["hyprctl", "dispatch", lua]).stdout.strip() == "ok"

    def focus(self, target: Target) -> None:
        self._dispatch(f'hl.dsp.focus({{ window = "address:{target.id}" }})')

    def send_shortcut(self, target: Target, key: str, terminal: bool) -> bool:
        mods = "CTRL SHIFT" if terminal else "CTRL"
        lua = (f'hl.dsp.send_shortcut({{ mods = "{mods}", key = "{key.upper()}", '
               f'window = "address:{target.id}" }})')
        return self._dispatch(lua) or _inject_shortcut(key, terminal)


class Sway(Desktop):
    name = "sway"

    def focused(self) -> Target | None:
        def walk(node):
            if node.get("focused"):
                return node
            for child in node.get("nodes", []) + node.get("floating_nodes", []):
                found = walk(child)
                if found:
                    return found
            return None

        node = walk(_json(["swaymsg", "-t", "get_tree"]) or {})
        if not node or node.get("type") not in ("con", "floating_con"):
            return None
        app_id = node.get("app_id") or (node.get("window_properties") or {}).get("class", "")
        return Target(str(node["id"]), app_id)

    def focus(self, target: Target) -> None:
        _run(["swaymsg", f"[con_id={target.id}]", "focus"])


class Niri(Desktop):
    name = "niri"

    def focused(self) -> Target | None:
        data = _json(["niri", "msg", "-j", "focused-window"])
        return Target(str(data["id"]), data.get("app_id") or "") if data else None

    def focus(self, target: Target) -> None:
        _run(["niri", "msg", "action", "focus-window", "--id", target.id])


def detect() -> Desktop:
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        return Hyprland()
    if os.environ.get("SWAYSOCK"):
        return Sway()
    if os.environ.get("NIRI_SOCKET"):
        return Niri()
    return Desktop()


def can_inject() -> bool:
    return isinstance(detect(), Hyprland) or bool(shutil.which("wtype") or shutil.which("ydotool"))


# ── Clipboard and notifications ────────────────────────────────────────────

def selection() -> str:
    """Highlighted text (Wayland primary selection): no Ctrl+C needed."""
    result = _run(["wl-paste", "--primary", "--no-newline", "--type", "text/plain"])
    return result.stdout if result.returncode == 0 else ""


def clipboard() -> str:
    result = _run(["wl-paste", "--no-newline", "--type", "text/plain"])
    return result.stdout if result.returncode == 0 else ""


def copy(text: str) -> None:
    subprocess.run(["wl-copy", "--type", "text/plain"], input=text, text=True, check=True)


def notify(body: str, *, replaces: int | None = None, urgency: str = "low",
           timeout_ms: int | None = None) -> int | None:
    argv = ["notify-send", "-a", APP_NAME, "-u", urgency, "-p"]
    if replaces:
        argv += ["-r", str(replaces)]
    if timeout_ms is not None:
        argv += ["-t", str(timeout_ms)]
    result = _run([*argv, APP_NAME, body])
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None
