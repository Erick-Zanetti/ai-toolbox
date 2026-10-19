from pathlib import Path

import pytest

from ai_toolbox import config, prompts, providers

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_split_translation_reads_language_body_and_note():
    raw = "@lang English\nOlá, tudo bem?\nLinha dois\n@note Usei 'tudo bem' por ser informal."
    assert prompts.split_translation(raw) == (
        "English", "Olá, tudo bem?\nLinha dois", "Usei 'tudo bem' por ser informal.")


def test_split_translation_without_markers_is_just_the_body():
    assert prompts.split_translation("Hello") == (None, "Hello", None)


def test_split_translation_while_header_streams():
    assert prompts.split_translation("@lang Eng") == ("Eng", "", None)


def test_render_fills_placeholders():
    out = prompts.render("Fix:\n{selection}\nAbout: {context}", "teh text", "dev")
    assert out == "Fix:\nteh text\nAbout: dev"


def test_render_appends_text_when_template_has_no_placeholder():
    out = prompts.render("Summarize.", "long text", "")
    assert out.endswith("<text>\nlong text\n</text>")


def test_literal_prompt_has_no_context_and_contextual_has_it():
    literal = prompts.translate_system(None, None, ("English", "Portuguese"), None)
    contextual = prompts.translate_system(None, "English", ("English", "Portuguese"), "I work at X")
    assert "I work at X" not in literal and "literally" in literal
    assert "I work at X" in contextual and "Translate into English." in contextual


def test_examples_load():
    cfg = config.load(EXAMPLES)
    assert cfg.commands["fix-spelling"].output == "window"
    assert "foot" in cfg.terminal_classes and cfg.copy_fallback is False
    assert cfg.commands["fix-spelling"].model == config.Model("claude", "haiku", None)
    assert cfg.translate.pair == ("English", "Portuguese (Brazil)")
    assert cfg.translate.languages[:2] == cfg.translate.pair


def test_command_with_other_provider_uses_that_providers_defaults(tmp_path):
    (tmp_path / "commands").mkdir()
    (tmp_path / "config.toml").write_text(
        '[providers.claude]\nmodel = "haiku"\n[providers.codex]\nmodel = "luna"\nreasoning = "low"\n')
    (tmp_path / "commands" / "x.toml").write_text('provider = "codex"\nprompt = "p"\n')
    assert config.load(tmp_path).commands["x"].model == config.Model("codex", "luna", "low")


def test_bad_output_is_rejected(tmp_path):
    (tmp_path / "commands").mkdir()
    (tmp_path / "config.toml").write_text('[providers.claude]\nmodel = "haiku"\n')
    (tmp_path / "commands" / "x.toml").write_text('output = "popup"\nprompt = "p"\n')
    with pytest.raises(config.ConfigError):
        config.load(tmp_path)


def test_claude_stream_parser_yields_text_deltas():
    lines = [
        '{"type":"system"}',
        '{"type":"stream_event","event":{"type":"content_block_delta",'
        '"delta":{"type":"text_delta","text":"Hi "}}}',
        '{"type":"stream_event","event":{"type":"content_block_delta","delta":{"type":"text_delta","text":"there"}}}',
        '{"type":"result","is_error":false}',
    ]
    assert "".join(providers._claude_chunks(iter(lines))) == "Hi there"


def test_claude_stream_parser_raises_on_error_result():
    with pytest.raises(providers.ProviderError):
        list(providers._claude_chunks(iter(['{"type":"result","is_error":true,"result":"limit"}'])))


def test_ui_strings_follow_system_language(monkeypatch):
    import importlib

    from ai_toolbox import i18n

    monkeypatch.setenv("LANG", "pt_BR.UTF-8")
    for var in ("LANGUAGE", "LC_ALL", "LC_MESSAGES"):
        monkeypatch.delenv(var, raising=False)
    assert importlib.reload(i18n).t("{n} words", n=2) == "2 palavras"
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert importlib.reload(i18n).t("{n} words", n=2) == "2 words"


def test_sse_parser_yields_content_until_done():
    lines = [
        b": keep-alive\n",
        b'data: {"choices":[{"delta":{"role":"assistant"}}]}\n',
        b'data: {"choices":[{"delta":{"content":"Ol"}}]}\n',
        b'data: {"choices":[{"delta":{"content":"\xc3\xa1"}}]}\n',
        b"data: [DONE]\n",
        b'data: {"choices":[{"delta":{"content":"ignored"}}]}\n',
    ]
    assert "".join(providers._sse_chunks(iter(lines))) == "Olá"


def test_openai_provider_needs_base_url(tmp_path):
    (tmp_path / "config.toml").write_text('[providers.local]\ntype = "openai"\nmodel = "llama3.2"\n')
    with pytest.raises(config.ConfigError):
        config.load(tmp_path)


def test_openai_provider_loads(tmp_path):
    (tmp_path / "config.toml").write_text(
        '[providers.local]\ntype = "openai"\nmodel = "llama3.2"\n'
        'base_url = "http://localhost:11434/v1"\n')
    model = config.load(tmp_path).default
    assert (model.type, model.base_url) == ("openai", "http://localhost:11434/v1")


def test_terminal_windows_paste_with_shift(monkeypatch):
    from ai_toolbox import desktop

    sent = []
    monkeypatch.setattr(desktop.time, "sleep", lambda _: None)

    class Fake(desktop.Desktop):
        def send_shortcut(self, target, key, terminal):
            sent.append(terminal)
            return True

    Fake().paste(desktop.Target("1", "foot"), ("foot",))
    Fake().paste(desktop.Target("2", "firefox"), ("foot",))
    assert sent == [True, False]


def test_http_run_streams_from_openai_compatible_server():
    import http.server
    import json
    import threading

    seen = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen["auth"] = self.headers.get("Authorization")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for part in ("Hello", " world"):
                chunk = {"choices": [{"delta": {"content": part}}]}
                self.wfile.write(f"data: {json.dumps(chunk)}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")

        def log_message(self, *_):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    model = config.Model("local", "tiny", kind="openai",
                         base_url=f"http://127.0.0.1:{server.server_port}/v1")
    try:
        assert providers.complete(model, "sys", "hi") == "Hello world"
    finally:
        server.shutdown()
    assert seen["body"]["messages"][0] == {"role": "system", "content": "sys"}
    assert seen["body"]["stream"] is True and seen["auth"] is None


def test_copy_fallback_reads_new_clipboard(monkeypatch):
    from ai_toolbox import desktop

    board = {"text": "old"}
    monkeypatch.setattr(desktop.time, "sleep", lambda _: None)
    monkeypatch.setattr(desktop, "clipboard", lambda: board["text"])

    class Fake(desktop.Desktop):
        def send_shortcut(self, target, key, terminal):
            board["text"] = "selected words"
            return key == "c"

    assert Fake().copy_selection(desktop.Target("1", "app"), ()) == "selected words"


def test_copy_fallback_gives_up_when_nothing_was_copied(monkeypatch):
    from ai_toolbox import desktop

    monkeypatch.setattr(desktop.time, "sleep", lambda _: None)
    monkeypatch.setattr(desktop, "clipboard", lambda: "old")

    class Fake(desktop.Desktop):
        def send_shortcut(self, target, key, terminal):
            return True

    assert Fake().copy_selection(desktop.Target("1", "app"), ()) == ""


def test_copy_fallback_is_off_by_default_and_never_hits_terminals(monkeypatch):
    from ai_toolbox import cli, desktop

    calls = []

    class Fake(desktop.Desktop):
        def focused(self):
            return desktop.Target("1", "foot")

        def copy_selection(self, target, terminal_classes):
            calls.append(target.app_id)
            return "copied"

    monkeypatch.setattr(desktop, "detect", lambda: Fake())
    monkeypatch.setattr(desktop, "selection", lambda: "")
    cfg = config.load(EXAMPLES)
    assert cli.capture(cfg).text == "" and calls == []

    import dataclasses
    on = dataclasses.replace(cfg, copy_fallback=True)
    assert cli.capture(on).text == "" and calls == []  # foot is a terminal


def test_retry_runs_on_the_result_with_edits():
    from ai_toolbox.editing import next_input

    assert next_input("orig", "result + my edit", False, True) == "result + my edit"
    assert next_input("orig", "result", False, False) == "result"
    assert next_input("orig edited", "result", True, False) == "orig edited"
    assert next_input("orig", "  ", False, False) == "orig"


def test_word_diff_marks_removed_and_added_spans():
    from ai_toolbox.editing import word_diff

    before, after = "I goes to store", "I went to the store"
    removed, added = word_diff(before, after)
    assert [before[a:b] for a, b in removed] == ["goes"]
    assert [after[a:b] for a, b in added] == ["went", "the "]


def test_store_round_trips_config_and_commands(tmp_path):
    import shutil

    from ai_toolbox.store import Store

    shutil.copytree(EXAMPLES, tmp_path, dirs_exist_ok=True)
    store = Store(tmp_path)
    data = store.config()
    data["notifications"] = "errors"
    store.save_config(data)
    assert store.config() == data

    cmd = store.commands()["fix-spelling"]
    cmd["output"] = "replace"
    store.save_command("fix-spelling", cmd)
    assert store.commands()["fix-spelling"] == cmd

    new_id = store.new_command_id("Make it Friendlier!")
    assert new_id == "make-it-friendlier"
    store.save_command(new_id, {"name": "x", "prompt": "a 'quoted' \"text\"\nline2"})
    loaded = config.load(tmp_path)
    assert loaded.notifications == "errors"
    assert loaded.commands[new_id].prompt == "a 'quoted' \"text\"\nline2"
    store.delete_command(new_id)
    assert new_id not in store.commands()


def test_store_writes_through_symlinks(tmp_path):
    from ai_toolbox.store import Store

    real = tmp_path / "dotfiles.toml"
    real.write_text('[providers.claude]\nmodel = "haiku"\n')
    (tmp_path / "cfg").mkdir()
    (tmp_path / "cfg" / "config.toml").symlink_to(real)
    store = Store(tmp_path / "cfg")
    data = store.config()
    data["copy_fallback"] = True
    store.save_config(data)
    assert (tmp_path / "cfg" / "config.toml").is_symlink()
    assert "copy_fallback = true" in real.read_text()


def test_notification_levels(monkeypatch):
    import dataclasses

    from ai_toolbox import cli, desktop

    sent = []
    monkeypatch.setattr(desktop, "notify", lambda body, **kw: sent.append(body))
    cfg = config.load(EXAMPLES)
    for level in ("all", "errors", "off"):
        c = dataclasses.replace(cfg, notifications=level)
        for kind in ("info", "warn", "error"):
            cli.notify(c, kind, f"{level}-{kind}")
    assert sent == ["all-info", "all-warn", "all-error", "errors-warn", "errors-error"]


def test_bad_notifications_value_is_rejected(tmp_path):
    (tmp_path / "config.toml").write_text('notifications = "loud"\n[providers.claude]\nmodel = "haiku"\n')
    with pytest.raises(config.ConfigError):
        config.load(tmp_path)


def test_glossary_reaches_command_and_translation_prompts(tmp_path):
    (tmp_path / "config.toml").write_text(
        'glossary = ["Titan", "FMP"]\n[providers.claude]\nmodel = "haiku"\n')
    cfg = config.load(tmp_path)
    assert cfg.glossary == ("Titan", "FMP")
    assert '"Titan", "FMP"' in prompts.command_system(cfg.glossary)
    assert '"Titan"' in prompts.translate_system(None, None, ("English", "Portuguese"), None, cfg.glossary)
    assert prompts.command_system(()) == prompts.COMMAND_SYSTEM


def test_language_placeholder_uses_system_language(monkeypatch):
    monkeypatch.setattr(prompts, "language_name", lambda: "Brazilian Portuguese")
    out = prompts.render("Explain in {language}: {selection}", "x", "")
    assert out == "Explain in Brazilian Portuguese: x"


def test_explain_command_has_no_diff():
    assert config.load(EXAMPLES).commands["explain"].diff is False
    assert config.load(EXAMPLES).commands["shorten"].diff is True


def test_refine_wraps_text_after_instruction():
    assert prompts.refine("  more formal ", "hey") == "more formal\n\n<text>\nhey\n</text>"


def test_portal_shortcut_events_press_and_release_in_order():
    from ai_toolbox import portal

    ctrl, shift, v = portal.KEYSYMS["ctrl"], portal.KEYSYMS["shift"], portal.KEYSYMS["v"]
    assert portal.shortcut_events("v", False) == [(ctrl, 1), (v, 1), (v, 0), (ctrl, 0)]
    assert portal.shortcut_events("v", True) == [
        (ctrl, 1), (shift, 1), (v, 1), (v, 0), (shift, 0), (ctrl, 0)]


def test_portal_unavailable_without_gi_returns_false(monkeypatch):
    import builtins

    from ai_toolbox import portal

    real_import = builtins.__import__

    def no_gi(name, *args, **kwargs):
        if name.startswith("gi"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_gi)
    monkeypatch.setattr(portal, "_instance", None)
    monkeypatch.setattr(portal, "_available", None)
    assert portal.send_shortcut("v", False) is False


def test_dictation_settings_load_and_validate(tmp_path):
    (tmp_path / "config.toml").write_text(
        '[providers.claude]\nmodel = "haiku"\n[dictation]\nlanguage = "pt"\nthen = "fix-spelling"\n')
    settings = config.load(tmp_path).dictation
    expected = ("pt", "fix-spelling", "large-v3-turbo")
    assert (settings.language, settings.then, settings.model) == expected
    (tmp_path / "config.toml").write_text(
        '[providers.claude]\nmodel = "haiku"\n[dictation]\ndevice = "tpu"\n')
    with pytest.raises(config.ConfigError):
        config.load(tmp_path)
    (tmp_path / "config.toml").write_text('[providers.claude]\nmodel = "haiku"\n[dictation]\nmodle = "x"\n')
    with pytest.raises(config.ConfigError):
        config.load(tmp_path)


def test_recorder_asks_for_16khz_mono(monkeypatch, tmp_path):
    from ai_toolbox import dictation

    monkeypatch.setattr(dictation.shutil, "which", lambda name: f"/usr/bin/{name}")
    argv = dictation.record_argv(tmp_path / "a.wav")
    assert argv[:7] == ["pw-record", "--rate", "16000", "--channels", "1", "--format", "s16"]


def test_stt_worker_protocol_with_fake_model(tmp_path):
    """Run the real worker script with a stub faster_whisper module."""
    import json
    import subprocess
    import sys
    import wave

    fake = tmp_path / "fake"
    (fake / "faster_whisper").mkdir(parents=True)
    (fake / "faster_whisper" / "__init__.py").write_text(
        "class _I:\n    language = 'pt'\n"
        "class _S:\n    text = ' olá mundo '\n"
        "class WhisperModel:\n"
        "    def __init__(self, *a, **k): pass\n"
        "    def transcribe(self, audio, **k): return [_S()], _I()\n")
    wav = tmp_path / "a.wav"
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\0\0" * 1600)
    worker = Path(__file__).resolve().parent.parent / "ai_toolbox" / "stt_worker.py"
    pytest.importorskip("numpy")
    proc = subprocess.run([sys.executable, str(worker), "m", "cpu", "int8"],
                          input=json.dumps({"wav": str(wav)}) + "\n", text=True,
                          capture_output=True, env={"PYTHONPATH": str(fake)}, timeout=30)
    lines = [json.loads(line) for line in proc.stdout.splitlines()]
    assert lines == [{"ready": True, "device": "cpu"}, {"text": "olá mundo", "language": "pt"}]



def test_selection_gives_up_when_the_owner_never_answers(monkeypatch, tmp_path):
    """An app can own the selection and never send its data; reading it must not
    hang the daemon."""
    import time

    from ai_toolbox import desktop

    fake = tmp_path / "wl-paste"
    fake.write_text("#!/bin/sh\nsleep 5\n")
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{tmp_path}:/usr/bin")
    monkeypatch.setattr(desktop, "SELECTION_TIMEOUT_S", 0.2)

    started = time.monotonic()
    assert desktop.selection() == ""
    assert desktop.clipboard() == ""
    assert time.monotonic() - started < 2
