"""Temmo code mode: the model writes the rules and the code; static check, sandbox, playtest, repair, fallback."""
import importlib.util
import json

import pytest

from terai_router.temmo import codegen as C
from terai_router.temmo import providers as P

DODGE = """window.TemmoGame = {
  title: 'Dodge', mechanic: 'avoid', rules: ['Move left and right', 'Avoid the red blocks', 'Survive 20 s to win', 'A hit loses'],
  init: function (s, W, H, rnd) { s.x = W / 2; s.rocks = []; s.t = 0; },
  update: function (s, input, dt, rnd) {
    if (input.left) s.x -= 200 * dt; if (input.right) s.x += 200 * dt;
    s.x = Math.max(10, Math.min(W - 10, s.x)); s.t += dt; s.score = Math.floor(s.t);
    if (rnd() < 0.05) s.rocks.push({x: rnd() * W, y: 0});
    for (var i = 0; i < s.rocks.length; i++) { var r = s.rocks[i]; r.y += 150 * dt;
      if (Math.abs(r.x - s.x) < 15 && Math.abs(r.y - (H - 20)) < 15) s.over = 'lose'; }
    if (s.t > 20) s.over = 'win';
  },
  draw: function (ctx, s, W, H) { ctx.fillStyle = '#123'; ctx.fillRect(0, 0, W, H); ctx.fillStyle = '#0f0'; ctx.fillRect(s.x - 10, H - 30, 20, 20);
    ctx.fillStyle = '#f33'; s.rocks.forEach(function (r) { ctx.fillRect(r.x - 8, r.y - 8, 16, 16); }); }
};"""


def _browser():
    if importlib.util.find_spec("playwright") is None:
        return False
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.launch().close()
        return True
    except Exception:
        return False


HAS_BROWSER = _browser()
needs_browser = pytest.mark.skipif(not HAS_BROWSER, reason="playwright + Chromium not installed")


def test_extract_and_static_check():
    assert C.extract_game("Here you go:\n```javascript\n" + DODGE + "\n```\nEnjoy") == DODGE
    assert C.static_check(DODGE) is None
    assert "missing window.TemmoGame" in C.static_check("var x = 1;")
    for bad in ("fetch('https://x.y')", "localStorage.setItem('a', 1)", "document.body.innerHTML = ''",
                "setTimeout(f, 10)", "eval('1')", "new Image()", "new WebSocket('wss://x')", "navigator.sendBeacon('/x')",
                "indexedDB.open('x')", "window.open('x')", "</script><script>"):
        err = C.static_check("window.TemmoGame = {}; " + bad)
        assert err and "forbidden" in err, bad
    assert "syntax" in (C.static_check("window.TemmoGame = { init: function ( {") or "syntax")


def test_sandboxed_page(tmp_path):
    page = C.write_game(DODGE, tmp_path, "g", thai=True, title="Dodge <b>").read_text(encoding="utf-8")
    assert 'sandbox="allow-scripts"' in page and "allow-same-origin" not in page
    assert "Dodge &lt;b&gt;" in page and '<html lang="th">' in page
    inner = C.inner_html(DODGE, thai=False)
    assert "default-src 'none'" in inner and "connect-src 'none'" in inner
    assert DODGE in inner


def test_mechanic_and_title():
    assert C.mechanic_of(DODGE) == "dodge" and C.title_of(DODGE) == "Dodge"
    assert C.mechanic_of("mechanic: 'zzz'") == "other" and C.mechanic_of("") == "unknown"
    assert C.lang_of("แมวเก็บปลา") == "Thai" and C.lang_of("cat") == "English"


@needs_browser
def test_playtest_pass_and_fail(tmp_path):
    ok = C.playtest(C.write_game(DODGE, tmp_path, "ok", False))
    assert ok["passed"], ok
    assert ok["checks"]["storage_blocked"] is True and set(ok["checks"]["input_keys"]) >= {"left", "right"}
    assert ok["checks"]["ends"] and ok["checks"]["live_screen"] in ("play", "end")
    never = DODGE.replace("s.over = 'lose'", "s.hit = 1").replace("s.over = 'win'", "s.done = 1")
    r = C.playtest(C.write_game(never, tmp_path, "never", False))
    assert not r["passed"] and "never reached a win or lose" in r["error"]
    deaf = DODGE.replace("if (input.left) s.x -= 200 * dt; if (input.right) s.x += 200 * dt;", "")
    r = C.playtest(C.write_game(deaf, tmp_path, "deaf", False))
    assert not r["passed"] and "no input changes the game" in r["error"]
    net = DODGE.replace("s.x = W / 2;", "s.x = W / 2; try { window['fe' + 'tch']('https://example.com/x').catch(function () {}); } catch (e) {}")
    r = C.playtest(C.write_game(net, tmp_path, "net", False))
    assert not r["passed"] and "Content Security Policy" in r["error"]
    loop = C.playtest(C.write_game("window.TemmoGame = {init: function (s) {}, update: function (s) { while (true) {} }, "
                                   "draw: function (c) { c.fillStyle = '#fff'; c.fillRect(0, 0, 9, 9); }};", tmp_path, "loop", False),
                      timeout=25)
    assert not loop["passed"] and "froze" in loop["error"]


class Scripted(P.Mock):
    def __init__(self, replies):
        super().__init__()
        self.replies = list(replies)
        self.prompts = []

    def complete(self, system, prompt, max_tokens=4096):
        self.prompts.append(prompt)
        return self.replies.pop(0) if self.replies else "no code"


@needs_browser
def test_build_repairs_then_passes(tmp_path, monkeypatch):
    s = Scripted(["```js\nwindow.TemmoGame = { init: function ( {\n```", DODGE])
    monkeypatch.setattr(C, "make", lambda name, model="": s)
    rep = C.build("dodge the falling rocks", tmp_path, provider="mock", attempts=3, fallback=False)
    assert rep["passed"] and rep["engine"] == "code" and rep["mechanic"] == "dodge"
    assert [a["kind"] for a in rep["attempts"]] == ["generate", "repair"]
    assert "syntax" in rep["attempts"][0]["error"] and "failed the automatic playtest" in s.prompts[1]
    assert (tmp_path / "game.html").exists() and json.loads((tmp_path / "report.json").read_text())["engine"] == "code"


def test_build_all_attempts_fail_without_fallback(tmp_path, monkeypatch):
    s = Scripted(["sorry", "window.TemmoGame = {}; fetch('x')", "still no"])
    monkeypatch.setattr(C, "make", lambda name, model="": s)
    rep = C.build("x", tmp_path, provider="mock", attempts=3, fallback=False)
    assert not rep["passed"] and rep["engine"] is None and len(rep["attempts"]) == 3
    assert [a["kind"] for a in rep["attempts"]] == ["generate", "generate", "generate"]  # no game object: regenerate


def test_build_falls_back_to_template(tmp_path, monkeypatch):
    s = Scripted(["sorry"])
    monkeypatch.setattr(C, "make", lambda name, model="": s)
    rep = C.build("แมวเก็บปลา", tmp_path, provider="mock", attempts=1, fallback_kwargs={"test": False, "mod": False})
    assert rep["engine"] == "template" and rep["mechanic"] == "maze" and rep["fallback_reason"]
    assert (tmp_path / "template").is_dir()
