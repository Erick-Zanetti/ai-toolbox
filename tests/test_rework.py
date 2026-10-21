"""Reply, tone and alternatives prompts."""

import pytest

from ai_toolbox import prompts


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
