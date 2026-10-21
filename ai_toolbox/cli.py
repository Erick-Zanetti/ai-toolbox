"""ai-toolbox: AI text commands and a translator for Wayland desktops.

  ai-toolbox                     command palette (search all commands)
  ai-toolbox run <command>       run on the selected text (output from the command file)
  ai-toolbox window <command>    same, but always show the result window
  ai-toolbox translate           translator window, prefilled with the selection
  ai-toolbox reply               write a reply to the selected message
  ai-toolbox settings            settings window
  ai-toolbox dictate             start/stop dictation (--then <command>, --cancel)
  ai-toolbox list                list commands
  ai-toolbox daemon              stay running so windows open instantly
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass

from . import config, desktop
from .i18n import t

APP_ID = "dev.aitoolbox.AiToolbox"
OBJECT_PATH = "/" + APP_ID.replace(".", "/")
TRANSLATE = "translate"
SETTINGS = "settings"
REPLY = "reply"


@dataclass(frozen=True)
class Invocation:
    """What was on screen when the shortcut fired."""

    text: str
    target: desktop.Target | None
    desk: desktop.Desktop


def notify(cfg: config.Config, level: str, body: str, **kw) -> int | None:
    """level: info (progress, done), warn (needs the user), error."""
    if cfg.notifications == "off" or (cfg.notifications == "errors" and level == "info"):
        return None
    if level == "error":
        kw.setdefault("urgency", "critical")
    elif level == "warn":
        kw.setdefault("urgency", "normal")
    return desktop.notify(body, **kw)


def capture(cfg: config.Config) -> Invocation:
    desk = desktop.detect()
    target = desk.focused()
    text = desktop.selection()
    # Opt-in: Ctrl+C with nothing selected clears a terminal prompt or copies
    # a whole line in some editors, so it is never sent to terminals.
    if (cfg.copy_fallback and not text.strip() and target is not None
            and target.app_id not in cfg.terminal_classes):
        text = desk.copy_selection(target, cfg.terminal_classes)
    return Invocation(text=text, target=target, desk=desk)


def deliver(action: str | None, text: str, inv: Invocation, cfg: config.Config) -> None:
    if not action or not text:
        return
    desktop.copy(text)
    if action == "copy":
        notify(cfg, "info", t("Copied."), timeout_ms=1500)
        return
    pasted = inv.target is not None and inv.desk.paste(inv.target, cfg.terminal_classes)
    if not pasted:
        notify(cfg, "warn", t("Copied: press Ctrl+V to paste."), timeout_ms=4000)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai-toolbox", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action")
    for action in ("run", "window"):
        p = sub.add_parser(action)
        p.add_argument("command")
    p = sub.add_parser("translate")
    p.add_argument("--empty", action="store_true", help="ignore the current selection")
    p.add_argument("--context", action="store_true", help="start with translation with context on")
    p = sub.add_parser("dictate")
    p.add_argument("--then", metavar="COMMAND", help="run a command on the transcript before pasting")
    p.add_argument("--cancel", action="store_true", help="stop without pasting")
    for action in ("list", "palette", "reply", "settings", "daemon"):
        sub.add_parser(action)
    return parser


def list_commands() -> int:
    try:
        cfg = config.load()
    except config.ConfigError as err:
        print(f"ai-toolbox: {err}", file=sys.stderr)
        return 2
    for cmd in cfg.commands.values():
        print(f"{cmd.id:<20} {cmd.output:<8} {cmd.model.provider}/{cmd.model.model:<14} {cmd.name}")
    return 0


def forward(argv: list[str]) -> bool:
    """Hand the call to a running instance through its 'cmdline' action using
    the gdbus binary: a few ms, versus ~100 ms to load GObject here."""
    gdbus = shutil.which("gdbus")
    if not gdbus:
        return False
    items = ", ".join("'" + a.replace("\\", "\\\\").replace("'", "\\'") + "'" for a in argv)
    result = subprocess.run(
        [gdbus, "call", "--session", "--dest", APP_ID, "--object-path", OBJECT_PATH,
         "--method", "org.freedesktop.Application.ActivateAction",
         "cmdline", f"[<@as [{items}]>]", "{}"],
        capture_output=True, timeout=5)
    return result.returncode == 0


def _primary_running() -> bool:
    """Is another ai-toolbox (daemon or open window) already on the session bus?"""
    from gi.repository import Gio, GLib

    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        reply = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus",
                              "org.freedesktop.DBus", "NameHasOwner",
                              GLib.Variant("(s)", (APP_ID,)), GLib.VariantType("(b)"),
                              Gio.DBusCallFlags.NONE, 500, None)
        return reply.unpack()[0]
    except GLib.Error:
        return False


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)  # validate (and --help) locally
    if args.action == "list":
        return list_commands()
    if args.action != "daemon" and forward(argv):
        return 0

    if _primary_running():
        # Hand the call to the running instance: Gio only, no GTK startup.
        from gi.repository import Gio

        remote = Gio.Application(application_id=APP_ID,
                                 flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        return remote.run(["ai-toolbox", *argv])

    from .app import run

    return run(["ai-toolbox", *argv])
