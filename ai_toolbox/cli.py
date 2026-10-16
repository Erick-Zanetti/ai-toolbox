"""ai-toolbox: AI text commands and a translator for Wayland desktops.

  ai-toolbox                     command palette (search all commands)
  ai-toolbox run <command>       run on the selected text (output from the command file)
  ai-toolbox window <command>    same, but always show the result window
  ai-toolbox translate           translator window, prefilled with the selection
  ai-toolbox list                list commands
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from . import config, desktop, prompts, providers
from .i18n import t

TRANSLATE = "translate"


@dataclass(frozen=True)
class Invocation:
    """What was on screen when the shortcut fired."""

    text: str
    target: desktop.Target | None
    desk: desktop.Desktop


def _capture(cfg: config.Config) -> Invocation:
    desk = desktop.detect()
    target = desk.focused()
    text = desktop.selection()
    if not text.strip() and target is not None:
        text = desk.copy_selection(target, cfg.terminal_classes)
    return Invocation(text=text, target=target, desk=desk)


def _deliver(action: str | None, text: str, inv: Invocation, cfg: config.Config) -> None:
    if not action or not text:
        return
    desktop.copy(text)
    if action == "copy":
        desktop.notify(t("Copied."), timeout_ms=1500)
        return
    pasted = inv.target is not None and inv.desk.paste(inv.target, cfg.terminal_classes)
    if not pasted:
        desktop.notify(t("Copied: press Ctrl+V to paste."), urgency="normal", timeout_ms=4000)


def _replace_in_place(cmd: config.Command, cfg: config.Config, inv: Invocation) -> int:
    note = desktop.notify(f"{cmd.name}…", timeout_ms=60_000)
    user = prompts.render(cmd.prompt, inv.text, cfg.context)
    try:
        result = providers.complete(cmd.model, prompts.COMMAND_SYSTEM, user)
    except providers.ProviderError as err:
        desktop.notify(t("{name} failed: {err}", name=cmd.name, err=err),
                       replaces=note, urgency="critical")
        return 1
    if not result:
        desktop.notify(t("{name}: empty reply.", name=cmd.name), replaces=note, urgency="normal")
        return 1
    if result == inv.text.strip():
        desktop.notify(t("{name}: nothing to change.", name=cmd.name), replaces=note, timeout_ms=2000)
        return 0
    desktop.notify(t("{name}: done.", name=cmd.name), replaces=note, timeout_ms=1500)
    _deliver("replace", result, inv, cfg)
    return 0


def _run(cmd: config.Command, cfg: config.Config, inv: Invocation, force_window: bool) -> int:
    if not inv.text.strip():
        desktop.notify(t("{name}: select some text first.", name=cmd.name), urgency="normal")
        return 1
    if cmd.output == "replace" and not force_window:
        return _replace_in_place(cmd, cfg, inv)

    from .ui import result

    outcome = result.show(cmd.name, cmd.model, prompts.COMMAND_SYSTEM,
                          prompts.render(cmd.prompt, inv.text, cfg.context), inv.text)
    _deliver(outcome.action, outcome.text, inv, cfg)
    return 0


def _translate(cfg: config.Config, inv: Invocation) -> int:
    from .ui import translate as window

    outcome = window.show(cfg, inv.text)
    _deliver(outcome.action, outcome.text, inv, cfg)
    return 0


def run_command(name: str, force_window: bool) -> int:
    cfg = config.load()
    cmd = cfg.commands.get(name)
    if cmd is None:
        print(f"unknown command '{name}'. Try: ai-toolbox list", file=sys.stderr)
        return 2
    return _run(cmd, cfg, _capture(cfg), force_window)


def translate(use_selection: bool) -> int:
    cfg = config.load()
    if use_selection:
        inv = _capture(cfg)
    else:
        desk = desktop.detect()
        inv = Invocation("", desk.focused(), desk)
    return _translate(cfg, inv)


def palette() -> int:
    cfg = config.load()
    inv = _capture(cfg)

    from .ui import palette as window

    choice = window.show(cfg, inv.text)
    if choice is None:
        return 0
    if choice == TRANSLATE:
        return _translate(cfg, inv)
    return _run(cfg.commands[choice], cfg, inv, force_window=False)


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
    sub.add_parser("list")
    sub.add_parser("palette")
    args = parser.parse_args(argv)

    try:
        if args.action in ("run", "window"):
            return run_command(args.command, force_window=args.action == "window")
        if args.action == "translate":
            return translate(use_selection=not args.empty)
        if args.action == "list":
            return list_commands()
        return palette()
    except config.ConfigError as err:
        desktop.notify(f"Config: {err}", urgency="critical")
        print(f"ai-toolbox: {err}", file=sys.stderr)
        return 2
