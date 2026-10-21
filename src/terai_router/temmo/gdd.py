"""Temmo Game Design Doc (GDD): prompt, parsing, validation and repair.

The GDD is the contract between the language model and the runtime. Whatever a provider
returns, ``repair`` turns it into a GDD the runtime can play: >= 3 levels, every gem and the
exit reachable from the start, walls on the border, bounded enemies and timers. Each fix is
recorded in ``gdd['_repairs']`` so the report can say what the model got right and what not.
"""
from __future__ import annotations

import json
import random
import re
from collections import deque

W_MIN, W_MAX, H_MIN, H_MAX = 9, 21, 7, 15
CELLS = set("#.PGEXH")

SYSTEM = ("You are Temmo, a game designer. You design complete small indie games for a fixed "
          "top-down maze runtime. Reply with ONE JSON object and nothing else.")

PROMPT = """Design a complete game for this idea: {idea}

The runtime is a top-down grid maze: the player collects every gem, then walks to the exit door; enemies patrol;
touching an enemy costs a life; the level timer must not reach 0. Return JSON with exactly these keys:
{{"title": short English title, "title_th": Thai title, "tagline": one Thai sentence,
 "story": 2 Thai sentences, "gem_name": Thai word, "enemy_name": Thai word,
 "win_title": Thai, "win_text": one Thai sentence,
 "palette": {{"bg":"#hex","wall":"#hex","floor":"#hex","player":"#hex","gem":"#hex","enemy":"#hex","exit":"#hex"}},
 "music": {{"menu": "music prompt e.g. calm folk waltz A minor 30 seconds", "level": "music prompt e.g. rock 140 bpm E minor 30 seconds"}},
 "voice": {{"start": Thai line, "exit_open": Thai line, "level_clear": Thai line, "win": Thai line, "lose": Thai line}},
 "sprites": {{"player": short English image prompt, "enemy": ..., "gem": ..., "exit": ..., "title": ...}},
 "levels": [3 to 5 objects {{"name": Thai, "time": seconds 40-120, "enemy_every": 1-3 (higher = slower enemies),
   "grid": list of equal-length strings, 13 wide, 9 tall, using # wall . floor P start (one) G gem E enemy X exit (one) H extra life}}]}}
Make the levels get harder (more enemies, less time)."""

LEVELS_PROMPT = """Make 3 levels for the maze game "{title}" ({idea}). Reply with JSON only:
{{"levels": [{{"name": "Thai name", "time": 90, "enemy_every": 3, "grid": ["#############", "#P..#.....G.#", "#.#.#.###.#.#", "#.#...#E..#.#", "#.###.#.###.#", "#G....#....X#", "#############"]}}, ...]}}
Each grid: 7 to 9 strings, all the same length (11 to 15), border of #, exactly one P and one X, 3 to 6 G, 0 to 3 E.
Level 2 and 3 need more E, more G and less time. Do not repeat a row more than twice."""

# Short, one-section prompts for small local models (each asked only when that section is missing).
SECTION_PROMPTS = {
    "text": ("Game idea: {idea}\nWrite the game's names. Reply with JSON only, like this example for a different idea "
             "(a rabbit picking carrots in a snowy forest, avoiding foxes):\n"
             '{{"title": "Snow Bunny Dash", "title_th": "กระต่ายน้อยฝ่าหิมะ", "tagline": "เก็บแครอทให้ครบแล้วหนีหมาจิ้งจอกกลับบ้าน", '
             '"gem_name": "แครอท", "enemy_name": "หมาจิ้งจอก", "win_title": "กลับบ้านแล้ว!", "win_text": "กระต่ายอิ่มท้องทั้งฝูง"}}\n'
             "Now the JSON for: {idea}"),
    "palette": ("Game idea: {idea}\nPick 7 colours that fit the place in the idea. Reply with JSON only:\n"
                '{{"palette": {{"bg": "#hex", "wall": "#hex", "floor": "#hex", "player": "#hex", "gem": "#hex", "enemy": "#hex", "exit": "#hex"}}}}'),
    "names": ("Game: {title} ({idea})\nGive 3 Thai level names that get harder, about places in the idea. "
              'Reply with JSON only: {{"names": ["...", "...", "..."]}}'),
}
PROMPT_LEAK = re.compile(r"for a game about|short english|thai title|english title|image prompt|one thai sentence|"
                         r"title for|json|#hex|\.\.\.|\{|\}|<|>|^title$|^ชื่อเกม$", re.I)


def looks_like_prompt(value, idea: str = "") -> bool:
    """True when a model echoed the instructions instead of answering (e.g. 'title for a game about ...')."""
    s = str(value or "").strip()
    if not s:
        return True
    if PROMPT_LEAK.search(s):
        return True
    return bool(idea) and len(s) > 20 and s in idea and len(s) > 0.8 * len(idea)


def idea_title(idea: str) -> str:
    """Last-resort Thai title taken from the idea itself (better than a generic default)."""
    s = re.split(r"[,，.!?\n]| ", str(idea).strip())[0]
    s = re.sub(r"^(เกม|game)\s*", "", s, flags=re.I).strip()
    return s[:30] or "เท็มโม"


def missing_sections(raw, idea: str = "") -> list:
    """Which small sections still need a model call: text, palette, names (levels are handled separately)."""
    d = raw if isinstance(raw, dict) else {}
    miss = []
    if any(looks_like_prompt(d.get(k), idea) for k in ("title", "title_th", "tagline")):
        miss.append("text")
    pal = d.get("palette") if isinstance(d.get("palette"), dict) else {}
    if sum(1 for v in pal.values() if isinstance(v, str) and HEX.match(v)) < 5:
        miss.append("palette")
    lv = d.get("levels") if isinstance(d.get("levels"), list) else []
    if len([x for x in lv if isinstance(x, dict) and str(x.get("name") or "").strip()
            and not looks_like_prompt(x.get("name"), idea)]) < 3:
        miss.append("names")
    return miss


def merge_section(raw: dict, section: str, reply, idea: str = "") -> list:
    """Copy only good values from a section reply into raw. Returns the keys filled."""
    r = reply if isinstance(reply, dict) else {}
    filled = []
    if section == "text":
        for k in DEFAULT_TEXT:
            v = r.get(k)
            if isinstance(v, str) and not looks_like_prompt(v, idea) and looks_like_prompt(raw.get(k), idea):
                raw[k] = v.strip()[:160]
                filled.append(k)
    elif section == "palette":
        pal = r.get("palette") if isinstance(r.get("palette"), dict) else r
        good = {k: v for k, v in pal.items() if k in DEFAULT_PALETTE_KEYS and isinstance(v, str) and HEX.match(v)}
        if len(good) >= 5:
            raw["palette"] = dict(raw.get("palette") if isinstance(raw.get("palette"), dict) else {}, **good)
            filled.append("palette")
    elif section == "names":
        names = [str(n).strip()[:40] for n in (r.get("names") or []) if isinstance(n, str) and not looks_like_prompt(n, idea)]
        if len(names) >= 3:
            raw["level_names"] = names[:6]
            filled.append("level_names")
    return filled


DEFAULT_PALETTE_KEYS = ("bg", "wall", "floor", "player", "gem", "enemy", "exit")

DEFAULT_TEXT = {
    "title": "Temmo Maze", "title_th": "เท็มโมเมซ", "tagline": "เก็บอัญมณีให้ครบแล้วหนีออกทางประตู",
    "story": "", "gem_name": "อัญมณี", "enemy_name": "ผี", "win_title": "ชนะแล้ว!", "win_text": "คุณผ่านทุกด่าน",
}
DEFAULT_VOICE = {"start": "เริ่มได้", "exit_open": "ประตูเปิดแล้ว", "level_clear": "ผ่านด่าน", "win": "ชนะแล้ว", "lose": "เกมจบ"}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def salvage_json(text: str):
    """Recover the top-level keys of a JSON object that was cut off (e.g. the model looped and hit max_tokens).

    Walks the text once, remembers every comma at depth 1, then tries to close the object at the last one that
    parses. Returns (dict, dropped_chars) or (None, 0)."""
    start = text.find("{")
    if start == -1:
        return None, 0
    depth, in_str, esc, cuts = 0, False, False, []
    for i in range(start, len(text)):
        c = text[i]
        if in_str:
            if esc:
                esc = False
            elif c == "\\":
                esc = True
            elif c == '"':
                in_str = False
            continue
        if c == '"':
            in_str = True
        elif c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
        elif c == "," and depth == 1:
            cuts.append(i)
    for cut in reversed(cuts):
        try:
            d = json.loads(text[start:cut] + "}")
            return d, len(text) - cut
        except ValueError:
            continue
    return None, 0


def extract_json(text: str):
    """First balanced {...} object in a model reply (handles ```json fences and chatter).

    If the outer object never closes, the top-level keys are salvaged instead of returning a nested object."""
    text = re.sub(r"```(?:json)?", "", text or "")
    whole = _balanced(text, first_only=True)
    if whole is not None:
        return whole
    salvaged, _ = salvage_json(text)
    if isinstance(salvaged, dict) and len(salvaged) >= 3:
        salvaged["_salvaged"] = True
        return salvaged
    return _balanced(text)


def _balanced(text: str, first_only: bool = False):
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
                continue
            if c == '"':
                in_str = True
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    chunk = text[start:i + 1]
                    for candidate in (chunk, re.sub(r",\s*([}\]])", r"\1", chunk)):
                        try:
                            return json.loads(candidate)
                        except ValueError:
                            pass
                    break
        if first_only:
            return None
        start = text.find("{", start + 1)
    return None


def reachable(grid, start):
    h, w = len(grid), len(grid[0])
    seen, q = {start}, deque([start])
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in seen and grid[ny][nx] != "#":
                seen.add((nx, ny))
                q.append((nx, ny))
    return seen


def find(grid, ch):
    return [(x, y) for y, row in enumerate(grid) for x, c in enumerate(row) if c == ch]


def carve(grid, a, b):
    """L-shaped corridor a -> b, turning walls into floor."""
    (x, y), (tx, ty) = a, b
    while x != tx:
        x += 1 if tx > x else -1
        if grid[y][x] == "#":
            grid[y][x] = "."
    while y != ty:
        y += 1 if ty > y else -1
        if grid[y][x] == "#":
            grid[y][x] = "."


def procedural_level(index: int, seed: int, w: int = 13, h: int = 9):
    """Maze by randomized DFS with extra loops; used when a model grid cannot be repaired."""
    rng = random.Random(seed * 1000 + index)
    g = [["#"] * w for _ in range(h)]
    stack, g[1][1] = [(1, 1)], "."
    while stack:
        x, y = stack[-1]
        nbrs = [(x + dx, y + dy, dx, dy) for dx, dy in ((2, 0), (-2, 0), (0, 2), (0, -2))
                if 0 < x + dx < w - 1 and 0 < y + dy < h - 1 and g[y + dy][x + dx] == "#"]
        if not nbrs:
            stack.pop()
            continue
        nx, ny, dx, dy = rng.choice(nbrs)
        g[y + dy // 2][x + dx // 2] = g[ny][nx] = "."
        stack.append((nx, ny))
    for _ in range(w * h // 8):  # loops so enemies can be avoided
        x, y = rng.randrange(1, w - 1), rng.randrange(1, h - 1)
        g[y][x] = "."
    floor = [(x, y) for y in range(1, h - 1) for x in range(1, w - 1) if g[y][x] == "."]
    rng.shuffle(floor)
    g[1][1] = "P"
    far = sorted(floor, key=lambda p: -(abs(p[0] - 1) + abs(p[1] - 1)))
    ex = far[0]
    g[ex[1]][ex[0]] = "X"
    spots = [p for p in floor if p != ex and abs(p[0] - 1) + abs(p[1] - 1) > 3]
    for p in spots[:4 + index]:
        g[p[1]][p[0]] = "G"
    for p in spots[4 + index:4 + index + 1 + index]:
        g[p[1]][p[0]] = "E"
    return ["".join(r) for r in g]


def repair_grid(raw, notes: list, index: int, seed: int):
    if not isinstance(raw, list) or not raw or not all(isinstance(r, str) for r in raw):
        notes.append(f"level {index + 1}: no usable grid -> procedural maze")
        return procedural_level(index, seed)
    rows = ["".join(c if c in CELLS else "." for c in r.replace(" ", ".")) for r in raw if r.strip()]
    w = max(len(r) for r in rows)
    if len(rows) < H_MIN - 2 or w < W_MIN - 2:
        notes.append(f"level {index + 1}: grid too small ({w}x{len(rows)}) -> procedural maze")
        return procedural_level(index, seed)
    rows = [r.ljust(w, "#")[:W_MAX - 2] for r in rows[:H_MAX - 2]]
    if any(len(r) != w for r in raw if r.strip()):
        notes.append(f"level {index + 1}: rows had unequal length -> padded")
    g = [list(r) for r in rows]
    # walls on the border (add a ring when the border is not already solid)
    if not (all(c == "#" for c in g[0] + g[-1]) and all(r[0] == "#" and r[-1] == "#" for r in g)):
        g = [["#"] * (len(g[0]) + 2)] + [["#"] + r + ["#"] for r in g] + [["#"] * (len(g[0]) + 2)]
        notes.append(f"level {index + 1}: added border wall")
    inner = [(x, y) for y in range(1, len(g) - 1) for x in range(1, len(g[0]) - 1)]
    for ch, label in (("P", "start"), ("X", "exit")):
        spots = find(g, ch)
        for x, y in spots[1:]:
            g[y][x] = "."
        if not spots:
            free = [p for p in inner if g[p[1]][p[0]] in ".#"]
            p = free[0] if ch == "P" else free[-1]
            g[p[1]][p[0]] = ch
            notes.append(f"level {index + 1}: missing {label} -> placed")
    if not find(g, "G"):
        free = [p for p in inner if g[p[1]][p[0]] == "."]
        for p in free[len(free) // 3::max(1, len(free) // 4)][:3]:
            g[p[1]][p[0]] = "G"
        notes.append(f"level {index + 1}: no gems -> placed 3")
    enemies = find(g, "E")
    for x, y in enemies[6:]:
        g[y][x] = "."
    if len(enemies) > 6:
        notes.append(f"level {index + 1}: {len(enemies)} enemies -> capped at 6")
    start = find(g, "P")[0]
    for x, y in enemies[:6]:  # never spawn an enemy next to the start
        if abs(x - start[0]) + abs(y - start[1]) <= 2:
            g[y][x] = "."
            notes.append(f"level {index + 1}: enemy too close to start -> removed")
    carved = 0
    for target in find(g, "G") + find(g, "X"):
        if target not in reachable(g, start):
            carve(g, start, target)
            carved += 1
    if carved:
        notes.append(f"level {index + 1}: {carved} gem/exit unreachable -> carved corridor")
    return ["".join(r) for r in g]


def repair(raw, idea: str, seed: int = 1) -> dict:
    notes: list = []
    d = raw if isinstance(raw, dict) else {}
    if not d:
        notes.append("reply was not JSON -> all defaults")
    out = {"id": re.sub(r"[^a-z0-9]+", "-", str(d.get("title") or idea).lower()).strip("-")[:40] or "temmo", "seed": seed, "idea": idea}
    for k, v in DEFAULT_TEXT.items():
        val = d.get(k)
        ok = isinstance(val, (str, int, float)) and str(val).strip() and not looks_like_prompt(val, idea)
        out[k] = str(val).strip()[:160] if ok else v
        if out[k] is v and k in ("title", "title_th", "tagline"):
            notes.append(f"{k}: missing or prompt-like -> fallback")
    if out["title_th"] is DEFAULT_TEXT["title_th"]:
        out["title_th"] = idea_title(idea)
    if out["title"] is DEFAULT_TEXT["title"]:
        out["title"] = out["title_th"]
    pal = d.get("palette") if isinstance(d.get("palette"), dict) else {}
    out["palette"] = {k: v for k, v in pal.items() if isinstance(v, str) and HEX.match(v)}
    mus = d.get("music") if isinstance(d.get("music"), dict) else {}
    out["music"] = {"menu": str(mus.get("menu") or "calm folk waltz 30 seconds")[:120],
                    "level": str(mus.get("level") or "rock 140 bpm 30 seconds")[:120], "seed": seed}
    voice = d.get("voice") if isinstance(d.get("voice"), dict) else {}
    out["voice"] = {k: str(voice.get(k) or v)[:80] for k, v in DEFAULT_VOICE.items()}
    spr = d.get("sprites") if isinstance(d.get("sprites"), dict) else {}
    hints = {"player": f"hero of {out['title']}", "enemy": out["enemy_name"], "gem": out["gem_name"], "exit": "exit door",
             "title": out["title"]}
    out["sprites"] = {k: str(spr.get(k) if spr.get(k) and not looks_like_prompt(spr.get(k), idea) else hints[k])[:120]
                      for k in hints}
    out["sprites"]["title"] = out["title"][:120]  # the title card shows the game's real title, never a prompt
    names = [n for n in (d.get("level_names") or []) if isinstance(n, str)]
    levels = d.get("levels") if isinstance(d.get("levels"), list) else []
    fixed = []
    for i, lv in enumerate(levels[:6]):
        lv = lv if isinstance(lv, dict) else {}
        try:
            t = int(float(lv.get("time", 90)))
        except (TypeError, ValueError):
            t = 90
        try:
            every = int(float(lv.get("enemy_every", 2)))
        except (TypeError, ValueError):
            every = 2
        fixed.append({"name": str(lv.get("name") or f"ด่าน {i + 1}")[:40], "time": max(40, min(180, t)),
                      "enemy_every": max(1, min(4, every)), "grid": repair_grid(lv.get("grid"), notes, i, seed)})
    while len(fixed) < 3:
        i = len(fixed)
        notes.append(f"level {i + 1}: missing -> procedural maze")
        fixed.append({"name": f"ด่าน {i + 1}", "time": 100 - 15 * i, "enemy_every": max(1, 3 - i), "grid": procedural_level(i, seed)})
    for i, lv in enumerate(fixed):  # thematic names from the names call replace generic or prompt-like ones
        generic = re.fullmatch(r"(ด่าน|level)\s*\d+", lv["name"], re.I) or looks_like_prompt(lv["name"], idea)
        if generic and i < len(names):
            lv["name"] = names[i].strip()[:40]
        elif generic:
            lv["name"] = f"ด่าน {i + 1}"
    out["levels"] = fixed
    out["_repairs"] = notes
    return out


def check(gdd: dict) -> list:
    """Hard rules for a 'full game' GDD. Empty list = passes."""
    errs = []
    if len(gdd.get("levels", [])) < 3:
        errs.append("fewer than 3 levels")
    for i, lv in enumerate(gdd.get("levels", [])):
        g = lv["grid"]
        if len({len(r) for r in g}) != 1:
            errs.append(f"level {i + 1}: ragged grid")
            continue
        if len(find(g, "P")) != 1 or len(find(g, "X")) != 1:
            errs.append(f"level {i + 1}: needs exactly one P and one X")
            continue
        r = reachable(g, find(g, "P")[0])
        if any(t not in r for t in find(g, "G") + find(g, "X")):
            errs.append(f"level {i + 1}: unreachable gem/exit")
        if not find(g, "G"):
            errs.append(f"level {i + 1}: no gems")
    return errs
