"""Temmo 1.0: provider contract tests (no network, no keys), GDD repair, mod checks, assembly."""
import base64
import json
import zipfile

import pytest

from terai_router.temmo import gdd, providers as P
from terai_router.temmo.pipeline import assemble, check_mod, extract_js

FAKE = {k: "test-key-123" for k in set(P.ENV_KEYS.values())}


# ---------- contract: request shape + response parsing for every BYOK provider ----------

def test_anthropic_contract():
    p = P.make("anthropic", env=FAKE)
    r = p.build_request("sys", "hi", 100)
    assert r.url == "https://api.anthropic.com/v1/messages"
    assert r.headers["x-api-key"] == "test-key-123" and r.headers["anthropic-version"] == "2023-06-01"
    assert r.body["system"] == "sys" and r.body["messages"] == [{"role": "user", "content": "hi"}]
    assert r.body["max_tokens"] == 100 and r.body["model"] == P.DEFAULT_MODELS["anthropic"]
    assert p.parse_response({"type": "message", "content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]}) == "ab"
    with pytest.raises(P.ProviderError):
        p.parse_response({"type": "error", "error": {"message": "bad"}})


def test_openai_contract():
    p = P.make("openai", env=FAKE)
    r = p.build_request("sys", "hi", 50)
    assert r.url == "https://api.openai.com/v1/chat/completions"
    assert r.headers["Authorization"] == "Bearer test-key-123"
    assert r.body["messages"][0] == {"role": "system", "content": "sys"} and r.body["max_completion_tokens"] == 50
    assert p.parse_response({"choices": [{"message": {"content": "ok"}}]}) == "ok"
    with pytest.raises(P.ProviderError):
        p.parse_response({"error": {"message": "quota"}})


def test_deepseek_contract():
    p = P.make("deepseek", env=FAKE)
    r = p.build_request("sys", "hi", 50)
    assert r.url == "https://api.deepseek.com/chat/completions"
    assert r.body["max_tokens"] == 50 and "max_completion_tokens" not in r.body
    assert r.body["model"] == "deepseek-chat"
    assert p.parse_response({"choices": [{"message": {"content": "x"}}]}) == "x"


def test_gemini_chat_contract_and_2_0_flash_not_default():
    p = P.make("gemini", env=FAKE)
    assert p.model != "gemini-2.0-flash"  # shut down 2026-06-01
    r = p.build_request("sys", "hi", 64)
    assert r.url.endswith(f"/models/{p.model}:generateContent") and r.headers["x-goog-api-key"] == "test-key-123"
    assert r.body["systemInstruction"]["parts"][0]["text"] == "sys"
    assert r.body["contents"][0]["parts"][0]["text"] == "hi"
    assert p.parse_response({"candidates": [{"content": {"parts": [{"text": "t1"}, {"text": "t2"}]}}]}) == "t1t2"


def test_nano_banana_contract():
    p = P.make("gemini-image", env=FAKE)
    r = p.build_request("", "a cat", 0)
    assert r.body["generationConfig"] == {"responseModalities": ["IMAGE"]}
    png = b"\x89PNG fake"
    data = {"candidates": [{"content": {"parts": [{"text": "here"}, {"inlineData": {"mimeType": "image/png", "data": base64.b64encode(png).decode()}}]}}]}
    assert p.parse_response(data) == png
    with pytest.raises(P.ProviderError):
        p.parse_response({"candidates": [{"content": {"parts": [{"text": "no image"}]}}]})


def test_no_key_never_calls_network():
    p = P.make("anthropic", env={})
    with pytest.raises(P.ProviderError, match="no key"):
        p.call("s", "p")


def test_roles_fall_back_without_keys():
    roles = P.resolve_roles(env={})
    assert roles["image"] == "sankpup" and roles["design"] == "local" and roles["chat"] == "local"
    roles = P.resolve_roles(env={"ANTHROPIC_API_KEY": "k"})
    assert roles["design"] == "anthropic" and roles["code"] == "anthropic" and roles["review"] == "local"


def test_mock_is_deterministic():
    m = P.Mock(script={"MARK": "reply"})
    assert m.complete("MARK", "x") == "reply"
    assert P.Mock().complete("s", "same") == P.Mock().complete("s", "same")


# ---------- GDD ----------

def test_extract_json_handles_fences_and_trailing_commas():
    assert gdd.extract_json('blah ```json\n{"a": [1,2,], "b": "x}"}\n``` tail') == {"a": [1, 2], "b": "x}"}
    assert gdd.extract_json("no json") is None


def test_repair_garbage_gives_playable_three_levels():
    g = gdd.repair(None, "cat game", seed=2)
    assert len(g["levels"]) == 3 and gdd.check(g) == []
    assert g["_repairs"]


def test_repair_fixes_unreachable_and_borders():
    raw = {"title": "T", "levels": [{"grid": ["P..#G", "...#.", "####X"], "time": 5, "enemy_every": 9}] * 3}
    g = gdd.repair(raw, "x")
    assert gdd.check(g) == []
    lv = g["levels"][0]
    assert lv["time"] == 40 and lv["enemy_every"] == 4
    assert all(c == "#" for c in lv["grid"][0])


def test_procedural_levels_are_valid():
    for i in range(5):
        g = {"levels": [{"grid": gdd.procedural_level(i, s)} for s in range(1, 4)]}
        assert gdd.check(g) == []


# ---------- mods ----------

def test_mod_checks():
    assert check_mod("window.TemmoMod = function (api) { api.on('gem', a => a.addScore(5)); };") is None
    assert "forbidden" in check_mod("window.TemmoMod = function (api) { fetch('x'); };")
    assert check_mod("console.log(1)") == "missing window.TemmoMod"
    assert extract_js("Sure!\n```js\nwindow.TemmoMod = function(api){}\n```").startswith("window.TemmoMod")


def test_assemble_outputs(tmp_path):
    g = gdd.repair(None, "x", 1)
    b = assemble(g, {"sprites": {}, "voice": {}}, None, tmp_path)
    html = open(b["html"], encoding="utf-8").read()
    assert "window.TEMMO_GAME" in html and "MUMLWA.setTable" in html and "<\\/script" not in html.split("window.TEMMO_GAME")[0][-50:]
    names = zipfile.ZipFile(b["zip"]).namelist()
    assert any(n.endswith("LICENSE-GPL-3.0.txt") for n in names) and any(n.endswith("engine.js") for n in names)
    data = json.loads(open(tmp_path / "game" / "game_data.js", encoding="utf-8").read().split("=", 1)[1].rstrip(";\n"))
    assert "_repairs" not in data and len(data["levels"]) == 3
