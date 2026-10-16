"""Shared GTK bits: app bootstrap, text views, word diff highlight, styles."""

from __future__ import annotations

import difflib
import re

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

APP_ID = "dev.aitoolbox.AiToolbox"

CSS = """
.atb-text { font-size: 15px; background: transparent; }
.atb-text text { background: transparent; }
.atb-pane { background: alpha(@view_fg_color, 0.04); border-radius: 12px; padding: 10px 12px; }
.atb-search { min-height: 42px; font-size: 16px; }
.atb-hint { font-size: 12px; opacity: 0.6; }
.atb-note { font-size: 13px; padding: 8px 12px; border-radius: 10px;
              background: alpha(@accent_bg_color, 0.12); }
"""

_TOKENS = re.compile(r"\s+|\w+|[^\w\s]", re.UNICODE)


def install_css() -> None:
    provider = Gtk.CssProvider()
    provider.load_from_string(CSS)
    Gtk.StyleContext.add_provider_for_display(
        Gdk.Display.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )


def text_view(editable: bool = True) -> tuple[Gtk.ScrolledWindow, Gtk.TextView]:
    view = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, editable=editable,
                        cursor_visible=editable, vexpand=True)
    view.add_css_class("atb-text")
    scroller = Gtk.ScrolledWindow(child=view, vexpand=True,
                                  hscrollbar_policy=Gtk.PolicyType.NEVER)
    scroller.add_css_class("atb-pane")
    return scroller, view


def buffer_text(view: Gtk.TextView) -> str:
    buf = view.get_buffer()
    return buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)


def highlight_changes(view: Gtk.TextView, before: str) -> None:
    """Tint the words of the view's text that differ from `before`."""
    buf = view.get_buffer()
    tag = buf.get_tag_table().lookup("changed")
    if tag is None:
        # Theme accent (follows the system accent / matugen colors), softened.
        accent = Adw.StyleManager.get_default().get_accent_color_rgba()
        accent.alpha = 0.3
        tag = buf.create_tag("changed", background_rgba=accent)
    buf.remove_tag(tag, buf.get_start_iter(), buf.get_end_iter())

    old = _TOKENS.findall(before)
    new = _TOKENS.findall(buffer_text(view))
    offsets, pos = [], 0
    for token in new:
        offsets.append(pos)
        pos += len(token)
    offsets.append(pos)

    matcher = difflib.SequenceMatcher(a=old, b=new, autojunk=False)
    for op, _, _, j1, j2 in matcher.get_opcodes():
        if op in ("replace", "insert") and j1 < j2:
            buf.apply_tag(tag, buf.get_iter_at_offset(offsets[j1]),
                          buf.get_iter_at_offset(offsets[j2]))


def shortcut(widget: Gtk.Widget, accel: str, callback) -> None:
    controller = Gtk.ShortcutController(scope=Gtk.ShortcutScope.GLOBAL)
    controller.add_shortcut(Gtk.Shortcut(
        trigger=Gtk.ShortcutTrigger.parse_string(accel),
        action=Gtk.CallbackAction.new(lambda *_: (callback(), True)[1]),
    ))
    widget.add_controller(controller)


def run_window(build) -> int:
    """Start a one-window app; `build(app)` returns the window."""
    app = Adw.Application(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)

    def activate(app: Adw.Application) -> None:
        install_css()
        build(app).present()

    app.connect("activate", activate)
    return app.run([])


def idle(fn):
    """Wrap a worker-thread callback so it runs on the GTK main loop."""
    return lambda *args: GLib.idle_add(lambda: (fn(*args), False)[1])
