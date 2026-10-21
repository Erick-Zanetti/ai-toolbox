"""History of delivered results: the JSON store, the CLI and recording on delivery."""

import dataclasses
import json
import stat
from datetime import datetime
from pathlib import Path

import pytest

from ai_toolbox import cli, config, desktop, history

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
NOW = datetime(2026, 10, 21, 14, 5, 9)


def _entry(output: str, source: str = "fix-spelling", text: str = "in") -> history.Entry:
    return history.entry(source, "Fix spelling", text, output, now=NOW)


def test_entries_round_trip_newest_first(tmp_path):
    path = tmp_path / "state" / "history.json"
    history.add(_entry("one"), 50, path)
    history.add(_entry("two"), 50, path)
    entries = history.load(path)
    assert [e.output for e in entries] == ["two", "one"]
    assert entries[0] == history.Entry("2026-10-21T14:05:09", "fix-spelling", "Fix spelling", "in", "two")


def test_history_keeps_only_the_newest_max_entries(tmp_path):
    path = tmp_path / "history.json"
    for n in range(5):
        history.add(_entry(str(n)), 3, path)
    assert [e.output for e in history.load(path)] == ["4", "3", "2"]
    assert [e.output for e in history.trim(history.load(path), 1)] == ["4"]


def test_missing_or_corrupt_file_is_an_empty_history(tmp_path):
    path = tmp_path / "history.json"
    assert history.load(path) == []
    path.write_text("{not json")
    assert history.load(path) == []
    path.write_text(json.dumps({"entries": "nope"}))
    assert history.load(path) == []
    path.write_text(json.dumps([{"output": "no other fields"}, _entry("ok").__dict__]))
    assert [e.output for e in history.load(path)] == ["ok"]


def test_history_file_is_private_and_written_atomically(tmp_path):
    path = tmp_path / "state" / "history.json"
    history.add(_entry("secret"), 50, path)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert [p.name for p in path.parent.iterdir()] == ["history.json"]


def test_clear_empties_the_history(tmp_path):
    path = tmp_path / "history.json"
    history.add(_entry("x"), 50, path)
    history.clear(path)
    assert history.load(path) == []
    history.clear(tmp_path / "never-written.json")


def test_search_matches_every_word_in_any_field():
    item = history.entry("translate", "Translate", "Bom dia", "Good morning", now=NOW)
    assert history.matches(item, "")
    assert history.matches(item, "good BOM")
    assert history.matches(item, "translate")
    assert not history.matches(item, "evening")


def test_preview_is_one_short_line():
    assert history.preview("  line one\n\n line   two ", 40) == "line one line two"
    assert history.preview("x" * 50, 10) == "x" * 9 + "…"


def test_summary_line_has_time_source_and_preview():
    line = history.summary(_entry("Fixed\ntext"))
    assert line.startswith("2026-10-21 14:05  fix-spelling")
    assert line.endswith("Fixed text") and "\n" not in line


@pytest.fixture
def fake_desktop(monkeypatch, tmp_path):
    sent = {"copied": [], "notes": []}
    monkeypatch.setattr(desktop, "copy", lambda text: sent["copied"].append(text))
    monkeypatch.setattr(desktop, "notify", lambda body, **kw: sent["notes"].append(body))
    monkeypatch.setattr(history, "HISTORY_FILE", tmp_path / "history.json")
    return sent


def _invocation() -> cli.Invocation:
    return cli.Invocation("teh text", None, desktop.Desktop())


def test_delivering_a_result_records_it(fake_desktop, tmp_path):
    cfg = config.load(EXAMPLES)
    cli.deliver("copy", "the text", _invocation(), cfg, source="fix-spelling", name="Fix spelling")
    cli.deliver("replace", "Hi", _invocation(), cfg, source="translate", name="Translate",
                original="Oi")
    cli.deliver(None, "closed", _invocation(), cfg, source="reply", name="Reply")
    entries = history.load(tmp_path / "history.json")
    assert [(e.source, e.input, e.output) for e in entries] == [
        ("translate", "Oi", "Hi"), ("fix-spelling", "teh text", "the text")]
    assert fake_desktop["copied"] == ["the text", "Hi"]


def test_nothing_is_recorded_when_history_is_off(fake_desktop, tmp_path):
    cfg = dataclasses.replace(config.load(EXAMPLES), history=config.History(enabled=False))
    cli.deliver("copy", "the text", _invocation(), cfg, source="fix-spelling", name="Fix spelling")
    assert not (tmp_path / "history.json").exists()
    assert fake_desktop["copied"] == ["the text"]


def test_cli_prints_clears_and_dumps_history(fake_desktop, tmp_path, capsys):
    path = tmp_path / "history.json"
    history.add(_entry("first"), 50, path)
    history.add(_entry("second", source="reply"), 50, path)

    assert cli.main(["history"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2 and "reply" in lines[0] and lines[0].endswith("second")

    assert cli.main(["history", "--json"]) == 0
    assert [e["output"] for e in json.loads(capsys.readouterr().out)] == ["second", "first"]

    assert cli.main(["history", "--clear"]) == 0
    capsys.readouterr()
    assert history.load(path) == []


def test_parser_knows_reply_and_history():
    parser = cli.build_parser()
    assert parser.parse_args(["reply"]).action == "reply"
    args = parser.parse_args(["history", "--json"])
    assert (args.action, args.json, args.clear) == ("history", True, False)


def test_dispatch_log_line_never_has_the_text():
    args = cli.build_parser().parse_args(["run", "fix-spelling"])
    assert cli.describe(args) == "run fix-spelling"
    assert cli.describe(cli.build_parser().parse_args(["reply"])) == "reply"
    assert cli.describe(cli.build_parser().parse_args([])) == "palette"
