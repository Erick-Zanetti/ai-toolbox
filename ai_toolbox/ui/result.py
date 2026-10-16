"""Raycast-style result window: the answer streams in, changed words are
highlighted, and Ctrl+Enter sends it back over the selection."""

from __future__ import annotations

from dataclasses import dataclass

from .. import providers
from ..config import Model
from ..i18n import t
from .common import Adw, Gtk, buffer_text, highlight_changes, idle, run_window, shortcut, text_view



@dataclass
class Outcome:
    action: str | None = None  # "replace" | "copy" | None (closed)
    text: str = ""


def show(title: str, model: Model, system: str, user: str, original: str) -> Outcome:
    outcome = Outcome()

    def build(app: Adw.Application) -> Adw.ApplicationWindow:
        win = Adw.ApplicationWindow(application=app, title=f"AI Toolbox · {title}",
                                    default_width=760, default_height=440)
        header = Adw.HeaderBar(title_widget=Adw.WindowTitle(
            title=title, subtitle=f"{model.provider} · {model.model}"))
        spinner = Adw.Spinner()
        header.pack_end(spinner)

        scroller, view = text_view(editable=True)
        status = Gtk.Label(xalign=0, wrap=True, css_classes=["atb-hint"])
        keys = ["Ctrl+Enter replace", "Ctrl+Shift+C copy", "Ctrl+R retry", "Esc close"]
        hints = Gtk.Label(label="  ·  ".join(t(k) for k in keys),
                          xalign=0, css_classes=["atb-hint"])
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                       margin_start=14, margin_end=14, margin_bottom=12, margin_top=4)
        body.append(scroller)
        body.append(status)
        body.append(hints)

        toolbar = Adw.ToolbarView(content=body)
        toolbar.add_top_bar(header)
        win.set_content(toolbar)

        state = {"run": None}

        def on_chunk(text: str) -> None:
            buf = view.get_buffer()
            buf.insert(buf.get_end_iter(), text)

        def on_done(error: str | None) -> None:
            spinner.set_visible(False)
            if error:
                status.set_label(t("Error: {err}", err=error))
                return
            buf = view.get_buffer()
            text = buffer_text(view).strip()
            buf.set_text(text)
            highlight_changes(view, original)
            status.set_label(t("No changes.") if text == original.strip() else "")

        def start() -> None:
            if state["run"]:
                state["run"].cancel()
            view.get_buffer().set_text("")
            status.set_label("")
            spinner.set_visible(True)
            try:
                state["run"] = providers.stream_in_thread(
                    model, system, user, idle(on_chunk), idle(on_done))
            except providers.ProviderError as err:
                on_done(str(err))

        def finish(action: str | None) -> None:
            if state["run"]:
                state["run"].cancel()
            outcome.action = action
            outcome.text = buffer_text(view).strip()
            win.close()

        shortcut(win, "<Control>Return", lambda: finish("replace"))
        shortcut(win, "<Control><Shift>c", lambda: finish("copy"))
        shortcut(win, "<Control>r", start)
        shortcut(win, "Escape", lambda: finish(None))
        def on_close(*_) -> bool:
            if state["run"]:
                state["run"].cancel()
            return False

        win.connect("close-request", on_close)

        start()
        return win

    run_window(build)
    return outcome
