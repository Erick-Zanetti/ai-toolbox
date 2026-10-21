"""Model lists offered by the Settings dropdowns."""

import http.server
import json
import threading
import time

import pytest

from ai_toolbox import models


def _serve(handler_cls):
    server = http.server.HTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/v1"


class _Quiet(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass


def _cache(tmp_path, entries):
    path = tmp_path / "models_cache.json"
    path.write_text(json.dumps({"fetched_at": "x", "models": entries}))
    return path


LEVELS = [{"effort": "low", "description": "fast"}, {"effort": "high", "description": "deep"}]


def test_claude_offers_the_aliases_the_cli_accepts():
    assert models.CLAUDE_MODELS == ("haiku", "sonnet", "opus")
    assert models.known("claude") == ["haiku", "sonnet", "opus"]


def test_dictation_offers_the_faster_whisper_sizes():
    assert models.known("dictation") == [
        "tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"]


def test_unknown_kind_offers_nothing():
    assert models.known("mystery") == []


def test_codex_lists_visible_models_by_priority(tmp_path):
    path = _cache(tmp_path, [
        {"slug": "b", "visibility": "list", "priority": 2},
        {"slug": "hidden", "visibility": "hide", "priority": 0},
        {"slug": "a", "visibility": "list", "priority": 1},
        {"slug": "c", "visibility": "list"},
    ])
    assert models.codex_models(path) == ["a", "b", "c"]
    assert models.known("codex", codex_cache=path) == ["a", "b", "c"]


@pytest.mark.parametrize("content", ["", "{not json", "[]", '{"models": 3}',
                                     '{"models": ["x", {"slug": 4, "visibility": "list"}]}'])
def test_codex_corrupt_cache_gives_nothing(tmp_path, content):
    path = tmp_path / "models_cache.json"
    path.write_text(content)
    assert models.codex_models(path) == []


def test_codex_missing_cache_gives_nothing(tmp_path):
    assert models.codex_models(tmp_path / "nope.json") == []


def test_codex_reasoning_levels_of_the_chosen_model(tmp_path):
    path = _cache(tmp_path, [
        {"slug": "a", "visibility": "list", "supported_reasoning_levels": LEVELS},
        {"slug": "b", "visibility": "list",
         "supported_reasoning_levels": [{"effort": "medium"}, {"effort": "max"}]},
    ])
    assert models.codex_reasoning("a", path) == ["low", "high"]
    # Unknown model: every level any listed model supports.
    assert models.codex_reasoning("zzz", path) == ["low", "high", "medium", "max"]


def test_codex_reasoning_falls_back_to_the_common_levels(tmp_path):
    assert models.codex_reasoning("a", tmp_path / "nope.json") == ["low", "medium", "high", "xhigh"]
    path = _cache(tmp_path, [{"slug": "a", "visibility": "list"}])
    assert models.codex_reasoning("a", path) == ["low", "medium", "high", "xhigh"]


def test_openai_lists_server_models_with_the_key_from_its_variable(monkeypatch):
    seen = {}

    class Handler(_Quiet):
        def do_GET(self):
            seen["path"], seen["auth"] = self.path, self.headers.get("Authorization")
            body = json.dumps({"object": "list", "data": [{"id": "llama3.2"}, {"id": "qwen3"},
                                                          {"id": "llama3.2"}, {"nope": 1}]})
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body.encode())

    monkeypatch.setenv("ATB_TEST_KEY", "sekret")
    server, url = _serve(Handler)
    try:
        assert models.openai_models(url + "/", "ATB_TEST_KEY") == ["llama3.2", "qwen3"]
    finally:
        server.shutdown()
    assert seen == {"path": "/v1/models", "auth": "Bearer sekret"}


def test_openai_without_key_sends_no_authorization():
    seen = {}

    class Handler(_Quiet):
        def do_GET(self):
            seen["auth"] = self.headers.get("Authorization")
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"data": []}')

    server, url = _serve(Handler)
    try:
        assert models.openai_models(url) == []
    finally:
        server.shutdown()
    assert seen["auth"] is None


@pytest.mark.parametrize("status,body", [(500, b"boom"), (200, b"not json"), (200, b'{"data": 1}')])
def test_openai_errors_give_nothing(status, body):
    class Handler(_Quiet):
        def do_GET(self):
            self.send_response(status)
            self.end_headers()
            self.wfile.write(body)

    server, url = _serve(Handler)
    try:
        assert models.openai_models(url) == []
    finally:
        server.shutdown()


def test_openai_server_down_or_no_url_gives_nothing():
    server, url = _serve(_Quiet)
    server.server_close()  # nothing listens on that port any more
    assert models.openai_models(url) == []
    assert models.openai_models("") == []
    assert models.openai_models("file:///etc") == []


def test_openai_slow_server_gives_up_after_the_timeout():
    class Handler(_Quiet):
        def do_GET(self):
            time.sleep(1)

    server, url = _serve(Handler)
    try:
        start = time.monotonic()
        assert models.openai_models(url, timeout=0.2) == []
        assert time.monotonic() - start < 0.9
    finally:
        server.shutdown()


def test_options_keep_the_configured_value_even_when_unknown():
    assert models.options("sonnet", ["haiku", "sonnet"]) == ["haiku", "sonnet"]
    assert models.options("my-model", ["haiku", "haiku"]) == ["haiku", "my-model"]
    assert models.options("", ["haiku"]) == ["haiku"]
    assert models.options(None, []) == []


def test_catalog_fetches_a_server_once_and_answers_every_asker():
    calls, answers, release = [], [], threading.Event()

    def fetch(base_url, api_key_env=None):
        calls.append((base_url, api_key_env))
        release.wait(2)
        return ["m1"]

    posted = threading.Event()

    def post(fn):
        fn()
        posted.set()

    catalog = models.Catalog(post=post, fetch=fetch)
    provider = {"type": "openai", "base_url": "http://x/v1", "api_key_env": "K"}
    catalog.request("ollama", provider, answers.append)
    catalog.request("ollama", provider, answers.append)
    release.set()
    assert posted.wait(2)
    deadline = time.monotonic() + 2
    while len(answers) < 2 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert answers == [["m1"], ["m1"]]
    assert calls == [("http://x/v1", "K")]

    catalog.request("ollama", provider, answers.append)  # cached now: answers at once
    assert answers[-1] == ["m1"] and len(calls) == 1


def test_catalog_answers_cli_kinds_at_once(tmp_path):
    answers = []
    catalog = models.Catalog(post=lambda fn: fn(), codex_cache=_cache(
        tmp_path, [{"slug": "a", "visibility": "list"}]))
    catalog.request("claude", {}, answers.append)
    catalog.request("work", {"type": "codex"}, answers.append)
    assert answers == [["haiku", "sonnet", "opus"], ["a"]]
