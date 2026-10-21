"""Headless Chromium test for a Temmo game: opens, no errors, menu, bot plays every level, high score saved."""
from __future__ import annotations

import time
from pathlib import Path


def _click_canvas(page, x, y):
    box = page.locator("#temmo").bounding_box()
    page.mouse.click(box["x"] + x * box["width"] / 720, box["y"] + y * box["height"] / 540)


def run(html_path: str, out: Path, timeout: float = 180.0, screenshots: bool = True) -> dict:
    from playwright.sync_api import sync_playwright
    url = Path(html_path).resolve().as_uri()
    res = {"passed": False, "errors": [], "checks": {}}
    t0 = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required"])
        page = browser.new_page(viewport={"width": 960, "height": 720})
        page.on("pageerror", lambda e: res["errors"].append("pageerror: " + str(e)))
        page.on("console", lambda m: m.type == "error" and res["errors"].append("console: " + m.text))
        page.goto(url + "?bot=1&fast=1")
        page.wait_for_function("window.TEMMO && TEMMO.state.screen === 'menu'", timeout=15000)
        res["checks"]["load_seconds"] = round(time.time() - t0, 2)
        res["checks"]["menu"] = True
        info = page.evaluate("""() => ({levels: TEMMO_GAME.levels.length, music: !!(window.MUMLWA && MUMLWA.generate),
            voice: Object.keys((TEMMO_GAME.assets||{}).voice||{}).length, sprites: Object.keys((TEMMO_GAME.assets||{}).sprites||{}).length,
            mod: typeof window.TemmoMod === 'function'})""")
        res["checks"].update(info)
        if screenshots:
            page.wait_for_timeout(400)
            page.screenshot(path=str(out / "shot_menu.png"))
        _click_canvas(page, 360, 262)  # Start button (a real click, so audio may start)
        page.wait_for_function("TEMMO.state.screen !== 'menu'", timeout=5000)
        res["checks"]["start_click"] = True
        try:
            page.wait_for_function("['victory','gameover'].includes(TEMMO.state.screen)", timeout=timeout * 1000)
        except Exception:
            res["errors"].append("timeout: bot did not finish")
        st = page.evaluate("TEMMO.state")
        res.update(result=st.get("result"), cleared=st.get("cleared"), score=st.get("score"), lives=st.get("lives"),
                   steps=st.get("totalSteps"), level=st.get("cleared", 0))
        saved = page.evaluate("TEMMO.store.get()")
        res["checks"]["highscore_saved"] = bool(saved.get("scores"))
        res["checks"]["progress_saved"] = saved.get("unlocked", 0)
        res["errors"] += [e for e in page.evaluate("window.__temmoErrors") if e not in res["errors"]]
        if screenshots:
            page.screenshot(path=str(out / "shot_end.png"))
            # gameplay frame at normal speed
            page2 = browser.new_page(viewport={"width": 960, "height": 720})
            page2.goto(url + "?bot=1")
            page2.wait_for_function("window.TEMMO && TEMMO.state.screen === 'menu'", timeout=15000)
            _click_canvas(page2, 360, 262)
            page2.wait_for_timeout(2500)
            page2.screenshot(path=str(out / "shot_play.png"))
        browser.close()
    res["seconds"] = round(time.time() - t0, 1)
    res["passed"] = (not res["errors"] and res.get("result") == "win" and res.get("cleared") == res["checks"].get("levels")
                     and res["checks"]["highscore_saved"])
    return res
