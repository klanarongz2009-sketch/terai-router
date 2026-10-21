"""Temmo code mode: the model writes the game rules and the game code itself.

idea -> model writes window.TemmoGame (rules + init/update/draw) -> static check -> sandboxed HTML5 harness
-> headless playtest (loads, input changes the game, a bot reaches win or lose) -> repair or retry -> template
fallback (the maze pipeline) only when every attempt fails.

Sandbox: the generated code runs inside <iframe sandbox="allow-scripts"> (opaque origin: no cookies,
localStorage, sessionStorage or indexedDB; no top navigation, popups or forms) with a CSP of
default-src 'none' (no fetch, XHR, WebSocket, EventSource, images or fonts from anywhere). A static check
rejects network, storage, DOM and eval APIs before the code is ever loaded, and the playtest fails a game
that makes any request.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .providers import ProviderError, make, resolve_roles

MECHANICS = ["dodge", "collect", "shooter", "catch", "breakout", "platformer", "snake", "maze", "rhythm",
             "puzzle", "racing", "clicker", "other"]

SYSTEM = """You write a tiny complete HTML5 canvas game in plain JavaScript. Reply with JavaScript only, no prose.
Define exactly one object:
window.TemmoGame = {
  title: 'short title',
  mechanic: 'one of: """ + ", ".join(MECHANICS) + """',
  rules: ['rule 1', 'rule 2', 'how to win', 'how to lose'],
  init: function (s, W, H, rnd) { /* put every game variable on s */ },
  update: function (s, input, dt, rnd) { /* input.left, input.right, input.up, input.down, input.action are true/false; dt is seconds */ },
  draw: function (ctx, s, W, H) { /* draw with the 2D canvas context ctx, shapes and text only */ }
};
Rules for the code:
- The player controls something with the input. Make the game fit the idea.
- The game must end: set s.over = 'win' when the player wins and s.over = 'lose' when the player loses. Keep s.score as a number.
- One round lasts 5 to 60 seconds, for example win at a target score or by surviving a timer. The player starts safe:
  the round must not end in the first seconds, and winning needs the player to do something.
- W and H are the canvas size (480 x 360) and can be used in every function. Call rnd() for random numbers (0 to 1); rnd is a function argument, not a field of s.
- Write helper functions inside the function that uses them (function spawn() { ... }) and call them directly.
- No network, no storage, no document, no eval, no setTimeout, no images. Under 100 lines."""

PROMPT = "Game idea: {idea}\nWrite the game now. Write the title and rules in {lang}."

REPAIR = ("This game failed the automatic playtest.\nProblem: {error}\n{hint}\nCode:\n{code}\n\n"
          "Return the whole fixed game (JavaScript only, same window.TemmoGame format and rules).")

FORBIDDEN = re.compile(r"\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|eval|importScripts|localStorage|sessionStorage|"
                       r"indexedDB|cookie|document|location|navigator|postMessage|Worker|setTimeout|setInterval|"
                       r"opener|top\.|parent\.|window\.open)\b|\b(?:Image|Audio|Function|import)\s*\(|<\s*/?\s*script")

CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; "
       "connect-src 'none'; form-action 'none'")


def lang_of(idea: str) -> str:
    return "Thai" if re.search(r"[\u0e00-\u0e7f]", idea or "") else "English"


def extract_game(text: str) -> str:
    t = text or ""
    m = re.search(r"```(?:js|javascript)?\s*(.*?)```", t, re.S)
    code = (m.group(1) if m else t.replace("```javascript", "").replace("```js", "").replace("```", "")).strip()
    i = code.find("window.TemmoGame")
    if i > 0:
        code = code[i:]
    return code.strip()


HINTS = [("is not a function", "Hint: define that helper as a local function inside init/update and call it directly."),
         ("is not defined", "Hint: every variable must live on s (set it in init) or be declared with var/let."),
         ("forbidden API", "Hint: remove that call completely; update() is already called every frame for you."),
         ("under 2 seconds", "Hint: the round ends at once. Only set s.over after the player has had a fair chance."),
         ("never reached", "Hint: set s.over = 'lose' when the player fails and s.over = 'win' at a goal or timer."),
         ("already over", "Hint: do not set s.over in init."),
         ("no input changes", "Hint: read input.left/right/up/down/action in update and move the player with them."),
         ("painted nothing", "Hint: fill the background and draw the player with ctx.fillRect using numbers set in init.")]


def hint_for(error: str) -> str:
    return next((h for k, h in HINTS if k in (error or "")), "")


def static_check(code: str) -> str | None:
    if "window.TemmoGame" not in code:
        return "missing window.TemmoGame = { ... }"
    m = FORBIDDEN.search(code)
    if m:
        return f"uses a forbidden API: {m.group(0)} (no network, storage, document, timers or eval)"
    if len(code) > 12000:
        return "code is too long (over 12000 characters)"
    node = shutil.which("node")
    if node:
        p = subprocess.run([node, "--check", "-"], input=code, capture_output=True, text=True, timeout=30)
        if p.returncode:
            lines = [x for x in p.stderr.strip().splitlines() if x.strip()]
            msg = next((x for x in lines if "Error" in x), lines[-1] if lines else "error")
            return "JavaScript syntax error: " + msg[:200]
    return None


# ---------------- harness ----------------

INNER = r"""<!doctype html><html><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="__CSP__">
<style>html,body{margin:0;background:#0b0d10;color:#dde;font:14px system-ui;text-align:center}
canvas{display:block;margin:6px auto;max-width:100vw;background:#111;touch-action:none}
#pad button{font:18px system-ui;width:56px;height:44px;margin:2px;border-radius:8px;border:1px solid #445;background:#1a1d24;color:#dde}</style>
</head><body><canvas id="c" width="480" height="360"></canvas>
<div id="pad"><button data-k="left">&#9664;</button><button data-k="up">&#9650;</button><button data-k="down">&#9660;</button><button data-k="right">&#9654;</button><button data-k="action">A</button></div>
<script>
var W = 480, H = 360;  /* small models often use W and H outside init */
window.TEMMO_ERRORS = [];
/* helpers the model put on TemmoGame (spawn: function () {...}) are often called as s.spawn(); give s a copy */
window.TEMMO_NEWSTATE = function (G) { var s = {score: 0, over: null};
  for (var k in G) if (typeof G[k] === 'function' && k !== 'init' && k !== 'update' && k !== 'draw') s[k] = G[k];
  return s; };
window.TEMMO_RNG = function (seed) { var a = seed >>> 0; return function () { a = (a + 0x6D2B79F5) | 0; var t = Math.imul(a ^ (a >>> 15), 1 | a);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; };
</script>
<script>
try {
__GAME__
} catch (e) { window.TEMMO_ERRORS.push('load: ' + e); }
</script>
<script>
(function () {
  var G = window.TemmoGame, cv = document.getElementById('c'), ctx = cv.getContext('2d'), W = cv.width, H = cv.height;
  var TH = __THAI__, input = {left: false, right: false, up: false, down: false, action: false};
  var keys = {ArrowLeft: 'left', ArrowRight: 'right', ArrowUp: 'up', ArrowDown: 'down', a: 'left', d: 'right', w: 'up', s: 'down', ' ': 'action', Enter: 'action', z: 'action'};
  var st = null, screen = 'menu', last = 0, err = null, rnd = null;
  function start() { var seed = (Date.now() & 0xffff) + 1; rnd = TEMMO_RNG(seed); Math.random = rnd; st = TEMMO_NEWSTATE(G);
    try { G.init(st, W, H, rnd); screen = 'play'; } catch (e) { err = 'init: ' + e; TEMMO_ERRORS.push(err); } }
  function text(t, y, size) { ctx.fillStyle = '#fff'; ctx.font = (size || 16) + 'px system-ui'; ctx.textAlign = 'center'; ctx.fillText(t, W / 2, y); }
  function menu() { ctx.fillStyle = '#0b0d10'; ctx.fillRect(0, 0, W, H); text(G && G.title || 'Temmo', 60, 28);
    ((G && G.rules) || []).slice(0, 6).forEach(function (r, i) { text(String(r).slice(0, 60), 110 + i * 26, 15); });
    text(TH ? 'กดปุ่มใดก็ได้เพื่อเริ่ม' : 'Press any key or tap to start', H - 30, 16); }
  function frame(t) {
    var dt = Math.min(0.05, last ? (t - last) / 1000 : 1 / 60); last = t;
    if (err) { ctx.fillStyle = '#300'; ctx.fillRect(0, 0, W, H); text(err.slice(0, 70), H / 2, 13); }
    else if (screen === 'menu' || !G) menu();
    else {
      try { if (screen === 'play') G.update(st, input, dt, rnd); ctx.save(); G.draw(ctx, st, W, H); ctx.restore(); }
      catch (e) { err = 'runtime: ' + e; TEMMO_ERRORS.push(err); }
      ctx.fillStyle = '#fff'; ctx.font = '14px system-ui'; ctx.textAlign = 'left'; ctx.fillText((TH ? 'คะแนน ' : 'Score ') + Math.round(+st.score || 0), 8, 18);
      if (st.over === 'win' || st.over === 'lose') { screen = 'end'; ctx.fillStyle = 'rgba(0,0,0,.6)'; ctx.fillRect(0, H / 2 - 40, W, 80);
        text(st.over === 'win' ? (TH ? 'ชนะ!' : 'You win!') : (TH ? 'แพ้' : 'Game over'), H / 2, 26);
        text(TH ? 'กดเพื่อเล่นใหม่' : 'Press to play again', H / 2 + 26, 14); }
    }
    requestAnimationFrame(frame);
  }
  function press(k, on) { if (on && screen !== 'play') { start(); return; } if (k) input[k] = on; }
  addEventListener('keydown', function (e) { press(keys[e.key], true); e.preventDefault(); });
  addEventListener('keyup', function (e) { if (keys[e.key]) input[keys[e.key]] = false; });
  cv.addEventListener('pointerdown', function () { if (screen !== 'play') start(); else input.action = true; });
  cv.addEventListener('pointerup', function () { input.action = false; });
  Array.prototype.forEach.call(document.querySelectorAll('#pad button'), function (b) {
    b.addEventListener('pointerdown', function (e) { press(b.dataset.k, true); e.preventDefault(); });
    b.addEventListener('pointerup', function () { input[b.dataset.k] = false; });
    b.addEventListener('pointerleave', function () { input[b.dataset.k] = false; }); });
  window.TEMMO_HARNESS = {screen: function () { return screen; }, state: function () { return st; }};
  requestAnimationFrame(frame);
})();
</script></body></html>"""

OUTER = """<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>html,body{{margin:0;height:100%;background:#0b0d10}}iframe{{border:0;width:100%;height:100%}}
.credit{{position:fixed;bottom:2px;right:6px;color:#667;font:11px system-ui}}</style></head>
<body><iframe id="game" sandbox="allow-scripts" srcdoc="{srcdoc}"></iframe>
<div class="credit">Rules and code written by {model} with Temmo (TER-AI). MIT.</div></body></html>
"""


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def inner_html(code: str, thai: bool) -> str:
    return (INNER.replace("__CSP__", CSP).replace("__THAI__", "true" if thai else "false")
            .replace("__GAME__", code.replace("</script", "<\\/script")))


def write_game(code: str, out: Path, name: str, thai: bool, title: str = "Temmo game", model: str = "Gemma 4") -> Path:
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{name}.js").write_text(code, encoding="utf-8")
    page = OUTER.format(lang="th" if thai else "en", title=_esc(title), model=_esc(model), srcdoc=_esc(inner_html(code, thai)))
    path = out / f"{name}.html"
    path.write_text(page, encoding="utf-8")
    return path


def title_of(code: str) -> str:
    m = re.search(r"title\s*:\s*(['\"`])(.*?)\1", code)
    return m.group(2)[:80] if m else "Temmo game"


SYNONYMS = {"paddle": "breakout", "bricks": "breakout", "avoid": "dodge", "survival": "dodge", "shoot": "shooter",
            "shooting": "shooter", "jump": "platformer", "runner": "platformer", "endless runner": "platformer",
            "collecting": "collect", "catching": "catch", "race": "racing", "click": "clicker", "tap": "clicker"}


def mechanic_of(code: str) -> str:
    m = re.search(r"mechanic\s*:\s*(['\"`])(.*?)\1", code)
    v = (m.group(2).strip().lower() if m else "")
    v = SYNONYMS.get(v, v)
    return v if v in MECHANICS else ("other" if v else "unknown")


# ---------------- playtest ----------------

def playtest(html: Path, timeout: float = 120.0) -> dict:
    """Run codetest in a child process so a game stuck in an endless loop cannot hang Temmo."""
    t0 = time.time()
    try:
        py = os.environ.get("TEMMO_PLAYTEST_PYTHON") or sys.executable  # a Python with playwright + Chromium
        p = subprocess.run([py, "-m", "terai_router.temmo.codetest", str(html)], capture_output=True, text=True,
                           timeout=timeout, cwd=str(Path(__file__).resolve().parents[2]))
        lines = [x for x in p.stdout.strip().splitlines() if x.startswith("{")]
        res = json.loads(lines[-1]) if lines else {"passed": False, "error": "playtest crashed: " + p.stderr.strip()[-300:]}
    except subprocess.TimeoutExpired:
        res = {"passed": False, "error": f"the game froze (no answer in {int(timeout)} s); check for endless loops"}
    res["seconds"] = round(time.time() - t0, 1)
    return res


# ---------------- build ----------------

def _complete(provider, system, prompt, max_tokens, seed):
    try:
        return provider.complete(system, prompt, max_tokens, seed=seed)
    except TypeError:
        return provider.complete(system, prompt, max_tokens)


def build(idea: str, out: str | Path, provider: str = "local", seed: int = 1, attempts: int = 3, max_tokens: int = 2000,
          fallback: bool = True, fallback_kwargs: dict | None = None, model: str = "") -> dict:
    """Generate, check, playtest and repair. Returns a report; report['engine'] is 'code' or 'template'."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    name = resolve_roles({"code": provider})["code"]
    prov = make(name, model=model)
    thai = lang_of(idea) == "Thai"
    rep = {"idea": idea, "provider": name, "attempts": [], "engine": None, "passed": False}
    code, error, gen_seed = "", None, seed
    for i in range(attempts):
        t = time.time()
        if i == 0 or not code or (error or "").startswith("missing window.TemmoGame") or i % 2 == 0:
            kind, gen_seed = "generate", seed + i
            prompt = PROMPT.format(idea=idea, lang=lang_of(idea))
        else:
            kind = "repair"
            prompt = REPAIR.format(error=error, code=code[:6000], hint=hint_for(error))
        try:
            reply = _complete(prov, SYSTEM, prompt, max_tokens, gen_seed + 100 * i)
        except ProviderError as e:
            rep["attempts"].append({"kind": kind, "error": f"provider: {e}", "seconds": round(time.time() - t, 1)})
            error = None
            continue
        (out / f"reply_{i + 1}.txt").write_text(reply, encoding="utf-8")
        code = extract_game(reply)
        error = static_check(code)
        info = {"kind": kind, "gen_seconds": round(time.time() - t, 1), "chars": len(code)}
        if not error:
            html = write_game(code, out, f"attempt_{i + 1}", thai, title_of(code))
            test = playtest(html)
            info["test"] = test
            error = None if test.get("passed") else test.get("error") or "playtest failed"
        info["error"] = error
        info["seconds"] = round(time.time() - t, 1)
        rep["attempts"].append(info)
        print(f"[temmo code] attempt {i + 1} {kind}: {'PASS' if not error else error[:160]}", file=sys.stderr, flush=True)
        if not error:
            title = title_of(code)
            final = write_game(code, out, "game", thai, title, model=getattr(prov, "model", name) or name)
            rep.update(engine="code", passed=True, html=str(final), title=title, mechanic=mechanic_of(code),
                       lines=code.count("\n") + 1, test=info["test"])
            break
    if not rep["passed"] and fallback:
        from .pipeline import build as template_build
        kw = dict(voice=False, screenshots=False)
        kw.update(fallback_kwargs or {})
        try:
            tr = template_build(idea, out / "template", roles={"design": name, "code": name, "repair": name, "review": name},
                                seed=seed, **kw)
            t = tr.get("test") or {}
            rep.update(engine="template", passed=bool(t.get("passed", not kw.get("test", True))), html=tr["build"]["html"],
                       title=tr["gdd"]["title"], mechanic="maze", fallback_reason=error)
        except Exception as e:  # the template path must never take the whole run down
            rep.update(engine="template", passed=False, mechanic="maze", fallback_reason=error,
                       fallback_error=f"{type(e).__name__}: {str(e)[:200]}")
    rep["seconds"] = round(time.time() - t0, 1)
    (out / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    return rep
