"""A dropdown row over plain string values (models, reasoning effort) whose list
can be refilled later, e.g. when a server answers or the provider changes."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from ..models import options
from .common import Adw, Gtk


class ChoiceRow:
    """`empty_label`, when given, is a first item that stands for "not set" (value
    ""). Only the person picking an item calls `on_change`; refilling does not,
    except when it drops a choice that is no longer offered."""

    def __init__(self, title: str, current: str | None, on_change: Callable[[str], None],
                 empty_label: str | None = None, subtitle: str = ""):
        self.value = current or ""
        self.values: list[str] = []
        self._empty_label = empty_label
        self._on_change = on_change
        self._filling = False
        self.row = Adw.ComboRow(title=title, subtitle=subtitle, enable_search=True,
                                expression=Gtk.PropertyExpression.new(Gtk.StringObject, None, "string"))
        self.row.connect("notify::selected", self._picked)
        self.set_known([])

    def set_known(self, known: Iterable[str], keep_unknown: bool = True) -> None:
        """Offer `known`. The current value stays listed even when unknown, unless
        `keep_unknown` is False and there is a "not set" item to fall back to."""
        known = [v for v in known if v]
        if not keep_unknown and self._empty_label is not None and self.value not in known:
            dropped, self.value = self.value, ""
            if dropped:
                self._on_change("")
        values = options(self.value, known)
        labels = list(values)
        if self._empty_label is not None:
            values, labels = ["", *values], [self._empty_label, *labels]
        self.values = values
        self._filling = True
        try:
            self.row.set_model(Gtk.StringList.new(labels))
            self.row.set_selected(values.index(self.value) if self.value in values else 0)
        finally:
            self._filling = False

    def _picked(self, row: Adw.ComboRow, _param) -> None:
        index = row.get_selected()
        if self._filling or not 0 <= index < len(self.values):
            return
        value = self.values[index]
        if value != self.value:
            self.value = value
            self._on_change(value)


def choice_row(title: str, current: str | None, known: Iterable[str],
               on_change: Callable[[str], None], empty_label: str | None = None) -> ChoiceRow:
    row = ChoiceRow(title, current, on_change, empty_label)
    row.set_known(known)
    return row
