"""The GTK application: one process owns every window.

The first `ai-toolbox` call becomes the primary instance; later calls hand
their arguments to it over D-Bus (GApplication command line) and exit, so
windows open without starting Python/GTK again. `ai-toolbox daemon` keeps
the primary alive between uses."""

from __future__ import annotations

import argparse
import threading

from . import config, desktop, prompts, providers
from .cli import SETTINGS, TRANSLATE, Invocation, build_parser, capture, deliver, notify
from .i18n import t
from .ui.common import APP_ID, Adw, Gio, GLib, idle, install_css  # noqa: F401


class ToolboxApp(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.connect("startup", lambda *_: install_css())
        # Fast path for later calls: `gdbus call ... ActivateAction cmdline`
        # (see cli.forward), no Python/GObject start-up on the caller side.
        action = Gio.SimpleAction.new("cmdline", GLib.VariantType("as"))
        action.connect("activate", lambda _a, param: self._from_args(param.unpack()))
        self.add_action(action)

    # ── Command line (local or forwarded from another call) ────────────────

    def do_command_line(self, command_line: Gio.ApplicationCommandLine) -> int:
        try:
            args = build_parser().parse_args(command_line.get_arguments()[1:])
        except SystemExit as exit_:
            return int(exit_.code or 0)
        try:
            return self._dispatch(args)
        except config.ConfigError as err:
            desktop.notify(f"Config: {err}", urgency="critical")
            command_line.printerr_literal(f"ai-toolbox: {err}\n")
            return 2

    def _from_args(self, argv: list[str]) -> None:
        try:
            self._dispatch(build_parser().parse_args(argv))
        except (SystemExit, config.ConfigError) as err:
            desktop.notify(f"ai-toolbox: {err}", urgency="critical")

    def _dispatch(self, args: argparse.Namespace) -> int:
        if args.action == "daemon":
            self.hold()  # stay alive with no windows
            return 0
        if args.action == "settings":
            self.open_settings()
            return 0
        cfg = config.load()  # fresh on every call: edits apply without a restart
        if args.action in ("run", "window"):
            cmd = cfg.commands.get(args.command)
            if cmd is None:
                notify(cfg, "error", f"unknown command '{args.command}'")
                return 2
            self.run_command(cmd, cfg, capture(cfg), force_window=args.action == "window")
        elif args.action == "translate":
            if args.empty:
                desk = desktop.detect()
                inv = Invocation("", desk.focused(), desk)
            else:
                inv = capture(cfg)
            self.open_translate(cfg, inv, args.context)
        else:
            self.open_palette(cfg, capture(cfg))
        return 0

    # ── Flows ──────────────────────────────────────────────────────────────

    def run_command(self, cmd: config.Command, cfg: config.Config, inv: Invocation,
                    force_window: bool) -> None:
        if not inv.text.strip():
            notify(cfg, "warn", t("{name}: select some text first.", name=cmd.name))
            return
        system = prompts.command_system(cfg.glossary)
        if cmd.output == "replace" and not force_window:
            self._replace_in_place(cmd, cfg, inv, system)
            return

        from .ui import result

        window = result.open_window(
            self, cmd.name, cmd.model, system,
            lambda text: prompts.render(cmd.prompt, text, cfg.context), inv.text, cmd.diff,
            lambda outcome: deliver(outcome.action, outcome.text, inv, cfg))
        window.present()

    def _replace_in_place(self, cmd: config.Command, cfg: config.Config, inv: Invocation,
                          system: str) -> None:
        note = notify(cfg, "info", f"{cmd.name}…", timeout_ms=60_000)
        user = prompts.render(cmd.prompt, inv.text, cfg.context)
        self.hold()

        def finish(result: str | None, error: str | None) -> None:
            try:
                if error:
                    notify(cfg, "error", t("{name} failed: {err}", name=cmd.name, err=error),
                           replaces=note)
                elif not result:
                    notify(cfg, "warn", t("{name}: empty reply.", name=cmd.name), replaces=note)
                elif result == inv.text.strip():
                    notify(cfg, "info", t("{name}: nothing to change.", name=cmd.name),
                           replaces=note, timeout_ms=2000)
                else:
                    notify(cfg, "info", t("{name}: done.", name=cmd.name),
                           replaces=note, timeout_ms=1500)
                    deliver("replace", result, inv, cfg)
            finally:
                self.release()

        def work() -> None:
            try:
                result, error = providers.complete(cmd.model, system, user), None
            except providers.ProviderError as err:
                result, error = None, str(err)
            idle(finish)(result, error)

        threading.Thread(target=work, daemon=True).start()

    def open_translate(self, cfg: config.Config, inv: Invocation, contextual: bool = False) -> None:
        from .ui import translate

        translate.open_window(
            self, cfg, inv.text, contextual,
            lambda outcome: deliver(outcome.action, outcome.text, inv, cfg)).present()

    def open_palette(self, cfg: config.Config, inv: Invocation) -> None:
        from .ui import palette

        def chosen(choice: str | None) -> None:
            if choice is None:
                return
            # Open the next window after the palette is gone, so focus is sane;
            # hold the app so it does not quit in between (no daemon running).
            self.hold()

            def next_window() -> bool:
                try:
                    self._after_palette(choice, cfg, inv)
                finally:
                    self.release()
                return False

            GLib.idle_add(next_window)

        palette.open_window(self, cfg, inv.text, chosen).present()

    def _after_palette(self, choice: str, cfg: config.Config, inv: Invocation) -> None:
        if choice == TRANSLATE:
            self.open_translate(cfg, inv)
        elif choice == SETTINGS:
            self.open_settings()
        else:
            self.run_command(cfg.commands[choice], cfg, inv, force_window=False)

    def open_settings(self) -> None:
        for window in self.get_windows():
            if getattr(window, "is_settings", False):
                window.present()
                return
        from .ui import settings

        window = settings.open_window(self)
        window.is_settings = True
        window.present()


def run(argv: list[str]) -> int:
    return ToolboxApp().run(argv)
