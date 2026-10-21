"""Small recording pill: pulsing dot, timer, then the transcription state.
Enter (or the dictation shortcut again) stops, Esc cancels."""

from __future__ import annotations

from collections.abc import Callable

from ..i18n import t
from .common import Adw, GLib, Gtk, hint_bar, on_closed, shortcut

TITLE = "AI Toolbox · Dictation"
STATES = {
    "recording": "Listening…",
    "setup": "Setting up dictation (one time, ~1 GB)…",
    "loading": "Loading the speech model…",
    "transcribing": "Transcribing…",
    "thinking": "Applying {name}…",
}


class Pill:
    def __init__(self, app: Adw.Application, on_stop: Callable[[], None],
                 on_cancel: Callable[[], None]):
        self.win = Adw.ApplicationWindow(application=app, title=TITLE, default_width=420,
                                         default_height=64, resizable=False)
        self.win.set_size_request(420, 64)  # libadwaita windows default to a 360x200 minimum
        self.win.add_css_class("atb-pill")
        self.dot = Gtk.Label(label="●", css_classes=["atb-rec-dot"])
        self.status = Gtk.Label(xalign=0, hexpand=True, ellipsize=3)
        self.clock = Gtk.Label(label="0:00", css_classes=["atb-pane-title"])
        self.spinner = Adw.Spinner(visible=False)
        row = Gtk.Box(spacing=12, margin_start=18, margin_end=14, margin_top=12, margin_bottom=12)
        for widget in (self.dot, self.spinner, self.status, self.clock,
                       hint_bar([("Enter", "stop"), ("Esc", "cancel")])):
            row.append(widget)
        self.win.set_content(row)
        self.started = GLib.get_monotonic_time()
        self.timer = GLib.timeout_add(250, self._tick)
        shortcut(self.win, "Return", on_stop)
        shortcut(self.win, "KP_Enter", on_stop)
        shortcut(self.win, "Escape", on_cancel)
        on_closed(self.win, self._stop_timer)
        self.set_state("recording")

    def _tick(self) -> bool:
        seconds = (GLib.get_monotonic_time() - self.started) // 1_000_000
        self.clock.set_label(f"{seconds // 60}:{seconds % 60:02d}")
        return True

    def _stop_timer(self) -> None:
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0

    def set_state(self, state: str, **values) -> None:
        recording = state == "recording"
        self.dot.set_visible(recording)
        self.spinner.set_visible(not recording)
        self.clock.set_visible(recording)
        if not recording:
            self._stop_timer()
        self.status.set_label(t(STATES[state], **values))

    def present(self) -> None:
        self.win.present()

    def close(self) -> None:
        self.win.close()
