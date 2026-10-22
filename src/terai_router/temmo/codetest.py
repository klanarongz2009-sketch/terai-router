"""Headless playtest for a Temmo code-mode game (run as a child process by codegen.playtest).

Pass = the page loads with no errors and no network requests, window.TemmoGame has the right shape,
init/update/draw run, the canvas is not blank, at least one input changes the game, the round does not end
before it starts, and a bot (random and held-key policies, 3 seeds, up to 90 s of game time each) reaches a
win or lose state. Every check is stepped by hand with a fixed dt, so the test is deterministic and fast.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PROBE = r"""() => {
  var R = {errors: (window.TEMMO_ERRORS || []).slice(), checks: {}};
  var G = window.TemmoGame;
  if (!G || typeof G !== 'object') { R.error = 'window.TemmoGame is not defined (the code did not run)'; return R; }
  var miss = ['init', 'update', 'draw'].filter(function (k) { return typeof G[k] !== 'function'; });
  if (miss.length) { R.error = 'window.TemmoGame is missing functions: ' + miss.join(', '); return R; }
  R.checks.rules = Array.isArray(G.rules) ? G.rules.length : 0;
  var cv = document.createElement('canvas'); cv.width = 480; cv.height = 360; var ctx = cv.getContext('2d');
  var W = 480, H = 360, DT = 1 / 30, KEYS = ['left', 'right', 'up', 'down', 'action'];
  function fresh(seed) { var r = TEMMO_RNG(seed); Math.random = r; var s = window.TEMMO_NEWSTATE ? TEMMO_NEWSTATE(G) : {score: 0, over: null}; G.init(s, W, H, r); return {s: s, r: r}; }
  function inp(o) { var x = {left: false, right: false, up: false, down: false, action: false}; for (var k in o) x[k] = o[k]; return x; }
  function snap(s) { try { return JSON.stringify(s, function (k, v) { return typeof v === 'number' ? Math.round(v * 100) / 100 : v; }); } catch (e) { return String(Math.random()); } }
  var g;
  try { g = fresh(1); } catch (e) { R.error = 'init threw: ' + e; return R; }
  if (g.s.over) { R.error = 'the game is already over right after init (s.over = ' + g.s.over + ')'; return R; }
  try { G.update(g.s, inp({}), DT, g.r); ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H); G.draw(ctx, g.s, W, H); }
  catch (e) { R.error = 'update/draw threw: ' + e; return R; }
  var d = ctx.getImageData(0, 0, W, H).data, colors = {};
  for (var i = 0; i < d.length; i += 4 * 97) colors[d[i] + ',' + d[i + 1] + ',' + d[i + 2]] = 1;
  R.checks.colors = Object.keys(colors).length;
  var bad = []; (function walk(o, path, depth) { if (depth > 3 || !o || typeof o !== 'object') return;
    Object.keys(o).slice(0, 60).forEach(function (k) { var v = o[k]; if (typeof v === 'number' && isNaN(v)) bad.push(path + k);
      else if (v && typeof v === 'object') walk(v, path + k + '.', depth + 1); }); })(g.s, 's.', 0);
  if (bad.length) R.checks.nan = bad.slice(0, 8);
  if (R.checks.colors < 2) { R.error = 'draw() painted nothing visible on the canvas' + (bad.length ? '; these values are NaN (a field used before it was set in init?): ' + bad.slice(0, 8).join(', ') : '; check that every x, y, width and height you draw is set in init'); return R; }
  // input: hold one key for 1.5 s and compare with no input from the same seed
  function run(seed, policy, steps) {
    var g = fresh(seed), t = 0, cur = {};
    for (var n = 0; n < steps; n++) {
      if (policy === 'random') { if (n % 8 === 0) { cur = {}; var k = KEYS[Math.floor(g.r() * 6)]; if (k) cur[k] = true; if (g.r() < 0.3) cur.action = true; } }
      else if (policy === 'zigzag') { cur = {}; cur[(Math.floor(n / 20) % 2) ? 'left' : 'right'] = true; cur.action = n % 4 === 0; }
      else if (policy !== 'none') { cur = {}; cur[policy] = true; }
      G.update(g.s, inp(cur), DT, g.r); t += DT;
      if (n % 30 === 0) G.draw(ctx, g.s, W, H);
      if (g.s.over) break;
    }
    return {s: g.s, t: Math.round(t * 10) / 10, over: g.s.over || null};
  }
  var base, changed = [];
  try { base = snap(run(7, 'none', 45).s); KEYS.forEach(function (k) { if (snap(run(7, k, 45).s) !== base) changed.push(k); }); }
  catch (e) { R.error = 'the game threw while playing: ' + e; return R; }
  R.checks.input_keys = changed;
  if (!changed.length) { R.error = 'no input changes the game: holding left, right, up, down or action for 1.5 s leaves the state the same'; return R; }
  var ends = {}, longest = 0, plays = [];
  try {
    ['random', 'zigzag', 'none'].concat(KEYS).forEach(function (pol) { [1, 2, 3].forEach(function (seed) {
      var r = run(seed, pol, 2700); plays.push(pol + ':' + seed + '=' + (r.over || 'none') + '@' + r.t);
      if (r.over === 'win' || r.over === 'lose') ends[r.over] = (ends[r.over] || 0) + 1;
      else if (r.over) R.errors.push('s.over must be win or lose, got ' + r.over);
      longest = Math.max(longest, r.t); }); });
  } catch (e) { R.error = 'the game threw while the bot played: ' + e; return R; }
  R.checks.ends = ends; R.checks.longest_round_s = longest; R.checks.bot_runs = plays.length;
  if (!ends.win && !ends.lose) { R.error = 'the bot played 90 s per round and never reached a win or lose state (s.over is never set)'; return R; }
  if (longest < 2) { R.error = 'every round ends in under 2 seconds, so there is nothing to play'; return R; }
  return R;
}"""


def run(html_path: str) -> dict:
    from playwright.sync_api import sync_playwright
    res = {"passed": False, "errors": [], "requests": []}
    url = Path(html_path).resolve().as_uri()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 520, "height": 520})
        page.on("pageerror", lambda e: res["errors"].append("pageerror: " + str(e)))
        page.on("console", lambda m: m.type == "error" and res["errors"].append("console: " + m.text))

        def on_request(r):
            if r.url != url and not r.url.startswith(("about:", "data:")) and r.url[:120] not in res["requests"]:
                res["requests"].append(r.url[:120])
        page.on("request", on_request)
        page.goto(url)
        page.wait_for_timeout(300)
        frame = next((f for f in page.frames if f != page.main_frame), None)
        if frame is None:
            res["error"] = "sandbox frame did not load"
        else:
            frame.wait_for_function("window.TEMMO_HARNESS !== undefined || (window.TEMMO_ERRORS||[]).length > 0", timeout=10000)
            sandboxed = frame.evaluate("() => { try { localStorage.getItem('x'); return false; } catch (e) { return true; } }")
            r = frame.evaluate(PROBE)
            res["checks"] = dict(r.get("checks", {}), storage_blocked=sandboxed)
            res["errors"] += r.get("errors", [])
            res["error"] = r.get("error")
            if not res["error"]:  # a real click starts the game in the live harness
                frame.locator("#c").click()
                page.wait_for_timeout(400)
                res["checks"]["live_screen"] = frame.evaluate("() => TEMMO_HARNESS.screen()")
                res["errors"] += frame.evaluate("() => TEMMO_ERRORS")
        browser.close()
    errs = sorted(set(res["errors"]))
    res["errors"] = errs
    if not res.get("error") and errs:
        res["error"] = "errors while running: " + "; ".join(errs)[:300]
    if not res.get("error") and res["requests"]:
        res["error"] = "the game tried to use the network: " + res["requests"][0]
    if not res.get("error") and res["checks"].get("live_screen") not in ("play", "end"):
        res["error"] = "the live game did not start on a key press"
    res["passed"] = not res.get("error")
    return res


if __name__ == "__main__":
    print(json.dumps(run(sys.argv[1]), ensure_ascii=False))
