"""Result window, Raycast style: original on top, result below, both editable.
What left the original is struck through in red, what is new in the result is
green. Ctrl+R runs again on the result (with your edits); Ctrl+T cycles its
tone, Alt+Down lists alternative versions; Ctrl+Enter sends the result back
over the selection."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .. import prompts, providers
from ..config import Model
from ..editing import next_input
from ..i18n import t
from .common import (Adw, GLib, Gtk, buffer_text, clear_diff, hint_bar, idle, pane, run_window,
                     shortcut, show_diff, stat_pill, text_view)
from .variants import Alternatives, Tone

DIFF_DEBOUNCE_MS = 250
KEYS = [("Ctrl+L", "ask"), ("Ctrl+R", "retry"), ("Ctrl+T", "tone"), ("Alt+↓", "alternatives"),
        ("Esc", "close")]


@dataclass
class Outcome:
    action: str | None = None  # "replace" | "copy" | None (closed)
    text: str = ""
    input: str | None = None  # what it was made from, for the history (None: the selection)


def open_window(app: Adw.Application, title: str, model: Model, system: str,
                render: Callable[[str], str], original: str, with_diff: bool,
                on_finish: Callable[[Outcome], None]) -> Adw.ApplicationWindow:
    """`render(text)` builds the user prompt for a given input text."""
    outcome = Outcome()

    def build(app: Adw.Application) -> Adw.ApplicationWindow:
        win = Adw.ApplicationWindow(application=app, title=f"AI Toolbox · {title}",
                                    default_width=820, default_height=600)
        replace_btn = Gtk.Button(label=t("Replace"), tooltip_text="Ctrl+Enter",
                                 css_classes=["suggested-action", "atb-action"])
        copy_btn = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text=f"{t('Copy')} (Ctrl+Shift+C)",
                              css_classes=["flat", "circular"])
        header = Adw.HeaderBar(title_widget=Adw.WindowTitle(
            title=title, subtitle=f"{model.provider} · {model.model}"))
        header.pack_end(replace_btn)
        header.pack_end(copy_btn)

        in_scroll, in_view = text_view(editable=True)
        out_scroll, out_view = text_view(editable=True)
        removed_pill, added_pill = stat_pill("del"), stat_pill("add")
        status = Gtk.Label(xalign=0, hexpand=True, ellipsize=3, css_classes=["atb-hint"])
        footer = Gtk.Box(spacing=12)
        footer.append(status)
        footer.append(hint_bar(KEYS))

        tone = Tone()
        alternatives = Alternatives(lambda option: pick(option))
        result_pane = pane(t("Result"), out_scroll, added_pill, tone.pill)
        result_pane.append(alternatives.listbox)

        panes = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL, wide_handle=True,
                          vexpand=True, shrink_start_child=False, shrink_end_child=False)
        panes.set_start_child(pane(t("Original"), in_scroll, removed_pill))
        panes.set_end_child(result_pane)
        panes.set_position(200)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                       margin_start=16, margin_end=16, margin_bottom=12, margin_top=4)
        ask = Gtk.Entry(placeholder_text=t("Ask for a change… e.g. more formal, as bullet points"),
                        primary_icon_name="mail-send-symbolic", hexpand=True)
        ask.add_css_class("atb-ask")
        body.append(panes)
        body.append(ask)
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

        def set_status(text: str, thinking: bool = False) -> None:
            status.set_label(text)
            (status.add_css_class if thinking else status.remove_css_class)("atb-thinking")

        def diff() -> None:
            if not with_diff:
                return
            removed, added = show_diff(in_view, out_view)
            removed_pill.set_label(f"−{removed}")
            added_pill.set_label(f"+{added}")
            removed_pill.set_visible(removed > 0)
            added_pill.set_visible(added > 0)

        def refresh_diff() -> bool:
            state["timer"] = 0
            if not state["streaming"]:
                diff()
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
            replace_btn.set_sensitive(True)
            if error:
                set_status(t("Error: {err}", err=error))
                return
            result = buffer_text(out_view).strip()
            set_text(out_view, result)
            state["in_edited"] = state["out_edited"] = False
            diff()
            same = result == buffer_text(in_view).strip()
            set_status(t("No changes.") if same else "")
            out_view.grab_focus()

        def start(text: str, user: str | None = None, tone_name: str = "neutral") -> None:
            if state["run"]:
                state["run"].cancel()
            alternatives.hide()
            tone.reset() if tone_name == "neutral" else tone.set(tone_name)
            set_text(in_view, text)
            set_text(out_view, "")
            clear_diff(in_view, out_view)
            removed_pill.set_visible(False)
            added_pill.set_visible(False)
            replace_btn.set_sensitive(False)
            set_status(t("Thinking…"), thinking=True)
            state["streaming"] = True
            state["run"] = providers.stream_in_thread(
                model, system, user or render(text), idle(on_chunk), idle(on_done))

        def current() -> str:
            return next_input(buffer_text(in_view), buffer_text(out_view),
                              state["in_edited"], state["out_edited"])

        def retry() -> None:
            start(current())

        def ask_change(*_) -> None:
            instruction = ask.get_text().strip()
            if not instruction:
                return
            text = current()
            ask.set_text("")
            start(text, prompts.refine(instruction, text))

        def cycle_tone() -> None:
            if state["streaming"]:
                return
            if tone.neutral is None or state["in_edited"] or state["out_edited"]:
                tone.neutral = (buffer_text(in_view), buffer_text(out_view), current())
            name = prompts.next_tone(tone.name)
            if name != "neutral":  # always from the neutral text, so tones never drift
                base = tone.neutral[2]
                start(base, prompts.tone(name, base), name)
                return
            alternatives.hide()
            original_text, result_text, _ = tone.neutral
            set_text(in_view, original_text)
            set_text(out_view, result_text)
            tone.set("neutral")
            diff()
            set_status("")

        def show_alternatives() -> None:
            text = current()
            if state["streaming"] or not text.strip():
                return
            set_status(t("Thinking…"), thinking=True)
            alternatives.fetch(model, system, prompts.alternatives(text),
                               lambda error: set_status(t("Error: {err}", err=error) if error else ""))

        def pick(option: str) -> None:
            out_view.get_buffer().set_text(option)  # counts as an edit: retry and tone use it
            tone.reset()  # the picked version is the new neutral
            out_view.grab_focus()

        def escape() -> None:
            if alternatives.visible:
                alternatives.hide()
                set_status("")
                out_view.grab_focus()
            else:
                finish(None)

        def finish(action: str | None) -> None:
            if state["run"]:
                state["run"].cancel()
            alternatives.cancel()
            outcome.action = action
            outcome.text = buffer_text(out_view).strip()
            win.close()

        def on_close(*_) -> bool:
            if state["run"]:
                state["run"].cancel()
            alternatives.cancel()
            return False

        in_view.get_buffer().connect("changed", lambda *_: on_edit("in_edited"))
        out_view.get_buffer().connect("changed", lambda *_: on_edit("out_edited"))
        replace_btn.connect("clicked", lambda *_: finish("replace"))
        copy_btn.connect("clicked", lambda *_: finish("copy"))
        shortcut(win, "<Control>Return", lambda: finish("replace"))
        shortcut(win, "<Control><Shift>c", lambda: finish("copy"))
        shortcut(win, "<Control>r", retry)
        shortcut(win, "<Control>l", ask.grab_focus)
        shortcut(win, "<Control>t", cycle_tone)
        shortcut(win, "<Alt>Down", show_alternatives)
        ask.connect("activate", ask_change)
        shortcut(win, "Escape", escape)
        win.connect("close-request", on_close)

        start(original)
        return win

    win = build(app)
    win.connect("destroy", lambda *_: on_finish(outcome))
    return win


def show(title: str, model: Model, system: str, render: Callable[[str], str],
         original: str, with_diff: bool = True) -> Outcome:
    box: dict = {}
    run_window(lambda app: open_window(app, title, model, system, render, original, with_diff,
                                       lambda value: box.setdefault("v", value)))
    return box.get("v")
