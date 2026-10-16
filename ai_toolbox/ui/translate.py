"""Translator window: source on top, translation below, updated as you type.
Literal by default; the "With context" toggle (Ctrl+I) adapts the
translation to the person described in context.md."""

from __future__ import annotations

from .. import providers, prompts
from ..config import Config
from ..i18n import t
from .common import Adw, GLib, Gtk, buffer_text, idle, run_window, shortcut, text_view
from .result import Outcome

DEBOUNCE_MS = 700
HINTS = ("Ctrl+Enter paste into app", "Ctrl+Shift+C copy", "Ctrl+S swap",
         "Ctrl+I with context", "Ctrl+P target", "Esc clear/close")


def _dropdown(items: list[str]) -> Gtk.DropDown:
    dd = Gtk.DropDown.new_from_strings(items)
    dd.set_enable_search(True)
    dd.set_search_match_mode(Gtk.StringFilterMatchMode.SUBSTRING)
    dd.set_expression(Gtk.PropertyExpression.new(Gtk.StringObject, None, "string"))
    return dd


def show(cfg: Config, text: str) -> Outcome:
    outcome = Outcome()
    tr = cfg.translate
    languages = list(tr.languages)
    sources = [t("Detect language"), *languages]
    targets = [f"Auto ({tr.pair[0]} ⇄ {tr.pair[1]})", *languages]

    def build(app: Adw.Application) -> Adw.ApplicationWindow:
        win = Adw.ApplicationWindow(application=app, title=f"AI Toolbox · {t('Translate')}",
                                    default_width=820, default_height=560)
        source_dd, target_dd = _dropdown(sources), _dropdown(targets)
        swap = Gtk.Button(icon_name="object-flip-horizontal-symbolic",
                          tooltip_text=t("Swap (Ctrl+S)"))
        langs = Gtk.Box(spacing=6)
        for widget in (source_dd, swap, target_dd):
            langs.append(widget)
        context_toggle = Gtk.Switch(valign=Gtk.Align.CENTER, tooltip_text="Ctrl+I")
        context_box = Gtk.Box(spacing=8)
        context_box.append(Gtk.Label(label=t("With context")))
        context_box.append(context_toggle)
        spinner = Adw.Spinner(visible=False)
        header = Adw.HeaderBar(title_widget=langs)
        header.pack_end(context_box)
        header.pack_end(spinner)

        src_scroll, src_view = text_view(editable=True)
        out_scroll, out_view = text_view(editable=True)
        info = Gtk.Label(xalign=0, css_classes=["atb-hint"])
        model_label = Gtk.Label(xalign=1, hexpand=True, css_classes=["atb-hint"])
        info_row = Gtk.Box()
        info_row.append(info)
        info_row.append(model_label)
        note = Gtk.Label(xalign=0, wrap=True, visible=False, css_classes=["atb-note"])
        hints = Gtk.Label(label="  ·  ".join(t(h) for h in HINTS), xalign=0, wrap=True, css_classes=["atb-hint"])

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8,
                       margin_start=14, margin_end=14, margin_bottom=12, margin_top=4)
        for widget in (src_scroll, info_row, out_scroll, note, hints):
            body.append(widget)
        toolbar = Adw.ToolbarView(content=body)
        toolbar.add_top_bar(header)
        win.set_content(toolbar)

        state = {"run": None, "timer": 0, "raw": "", "detected": None, "quiet": False}

        def selected(dd: Gtk.DropDown, offset_items: list[str]) -> str | None:
            index = dd.get_selected()
            return offset_items[index] if index > 0 else None

        def model():
            return tr.contextual if context_toggle.get_active() else tr.literal

        def refresh_info() -> None:
            words = len(buffer_text(src_view).split())
            detected = state["detected"]
            parts = [t("Detected: {lang}", lang=detected)] if detected and source_dd.get_selected() == 0 else []
            parts.append(t("{n} word" if words == 1 else "{n} words", n=words))
            info.set_label("  ·  ".join(parts))
            m = model()
            mode = t("with context") if context_toggle.get_active() else t("literal")
            model_label.set_label(f"{mode} · {m.provider} · {m.model}")

        def render_output() -> None:
            lang, body_text, note_text = prompts.split_translation(state["raw"])
            if lang:
                state["detected"] = lang
            # Hide the '@lang' header while it is still streaming in.
            if state["raw"].startswith("@") and "\n" not in state["raw"]:
                body_text = ""
            out_view.get_buffer().set_text(body_text)
            note.set_visible(bool(note_text))
            note.set_label(f"💡 {note_text}" if note_text else "")
            refresh_info()

        def on_chunk(chunk: str) -> None:
            state["raw"] += chunk
            render_output()

        def on_done(error: str | None) -> None:
            spinner.set_visible(False)
            if error:
                out_view.get_buffer().set_text(t("Error: {err}", err=error))

        def translate_now() -> bool:
            state["timer"] = 0
            if state["run"]:
                state["run"].cancel()
            source_text = buffer_text(src_view).strip()
            state["raw"] = ""
            if not source_text:
                out_view.get_buffer().set_text("")
                note.set_visible(False)
                spinner.set_visible(False)
                return False
            system = prompts.translate_system(
                selected(source_dd, sources), selected(target_dd, targets), tr.pair,
                cfg.context if context_toggle.get_active() else None)
            spinner.set_visible(True)
            try:
                state["run"] = providers.stream_in_thread(
                    model(), system, source_text, idle(on_chunk), idle(on_done))
            except providers.ProviderError as err:
                on_done(str(err))
            return False

        def schedule(*_) -> None:
            refresh_info()
            if state["quiet"]:
                return
            if state["timer"]:
                GLib.source_remove(state["timer"])
            state["timer"] = GLib.timeout_add(DEBOUNCE_MS, translate_now)

        def swap_languages() -> None:
            src, dst = selected(source_dd, sources), selected(target_dd, targets)
            detected = src or state["detected"]
            new_source = dst
            if new_source is None and detected:  # auto pair: the other side of the pair
                new_source = tr.pair[1] if detected == tr.pair[0] else tr.pair[0]
            state["quiet"] = True
            source_dd.set_selected(sources.index(new_source) if new_source in sources else 0)
            target_dd.set_selected(targets.index(detected) if detected in targets else 0)
            src_view.get_buffer().set_text(buffer_text(out_view))
            state["quiet"] = False
            translate_now()

        def finish(action: str | None) -> None:
            if state["run"]:
                state["run"].cancel()
            outcome.action = action
            outcome.text = buffer_text(out_view).strip()
            win.close()

        def escape() -> None:
            if buffer_text(src_view).strip():
                src_view.get_buffer().set_text("")
            else:
                finish(None)

        src_view.get_buffer().connect("changed", schedule)
        source_dd.connect("notify::selected", schedule)
        target_dd.connect("notify::selected", schedule)
        context_toggle.connect("notify::active", lambda *_: translate_now())
        swap.connect("clicked", lambda *_: swap_languages())

        shortcut(win, "<Control>Return", lambda: finish("replace"))
        shortcut(win, "<Control><Shift>c", lambda: finish("copy"))
        shortcut(win, "<Control>s", swap_languages)
        shortcut(win, "<Control>i", lambda: context_toggle.set_active(not context_toggle.get_active()))
        shortcut(win, "<Control>p", lambda: target_dd.activate())
        shortcut(win, "<Control><Shift>p", lambda: source_dd.activate())
        shortcut(win, "Escape", escape)
        win.connect("close-request", lambda *_: bool(state["run"] and state["run"].cancel()))

        src_view.grab_focus()
        if text:
            state["quiet"] = True
            src_view.get_buffer().set_text(text)
            state["quiet"] = False
            translate_now()
        refresh_info()
        return win

    run_window(build)
    return outcome
