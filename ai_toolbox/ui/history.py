"""History window: your recent results, newest first. Type to filter, Enter
or a double click copies the result."""

from __future__ import annotations

from collections.abc import Callable

from .. import history
from ..i18n import t
from .common import Adw, Gtk, hint_bar, on_closed, run_window, shortcut

KEYS = [("↑↓", "navigate"), ("Enter", "copy"), ("Esc", "close")]


def _row(item: history.Entry) -> Gtk.ListBoxRow:
    row = Adw.ActionRow(title=history.preview(item.output), use_markup=False,
                        subtitle=f"{history.short_time(item)}  ·  {item.name}",
                        activatable=True, title_lines=1, subtitle_lines=1)
    row.entry = item
    return row


def open_window(app: Adw.Application, on_finish: Callable[[history.Entry | None], None]
                ) -> Adw.ApplicationWindow:
    chosen: dict[str, history.Entry | None] = {"entry": None}

    def build(app: Adw.Application) -> Adw.ApplicationWindow:
        win = Adw.ApplicationWindow(application=app, title=f"AI Toolbox · {t('History')}",
                                    default_width=680, default_height=520)
        search = Gtk.SearchEntry(placeholder_text=t("Search history"), hexpand=True)
        search.add_css_class("atb-search")
        clear_btn = Gtk.Button(icon_name="user-trash-symbolic", tooltip_text=t("Clear history"),
                               valign=Gtk.Align.CENTER, css_classes=["flat", "circular"])
        top = Gtk.Box(spacing=8)
        top.append(search)
        top.append(clear_btn)

        listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.BROWSE,
                              activate_on_single_click=False)
        listbox.add_css_class("navigation-sidebar")
        listbox.set_placeholder(Gtk.Label(label=t("Nothing here yet: results you replace, paste "
                                                  "or copy show up here."),
                                          wrap=True, margin_top=24, css_classes=["dim-label"]))
        for item in history.load():
            listbox.append(_row(item))
        scroller = Gtk.ScrolledWindow(child=listbox, vexpand=True,
                                      hscrollbar_policy=Gtk.PolicyType.NEVER)

        footer = Gtk.Box(spacing=12)
        footer.append(Gtk.Label(label=t("History"), xalign=0, hexpand=True,
                                css_classes=["atb-pane-title"]))
        footer.append(hint_bar(KEYS))

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                       margin_start=14, margin_end=14, margin_top=14, margin_bottom=12)
        for widget in (top, scroller, footer):
            body.append(widget)
        win.set_content(body)

        def matches(row) -> bool:
            return history.matches(row.entry, search.get_text())

        def visible_rows() -> list[Gtk.ListBoxRow]:
            rows, row = [], listbox.get_first_child()
            while row:
                if isinstance(row, Adw.ActionRow) and matches(row):
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
            if row is None or not matches(row):
                return
            chosen["entry"] = row.entry
            win.close()

        def clear_all() -> None:
            history.clear()
            listbox.remove_all()

        def confirm_clear(*_) -> None:
            dialog = Adw.AlertDialog(heading=t("Clear history?"),
                                     body=t("Every saved result is deleted. This cannot be undone."))
            dialog.add_response("cancel", t("Cancel"))
            dialog.add_response("clear", t("Clear"))
            dialog.set_response_appearance("clear", Adw.ResponseAppearance.DESTRUCTIVE)
            dialog.set_default_response("cancel")
            dialog.set_close_response("cancel")
            dialog.connect("response", lambda _d, response: response == "clear" and clear_all())
            dialog.present(win)

        listbox.set_filter_func(matches)
        search.connect("search-changed", refilter)
        search.connect("activate", lambda *_: activate())
        search.connect("stop-search", lambda *_: win.close())
        listbox.connect("row-activated", lambda _lb, row: activate(row))
        clear_btn.connect("clicked", confirm_clear)
        shortcut(win, "Down", lambda: move(1))
        shortcut(win, "Up", lambda: move(-1))
        shortcut(win, "Escape", win.close)

        refilter()
        search.grab_focus()
        return win

    win = build(app)
    on_closed(win, lambda: on_finish(chosen["entry"]))
    return win


def show() -> history.Entry | None:
    box: dict = {}
    run_window(lambda app: open_window(app, lambda value: box.setdefault("v", value)))
    return box.get("v")
