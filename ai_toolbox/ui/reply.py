"""Reply window: the message you received on top, your notes (any language)
in the middle, the reply below, written as you and in the language of the
message. Enter with empty notes suggests three replies to pick from. Ctrl+T
and Alt+Down work on the reply as in the result window. Ctrl+Enter copies:
the selection is the other person's message, so nothing is replaced."""

from __future__ import annotations

from collections.abc import Callable

from .. import prompts, providers
from ..config import Config
from ..i18n import t
from .common import Adw, Gtk, buffer_text, hint_bar, idle, pane, run_window, shortcut, text_view
from .result import Outcome
from .variants import Alternatives, Tone

KEYS = [("Enter", "write"), ("Ctrl+T", "tone"), ("Alt+↓", "alternatives"),
        ("Ctrl+Enter", "copy"), ("Esc", "close")]


def open_window(app: Adw.Application, cfg: Config, received: str,
                on_finish: Callable[[Outcome], None]) -> Adw.ApplicationWindow:
    outcome = Outcome()
    model = cfg.default
    reply_system = prompts.reply_system(cfg.context, cfg.glossary)
    rework_system = prompts.command_system(cfg.glossary)  # tone and alternatives

    def build(app: Adw.Application) -> Adw.ApplicationWindow:
        win = Adw.ApplicationWindow(application=app, title=f"AI Toolbox · {t('Reply')}",
                                    default_width=760, default_height=640)
        copy_btn = Gtk.Button(label=t("Copy"), tooltip_text="Ctrl+Enter",
                              css_classes=["suggested-action", "atb-action"])
        header = Adw.HeaderBar(title_widget=Adw.WindowTitle(
            title=t("Reply"), subtitle=f"{model.provider} · {model.model}"))
        header.pack_end(copy_btn)

        msg_scroll, msg_view = text_view(editable=True)
        reply_scroll, reply_view = text_view(editable=True)
        notes = Gtk.Entry(placeholder_text=t("Your notes, in any language… empty: three suggestions"),
                          primary_icon_name="document-edit-symbolic", hexpand=True)
        notes.add_css_class("atb-ask")
        tone = Tone()
        options = Alternatives(lambda option: pick(option))
        status = Gtk.Label(xalign=0, hexpand=True, ellipsize=3, css_classes=["atb-hint"])
        footer = Gtk.Box(spacing=12)
        footer.append(status)
        footer.append(hint_bar(KEYS))

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                       margin_start=16, margin_end=16, margin_bottom=12, margin_top=4)
        for widget in (pane(t("Received message"), msg_scroll), notes,
                       pane(t("Reply"), reply_scroll, tone.pill), options.listbox, footer):
            body.append(widget)
        toolbar = Adw.ToolbarView(content=body)
        toolbar.add_top_bar(header)
        win.set_content(toolbar)

        state = {"run": None, "streaming": False, "quiet": False, "edited": False}

        def set_reply(text: str) -> None:
            state["quiet"] = True
            reply_view.get_buffer().set_text(text)
            state["quiet"] = False

        def set_status(text: str, thinking: bool = False) -> None:
            status.set_label(text)
            (status.add_css_class if thinking else status.remove_css_class)("atb-thinking")

        def on_edit(*_) -> None:
            if not state["quiet"] and not state["streaming"]:
                state["edited"] = True

        def on_chunk(text: str) -> None:
            buf = reply_view.get_buffer()
            state["quiet"] = True
            buf.insert(buf.get_end_iter(), text)
            state["quiet"] = False

        def on_done(error: str | None) -> None:
            state["streaming"] = False
            copy_btn.set_sensitive(True)
            if error:
                set_status(t("Error: {err}", err=error))
                return
            set_reply(buffer_text(reply_view).strip())
            state["edited"] = False
            set_status("")

        def stream(system: str, user: str, tone_name: str = "neutral") -> None:
            if state["run"]:
                state["run"].cancel()
            options.hide()
            tone.reset() if tone_name == "neutral" else tone.set(tone_name)
            set_reply("")
            copy_btn.set_sensitive(False)
            set_status(t("Thinking…"), thinking=True)
            state["streaming"] = True
            state["run"] = providers.stream_in_thread(model, system, user, idle(on_chunk), idle(on_done))

        def message() -> str | None:
            text = buffer_text(msg_view).strip()
            if not text:
                set_status(t("Paste the message you received first."))
                msg_view.grab_focus()
            return text or None

        def show_options(system: str, user: str) -> None:
            set_status(t("Thinking…"), thinking=True)
            options.fetch(model, system, user,
                          lambda error: set_status(t("Error: {err}", err=error) if error else ""))

        def write(*_) -> None:
            received_text = message()
            if received_text is None or state["streaming"]:
                return
            note = notes.get_text().strip()
            if note:
                stream(reply_system, prompts.reply_prompt(received_text, note))
            else:
                show_options(reply_system, prompts.reply_suggestions_prompt(received_text))

        def alternatives() -> None:
            text = buffer_text(reply_view).strip()
            if state["streaming"]:
                return
            if not text:  # nothing written yet: suggest replies instead
                write()
                return
            show_options(rework_system, prompts.alternatives(text))

        def pick(option: str) -> None:
            set_reply(option)
            tone.reset()  # the picked version is the new neutral
            reply_view.grab_focus()

        def cycle_tone() -> None:
            text = buffer_text(reply_view).strip()
            if state["streaming"] or not text:
                return
            if tone.neutral is None or state["edited"]:
                tone.neutral = text
            name = prompts.next_tone(tone.name)
            if name == "neutral":
                options.hide()
                set_reply(tone.neutral)
                tone.set("neutral")
                return
            stream(rework_system, prompts.tone(name, tone.neutral), name)

        def finish(action: str | None) -> None:
            text = buffer_text(reply_view).strip()
            if action and not text:
                return
            if state["run"]:
                state["run"].cancel()
            options.cancel()
            outcome.action = action
            outcome.text = text
            outcome.input = buffer_text(msg_view).strip()
            win.close()

        def escape() -> None:
            if options.visible:
                options.hide()
                set_status("")
            else:
                finish(None)

        def on_close(*_) -> bool:
            if state["run"]:
                state["run"].cancel()
            options.cancel()
            return False

        reply_view.get_buffer().connect("changed", on_edit)
        notes.connect("activate", write)
        copy_btn.connect("clicked", lambda *_: finish("copy"))
        shortcut(win, "<Control>Return", lambda: finish("copy"))
        shortcut(win, "<Control>t", cycle_tone)
        shortcut(win, "<Alt>Down", alternatives)
        shortcut(win, "Escape", escape)
        win.connect("close-request", on_close)

        msg_view.get_buffer().set_text(received.strip())
        (notes if received.strip() else msg_view).grab_focus()
        return win

    win = build(app)
    win.connect("destroy", lambda *_: on_finish(outcome))
    return win


def show(cfg: Config, received: str) -> Outcome:
    box: dict = {}
    run_window(lambda app: open_window(app, cfg, received, lambda value: box.setdefault("v", value)))
    return box.get("v")
