"""ai-toolbox: AI text commands and a translator for Wayland desktops.

  ai-toolbox                     command palette (search all commands)
  ai-toolbox run <command>       run on the selected text (output from the command file)
  ai-toolbox window <command>    same, but always show the result window
  ai-toolbox translate           translator window, prefilled with the selection
  ai-toolbox list                list commands
  ai-toolbox settings            settings window
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from . import config, desktop, prompts, providers
from .i18n import t

TRANSLATE = "translate"
SETTINGS = "settings"


@dataclass(frozen=True)
class Invocation:
    """What was on screen when the shortcut fired."""

    text: str
    target: desktop.Target | None
    desk: desktop.Desktop


def _notify(cfg: config.Config, level: str, body: str, **kw) -> int | None:
    """level: info (progress, done), warn (needs the user), error."""
    if cfg.notifications == "off" or (cfg.notifications == "errors" and level == "info"):
        return None
    if level == "error":
        kw.setdefault("urgency", "critical")
    elif level == "warn":
        kw.setdefault("urgency", "normal")
    return desktop.notify(body, **kw)


def _capture(cfg: config.Config) -> Invocation:
    desk = desktop.detect()
    target = desk.focused()
    text = desktop.selection()
    # Opt-in: Ctrl+C with nothing selected clears a terminal prompt or copies
    # a whole line in some editors, so it is never sent to terminals.
    if (cfg.copy_fallback and not text.strip() and target is not None
            and target.app_id not in cfg.terminal_classes):
        text = desk.copy_selection(target, cfg.terminal_classes)
    return Invocation(text=text, target=target, desk=desk)


def _deliver(action: str | None, text: str, inv: Invocation, cfg: config.Config) -> None:
    if not action or not text:
        return
    desktop.copy(text)
    if action == "copy":
        _notify(cfg, "info", t("Copied."), timeout_ms=1500)
        return
    pasted = inv.target is not None and inv.desk.paste(inv.target, cfg.terminal_classes)
    if not pasted:
        _notify(cfg, "warn", t("Copied: press Ctrl+V to paste."), timeout_ms=4000)


def _replace_in_place(cmd: config.Command, cfg: config.Config, inv: Invocation) -> int:
    note = _notify(cfg, "info", f"{cmd.name}…", timeout_ms=60_000)
    user = prompts.render(cmd.prompt, inv.text, cfg.context)
    try:
        result = providers.complete(cmd.model, prompts.COMMAND_SYSTEM, user)
    except providers.ProviderError as err:
        _notify(cfg, "error", t("{name} failed: {err}", name=cmd.name, err=err), replaces=note)
        return 1
    if not result:
        _notify(cfg, "warn", t("{name}: empty reply.", name=cmd.name), replaces=note)
        return 1
    if result == inv.text.strip():
        _notify(cfg, "info", t("{name}: nothing to change.", name=cmd.name), replaces=note, timeout_ms=2000)
        return 0
    _notify(cfg, "info", t("{name}: done.", name=cmd.name), replaces=note, timeout_ms=1500)
    _deliver("replace", result, inv, cfg)
    return 0


def _run(cmd: config.Command, cfg: config.Config, inv: Invocation, force_window: bool) -> int:
    if not inv.text.strip():
        _notify(cfg, "warn", t("{name}: select some text first.", name=cmd.name))
        return 1
    if cmd.output == "replace" and not force_window:
        return _replace_in_place(cmd, cfg, inv)

    from .ui import result

    outcome = result.show(cmd.name, cmd.model, prompts.COMMAND_SYSTEM,
                          lambda text: prompts.render(cmd.prompt, text, cfg.context), inv.text)
    _deliver(outcome.action, outcome.text, inv, cfg)
    return 0


def _translate(cfg: config.Config, inv: Invocation, contextual: bool = False) -> int:
    from .ui import translate as window

    outcome = window.show(cfg, inv.text, contextual)
    _deliver(outcome.action, outcome.text, inv, cfg)
    return 0


def run_command(name: str, force_window: bool) -> int:
    cfg = config.load()
    cmd = cfg.commands.get(name)
    if cmd is None:
        print(f"unknown command '{name}'. Try: ai-toolbox list", file=sys.stderr)
        return 2
    return _run(cmd, cfg, _capture(cfg), force_window)


def translate(use_selection: bool, contextual: bool = False) -> int:
    cfg = config.load()
    if use_selection:
        inv = _capture(cfg)
    else:
        desk = desktop.detect()
        inv = Invocation("", desk.focused(), desk)
    return _translate(cfg, inv, contextual)


def palette() -> int:
    cfg = config.load()
    inv = _capture(cfg)

    from .ui import palette as window

    choice = window.show(cfg, inv.text)
    if choice is None:
        return 0
    if choice == TRANSLATE:
        return _translate(cfg, inv)
    if choice == SETTINGS:
        return settings()
    return _run(cfg.commands[choice], cfg, inv, force_window=False)


def settings() -> int:
    from .ui import settings as window

    return window.show()


def list_commands() -> int:
    cfg = config.load()
    for cmd in cfg.commands.values():
        print(f"{cmd.id:<20} {cmd.output:<8} {cmd.model.provider}/{cmd.model.model:<14} {cmd.name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ai-toolbox", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action")
    for action in ("run", "window"):
        p = sub.add_parser(action)
        p.add_argument("command")
    p = sub.add_parser("translate")
    p.add_argument("--empty", action="store_true", help="ignore the current selection")
    p.add_argument("--context", action="store_true", help="start with translation with context on")
    sub.add_parser("list")
    sub.add_parser("palette")
    sub.add_parser("settings")
    args = parser.parse_args(argv)

    try:
        if args.action in ("run", "window"):
            return run_command(args.command, force_window=args.action == "window")
        if args.action == "translate":
            return translate(use_selection=not args.empty, contextual=args.context)
        if args.action == "list":
            return list_commands()
        if args.action == "settings":
            return settings()
        return palette()
    except config.ConfigError as err:
        desktop.notify(f"Config: {err}", urgency="critical")
        print(f"ai-toolbox: {err}", file=sys.stderr)
        return 2
