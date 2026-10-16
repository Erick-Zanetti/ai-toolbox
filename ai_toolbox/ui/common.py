"""Shared GTK bits: app bootstrap, text views, word diff highlight, styles."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from ..editing import word_diff  # noqa: E402

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


# Fixed hues (readable on light and dark), softened with alpha.
ADDED_RGBA = (0.18, 0.76, 0.49, 0.30)
REMOVED_RGBA = (0.88, 0.11, 0.14, 0.28)


def _rgba(values: tuple[float, float, float, float]) -> Gdk.RGBA:
    color = Gdk.RGBA()
    color.red, color.green, color.blue, color.alpha = values
    return color


def _tag(buf: Gtk.TextBuffer, name: str) -> Gtk.TextTag:
    tag = buf.get_tag_table().lookup(name)
    if tag is None:
        if name == "removed":
            tag = buf.create_tag(name, background_rgba=_rgba(REMOVED_RGBA), strikethrough=True)
        else:
            tag = buf.create_tag(name, background_rgba=_rgba(ADDED_RGBA))
    return tag


def _paint(view: Gtk.TextView, name: str, spans: list[tuple[int, int]]) -> None:
    buf = view.get_buffer()
    tag = _tag(buf, name)
    buf.remove_tag(tag, buf.get_start_iter(), buf.get_end_iter())
    for start, end in spans:
        buf.apply_tag(tag, buf.get_iter_at_offset(start), buf.get_iter_at_offset(end))


def show_diff(before_view: Gtk.TextView, after_view: Gtk.TextView) -> None:
    """Red strike-through on what left `before_view`, green on what is new in `after_view`."""
    removed, added = word_diff(buffer_text(before_view), buffer_text(after_view))
    _paint(before_view, "removed", removed)
    _paint(after_view, "added", added)


def clear_diff(before_view: Gtk.TextView, after_view: Gtk.TextView) -> None:
    _paint(before_view, "removed", [])
    _paint(after_view, "added", [])


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
