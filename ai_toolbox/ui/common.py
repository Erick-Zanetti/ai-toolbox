"""Shared GTK bits: app bootstrap, text views, word diff highlight, styles."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # noqa: E402

from ..editing import word_diff  # noqa: E402

from ..cli import APP_ID  # noqa: E402,F401  (one source of truth)

CSS = """
.atb-text { font-size: 15px; background: transparent; }
.atb-text text { background: transparent; }
.atb-pane { background: alpha(@view_fg_color, 0.045); border-radius: 14px; padding: 12px 14px;
            border: 1px solid alpha(@view_fg_color, 0.06); }
.atb-pane-title { font-size: 11px; font-weight: 700; letter-spacing: 0.06em; opacity: 0.55; }
.atb-search { min-height: 44px; font-size: 17px; border-radius: 12px; }
.atb-hint { font-size: 12px; opacity: 0.6; }
.atb-note { font-size: 13px; padding: 10px 12px; border-radius: 12px;
            background: alpha(@accent_bg_color, 0.14); }
.atb-key { font-family: monospace; font-size: 11px; font-weight: 600; min-width: 14px;
           padding: 1px 6px; border-radius: 6px; background: alpha(@window_fg_color, 0.08);
           border: 1px solid alpha(@window_fg_color, 0.14);
           box-shadow: inset 0 -1px alpha(@window_fg_color, 0.14); }
.atb-keylabel { font-size: 12px; opacity: 0.65; margin-right: 10px; }
.atb-stat { font-size: 11px; font-weight: 700; padding: 1px 8px; border-radius: 999px; }
.atb-stat-add { color: #2ec27e; background: alpha(#2ec27e, 0.15); }
.atb-stat-del { color: #e66159; background: alpha(#e01b24, 0.15); }
.atb-tone { color: @accent_color; background: alpha(@accent_bg_color, 0.18); }
.atb-tile { border-radius: 10px; padding: 7px; background: alpha(@accent_bg_color, 0.18);
            color: @accent_color; }
.atb-chip { border-radius: 12px; padding: 8px 12px; background: alpha(@view_fg_color, 0.05);
            border: 1px solid alpha(@view_fg_color, 0.06); }
.atb-action { padding-left: 16px; padding-right: 16px; border-radius: 10px; font-weight: 700; }
.atb-ask { min-height: 38px; border-radius: 10px; }
.atb-lang > button { border-radius: 999px; padding-left: 14px; padding-right: 10px; }
.atb-tile > image { color: @accent_color; -gtk-icon-style: symbolic; }
.atb-rec-dot { color: #e01b24; font-size: 18px; animation: atb-pulse 0.7s ease-in-out infinite alternate; }
@keyframes atb-pulse { from { opacity: 0.35; } to { opacity: 0.95; } }
.atb-thinking { font-size: 12px; animation: atb-pulse 0.8s ease-in-out infinite alternate; }
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


def pane(title: str, scroller: Gtk.Widget, *pills: Gtk.Label) -> Gtk.Box:
    """A text pane under a small uppercase title, with optional pills beside it."""
    head = Gtk.Box(spacing=8)
    head.append(Gtk.Label(label=title.upper(), xalign=0, css_classes=["atb-pane-title"]))
    for pill in pills:
        head.append(pill)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    box.append(head)
    box.append(scroller)
    return box


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


def show_diff(before_view: Gtk.TextView, after_view: Gtk.TextView) -> tuple[int, int]:
    """Red strike-through on what left `before_view`, green on what is new in
    `after_view`. Returns (removed, added) change counts."""
    removed, added = word_diff(buffer_text(before_view), buffer_text(after_view))
    _paint(before_view, "removed", removed)
    _paint(after_view, "added", added)
    return len(removed), len(added)


def clear_diff(before_view: Gtk.TextView, after_view: Gtk.TextView) -> None:
    _paint(before_view, "removed", [])
    _paint(after_view, "added", [])


def hint_bar(items: list[tuple[str, str]]) -> Gtk.Box:
    """Keyboard hints drawn as keycaps: [("Ctrl+Enter", "replace"), ...]."""
    from ..i18n import t

    bar = Gtk.Box(spacing=4, halign=Gtk.Align.END, valign=Gtk.Align.CENTER)
    for keys, label in items:
        for key in keys.split("+"):
            bar.append(Gtk.Label(label=key, css_classes=["atb-key"]))
        bar.append(Gtk.Label(label=t(label), css_classes=["atb-keylabel"]))
    return bar


def icon_tile(icon_name: str, size: int = 18) -> Gtk.Widget:
    image = Gtk.Image(icon_name=icon_name, pixel_size=size)
    tile = Gtk.Box(valign=Gtk.Align.CENTER, css_classes=["atb-tile"])
    tile.append(image)
    return tile


def stat_pill(kind: str) -> Gtk.Label:
    """A small '+3' / '−2' counter; kind is 'add' or 'del'."""
    return Gtk.Label(visible=False, css_classes=["atb-stat", f"atb-stat-{kind}"])


def shortcut(widget: Gtk.Widget, accel: str, callback) -> None:
    controller = Gtk.ShortcutController(scope=Gtk.ShortcutScope.GLOBAL)
    # Capture phase: run before focused text views, which would otherwise
    # eat keys like Ctrl+Enter (newline).
    controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
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
