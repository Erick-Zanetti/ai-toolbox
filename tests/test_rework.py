"""Reply, tone and alternatives prompts; the [history] config table."""

import pytest

from ai_toolbox import config, prompts


def test_tones_cycle_and_wrap_back_to_neutral():
    assert prompts.TONES[0] == "neutral"
    seen, tone = [], "neutral"
    for _ in prompts.TONES:
        tone = prompts.next_tone(tone)
        seen.append(tone)
    assert seen == [*prompts.TONES[1:], "neutral"]
    assert prompts.next_tone("unknown") == prompts.TONES[1]


def test_tone_prompt_wraps_the_text_after_a_tone_instruction():
    out = prompts.tone("formal", "hey, cant make it")
    assert "formal" in out.lower()
    assert out.endswith("<text>\nhey, cant make it\n</text>")
    with pytest.raises(ValueError):
        prompts.tone("neutral", "x")


def test_every_tone_but_neutral_has_its_own_instruction():
    rewrites = {prompts.tone(name, "x") for name in prompts.TONES[1:]}
    assert len(rewrites) == len(prompts.TONES) - 1


def test_alternatives_prompt_asks_for_three_separated_versions():
    out = prompts.alternatives("We should ship it.")
    assert "three" in out and prompts.SEPARATOR in out
    assert out.endswith("<text>\nWe should ship it.\n</text>")


def test_parse_suggestions_one_per_line_drops_numbering_and_quotes():
    raw = '1. Sure, on it!\n2) "Can we do Friday instead?"\n\n- No, sorry\n4. One too many'
    assert prompts.parse_suggestions(raw) == ["Sure, on it!", "Can we do Friday instead?", "No, sorry"]


def test_parse_suggestions_keeps_multi_line_versions_between_separators():
    raw = "First line\nsecond line\n---\n“Second”\n---\n* Third\n---\n"
    assert prompts.parse_suggestions(raw) == ["First line\nsecond line", "Second", "Third"]


def test_parse_suggestions_skips_duplicates_and_blanks():
    assert prompts.parse_suggestions("ok\n\nok\n  \n") == ["ok"]
    assert prompts.parse_suggestions("") == []


def test_reply_system_writes_as_the_user_in_the_received_language():
    system = prompts.reply_system("I am Erick, a developer.", ("Titan",))
    assert "I am Erick, a developer." in system
    assert "language of the received message" in system
    assert '"Titan"' in system
    assert "about_the_user" not in prompts.reply_system("", ())


def test_reply_prompts_carry_the_message_and_the_notes():
    out = prompts.reply_prompt("Can you review my PR?", "  diz que vejo amanhã ")
    assert "<received_message>\nCan you review my PR?\n</received_message>" in out
    assert "<my_notes>\ndiz que vejo amanhã\n</my_notes>" in out
    suggestions = prompts.reply_suggestions_prompt("Lunch?")
    assert "<received_message>\nLunch?\n</received_message>" in suggestions
    assert "three" in suggestions and "one per line" in suggestions.lower()


def _config(tmp_path, extra: str = "") -> config.Config:
    (tmp_path / "config.toml").write_text(f'{extra}\n[providers.claude]\nmodel = "haiku"\n')
    return config.load(tmp_path)


def test_history_is_on_with_50_entries_by_default(tmp_path):
    assert _config(tmp_path).history == config.History(enabled=True, max_entries=50)


def test_history_settings_load(tmp_path):
    cfg = _config(tmp_path, "[history]\nenabled = false\nmax_entries = 10")
    assert cfg.history == config.History(enabled=False, max_entries=10)


@pytest.mark.parametrize("table", [
    "[history]\nmax_entries = 0",
    "[history]\nmax_entries = true",
    "[history]\nenabled = \"yes\"",
    "[history]\nlimit = 5",
])
def test_bad_history_settings_are_rejected(tmp_path, table):
    with pytest.raises(config.ConfigError):
        _config(tmp_path, table)


def test_every_ui_string_has_a_portuguese_translation():
    import ast
    from pathlib import Path

    from ai_toolbox import i18n

    root = Path(__file__).resolve().parent.parent / "ai_toolbox"
    missing = {
        node.args[0].value
        for path in root.rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "t"
        and node.args and isinstance(node.args[0], ast.Constant)
        and node.args[0].value not in i18n._PT
    }
    assert missing == set()


def test_tone_names_are_translated():
    from ai_toolbox import i18n

    assert all(name in i18n._PT for name in prompts.TONES)
