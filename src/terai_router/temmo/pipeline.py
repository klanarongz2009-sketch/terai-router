"""Temmo pipeline: idea -> GDD -> tasks -> code -> assets -> assembled game -> headless test -> fix loop."""
from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

from . import gdd as gddmod
from .providers import ProviderError, make, resolve_roles

HERE = Path(__file__).resolve().parent
RUNTIME = HERE / "runtime"
DOCS = HERE.parents[2] / "docs"

MOD_SYSTEM = ("You write small JavaScript mods for the Temmo maze runtime. Reply with JavaScript only, no prose. "
              "Define exactly: window.TemmoMod = function (api) { ... }. Available: api.on(event, fn) with events "
              "'levelStart','gem','step','hit'; api.state -> {screen, level, score, lives, gems, steps}; "
              "api.addScore(n); api.addTime(seconds); api.toast(text). No network, no DOM, no eval, under 40 lines.")
MOD_PROMPT = ("Game: {title} - {tagline}. Write a mod that adds one fun rule that fits the theme, for example a "
              "combo bonus when gems are collected quickly, or a time bonus on each level start. Thai text for toasts.")
REPAIR_PROMPT = ("This Temmo mod failed the automatic test with: {error}\n\nMod:\n{code}\n\nReturn the fixed mod "
                 "(JavaScript only, same rules).")
FORBIDDEN = re.compile(r"\b(fetch|XMLHttpRequest|WebSocket|eval|Function\s*\(|import\s*\(|document\.cookie|localStorage|location\s*=)")


def log(report, stage, **info):
    info = dict(stage=stage, t=round(time.time() - report["_t0"], 2), **info)
    report["stages"].append(info)
    print(f"[temmo] {stage}: " + json.dumps({k: v for k, v in info.items() if k not in ('stage',)}, ensure_ascii=False)[:300],
          file=sys.stderr, flush=True)


def extract_js(text: str) -> str:
    m = re.search(r"```(?:js|javascript)?\s*(.*?)```", text or "", re.S)
    code = (m.group(1) if m else text or "").strip()
    i = code.find("window.TemmoMod")
    return code[i:] if i > 0 else code


def check_mod(code: str) -> str | None:
    if "window.TemmoMod" not in code:
        return "missing window.TemmoMod"
    if FORBIDDEN.search(code):
        return "uses a forbidden API: " + FORBIDDEN.search(code).group(0)
    if len(code) > 4000:
        return "too long"
    node = shutil.which("node")
    if node:
        p = subprocess.run([node, "--check", "-"], input=code, capture_output=True, text=True, timeout=30)
        if p.returncode:
            return "syntax: " + (p.stderr.strip().splitlines() or ["error"])[-1][:200]
    return None


def ask(report, out: Path, key: str, provider, system: str, prompt: str, max_tokens: int, replay: bool) -> str:
    """Call a provider, keeping the raw reply in out/replies/<key>.txt. With replay=True a saved reply is
    reused (no new model call) and the report marks the stage as replayed."""
    d = out / "replies"
    d.mkdir(exist_ok=True)
    f = d / f"{key}.txt"
    if replay and f.exists():
        report.setdefault("replayed", []).append(key)
        return f.read_text(encoding="utf-8")
    text = provider.complete(system, prompt, max_tokens)
    f.write_text(text, encoding="utf-8")
    return text


# ---------------- assets ----------------

def make_sprites(g: dict, roles: dict, report: dict) -> dict:
    out = {}
    prov = None if roles["image"] in ("sankpup",) else make(roles["image"])
    from terai_router import sankpup
    for i, (name, prompt) in enumerate(g["sprites"].items()):
        size = 512 if name == "title" else 128
        png, engine = None, "sankpup-offline"
        if prov is not None:
            try:
                png, engine = prov.call("Game sprite, plain background, centered.", prompt), roles["image"]
            except ProviderError as e:
                report["warnings"].append(f"image provider failed for {name}: {e}; using SANKPUP")
        if png is None:
            art = sankpup.generate(prompt, engine="offline", seed=g["seed"] * 10 + i)
            png = art.to_bytes("png", size)
        out[name] = "data:image/png;base64," + base64.b64encode(png).decode()
        report["assets"].append({"kind": "sprite", "name": name, "engine": engine, "bytes": len(png)})
    return out


def make_voice(g: dict, work: Path, report: dict) -> dict:
    """TTH lines (Wayu local engine). Needs a Python with kokoro: $TEMMO_TTH_PYTHON or this one."""
    py = os.environ.get("TEMMO_TTH_PYTHON") or sys.executable
    src = str(HERE.parents[1])
    lines = {k: v for k, v in g["voice"].items()}
    jobs = [(k, v, str(work / f"voice_{k}.mp3")) for k, v in lines.items()]
    code = ("import sys,json; sys.path.insert(0,%r); from terai_router import tth; "
            "r=[]\nfor k,t,o in json.load(sys.stdin):\n    tth.speak(t,o,voice='f_young_clear')\n    r.append(k)\nprint(json.dumps(r))") % src
    try:
        p = subprocess.run([py, "-c", code], input=json.dumps(jobs), capture_output=True, text=True, timeout=900)
        if p.returncode:
            raise RuntimeError(p.stderr.strip()[-300:])
    except Exception as e:  # voice is optional; the game still has SFX + music
        report["warnings"].append(f"TTH voice skipped: {e}")
        return {}
    out = {}
    for k, _t, o in jobs:
        if Path(o).exists():
            b = Path(o).read_bytes()
            out[k] = "data:audio/mpeg;base64," + base64.b64encode(b).decode()
            report["assets"].append({"kind": "voice", "name": k, "engine": "TTH", "bytes": len(b), "text": lines[k]})
    return out


# ---------------- assemble ----------------

INDEX = """<!doctype html>
<html lang="th"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>html,body{{margin:0;background:{bg};height:100%}}body{{display:flex;align-items:center;justify-content:center}}
canvas{{max-width:100vw;max-height:100vh;aspect-ratio:4/3;touch-action:none;image-rendering:pixelated}}
.credit{{position:fixed;bottom:2px;right:6px;color:#667;font:11px system-ui}}</style></head>
<body><canvas id="temmo" width="720" height="540"></canvas>
<div class="credit">Made with Temmo 1.0 (TER-AI). Music data: GPL-3.0, see LICENSES.txt</div>
{scripts}
</body></html>
"""
SCRIPT_ORDER = ["muml_wa_table.js", "muml_wa.js", "music_init.js", "game_data.js", "mod.js", "engine.js"]


def assemble(g: dict, assets: dict, mod_code: str | None, out: Path) -> dict:
    game = out / "game"
    if game.exists():
        shutil.rmtree(game)
    game.mkdir(parents=True)
    data = {k: v for k, v in g.items() if not k.startswith("_")}
    data["assets"] = assets
    files = {
        "muml_wa_table.js": (DOCS / "muml_wa_table.js").read_text(encoding="utf-8"),
        "muml_wa.js": (DOCS / "muml_wa.js").read_text(encoding="utf-8"),
        "music_init.js": "if (window.MUMLWA && window.MUML_WA_TABLE) MUMLWA.setTable(window.MUML_WA_TABLE);\n",
        "game_data.js": "window.TEMMO_GAME = " + json.dumps(data, ensure_ascii=False) + ";\n",
        "mod.js": (mod_code or "/* no mod */") + "\n",
        "engine.js": (RUNTIME / "engine.js").read_text(encoding="utf-8"),
    }
    for name, body in files.items():
        (game / name).write_text(body, encoding="utf-8")
    shutil.copy(DOCS / "LICENSE-GPL-3.0.txt", game / "LICENSE-GPL-3.0.txt")
    (game / "LICENSES.txt").write_text(
        "Game code (engine.js, game_data.js, mod.js, index.html): MIT, made with Temmo 1.0 / TER-AI.\n"
        "muml_wa.js: MIT (TER-AI MuML 1.0 WA).\n"
        "muml_wa_table.js: GPL-3.0-only data built from the Nottingham Music Database "
        "(jukedeck/nottingham-dataset, commit 0992bb6c). Full text: LICENSE-GPL-3.0.txt.\n"
        "Voice: TTH (Wayu-Paxa-TTS-Edge weights, CC-BY-NC-4.0, credit Paxa Labs): non-commercial use only.\n", encoding="utf-8")
    bg = g.get("palette", {}).get("bg", "#0b0d10")
    tags = "\n".join(f'<script src="{n}"></script>' for n in SCRIPT_ORDER)
    (game / "index.html").write_text(INDEX.format(title=g["title"], bg=bg, scripts=tags), encoding="utf-8")
    inline = "\n".join("<script>\n" + files[n].replace("</script", "<\\/script") + "\n</script>" for n in SCRIPT_ORDER)
    single = out / f"{g['id']}.html"
    single.write_text(INDEX.format(title=g["title"], bg=bg, scripts=inline), encoding="utf-8")
    zpath = out / f"{g['id']}.zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(game.iterdir()):
            z.write(f, f"{g['id']}/{f.name}")
    return {"dir": str(game), "html": str(single), "zip": str(zpath), "html_bytes": single.stat().st_size,
            "zip_bytes": zpath.stat().st_size}


# ---------------- main entry ----------------

def build(idea: str, out: str | Path, roles: dict | None = None, seed: int = 1, test: bool = True,
          max_fix_rounds: int = 3, voice: bool = True, mod: bool = True, screenshots: bool = True,
          replay: bool = False) -> dict:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    roles = resolve_roles(roles)
    report = {"idea": idea, "roles": roles, "stages": [], "assets": [], "warnings": [], "_t0": time.time()}
    providers = {}

    def prov(role):
        name = roles[role]
        if name not in providers:
            providers[name] = make(name)
        return providers[name]

    # 1. design (GDD)
    t = time.time()
    try:
        raw_text = ask(report, out, "design", prov("design"), gddmod.SYSTEM, gddmod.PROMPT.format(idea=idea), 2500, replay)
    except Exception as e:  # provider down -> defaults; the report says so
        raw_text = ""
        report["warnings"].append(f"design provider failed: {e}")
    (out / "design_raw.txt").write_text(raw_text, encoding="utf-8")
    raw = gddmod.extract_json(raw_text)
    levels_from = "design"
    json_ok = raw is not None
    raw = raw if isinstance(raw, dict) else {}
    if not isinstance(raw.get("levels"), list):
        # small models often loop inside the grids; ask for the levels alone (a shorter job)
        try:
            lt = ask(report, out, "levels", prov("design"), gddmod.SYSTEM, gddmod.LEVELS_PROMPT.format(
                idea=idea, title=raw.get("title", idea)), 1200, replay)
            lj = gddmod.extract_json(lt)
            lv = lj.get("levels") if isinstance(lj, dict) else (lj if isinstance(lj, list) else None)
            if isinstance(lv, list):
                raw["levels"], levels_from = lv, "levels call"
        except Exception as e:
            report["warnings"].append(f"levels call failed: {e}")
    # 1b. small models often skip sections or echo the prompt: ask again only for what is missing
    fills = {}
    for sec in gddmod.missing_sections(raw, idea):
        title = raw.get("title") if not gddmod.looks_like_prompt(raw.get("title"), idea) else idea
        for attempt in (1, 2):
            try:
                st = ask(report, out, f"fill_{sec}_{attempt}", prov("design"), gddmod.SYSTEM,
                         gddmod.SECTION_PROMPTS[sec].format(idea=idea, title=title), 400, replay)
                got = gddmod.merge_section(raw, sec, gddmod.extract_json(st), idea)
            except Exception as e:
                report["warnings"].append(f"fill {sec} attempt {attempt} failed: {e}")
                got = []
            if got:
                fills[sec] = attempt
                break
        else:
            fills[sec] = 0
    report["fills"] = fills
    g = gddmod.repair(raw, idea, seed)
    log(report, "design", provider=roles["design"], seconds=round(time.time() - t, 1), json_ok=json_ok, fills=fills, salvaged=bool(isinstance(raw, dict) and raw.get("_salvaged")), levels_from=levels_from,
        reply_chars=len(raw_text), repairs=g["_repairs"], levels=len(g["levels"]))

    # 2. review (second opinion; only when it is a different provider)
    if roles["review"] != roles["design"]:
        try:
            rv = prov("review").complete("You review game design docs. Reply with JSON {\"issues\": [short strings]}.",
                                         json.dumps({k: g[k] for k in ('title', 'tagline', 'levels')}, ensure_ascii=False), 800)
            log(report, "review", provider=roles["review"], issues=(gddmod.extract_json(rv) or {}).get("issues"))
        except Exception as e:
            report["warnings"].append(f"review skipped: {e}")
    else:
        log(report, "review", skipped="same provider as design")

    # 3. tasks
    tasks = ["game_data.js (GDD + levels)", "engine.js (runtime)", "mod.js (provider code)"] + \
            [f"sprite:{k}" for k in g["sprites"]] + [f"voice:{k}" for k in g["voice"]] + \
            ["music: MuML WA menu + level", "assemble zip + single html", "headless test with bot"]
    log(report, "tasks", count=len(tasks), tasks=tasks)

    # 4. code (mod written by the code provider, checked, repaired)
    mod_code, mod_info = None, {"attempts": []}
    if mod:
        try:
            t = time.time()
            code = extract_js(ask(report, out, "mod", prov("code"), MOD_SYSTEM, MOD_PROMPT.format(**g), 700, replay))
            err = check_mod(code)
            mod_info["attempts"].append({"provider": roles["code"], "error": err, "seconds": round(time.time() - t, 1)})
            if err:
                t = time.time()
                code = extract_js(ask(report, out, "mod_repair", prov("repair"), MOD_SYSTEM,
                                      REPAIR_PROMPT.format(error=err, code=code), 700, replay))
                err = check_mod(code)
                mod_info["attempts"].append({"provider": roles["repair"], "error": err, "seconds": round(time.time() - t, 1)})
            mod_code = None if err else code
            (out / "mod_candidate.js").write_text(code, encoding="utf-8")
        except Exception as e:
            report["warnings"].append(f"mod skipped: {e}")
    log(report, "code", mod_kept=mod_code is not None, **mod_info)

    # 5. assets
    t = time.time()
    assets = {"sprites": make_sprites(g, roles, report)}
    if voice:
        assets["voice"] = make_voice(g, out, report)
    log(report, "assets", seconds=round(time.time() - t, 1), count=len(report["assets"]))

    # 6+7. assemble, test, fix loop
    result = None
    for rnd in range(max_fix_rounds + 1):
        built = assemble(g, assets, mod_code, out)
        if not test:
            break
        from .bottest import run as run_test
        result = run_test(built["html"], out, screenshots=screenshots and rnd == 0 or screenshots)
        log(report, "test", round=rnd, **{k: v for k, v in result.items() if k != "shots"})
        if result["passed"]:
            break
        # fix: a mod that throws is dropped first; then the level the bot failed gets easier
        if mod_code and any("mod" in e for e in result["errors"]):
            mod_code = None
            report["warnings"].append("mod removed after runtime error")
            continue
        lv = g["levels"][min(result.get("level", 0), len(g["levels"]) - 1)]
        lv["enemy_every"] = min(4, lv["enemy_every"] + 1)
        lv["time"] = min(180, lv["time"] + 30)
        grid = [list(r) for r in lv["grid"]]
        es = gddmod.find(grid, "E")
        if es and rnd >= 1:
            x, y = es[-1]
            grid[y][x] = "."
            lv["grid"] = ["".join(r) for r in grid]
        g["_repairs"].append(f"test round {rnd}: level {result.get('level', 0) + 1} made easier")
    report["gdd_check"] = gddmod.check(g)
    report["build"] = built
    report["test"] = result
    report["gdd"] = {k: v for k, v in g.items()}
    report["seconds"] = round(time.time() - report.pop("_t0"), 1)
    report["provider_calls"] = {n: p.calls for n, p in providers.items()}
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report
