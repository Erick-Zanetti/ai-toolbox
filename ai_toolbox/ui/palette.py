"""Command palette: type to filter, Enter to run on the selected text."""

from __future__ import annotations

from ..config import Config
from ..i18n import t
from .common import Adw, Gtk, run_window, shortcut

TRANSLATE = "translate"
PREVIEW_CHARS = 140


def _row(item_id: str, title: str, subtitle: str, icon: str) -> Gtk.ListBoxRow:
    row = Adw.ActionRow(title=title, subtitle=subtitle, activatable=True)
    row.add_prefix(Gtk.Image(icon_name=icon, pixel_size=20))
    row.item_id = item_id
    row.search_text = f"{title} {item_id}".lower()
    return row


def show(cfg: Config, selection: str) -> str | None:
    chosen: dict[str, str | None] = {"id": None}

    def build(app: Adw.Application) -> Adw.ApplicationWindow:
        win = Adw.ApplicationWindow(application=app, title="AI Toolbox",
                                    default_width=640, default_height=440)
        search = Gtk.SearchEntry(placeholder_text=t("Search commands"), hexpand=True)
        search.add_css_class("atb-search")

        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.BROWSE)
        listbox.add_css_class("navigation-sidebar")
        listbox.append(_row(TRANSLATE, t("Translate"), t("Translate text"),
                            "preferences-desktop-locale-symbolic"))
        for cmd in cfg.commands.values():
            kind = t("Replaces the selection") if cmd.output == "replace" else t("Shows the result")
            listbox.append(_row(cmd.id, cmd.name, f"{kind}  ·  {cmd.model.provider} · {cmd.model.model}",
                                cmd.icon))
        listbox.append(_row("settings", t("Settings"), t("Commands, notifications, models"),
                            "preferences-system-symbolic"))
        scroller = Gtk.ScrolledWindow(child=listbox, vexpand=True,
                                      hscrollbar_policy=Gtk.PolicyType.NEVER)

        text = " ".join(selection.split())
        preview = (text[:PREVIEW_CHARS] + "…") if len(text) > PREVIEW_CHARS else text
        selected_label = Gtk.Label(
            label=f"{t('Selected text')}: {preview}" if preview else t("No text selected"),
            xalign=0, ellipsize=3, css_classes=["atb-hint"])
        hints = Gtk.Label(label=t("Enter run  ·  Esc close"), xalign=1, css_classes=["atb-hint"])
        footer = Gtk.Box(spacing=12)
        selected_label.set_hexpand(True)
        footer.append(selected_label)
        footer.append(hints)

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                       margin_start=14, margin_end=14, margin_top=14, margin_bottom=12)
        body.append(search)
        body.append(scroller)
        body.append(footer)
        win.set_content(body)

        def visible_rows() -> list[Gtk.ListBoxRow]:
            rows, row = [], listbox.get_first_child()
            while row:
                if _matches(row):
                    rows.append(row)
                row = row.get_next_sibling()
            return rows

        def _matches(row) -> bool:
            words = search.get_text().lower().split()
            return all(w in row.search_text for w in words)

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

        listbox.set_filter_func(_matches)
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

    run_window(build)
    return chosen["id"]
