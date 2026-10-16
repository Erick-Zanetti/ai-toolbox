"""The GTK application: one process owns every window.

The first `ai-toolbox` call becomes the primary instance; later calls hand
their arguments to it over D-Bus (GApplication command line) and exit, so
windows open without starting Python/GTK again. `ai-toolbox daemon` keeps
the primary alive between uses."""

from __future__ import annotations

import argparse
import threading

from . import config, desktop, dictation, prompts, providers
from .cli import SETTINGS, TRANSLATE, Invocation, build_parser, capture, deliver, notify
from .i18n import t
from .ui.common import APP_ID, Adw, Gio, GLib, idle, install_css  # noqa: F401


class ToolboxApp(Adw.Application):
    def __init__(self) -> None:
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.connect("startup", lambda *_: install_css())
        self.engine: dictation.Engine | None = None
        self.dictating: dict | None = None
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
        if args.action == "dictate":
            self.dictate(cfg, args.then if args.then is not None else cfg.dictation.then, args.cancel)
            return 0
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

    # ── Dictation ──────────────────────────────────────────────────────────

    def dictate(self, cfg: config.Config, then: str, cancel: bool) -> None:
        """Toggle: the first call starts recording, the next one transcribes."""
        if self.dictating:
            self._cancel_dictation() if cancel else self._finish_dictation()
            return
        if cancel:
            return
        from .ui.dictation import Pill

        desk = desktop.detect()
        inv = Invocation("", desk.focused(), desk)
        try:
            recorder = dictation.Recorder()
        except dictation.DictationError as err:
            notify(cfg, "error", t("Dictation failed: {err}", err=err))
            return
        pill = Pill(self, self._finish_dictation, self._cancel_dictation)
        self.dictating = {"recorder": recorder, "pill": pill, "inv": inv, "cfg": cfg,
                          "then": then, "busy": False}
        self.hold()
        pill.present()

    def _end_dictation(self) -> None:
        session, self.dictating = self.dictating, None
        if session:
            session["pill"].close()
            self.release()

    def _cancel_dictation(self) -> None:
        if self.dictating and not self.dictating["busy"]:
            self.dictating["recorder"].cancel()
            self._end_dictation()

    def _engine(self, settings: config.Dictation, on_status) -> dictation.Engine:
        if self.engine is None or self.engine.settings != settings:
            self.engine = dictation.Engine(settings)
            GLib.timeout_add_seconds(60, lambda: (self.engine and self.engine.unload_if_idle(), True)[1])
        self.engine.on_status = on_status
        return self.engine

    def _finish_dictation(self) -> None:
        session = self.dictating
        if not session or session["busy"]:
            return
        session["busy"] = True
        cfg, pill = session["cfg"], session["pill"]
        try:
            wav = session["recorder"].stop()
        except dictation.DictationError as err:
            notify(cfg, "error", t("Dictation failed: {err}", err=err))
            self._end_dictation()
            return
        pill.set_state("transcribing")
        engine = self._engine(cfg.dictation, idle(lambda state: pill.set_state(state)))
        command = cfg.commands.get(session["then"]) if session["then"] else None

        def work() -> None:
            text, error = "", None
            try:
                text = engine.transcribe(wav)
                if text and command:
                    idle(lambda: pill.set_state("thinking", name=command.name))()
                    text = providers.complete(
                        command.model, prompts.command_system(cfg.glossary),
                        prompts.render(command.prompt, text, cfg.context))
            except (dictation.DictationError, providers.ProviderError) as err:
                error = str(err)
            finally:
                wav.unlink(missing_ok=True)
            idle(done)(text, error)

        def done(text: str, error: str | None) -> None:
            self._end_dictation()
            if error:
                notify(cfg, "error", t("Dictation failed: {err}", err=error))
            elif not text.strip():
                notify(cfg, "warn", t("Nothing heard."))
            else:
                deliver("replace", text.strip(), session["inv"], cfg)

        threading.Thread(target=work, daemon=True).start()

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
