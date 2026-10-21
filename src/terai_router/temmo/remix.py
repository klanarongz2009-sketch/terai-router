"""Temmo remix: small, safe edits to a finished game (text, levels, colours). MIT.

A remix never rewrites code. It returns a *patch* limited to ALLOWED fields, validated here, so a
community game can be remixed by a small free model (local Gemma) or, with no model at all, by the
rule engine below. The same rules run in the browser (docs/temmo/community.js).
"""
from __future__ import annotations

import copy
import json
import re

TEXT_FIELDS = ("title", "title_th", "tagline", "win_title", "win_text", "gem_name", "enemy_name")
PALETTE_KEYS = ("bg", "wall", "floor", "player", "gem", "enemy", "exit")
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

COLORS = {
    "แดง": "#e53935", "red": "#e53935", "ส้ม": "#fb8c00", "orange": "#fb8c00", "เหลือง": "#fdd835",
    "yellow": "#fdd835", "เขียว": "#43a047", "green": "#43a047", "ฟ้า": "#4fc3f7", "sky": "#4fc3f7",
    "น้ำเงิน": "#1e3a8a", "blue": "#1e88e5", "ม่วง": "#8e24aa", "purple": "#8e24aa", "ชมพู": "#f06292",
    "pink": "#f06292", "ดำ": "#0b0d10", "black": "#0b0d10", "ขาว": "#f5f5f5", "white": "#f5f5f5",
    "น้ำตาล": "#6d4c41", "brown": "#6d4c41", "เทา": "#607d8b", "grey": "#607d8b", "gray": "#607d8b",
}
PARTS = {
    "พื้นหลัง": "bg", "background": "bg", "bg": "bg", "กำแพง": "wall", "wall": "wall", "พื้น": "floor",
    "floor": "floor", "ผู้เล่น": "player", "ตัวละคร": "player", "player": "player", "ไอเทม": "gem",
    "ของ": "gem", "gem": "gem", "ศัตรู": "enemy", "enemy": "enemy", "ประตู": "exit", "exit": "exit",
    # v0.13: "enemies" and "door" ("walls", "gems"... already start with a part word)
    "enemies": "enemy", "door": "exit",
}
# longest first so "พื้นหลัง" wins over "พื้น"
_PART_WORDS = sorted(PARTS, key=len, reverse=True)
_COLOR_WORDS = sorted(COLORS, key=len, reverse=True)
# a clause break between two words: "pink background, blue walls" pairs inside each clause
_SEP = re.compile(r"[,;.!?\n&+]|(?:^|[^a-z])(?:and|then)(?:[^a-z]|$)|และ|แล้ว")
MAX_LEVELS = 10

AI_SYSTEM = ("You edit small maze games. Reply with ONE JSON object (a patch) and nothing else. Allowed keys: "
             "title, title_th, tagline, win_title, win_text, gem_name, enemy_name (strings), "
             "palette (object of bg/wall/floor/player/gem/enemy/exit -> #rrggbb), "
             "time_delta (integer seconds added to every level, -30..30), enemy_speed (\"faster\" or \"slower\"), "
             "add_levels (integer 1..3: add mirrored copies of existing levels, max 10 levels in total).")
AI_PROMPT = "Game: {title} ({title_th}) - {tagline}\nPalette: {palette}\nPlayer request: {instruction}\nPatch JSON:"


def clean_text(v, limit: int = 80) -> str:
    s = re.sub(r"[<>{}`\\]", "", str(v)).strip()
    return re.sub(r"\s+", " ", s)[:limit]


def _tokens(low: str) -> list:
    """Part and colour words, left to right (longest word first at each position)."""
    toks, i = [], 0
    while i < len(low):
        w = next((w for w in _PART_WORDS if low.startswith(w, i)), None)
        kind, table = ("part", PARTS) if w else ("color", COLORS)
        if not w:
            w = next((c for c in _COLOR_WORDS if low.startswith(c, i)), None)
        if w:
            toks.append({"kind": kind, "val": table[w], "en": w.isascii(), "start": i, "end": i + len(w), "used": False})
            i += len(w)
            continue
        i += 1
    return toks


def _palette(low: str) -> dict:
    """Thai order and "background pink" (part, then colour) work as before v0.13: each part word takes the
    first colour word after it. English order ("pink background", "blue walls") is read only for English
    words: a colour right before a part word in the same clause, when that part has no colour yet."""
    t = _tokens(low)

    def sep(a, b):
        return bool(_SEP.search(low[a["end"]:b["start"]]))

    def en_part(j, after):
        return j < len(t) and t[j]["kind"] == "part" and t[j]["en"] and not t[j]["used"] and not sep(after, t[j])

    pal: dict = {}
    part, pi = None, -1
    for j, tok in enumerate(t):
        if tok["kind"] == "part":
            if not tok["used"]:
                part, pi = tok, j
            continue
        if part is None:
            continue
        if tok["en"] and part["en"]:
            prev = t[pi - 1] if pi > 0 else None
            claimed = bool(prev and prev["kind"] == "color" and prev["en"] and not prev["used"] and not sep(prev, part))
            if (sep(part, tok) or claimed) and en_part(j + 1, tok):
                nxt = t[j + 1]  # "pink background, blue walls": blue goes to walls, not background
                pal[nxt["val"]] = tok["val"]
                tok["used"] = nxt["used"] = True
                part = None
                continue
        pal[part["val"]] = tok["val"]
        tok["used"] = part["used"] = True
        part = None
    for j, tok in enumerate(t):  # English order: colour, then its part
        if tok["kind"] == "color" and tok["en"] and not tok["used"] and en_part(j + 1, tok) and t[j + 1]["val"] not in pal:
            pal[t[j + 1]["val"]] = tok["val"]
            tok["used"] = t[j + 1]["used"] = True
    return pal


def _add_levels(low: str) -> int:
    m = re.search(r"(?:add|plus)\s+(\d+)\s+(?:more\s+|extra\s+|new\s+)?levels?|(\d+)\s+(?:more|extra|new)\s+levels?", low)
    if m:
        return int(m.group(1) or m.group(2))
    if re.search(r"(?:more|extra|add|new)\s+levels", low):
        return 2
    if re.search(r"(?:one more|another|an extra|add an?|extra|new)\s+level", low):
        return 1
    return 0


def rule_patch(instruction: str) -> dict:
    """Free, offline remix: colour words, a new title, easier/harder."""
    s = str(instruction or "").strip()
    low = s.lower()
    patch: dict = {}
    m = re.search(r"(?:ชื่อ(?:เกม)?|title)\s*[:=]?\s*[\"“']?([^\"”'\n]{1,60})", s, re.I)
    if m and m.group(1).strip():
        name = clean_text(m.group(1), 60)
        patch["title_th" if re.search(r"[\u0e00-\u0e7f]", name) else "title"] = name
    m = re.search(r"(?:คำโปรย|tagline)\s*[:=]?\s*[\"“']?([^\"”'\n]{1,100})", s, re.I)
    if m:
        patch["tagline"] = clean_text(m.group(1), 100)
    pal = _palette(low)
    if pal:
        patch["palette"] = pal
    if re.search(r"ง่ายขึ้น|ง่ายลง|easier|เวลาเพิ่ม|more time", low):
        patch["time_delta"], patch["enemy_speed"] = 20, "slower"
    elif re.search(r"ยากขึ้น|harder|เวลาน้อยลง|less time", low):
        patch["time_delta"], patch["enemy_speed"] = -15, "faster"
    if re.search(r"faster enem|enem[a-z]* (?:move |are |go )?faster|speed up (?:the )?enem|quicker enem", low):
        patch["enemy_speed"] = "faster"
    elif re.search(r"slower enem|enem[a-z]* (?:move |are |go )?slower|slow down (?:the )?enem", low):
        patch["enemy_speed"] = "slower"
    n = _add_levels(low)
    if n:
        patch["add_levels"] = n
    return patch


def validate_patch(p) -> dict:
    if not isinstance(p, dict):
        return {}
    out: dict = {}
    for k in TEXT_FIELDS:
        if isinstance(p.get(k), str) and clean_text(p[k]):
            out[k] = clean_text(p[k], 100 if k in ("tagline", "win_text") else 60)
    if isinstance(p.get("palette"), dict):
        pal = {k: v.lower() for k, v in p["palette"].items() if k in PALETTE_KEYS and isinstance(v, str) and HEX.match(v)}
        if pal:
            out["palette"] = pal
    try:
        if "time_delta" in p:
            out["time_delta"] = max(-30, min(30, int(float(p["time_delta"]))))
    except (TypeError, ValueError):
        pass
    if p.get("enemy_speed") in ("faster", "slower"):
        out["enemy_speed"] = p["enemy_speed"]
    try:
        if "add_levels" in p and int(float(p["add_levels"])) >= 1:
            out["add_levels"] = min(3, int(float(p["add_levels"])))
    except (TypeError, ValueError):
        pass
    return out


def apply_patch(game: dict, patch: dict) -> dict:
    g = copy.deepcopy(game)
    patch = validate_patch(patch)
    for k in TEXT_FIELDS:
        if k in patch:
            g[k] = patch[k]
    if "palette" in patch:
        g["palette"] = dict(g.get("palette") or {}, **patch["palette"])
    levels = g.get("levels")
    if patch.get("add_levels") and isinstance(levels, list) and levels:
        orig = len(levels)
        for k in range(patch["add_levels"]):  # a new level = an earlier one, mirrored left to right
            if len(levels) >= MAX_LEVELS:
                break
            lv = copy.deepcopy(levels[k % orig])
            lv["grid"] = [str(row)[::-1] for row in lv.get("grid") or []]
            lv["name"] = str(lv.get("name") or "Level") + " (mirror)"
            levels.append(lv)
    for lv in g.get("levels") or []:
        if "time_delta" in patch:
            lv["time"] = max(40, min(180, int(lv.get("time", 90)) + patch["time_delta"]))
        if "enemy_speed" in patch:
            step = 1 if patch["enemy_speed"] == "slower" else -1
            lv["enemy_every"] = max(1, min(4, int(lv.get("enemy_every", 2)) + step))
    g["remix_of"] = game.get("remix_of") or game.get("id")
    return g


def ai_patch(game: dict, instruction: str, provider) -> dict:
    from .gdd import extract_json
    prompt = AI_PROMPT.format(title=game.get("title", ""), title_th=game.get("title_th", ""), tagline=game.get("tagline", ""),
                              palette=json.dumps(game.get("palette", {})), instruction=clean_text(instruction, 200))
    return validate_patch(extract_json(provider.complete(AI_SYSTEM, prompt, 300)))


def remix(game: dict, instruction: str, provider=None) -> tuple[dict, dict, str]:
    """Return (new game, patch, source). The rule engine fills in whatever the model left out."""
    rules = validate_patch(rule_patch(instruction))
    patch, source = {}, "rules"
    if provider is not None and getattr(provider, "name", "") != "mock":
        try:
            patch = ai_patch(game, instruction, provider)
            source = "ai" if patch else "rules"
        except Exception:  # model down -> rules only
            patch = {}
    merged = dict(rules, **patch)
    if "palette" in rules and "palette" in patch:
        merged["palette"] = dict(rules["palette"], **patch["palette"])
    if patch and rules and set(rules) - set(patch):
        source = "ai+rules"
    return apply_patch(game, merged), merged, source


GAME_LINE = re.compile(r"^window\.TEMMO_GAME = (.*);$", re.M)


def read_game(html: str) -> dict:
    m = GAME_LINE.search(html)
    if not m:
        raise ValueError("not a Temmo single-file game")
    return json.loads(m.group(1))


def write_game(html: str, game: dict) -> str:
    """Swap the game data inside a single-file game (the share/export step)."""
    read_game(html)
    body = json.dumps(game, ensure_ascii=False).replace("</script", "<\\/script")
    html = GAME_LINE.sub(lambda _m: "window.TEMMO_GAME = " + body + ";", html, count=1)
    t = clean_text(game.get("title", "Temmo"), 60)
    return re.sub(r"<title>.*?</title>", f"<title>{t}</title>", html, count=1, flags=re.S)
