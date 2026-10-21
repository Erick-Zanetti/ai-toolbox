"""Command palette: type to filter, Enter to run on the selected text."""

from __future__ import annotations

from collections.abc import Callable

from ..cli import HISTORY, REPLY, SETTINGS, TRANSLATE
from ..config import Config
from ..i18n import t
from .common import Adw, Gtk, hint_bar, icon_tile, on_closed, run_window, shortcut

PREVIEW_CHARS = 180
KEYS = [("↑↓", "navigate"), ("Enter", "run"), ("Esc", "close")]


def _row(item_id: str, title: str, subtitle: str, icon: str) -> Gtk.ListBoxRow:
    row = Adw.ActionRow(title=title, subtitle=subtitle, activatable=True)
    row.add_prefix(icon_tile(icon))
    row.item_id = item_id
    row.search_text = f"{title} {item_id}".lower()
    return row


def _selection_chip(selection: str) -> Gtk.Widget:
    text = " ".join(selection.split())
    preview = (text[:PREVIEW_CHARS] + "…") if len(text) > PREVIEW_CHARS else text
    chip = Gtk.Box(spacing=10, css_classes=["atb-chip"])
    chip.append(Gtk.Image(icon_name="insert-text-symbolic" if preview else "dialog-information-symbolic",
                          valign=Gtk.Align.START, opacity=0.6))
    chip.append(Gtk.Label(label=preview or t("No text selected"), xalign=0, hexpand=True,
                          wrap=True, lines=2, ellipsize=3,
                          css_classes=[] if preview else ["dim-label"]))
    return chip


def open_window(app: Adw.Application, cfg: Config, selection: str,
                on_finish: Callable[[str | None], None]) -> Adw.ApplicationWindow:
    chosen: dict[str, str | None] = {"id": None}

    def build(app: Adw.Application) -> Adw.ApplicationWindow:
        win = Adw.ApplicationWindow(application=app, title="AI Toolbox",
                                    default_width=620, default_height=460)
        search = Gtk.SearchEntry(placeholder_text=t("Search commands"), hexpand=True)
        search.add_css_class("atb-search")

        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.BROWSE)
        listbox.add_css_class("navigation-sidebar")
        for cmd in cfg.commands.values():
            kind = t("Replaces the selection") if cmd.output == "replace" else t("Shows the result")
            listbox.append(_row(cmd.id, cmd.name,
                                f"{kind}  ·  {cmd.model.provider} · {cmd.model.model}", cmd.icon))
        listbox.append(_row(TRANSLATE, t("Translate"), t("Translate text"),
                            "preferences-desktop-locale-symbolic"))
        listbox.append(_row(REPLY, t("Reply"), t("Write a reply to the selected message"),
                            "mail-reply-sender-symbolic"))
        listbox.append(_row(HISTORY, t("History"), t("Recent results, copy one again"),
                            "document-open-recent-symbolic"))
        listbox.append(_row(SETTINGS, t("Settings"), t("Commands, notifications, models"),
                            "preferences-system-symbolic"))
        scroller = Gtk.ScrolledWindow(child=listbox, vexpand=True,
                                      hscrollbar_policy=Gtk.PolicyType.NEVER)

        footer = Gtk.Box(spacing=12)
        footer.append(Gtk.Label(label="AI Toolbox", xalign=0, hexpand=True,
                                css_classes=["atb-pane-title"]))
        footer.append(hint_bar(KEYS))

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                       margin_start=14, margin_end=14, margin_top=14, margin_bottom=12)
        for widget in (search, _selection_chip(selection), scroller, footer):
            body.append(widget)
        win.set_content(body)

        def matches(row) -> bool:
            words = search.get_text().lower().split()
            return all(w in row.search_text for w in words)

        def visible_rows() -> list[Gtk.ListBoxRow]:
            rows, row = [], listbox.get_first_child()
            while row:
                if matches(row):
                    rows.append(row)
                row = row.get_next_sibling()
            return rows

        def refilter(*_) -> None:
            listbox.invalidate_filter()
            rows = visible_rows()
            if rows:
                listbox.select_row(rows[0])

        def move(step: int) -> None:
            rows = visible_rows()
            if not rows:
                return
            current = listbox.get_selected_row()
            index = rows.index(current) if current in rows else -1
            listbox.select_row(rows[max(0, min(len(rows) - 1, index + step))])

        def activate(row=None) -> None:
            row = row or listbox.get_selected_row()
            if row is None:
                return
            chosen["id"] = row.item_id
            win.close()

        listbox.set_filter_func(matches)
        search.connect("search-changed", refilter)
        search.connect("activate", lambda *_: activate())
        search.connect("stop-search", lambda *_: win.close())
        listbox.connect("row-activated", lambda _lb, row: activate(row))
        shortcut(win, "Down", lambda: move(1))
        shortcut(win, "Up", lambda: move(-1))
        shortcut(win, "Escape", win.close)

        listbox.select_row(listbox.get_row_at_index(0))
        search.grab_focus()
        return win

    win = build(app)
    on_closed(win, lambda: on_finish(chosen["id"]))
    return win


def show(cfg: Config, selection: str) -> str | None:
    box: dict = {}
    run_window(lambda app: open_window(app, cfg, selection, lambda value: box.setdefault("v", value)))
    return box.get("v")
