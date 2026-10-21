"""The dropdown rows Settings uses for models and reasoning effort."""

import pytest

gi = pytest.importorskip("gi")


@pytest.fixture
def choice():
    """GTK starts here, not at import, so collecting this file does not touch
    other tests (and it skips where GTK 4 or a display is missing)."""
    try:
        gi.require_version("Gtk", "4.0")
        gi.require_version("Adw", "1")
    except ValueError:
        pytest.skip("GTK 4 / libadwaita not installed")
    from gi.repository import Adw, Gtk

    if not Gtk.init_check():
        pytest.skip("no display")
    Adw.init()
    from ai_toolbox.ui import choice

    return choice


def _labels(row):
    model = row.get_model()
    return [model.get_string(i) for i in range(model.get_n_items())]


def _pick(row, label):
    row.set_selected(_labels(row).index(label))


def test_lists_known_values_after_the_unset_item_and_selects_the_current(choice):
    changes = []
    row = choice.ChoiceRow("Model", "sonnet", changes.append, empty_label="Provider default")
    row.set_known(["haiku", "sonnet", "opus"])

    assert _labels(row.row) == ["Provider default", "haiku", "sonnet", "opus"]
    assert row.row.get_selected() == 2 and row.value == "sonnet"
    assert row.row.get_enable_search()
    assert changes == []  # filling the list writes nothing


def test_picking_writes_the_value_and_the_unset_item_writes_empty(choice):
    changes = []
    row = choice.ChoiceRow("Model", "", changes.append, empty_label="Provider default")
    row.set_known(["haiku", "opus"])
    assert row.row.get_selected() == 0

    _pick(row.row, "opus")
    _pick(row.row, "Provider default")

    assert changes == ["opus", ""]


def test_an_unknown_configured_value_stays_listed_and_selected(choice):
    changes = []
    row = choice.ChoiceRow("GPU model", "distil-large-v3", changes.append)
    row.set_known(["small", "large-v3-turbo"])

    assert _labels(row.row) == ["small", "large-v3-turbo", "distil-large-v3"]
    assert row.value == "distil-large-v3" and changes == []


def test_new_list_keeps_a_still_valid_choice(choice):
    changes = []
    row = choice.ChoiceRow("Model", "b", changes.append, empty_label="Default")
    row.set_known(["a", "b"])
    row.set_known(["b", "c"], keep_unknown=False)

    assert _labels(row.row) == ["Default", "b", "c"]
    assert row.value == "b" and row.row.get_selected() == 1 and changes == []


def test_new_list_without_the_choice_falls_back_to_unset(choice):
    changes = []
    row = choice.ChoiceRow("Model", "haiku", changes.append, empty_label="Default")
    row.set_known(["haiku"])
    row.set_known(["gpt-x"], keep_unknown=False)

    assert _labels(row.row) == ["Default", "gpt-x"]
    assert row.value == "" and row.row.get_selected() == 0 and changes == [""]
