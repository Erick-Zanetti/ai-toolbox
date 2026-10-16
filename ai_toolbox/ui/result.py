"""Result window, Raycast style: original on top, result below, both editable.
What left the original is struck through in red, what is new in the result is
green. Ctrl+R runs again on the result (with your edits); Ctrl+Enter sends the
result back over the selection."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .. import providers
from ..config import Model
from ..editing import next_input
from ..i18n import t
from .common import (Adw, GLib, Gtk, buffer_text, clear_diff, idle, run_window,
                     shortcut, show_diff, text_view)

DIFF_DEBOUNCE_MS = 250
KEYS = ("Ctrl+Enter replace", "Ctrl+Shift+C copy", "Ctrl+R retry", "Esc close")


@dataclass
class Outcome:
    action: str | None = None  # "replace" | "copy" | None (closed)
    text: str = ""


def _pane(title: str, view_scroller: Gtk.Widget) -> Gtk.Box:
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    box.append(Gtk.Label(label=title, xalign=0, css_classes=["atb-hint"]))
    box.append(view_scroller)
    return box


def show(title: str, model: Model, system: str, render: Callable[[str], str],
         original: str) -> Outcome:
    """`render(text)` builds the user prompt for a given input text."""
    outcome = Outcome()

    def build(app: Adw.Application) -> Adw.ApplicationWindow:
        win = Adw.ApplicationWindow(application=app, title=f"AI Toolbox · {title}",
                                    default_width=820, default_height=600)
        header = Adw.HeaderBar(title_widget=Adw.WindowTitle(
            title=title, subtitle=f"{model.provider} · {model.model}"))
        spinner = Adw.Spinner()
        header.pack_end(spinner)

        in_scroll, in_view = text_view(editable=True)
        out_scroll, out_view = text_view(editable=True)
        status = Gtk.Label(xalign=0, wrap=True, css_classes=["atb-hint"])
        hints = Gtk.Label(label="  ·  ".join(t(k) for k in KEYS), xalign=1,
                          hexpand=True, css_classes=["atb-hint"])
        footer = Gtk.Box(spacing=12)
        footer.append(status)
        footer.append(hints)

        panes = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL, wide_handle=True,
                          vexpand=True, shrink_start_child=False, shrink_end_child=False)
        panes.set_start_child(_pane(t("Original"), in_scroll))
        panes.set_end_child(_pane(t("Result"), out_scroll))
        panes.set_position(200)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                       margin_start=14, margin_end=14, margin_bottom=12, margin_top=4)
        body.append(panes)
        body.append(footer)
        toolbar = Adw.ToolbarView(content=body)
        toolbar.add_top_bar(header)
        win.set_content(toolbar)

        state = {"run": None, "streaming": False, "quiet": False,
                 "in_edited": False, "out_edited": False, "timer": 0}

        def set_text(view: Gtk.TextView, text: str) -> None:
            state["quiet"] = True
            view.get_buffer().set_text(text)
            state["quiet"] = False

        def refresh_diff() -> bool:
            state["timer"] = 0
            if not state["streaming"]:
                show_diff(in_view, out_view)
            return False

        def on_edit(which: str) -> None:
            if state["quiet"] or state["streaming"]:
                return
            state[which] = True
            if state["timer"]:
                GLib.source_remove(state["timer"])
            state["timer"] = GLib.timeout_add(DIFF_DEBOUNCE_MS, refresh_diff)

        def on_chunk(text: str) -> None:
            buf = out_view.get_buffer()
            state["quiet"] = True
            buf.insert(buf.get_end_iter(), text)
            state["quiet"] = False

        def on_done(error: str | None) -> None:
            state["streaming"] = False
            spinner.set_visible(False)
            if error:
                status.set_label(t("Error: {err}", err=error))
                return
            result = buffer_text(out_view).strip()
            set_text(out_view, result)
            state["in_edited"] = state["out_edited"] = False
            show_diff(in_view, out_view)
            same = result == buffer_text(in_view).strip()
            status.set_label(t("No changes.") if same else "")
            out_view.grab_focus()

        def start(text: str) -> None:
            if state["run"]:
                state["run"].cancel()
            set_text(in_view, text)
            set_text(out_view, "")
            clear_diff(in_view, out_view)
            status.set_label("")
            spinner.set_visible(True)
            state["streaming"] = True
            state["run"] = providers.stream_in_thread(
                model, system, render(text), idle(on_chunk), idle(on_done))

        def retry() -> None:
            start(next_input(buffer_text(in_view), buffer_text(out_view),
                             state["in_edited"], state["out_edited"]))

        def finish(action: str | None) -> None:
            if state["run"]:
                state["run"].cancel()
            outcome.action = action
            outcome.text = buffer_text(out_view).strip()
            win.close()

        def on_close(*_) -> bool:
            if state["run"]:
                state["run"].cancel()
            return False

        in_view.get_buffer().connect("changed", lambda *_: on_edit("in_edited"))
        out_view.get_buffer().connect("changed", lambda *_: on_edit("out_edited"))
        shortcut(win, "<Control>Return", lambda: finish("replace"))
        shortcut(win, "<Control><Shift>c", lambda: finish("copy"))
        shortcut(win, "<Control>r", retry)
        shortcut(win, "Escape", lambda: finish(None))
        win.connect("close-request", on_close)

        start(original)
        return win

    run_window(build)
    return outcome
