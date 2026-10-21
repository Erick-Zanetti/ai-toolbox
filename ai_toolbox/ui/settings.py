"""Settings window: General, Commands, Translate, Context. Changes save on
their own (debounced) and are validated by loading the config back."""

from __future__ import annotations

from collections.abc import Callable

from .. import config
from ..i18n import t
from ..store import Store
from .common import Adw, GLib, Gtk, buffer_text, run_window

SAVE_DEBOUNCE_MS = 600
NOTIFICATION_LEVELS = ("all", "errors", "off")
OUTPUT_MODES = ("window", "replace")
PROVIDER_KINDS = {
    "claude": "Claude Code CLI · Claude subscription",
    "codex": "Codex CLI · ChatGPT subscription",
    "openai": "OpenAI-compatible server",
}
DEFAULT_PROMPT = "Rewrite the text ...\n\n<text>\n{selection}\n</text>\n"


def _combo(title: str, labels: list[str], selected: int, on_change: Callable[[int], None],
           subtitle: str = "") -> Adw.ComboRow:
    row = Adw.ComboRow(title=title, subtitle=subtitle, model=Gtk.StringList.new(labels))
    row.set_selected(max(0, selected))
    row.connect("notify::selected", lambda r, _p: on_change(r.get_selected()))
    return row


def _entry(title: str, text: str, on_change: Callable[[str], None]) -> Adw.EntryRow:
    row = Adw.EntryRow(title=title, text=text)
    row.connect("changed", lambda r: on_change(r.get_text()))
    return row


def _text_area(text: str, on_change: Callable[[str], None], height: int = 160) -> Gtk.Widget:
    view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, top_margin=10, bottom_margin=10,
                        left_margin=12, right_margin=12, monospace=True)
    view.get_buffer().set_text(text)
    view.get_buffer().connect("changed", lambda *_: on_change(buffer_text(view)))
    scroller = Gtk.ScrolledWindow(child=view, min_content_height=height,
                                  hscrollbar_policy=Gtk.PolicyType.NEVER)
    frame = Gtk.Frame(child=scroller)
    frame.add_css_class("view")
    return frame


class Settings:
    def __init__(self, app: Adw.Application):
        self.store = Store()
        self.data = self.store.config()
        self.commands = self.store.commands()
        self.pending: set[str] = set()  # "config", "context", "cmd:<id>"
        self.timer = 0
        self.context_text = self.store.context()

        self.win = Adw.ApplicationWindow(application=app, title=f"AI Toolbox · {t('Settings')}",
                                         default_width=760, default_height=720)
        self.toasts = Adw.ToastOverlay()
        self.stack = stack = Adw.ViewStack()
        stack.add_titled_with_icon(self._general_page(), "general", t("General"),
                                   "preferences-system-symbolic")
        stack.add_titled_with_icon(self._commands_page(), "commands", t("Commands"),
                                   "view-list-bullet-symbolic")
        stack.add_titled_with_icon(self._translate_page(), "translate", t("Translate"),
                                   "preferences-desktop-locale-symbolic")
        stack.add_titled_with_icon(self._context_page(), "context", t("Context"),
                                   "user-info-symbolic")
        header = Adw.HeaderBar(title_widget=Adw.ViewSwitcher(
            stack=stack, policy=Adw.ViewSwitcherPolicy.WIDE))
        toolbar = Adw.ToolbarView(content=stack)
        toolbar.add_top_bar(header)
        self.toasts.set_child(toolbar)
        self.win.set_content(self.toasts)
        self.win.connect("close-request", lambda *_: (self._flush(), False)[1])

    # ── Saving ────────────────────────────────────────────────────────────

    def _changed(self, what: str) -> None:
        self.pending.add(what)
        if self.timer:
            GLib.source_remove(self.timer)
        self.timer = GLib.timeout_add(SAVE_DEBOUNCE_MS, self._flush)

    def _flush(self) -> bool:
        self.timer = 0
        pending, self.pending = self.pending, set()
        for what in pending:
            if what == "config":
                self.store.save_config(self.data)
            elif what == "context":
                self.store.save_context(self.context_text)
            elif what.startswith("cmd:"):
                command_id = what[4:]
                if command_id in self.commands:
                    self.store.save_command(command_id, self.commands[command_id])
        if pending:
            try:
                config.load(self.store.dir)
            except config.ConfigError as err:
                self.toasts.add_toast(Adw.Toast(title=t("Config error: {err}", err=err), timeout=6))
        return False

    def _set(self, table: dict, key: str, value, what: str = "config") -> None:
        if value in ("", None):
            table.pop(key, None)
        else:
            table[key] = value
        self._changed(what)

    # ── Pages ─────────────────────────────────────────────────────────────

    def _providers(self) -> list[str]:
        return list(self.data.get("providers", {}))

    def _general_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage()

        behavior = Adw.PreferencesGroup(title=t("Behavior"))
        level = self.data.get("notifications", "all")
        behavior.add(_combo(
            t("Notifications"),
            [t("All"), t("Errors only"), t("Off")],
            NOTIFICATION_LEVELS.index(level) if level in NOTIFICATION_LEVELS else 0,
            lambda i: self._set(self.data, "notifications", NOTIFICATION_LEVELS[i]),
            t("Progress and results of commands that replace text directly"),
        ))
        fallback = Adw.SwitchRow(title=t("Copy when nothing is highlighted"),
                                 subtitle=t("Sends Ctrl+C to the app (never to terminals)"),
                                 active=bool(self.data.get("copy_fallback", False)))
        fallback.connect("notify::active",
                         lambda r, _p: self._set(self.data, "copy_fallback", r.get_active()))
        behavior.add(fallback)
        kept = self.data.setdefault("history", {})
        keep = Adw.SwitchRow(title=t("Keep a history"),
                             subtitle=t("Recent results, under History in the palette. "
                                        "Stays on this computer."),
                             active=bool(kept.get("enabled", True)))
        keep.connect("notify::active", lambda r, _p: self._set(kept, "enabled", r.get_active()))
        behavior.add(keep)
        page.add(behavior)

        words = Adw.PreferencesGroup(
            title=t("Personal dictionary"),
            description=t("Product names, acronyms and jargon that commands and "
                          "translations must never change."))
        words.add(_entry(t("Terms (comma separated)"), ", ".join(self.data.get("glossary", [])),
                         lambda v: self._set(self.data, "glossary",
                                             [x.strip() for x in v.split(",") if x.strip()] or None)))
        page.add(words)
        page.add(self._dictation_group())

        accounts = Adw.PreferencesGroup(
            title=t("AI accounts"),
            description=t("claude and codex use your logged-in CLIs; openai is any "
                          "OpenAI-compatible server such as Ollama."))
        names = self._providers()
        default = self.data.get("default_provider", names[0] if names else "")
        accounts.add(_combo(t("Default provider"), names,
                            names.index(default) if default in names else 0,
                            lambda i: self._set(self.data, "default_provider", names[i])))
        for name, provider in self.data.get("providers", {}).items():
            kind = provider.get("type", name)
            row = Adw.ExpanderRow(title=name, subtitle=f"{t(PROVIDER_KINDS.get(kind, kind))}"
                                  f"  ·  {provider.get('model', '')}")
            row.add_row(_entry(t("Default model"), provider.get("model", ""),
                               lambda v, p=provider: self._set(p, "model", v)))
            if kind == "codex":
                row.add_row(_entry(t("Reasoning effort"), provider.get("reasoning", ""),
                                   lambda v, p=provider: self._set(p, "reasoning", v)))
            if kind == "openai":
                row.add_row(_entry(t("Server URL"), provider.get("base_url", ""),
                                   lambda v, p=provider: self._set(p, "base_url", v)))
                row.add_row(_entry(t("API key variable (optional)"), provider.get("api_key_env", ""),
                                   lambda v, p=provider: self._set(p, "api_key_env", v)))
            accounts.add(row)
        if not any(p.get("type") == "openai" for p in self.data.get("providers", {}).values()):
            add = Adw.ButtonRow(title=t("Add local models (Ollama)"),
                                start_icon_name="list-add-symbolic")
            add.connect("activated", lambda *_: self._add_ollama())
            accounts.add(add)
        page.add(accounts)
        return page

    def _dictation_group(self) -> Adw.PreferencesGroup:
        spec = self.data.setdefault("dictation", {})
        group = Adw.PreferencesGroup(
            title=t("Dictation"),
            description=t("Local Whisper speech-to-text. The first use downloads the model."))
        devices = ("auto", "cuda", "cpu")
        device = spec.get("device", "auto")
        group.add(_combo(t("Device"), [t("Automatic (GPU when available)"), "NVIDIA GPU", "CPU"],
                         devices.index(device) if device in devices else 0,
                         lambda i: self._set(spec, "device", devices[i])))
        group.add(_entry(t("GPU model"), spec.get("model", "large-v3-turbo"),
                         lambda v: self._set(spec, "model", v)))
        group.add(_entry(t("CPU model"), spec.get("cpu_model", "small"),
                         lambda v: self._set(spec, "cpu_model", v)))
        group.add(_entry(t("Language (empty = detect)"), spec.get("language", ""),
                         lambda v: self._set(spec, "language", v)))
        names = [t("Paste as spoken"), *self.commands]
        then = spec.get("then", "")
        group.add(_combo(t("After transcribing"), names,
                         names.index(then) if then in names else 0,
                         lambda i: self._set(spec, "then", "" if i == 0 else names[i])))
        return group

    def _add_ollama(self) -> None:
        self.data.setdefault("providers", {})["ollama"] = {
            "type": "openai", "base_url": "http://localhost:11434/v1", "model": "llama3.2"}
        self._changed("config")
        self._flush()
        self.toasts.add_toast(Adw.Toast(title=t("Added. Reopen settings to edit it."), timeout=4))

    def _command_row(self, command_id: str, group: Adw.PreferencesGroup) -> Adw.ExpanderRow:
        cmd = self.commands[command_id]
        what = f"cmd:{command_id}"
        row = Adw.ExpanderRow(title=cmd.get("name", command_id))

        def subtitle() -> str:
            mode = t("Replaces directly") if cmd.get("output") == "replace" else t("Shows a window")
            provider = cmd.get("provider", self.data.get("default_provider", ""))
            model = cmd.get("model", "")
            return f"{mode}  ·  {provider}{' · ' + model if model else ''}"

        def update(key: str, value) -> None:
            self._set(cmd, key, value, what)
            row.set_subtitle(subtitle())
            if key == "name":
                row.set_title(value or command_id)

        row.set_subtitle(subtitle())
        row.add_row(_entry(t("Name"), cmd.get("name", ""), lambda v: update("name", v)))
        output = cmd.get("output", "window")
        row.add_row(_combo(
            t("Result"), [t("Show a window"), t("Replace directly")],
            OUTPUT_MODES.index(output) if output in OUTPUT_MODES else 0,
            lambda i: update("output", OUTPUT_MODES[i])))
        names = [t("Default"), *self._providers()]
        provider = cmd.get("provider")
        row.add_row(_combo(t("Provider"), names,
                           names.index(provider) if provider in names else 0,
                           lambda i: update("provider", None if i == 0 else names[i])))
        row.add_row(_entry(t("Model (empty = provider default)"), cmd.get("model", ""),
                           lambda v: update("model", v)))
        row.add_row(_entry(t("Icon name"), cmd.get("icon", ""), lambda v: update("icon", v)))

        prompt = Adw.PreferencesRow(activatable=False)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, margin_top=10,
                      margin_bottom=10, margin_start=12, margin_end=12)
        box.append(Gtk.Label(label=t("Prompt  ·  {selection} {clipboard} {context}"),
                             xalign=0, css_classes=["dim-label", "caption"]))
        box.append(_text_area(cmd.get("prompt", ""), lambda v: update("prompt", v)))
        prompt.set_child(box)
        row.add_row(prompt)

        delete = Adw.ButtonRow(title=t("Delete command"), start_icon_name="user-trash-symbolic")
        delete.add_css_class("destructive-action")

        def remove(*_) -> None:
            self.commands.pop(command_id, None)
            self.pending.discard(what)
            self.store.delete_command(command_id)
            group.remove(row)

        delete.connect("activated", remove)
        row.add_row(delete)
        return row

    def _commands_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(
            title=t("Commands"),
            description=t("Each command runs a prompt on the selected text."))
        add = Gtk.Button(icon_name="list-add-symbolic", tooltip_text=t("New command"),
                         css_classes=["flat"])
        group.set_header_suffix(add)
        for command_id in self.commands:
            group.add(self._command_row(command_id, group))

        def new(*_) -> None:
            name = t("New command")
            command_id = self.store.new_command_id(name)
            self.commands[command_id] = {"name": name, "output": "window", "prompt": DEFAULT_PROMPT}
            self._changed(f"cmd:{command_id}")
            row = self._command_row(command_id, group)
            group.add(row)
            row.set_expanded(True)

        add.connect("clicked", new)
        page.add(group)
        return page

    def _translate_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage()
        tr = self.data.setdefault("translate", {})
        pair = list(tr.get("pair", ["English", "Portuguese (Brazil)"]))

        def set_pair(index: int, value: str) -> None:
            pair[index] = value
            self._set(tr, "pair", list(pair))

        langs = Adw.PreferencesGroup(
            title=t("Languages"),
            description=t("Auto target: text in one language of the pair goes to the other."))
        langs.add(_entry(t("Language A"), pair[0], lambda v: set_pair(0, v)))
        langs.add(_entry(t("Language B"), pair[1], lambda v: set_pair(1, v)))
        langs.add(_entry(t("More languages (comma separated)"), ", ".join(tr.get("languages", [])),
                         lambda v: self._set(tr, "languages",
                                             [x.strip() for x in v.split(",") if x.strip()])))
        page.add(langs)

        names = [t("Default"), *self._providers()]
        for key, title in (("literal", t("Literal translation")),
                           ("contextual", t("Translation with context"))):
            spec = tr.setdefault(key, {})
            group = Adw.PreferencesGroup(title=title)
            provider = spec.get("provider")
            group.add(_combo(t("Provider"), names,
                             names.index(provider) if provider in names else 0,
                             lambda i, s=spec: self._set(s, "provider", None if i == 0 else names[i])))
            group.add(_entry(t("Model (empty = provider default)"), spec.get("model", ""),
                             lambda v, s=spec: self._set(s, "model", v)))
            page.add(group)
        return page

    def _context_page(self) -> Adw.PreferencesPage:
        page = Adw.PreferencesPage()
        group = Adw.PreferencesGroup(
            title=t("About you"),
            description=t("Used by translation with context and by commands with {context}: "
                          "who you are, who you write to, the tone you want."))

        def update(text: str) -> None:
            self.context_text = text
            self._changed("context")

        group.add(_text_area(self.context_text, update, height=360))
        page.add(group)
        return page


def open_window(app: Adw.Application) -> Adw.ApplicationWindow:
    return Settings(app).win


def show() -> int:
    return run_window(open_window)
