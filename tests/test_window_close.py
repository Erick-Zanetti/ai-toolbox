"""Windows report their outcome when they close, not when Python collects them."""

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "4.0")


@pytest.fixture
def window():
    """A realized window: close() ignores one that was never realized. GTK starts
    here, not at import, so collecting this file does not touch other tests."""
    from gi.repository import Gtk

    if not Gtk.init_check():
        pytest.skip("no display")
    win = Gtk.Window()
    win.realize()
    return win


def test_close_reports_at_once_even_while_python_still_holds_the_window(window):
    from ai_toolbox.ui.common import on_closed

    calls = []
    keep = [window]  # the windows' own closures hold them like this
    on_closed(window, lambda: calls.append("closed"))

    window.close()

    assert calls == ["closed"]
    assert keep


def test_close_then_destroy_reports_once(window):
    from ai_toolbox.ui.common import on_closed

    calls = []
    on_closed(window, lambda: calls.append("closed"))

    window.close()
    window.destroy()

    assert calls == ["closed"]
