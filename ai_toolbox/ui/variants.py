"""Tone (Ctrl+T) and alternative versions (Alt+Down) for an editable result,
shared by the result and reply windows."""

from __future__ import annotations

from collections.abc import Callable

from .. import prompts, providers
from ..config import Model
from ..i18n import t
from .common import Gtk, idle


class Tone:
    """Which tone the result is in, shown as a pill while it is not neutral.
    `neutral` keeps the panes as they were before the first rewrite, so
    cycling back restores them without asking the model again."""

    def __init__(self) -> None:
        self.name = "neutral"
        self.neutral = None
        self.pill = Gtk.Label(visible=False, tooltip_text="Ctrl+T",
                              css_classes=["atb-stat", "atb-tone"])

    def set(self, name: str) -> None:
        self.name = name
        self.pill.set_label(t(name))  # tone names are in the i18n table
        self.pill.set_visible(name != "neutral")

    def reset(self) -> None:
        """A new result (run, retry, ask): it becomes the neutral version."""
        self.neutral = None
        self.set("neutral")


class Alternatives:
    """Up to three versions listed under a result; Enter or a click hands the
    chosen one to `on_pick`."""

    def __init__(self, on_pick: Callable[[str], None]):
        self.run = None
        self.listbox = Gtk.ListBox(selection_mode=Gtk.SelectionMode.BROWSE, visible=False,
                                   css_classes=["boxed-list"])

        def picked(_lb, row: Gtk.ListBoxRow) -> None:
            self.hide()
            on_pick(row.option)

        self.listbox.connect("row-activated", picked)

    @property
    def visible(self) -> bool:
        return self.listbox.get_visible()

    def show(self, options: list[str]) -> None:
        self.listbox.remove_all()
        for option in options:
            label = Gtk.Label(label=option, xalign=0, wrap=True, wrap_mode=2, lines=3, ellipsize=3,
                              margin_top=8, margin_bottom=8, margin_start=12, margin_end=12)
            row = Gtk.ListBoxRow(child=label)
            row.option = option
            self.listbox.append(row)
        self.listbox.set_visible(bool(options))
        if options:
            first = self.listbox.get_row_at_index(0)
            self.listbox.select_row(first)
            first.grab_focus()

    def hide(self) -> None:
        self.cancel()
        self.listbox.set_visible(False)

    def cancel(self) -> None:
        if self.run:
            self.run.cancel()
            self.run = None

    def fetch(self, model: Model, system: str, user: str,
              on_status: Callable[[str | None], None]) -> None:
        """One request; `on_status` gets None when the list is shown, or an error."""
        self.hide()
        raw: list[str] = []

        def done(error: str | None) -> None:
            self.run = None
            options = [] if error else prompts.parse_suggestions("".join(raw))
            if not error and not options:
                error = t("No alternatives.")
            on_status(error)
            if options:
                self.show(options)

        self.run = providers.stream_in_thread(model, system, user, raw.append, idle(done))
