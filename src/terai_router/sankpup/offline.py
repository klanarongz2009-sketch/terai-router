"""Offline SANKPUP engine: a deterministic rule/template generator.

It turns a Thai or English prompt into SVG code with no model and no network.
The prompt is scanned against a small lexicon (subjects, colours, sizes,
numbers, relations such as "on"/"under", and scenes such as night or sea),
then a scene is laid out from hand-drawn vector templates.

The same algorithm is ported to JavaScript in ``docs/sankpup.js`` for the
GitHub Pages demo; ``tests/test_sankpup_js_parity.py`` checks that both
produce byte-identical SVG for the same prompt and seed.  Keep every change
here mirrored there: integer coordinates only, ``math.floor`` (``Math.floor``)
for rounding, fixed trig tables, and the same RNG call order.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

W = 512
GROUND_Y = 400
WATER_Y = 260
SAND_Y = 470
MAX_PROMPT = 500

# Whitespace set shared with the JS port (Python's \s and JS's \s differ).
_WS_RE = re.compile("[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+")
_WORD_CH = re.compile("[a-z0-9]")

DEFAULT_COLORS = {
    "cat": "#f76b15", "dog": "#c08552", "bird": "#3e63dd", "fish": "#f76b15",
    "butterfly": "#8e4ec6", "tree": "#30a46c", "flower": "#e93d82",
    "house": "#f5d0a9", "car": "#e5484d", "boat": "#e5484d", "rocket": "#e8e8ec",
    "robot": "#8b8d98", "sun": "#ffc53d", "moon": "#f1e7c5", "star": "#ffc53d",
    "cloud": "#f4f4f4", "mountain": "#6b7a8f", "heart": "#e5484d",
}
SKY = ("sun", "moon", "star", "cloud", "bird", "butterfly", "heart")
GROUND_SIZE = {
    "cat": 150, "dog": 150, "tree": 230, "flower": 130, "house": 220, "car": 200,
    "boat": 200, "robot": 180, "rocket": 220, "fish": 100,
}
# Offset (in units of size, from the centre) of the lowest point of a drawing.
FOOT = {"car": 0.42, "boat": 0.32, "bird": 0.2, "fish": 0.2, "cloud": 0.23, "heart": 0.4}
# Where something placed "on" this concept rests (y offset in units of size).
SURFACE = {
    "moon": -0.39, "sun": -0.24, "cloud": -0.2, "star": -0.12, "house": -0.36,
    "car": -0.16, "boat": 0.1, "tree": -0.42, "mountain": -0.4, "robot": -0.36,
    "dog": -0.1, "cat": -0.05, "rocket": -0.3, "fish": -0.12, "bird": -0.1,
    "heart": -0.25, "flower": -0.2, "butterfly": -0.1,
}
PALETTE = ("#e5484d", "#f76b15", "#ffc53d", "#30a46c", "#5eb1ef", "#3e63dd", "#8e4ec6", "#e93d82")
ABSTRACT_BG = (("#1b1145", "#3e63dd"), ("#fff1e6", "#ffd6a0"), ("#e6f6ff", "#8fd3ff"), ("#0b1d3a", "#8e4ec6"))
OPACITY = ("0.5", "0.8", "1")
# Fixed trig tables (no sin/cos at runtime, so Python and JS agree bit for bit).
COS6 = (1.0, 0.5, -0.5, -1.0, -0.5, 0.5)
SIN6 = (0.0, 0.866, 0.866, 0.0, -0.866, -0.866)
COS12 = (1.0, 0.866, 0.5, 0.0, -0.5, -0.866, -1.0, -0.866, -0.5, 0.0, 0.5, 0.866)
SIN12 = (0.0, 0.5, 0.866, 1.0, 0.866, 0.5, 0.0, -0.5, -0.866, -1.0, -0.866, -0.5)
COS10 = (0.0, 0.588, 0.951, 0.951, 0.588, 0.0, -0.588, -0.951, -0.951, -0.588)
SIN10 = (-1.0, -0.809, -0.309, 0.309, 0.809, 1.0, 0.809, 0.309, -0.309, -0.809)


@lru_cache(maxsize=1)
def lexicon() -> dict:
    path = Path(__file__).with_name("data") / "lexicon.json"
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_prompt(text: str) -> str:
    text = unicodedata.normalize("NFC", str(text))
    text = "".join(ch for ch in text if ord(ch) <= 0xFFFF)
    text = _WS_RE.sub(" ", text).strip().lower()
    return text[:MAX_PROMPT]


def fnv1a(text: str) -> int:
    h = 0x811C9DC5
    for b in text.encode("utf-8"):
        h ^= b
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


class Rng:
    """mulberry32, identical to the JS implementation."""

    def __init__(self, seed: int) -> None:
        self.a = seed & 0xFFFFFFFF

    def next(self) -> float:
        self.a = (self.a + 0x6D2B79F5) & 0xFFFFFFFF
        t = self.a
        t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
        t ^= (t + (((t ^ (t >> 7)) * (t | 61)) & 0xFFFFFFFF)) & 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    def int(self, lo: int, hi: int) -> int:
        return lo + math.floor(self.next() * (hi - lo + 1))


def shade(color: str, amt: int) -> str:
    out = "#"
    for i in (1, 3, 5):
        v = max(0, min(255, int(color[i:i + 2], 16) + amt))
        out += format(v, "02x")
    return out


def luminance(color: str) -> int:
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return (r * 299 + g * 587 + b * 114) // 1000


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ---------------------------------------------------------------- parsing

@lru_cache(maxsize=1)
def _entries() -> tuple:
    lex = lexicon()
    rows = []
    for kind in ("subjects", "colors", "relations", "sizes", "numbers"):
        for value, langs in lex[kind].items():
            for lang in ("th", "en"):
                for word in langs.get(lang, []):
                    rows.append((word, kind, value, lang))
    for lang in ("th", "en"):
        for word in lex["stop"].get(lang, []):
            rows.append((word, "stop", "", lang))
    rows.sort(key=lambda r: (-len(r[0]), r[0], r[1]))
    return tuple(rows)


def _is_word(ch: str) -> bool:
    return bool(_WORD_CH.match(ch))


def _en_end(text: str, start: int, end: int) -> int:
    """Return the match end for an English word (allowing plural s/es) or -1."""
    n = len(text)
    if start > 0 and _is_word(text[start - 1]):
        return -1
    if end < n and text[end] == "s" and (end + 1 >= n or not _is_word(text[end + 1])):
        end += 1
    elif end + 1 < n and text[end:end + 2] == "es" and (end + 2 >= n or not _is_word(text[end + 2])):
        end += 2
    if end < n and _is_word(text[end]):
        return -1
    return end


def scan(text: str) -> list:
    """Longest-match tokenizer over the lexicon (Thai needs no spaces)."""
    tokens = []
    n = len(text)
    i = 0
    entries = _entries()
    while i < n:
        ch = text[i]
        if "0" <= ch <= "9":
            j = i
            while j < n and "0" <= text[j] <= "9":
                j += 1
            v = int(text[i:j])
            if 1 <= v <= 9:
                k = i - 1
                while k >= 0 and text[k] == " ":
                    k -= 1
                lang = "th" if k >= 0 and "\u0e00" <= text[k] <= "\u0e7f" else "en"
                tokens.append({"kind": "numbers", "value": str(v), "lang": lang, "start": i, "end": j})
            i = j
            continue
        hit = None
        for word, kind, value, lang in entries:
            if text.startswith(word, i):
                end = i + len(word)
                if lang == "en":
                    end = _en_end(text, i, end)
                    if end < 0:
                        continue
                hit = {"kind": kind, "value": value, "lang": lang, "start": i, "end": end}
                break
        if hit:
            if hit["kind"] != "stop":
                tokens.append(hit)
            i = hit["end"]
        else:
            i += 1
    return tokens


def find_scenes(text: str) -> list:
    found = []
    for name, langs in lexicon()["scenes"].items():
        hit = False
        for lang in ("th", "en"):
            for word in langs.get(lang, []):
                pos = text.find(word)
                while pos >= 0 and not hit:
                    if lang == "th" or _en_end(text, pos, pos + len(word)) >= 0:
                        hit = True
                    pos = text.find(word, pos + 1)
        if hit:
            found.append(name)
    return found


def parse(text: str) -> dict:
    tokens = scan(text)
    subj = [p for p, t in enumerate(tokens) if t["kind"] == "subjects"]
    mentions = {p: {"concept": tokens[p]["value"], "color": None, "count": None, "size": None} for p in subj}

    def before(p):
        c = [q for q in subj if q < p]
        return c[-1] if c else None

    def after(p):
        c = [q for q in subj if q > p]
        return c[0] if c else None

    relations = []
    used = set()
    for p, t in enumerate(tokens):
        kind = t["kind"]
        if kind in ("colors", "numbers", "sizes"):
            if t["lang"] == "th":
                target = before(p)
                if target is None:
                    target = after(p)
            else:
                target = after(p)
                if target is None:
                    target = before(p)
            if target is None:
                continue
            key = {"colors": "color", "numbers": "count", "sizes": "size"}[kind]
            if mentions[target][key] is None:
                mentions[target][key] = int(t["value"]) if key == "count" else t["value"]
        elif kind == "relations":
            a, b = before(p), after(p)
            if a is None or b is None or a in used or b in used or len(relations) >= 2:
                continue
            relations.append({"kind": t["value"], "a": a, "b": b})
            used.add(a)
            used.add(b)
    return {
        "mentions": [dict(mentions[p], pos=p) for p in subj],
        "relations": relations,
        "scenes": find_scenes(text),
    }


# ---------------------------------------------------------------- drawing

class Pen:
    def __init__(self, cx: int, cy: int, s: int) -> None:
        self.cx, self.cy, self.s = cx, cy, s

    def x(self, f: float) -> int:
        return math.floor(self.cx + self.s * f)

    def y(self, f: float) -> int:
        return math.floor(self.cy + self.s * f)

    def l(self, f: float) -> int:
        return max(1, math.floor(self.s * f))

    def pts(self, *fs: float) -> str:
        return " ".join(f"{self.x(fs[i])},{self.y(fs[i + 1])}" for i in range(0, len(fs), 2))


INK = "#1d1d1f"


def _eye(c: str) -> str:
    return "#ffc53d" if luminance(c) < 80 else INK


def draw_cat(p: Pen, c: str) -> str:
    o = shade(c, -60)
    sw = p.l(0.012)
    e = _eye(c)
    return (
        f'<path d="M{p.x(0.2)},{p.y(0.4)} Q{p.x(0.5)},{p.y(0.35)} {p.x(0.42)},{p.y(0.05)}" fill="none" stroke="{c}" stroke-width="{p.l(0.06)}" stroke-linecap="round"/>'
        f'<ellipse cx="{p.x(0)}" cy="{p.y(0.25)}" rx="{p.l(0.28)}" ry="{p.l(0.24)}" fill="{c}" stroke="{o}" stroke-width="{sw}"/>'
        f'<ellipse cx="{p.x(0)}" cy="{p.y(0.3)}" rx="{p.l(0.14)}" ry="{p.l(0.14)}" fill="{shade(c, 40)}"/>'
        f'<polygon points="{p.pts(-0.18, -0.24, -0.13, -0.45, -0.03, -0.32)}" fill="{c}" stroke="{o}" stroke-width="{sw}"/>'
        f'<polygon points="{p.pts(0.18, -0.24, 0.13, -0.45, 0.03, -0.32)}" fill="{c}" stroke="{o}" stroke-width="{sw}"/>'
        f'<circle cx="{p.x(0)}" cy="{p.y(-0.15)}" r="{p.l(0.2)}" fill="{c}" stroke="{o}" stroke-width="{sw}"/>'
        f'<circle cx="{p.x(-0.07)}" cy="{p.y(-0.17)}" r="{p.l(0.03)}" fill="{e}"/>'
        f'<circle cx="{p.x(0.07)}" cy="{p.y(-0.17)}" r="{p.l(0.03)}" fill="{e}"/>'
        f'<polygon points="{p.pts(-0.02, -0.1, 0.02, -0.1, 0, -0.08)}" fill="#e93d82"/>'
        f'<path d="M{p.x(-0.06)},{p.y(-0.08)} L{p.x(-0.25)},{p.y(-0.11)} M{p.x(-0.06)},{p.y(-0.07)} L{p.x(-0.25)},{p.y(-0.04)} '
        f'M{p.x(0.06)},{p.y(-0.08)} L{p.x(0.25)},{p.y(-0.11)} M{p.x(0.06)},{p.y(-0.07)} L{p.x(0.25)},{p.y(-0.04)}" stroke="{o}" stroke-width="{sw}"/>'
    )


def draw_dog(p: Pen, c: str) -> str:
    d = shade(c, -50)
    e = _eye(c)
    return (
        f'<path d="M{p.x(0.28)},{p.y(0.2)} Q{p.x(0.45)},{p.y(0.05)} {p.x(0.4)},{p.y(-0.05)}" fill="none" stroke="{c}" stroke-width="{p.l(0.05)}" stroke-linecap="round"/>'
        f'<rect x="{p.x(-0.22)}" y="{p.y(0.32)}" width="{p.l(0.08)}" height="{p.l(0.18)}" fill="{d}"/>'
        f'<rect x="{p.x(0.14)}" y="{p.y(0.32)}" width="{p.l(0.08)}" height="{p.l(0.18)}" fill="{d}"/>'
        f'<ellipse cx="{p.x(0.02)}" cy="{p.y(0.25)}" rx="{p.l(0.3)}" ry="{p.l(0.17)}" fill="{c}"/>'
        f'<ellipse cx="{p.x(-0.31)}" cy="{p.y(-0.06)}" rx="{p.l(0.06)}" ry="{p.l(0.13)}" fill="{d}"/>'
        f'<ellipse cx="{p.x(0.01)}" cy="{p.y(-0.06)}" rx="{p.l(0.06)}" ry="{p.l(0.13)}" fill="{d}"/>'
        f'<circle cx="{p.x(-0.15)}" cy="{p.y(-0.1)}" r="{p.l(0.18)}" fill="{c}"/>'
        f'<ellipse cx="{p.x(-0.15)}" cy="{p.y(-0.01)}" rx="{p.l(0.09)}" ry="{p.l(0.06)}" fill="{shade(c, 50)}"/>'
        f'<circle cx="{p.x(-0.15)}" cy="{p.y(-0.05)}" r="{p.l(0.03)}" fill="{INK}"/>'
        f'<circle cx="{p.x(-0.21)}" cy="{p.y(-0.15)}" r="{p.l(0.025)}" fill="{e}"/>'
        f'<circle cx="{p.x(-0.09)}" cy="{p.y(-0.15)}" r="{p.l(0.025)}" fill="{e}"/>'
    )


def draw_bird(p: Pen, c: str) -> str:
    return (
        f'<polygon points="{p.pts(-0.25, 0, -0.5, -0.12, -0.48, 0.12)}" fill="{shade(c, -40)}"/>'
        f'<ellipse cx="{p.x(0)}" cy="{p.y(0.03)}" rx="{p.l(0.3)}" ry="{p.l(0.18)}" fill="{c}"/>'
        f'<circle cx="{p.x(0.22)}" cy="{p.y(-0.12)}" r="{p.l(0.14)}" fill="{c}"/>'
        f'<path d="M{p.x(-0.14)},{p.y(0)} Q{p.x(0.0)},{p.y(-0.32)} {p.x(0.14)},{p.y(0)} Z" fill="{shade(c, -40)}"/>'
        f'<polygon points="{p.pts(0.34, -0.16, 0.47, -0.1, 0.34, -0.06)}" fill="#ffc53d"/>'
        f'<circle cx="{p.x(0.25)}" cy="{p.y(-0.15)}" r="{p.l(0.025)}" fill="{INK}"/>'
    )


def draw_fish(p: Pen, c: str) -> str:
    return (
        f'<polygon points="{p.pts(-0.2, 0, -0.48, -0.2, -0.48, 0.2)}" fill="{shade(c, -40)}"/>'
        f'<polygon points="{p.pts(0, -0.17, 0.12, -0.3, 0.18, -0.15)}" fill="{shade(c, -40)}"/>'
        f'<ellipse cx="{p.x(0.05)}" cy="{p.y(0)}" rx="{p.l(0.35)}" ry="{p.l(0.2)}" fill="{c}"/>'
        f'<path d="M{p.x(0)},{p.y(-0.17)} Q{p.x(-0.07)},{p.y(0)} {p.x(0)},{p.y(0.17)}" fill="none" stroke="{shade(c, 70)}" stroke-width="{p.l(0.04)}"/>'
        f'<circle cx="{p.x(0.25)}" cy="{p.y(-0.04)}" r="{p.l(0.045)}" fill="#ffffff"/>'
        f'<circle cx="{p.x(0.26)}" cy="{p.y(-0.04)}" r="{p.l(0.022)}" fill="{INK}"/>'
    )


def draw_butterfly(p: Pen, c: str) -> str:
    lt = shade(c, 50)
    return (
        f'<ellipse cx="{p.x(-0.2)}" cy="{p.y(-0.14)}" rx="{p.l(0.2)}" ry="{p.l(0.24)}" fill="{c}"/>'
        f'<ellipse cx="{p.x(0.2)}" cy="{p.y(-0.14)}" rx="{p.l(0.2)}" ry="{p.l(0.24)}" fill="{c}"/>'
        f'<ellipse cx="{p.x(-0.15)}" cy="{p.y(0.17)}" rx="{p.l(0.14)}" ry="{p.l(0.17)}" fill="{lt}"/>'
        f'<ellipse cx="{p.x(0.15)}" cy="{p.y(0.17)}" rx="{p.l(0.14)}" ry="{p.l(0.17)}" fill="{lt}"/>'
        f'<circle cx="{p.x(-0.2)}" cy="{p.y(-0.17)}" r="{p.l(0.06)}" fill="#ffffff" fill-opacity="0.8"/>'
        f'<circle cx="{p.x(0.2)}" cy="{p.y(-0.17)}" r="{p.l(0.06)}" fill="#ffffff" fill-opacity="0.8"/>'
        f'<rect x="{p.x(-0.03)}" y="{p.y(-0.3)}" width="{p.l(0.06)}" height="{p.l(0.6)}" rx="{p.l(0.03)}" fill="{INK}"/>'
        f'<path d="M{p.x(0)},{p.y(-0.28)} Q{p.x(-0.05)},{p.y(-0.45)} {p.x(-0.15)},{p.y(-0.48)} M{p.x(0)},{p.y(-0.28)} Q{p.x(0.05)},{p.y(-0.45)} {p.x(0.15)},{p.y(-0.48)}" fill="none" stroke="{INK}" stroke-width="{p.l(0.015)}"/>'
    )


def draw_tree(p: Pen, c: str) -> str:
    return (
        f'<rect x="{p.x(-0.07)}" y="{p.y(0)}" width="{p.l(0.14)}" height="{p.l(0.5)}" fill="#8d5a3b"/>'
        f'<circle cx="{p.x(-0.2)}" cy="{p.y(-0.02)}" r="{p.l(0.2)}" fill="{shade(c, -20)}"/>'
        f'<circle cx="{p.x(0.2)}" cy="{p.y(-0.02)}" r="{p.l(0.2)}" fill="{shade(c, -20)}"/>'
        f'<circle cx="{p.x(0)}" cy="{p.y(-0.2)}" r="{p.l(0.3)}" fill="{c}"/>'
        f'<circle cx="{p.x(-0.08)}" cy="{p.y(-0.28)}" r="{p.l(0.1)}" fill="{shade(c, 40)}" fill-opacity="0.6"/>'
    )


def draw_flower(p: Pen, c: str) -> str:
    out = (
        f'<path d="M{p.x(0)},{p.y(0.5)} Q{p.x(0.06)},{p.y(0.2)} {p.x(0)},{p.y(-0.1)}" fill="none" stroke="#30a46c" stroke-width="{p.l(0.04)}"/>'
        f'<path d="M{p.x(0.01)},{p.y(0.27)} Q{p.x(0.2)},{p.y(0.1)} {p.x(0.27)},{p.y(0.2)} Q{p.x(0.16)},{p.y(0.31)} {p.x(0.01)},{p.y(0.27)} Z" fill="#30a46c"/>'
    )
    for i in range(6):
        out += f'<circle cx="{p.x(0.15 * COS6[i])}" cy="{p.y(-0.15 + 0.15 * SIN6[i])}" r="{p.l(0.1)}" fill="{c}"/>'
    out += f'<circle cx="{p.x(0)}" cy="{p.y(-0.15)}" r="{p.l(0.09)}" fill="#ffc53d"/>'
    return out


def draw_house(p: Pen, c: str) -> str:
    return (
        f'<rect x="{p.x(0.18)}" y="{p.y(-0.4)}" width="{p.l(0.08)}" height="{p.l(0.2)}" fill="#8b5e3c"/>'
        f'<rect x="{p.x(-0.35)}" y="{p.y(-0.06)}" width="{p.l(0.7)}" height="{p.l(0.56)}" fill="{c}" stroke="{shade(c, -60)}" stroke-width="{p.l(0.01)}"/>'
        f'<polygon points="{p.pts(-0.45, -0.05, 0, -0.45, 0.45, -0.05)}" fill="#b4442e"/>'
        f'<rect x="{p.x(-0.08)}" y="{p.y(0.2)}" width="{p.l(0.16)}" height="{p.l(0.3)}" fill="#8d5a3b"/>'
        f'<rect x="{p.x(-0.28)}" y="{p.y(0.05)}" width="{p.l(0.14)}" height="{p.l(0.12)}" fill="#bfe3ff" stroke="#ffffff" stroke-width="{p.l(0.012)}"/>'
        f'<rect x="{p.x(0.14)}" y="{p.y(0.05)}" width="{p.l(0.14)}" height="{p.l(0.12)}" fill="#bfe3ff" stroke="#ffffff" stroke-width="{p.l(0.012)}"/>'
    )


def draw_car(p: Pen, c: str) -> str:
    return (
        f'<polygon points="{p.pts(-0.3, 0.06, -0.18, -0.18, 0.18, -0.18, 0.32, 0.06)}" fill="{shade(c, -30)}"/>'
        f'<polygon points="{p.pts(-0.24, 0.04, -0.15, -0.13, -0.02, -0.13, -0.02, 0.04)}" fill="#bfe3ff"/>'
        f'<polygon points="{p.pts(0.03, 0.04, 0.03, -0.13, 0.15, -0.13, 0.25, 0.04)}" fill="#bfe3ff"/>'
        f'<rect x="{p.x(-0.48)}" y="{p.y(0.04)}" width="{p.l(0.96)}" height="{p.l(0.25)}" rx="{p.l(0.06)}" fill="{c}"/>'
        f'<circle cx="{p.x(0.44)}" cy="{p.y(0.12)}" r="{p.l(0.03)}" fill="#ffc53d"/>'
        f'<circle cx="{p.x(-0.27)}" cy="{p.y(0.3)}" r="{p.l(0.12)}" fill="{INK}"/>'
        f'<circle cx="{p.x(-0.27)}" cy="{p.y(0.3)}" r="{p.l(0.05)}" fill="#8b8d98"/>'
        f'<circle cx="{p.x(0.27)}" cy="{p.y(0.3)}" r="{p.l(0.12)}" fill="{INK}"/>'
        f'<circle cx="{p.x(0.27)}" cy="{p.y(0.3)}" r="{p.l(0.05)}" fill="#8b8d98"/>'
    )


def draw_boat(p: Pen, c: str) -> str:
    return (
        f'<rect x="{p.x(-0.015)}" y="{p.y(-0.45)}" width="{p.l(0.03)}" height="{p.l(0.56)}" fill="#8d5a3b"/>'
        f'<polygon points="{p.pts(0.03, -0.42, 0.03, 0.05, 0.36, 0.05)}" fill="#f4f4f4"/>'
        f'<polygon points="{p.pts(-0.03, -0.32, -0.03, 0.05, -0.28, 0.05)}" fill="#e8e8ec"/>'
        f'<polygon points="{p.pts(-0.45, 0.1, 0.45, 0.1, 0.32, 0.32, -0.32, 0.32)}" fill="{c}" stroke="{shade(c, -60)}" stroke-width="{p.l(0.01)}"/>'
    )


def draw_rocket(p: Pen, c: str) -> str:
    return (
        f'<polygon points="{p.pts(-0.1, 0.3, 0, 0.5, 0.1, 0.3)}" fill="#f76b15"/>'
        f'<polygon points="{p.pts(-0.05, 0.3, 0, 0.42, 0.05, 0.3)}" fill="#ffc53d"/>'
        f'<polygon points="{p.pts(-0.12, 0.08, -0.26, 0.32, -0.12, 0.28)}" fill="#e5484d"/>'
        f'<polygon points="{p.pts(0.12, 0.08, 0.26, 0.32, 0.12, 0.28)}" fill="#e5484d"/>'
        f'<path d="M{p.x(0)},{p.y(-0.48)} Q{p.x(0.19)},{p.y(-0.25)} {p.x(0.13)},{p.y(0.3)} L{p.x(-0.13)},{p.y(0.3)} Q{p.x(-0.19)},{p.y(-0.25)} {p.x(0)},{p.y(-0.48)} Z" fill="{c}" stroke="{shade(c, -70)}" stroke-width="{p.l(0.01)}"/>'
        f'<circle cx="{p.x(0)}" cy="{p.y(-0.1)}" r="{p.l(0.07)}" fill="#5eb1ef" stroke="#8b8d98" stroke-width="{p.l(0.02)}"/>'
    )


def draw_robot(p: Pen, c: str) -> str:
    d = shade(c, -40)
    return (
        f'<rect x="{p.x(-0.01)}" y="{p.y(-0.47)}" width="{p.l(0.02)}" height="{p.l(0.1)}" fill="{d}"/>'
        f'<circle cx="{p.x(0)}" cy="{p.y(-0.47)}" r="{p.l(0.03)}" fill="#e5484d"/>'
        f'<rect x="{p.x(-0.36)}" y="{p.y(-0.08)}" width="{p.l(0.1)}" height="{p.l(0.28)}" rx="{p.l(0.03)}" fill="{d}"/>'
        f'<rect x="{p.x(0.26)}" y="{p.y(-0.08)}" width="{p.l(0.1)}" height="{p.l(0.28)}" rx="{p.l(0.03)}" fill="{d}"/>'
        f'<rect x="{p.x(-0.17)}" y="{p.y(0.27)}" width="{p.l(0.12)}" height="{p.l(0.23)}" fill="{d}"/>'
        f'<rect x="{p.x(0.05)}" y="{p.y(0.27)}" width="{p.l(0.12)}" height="{p.l(0.23)}" fill="{d}"/>'
        f'<rect x="{p.x(-0.24)}" y="{p.y(-0.1)}" width="{p.l(0.48)}" height="{p.l(0.38)}" rx="{p.l(0.05)}" fill="{c}"/>'
        f'<rect x="{p.x(-0.1)}" y="{p.y(0)}" width="{p.l(0.2)}" height="{p.l(0.12)}" fill="#ffc53d"/>'
        f'<rect x="{p.x(-0.18)}" y="{p.y(-0.38)}" width="{p.l(0.36)}" height="{p.l(0.26)}" rx="{p.l(0.04)}" fill="{c}"/>'
        f'<circle cx="{p.x(-0.08)}" cy="{p.y(-0.27)}" r="{p.l(0.04)}" fill="#5eb1ef"/>'
        f'<circle cx="{p.x(0.08)}" cy="{p.y(-0.27)}" r="{p.l(0.04)}" fill="#5eb1ef"/>'
        f'<rect x="{p.x(-0.08)}" y="{p.y(-0.19)}" width="{p.l(0.16)}" height="{p.l(0.03)}" fill="{INK}"/>'
    )


def draw_sun(p: Pen, c: str) -> str:
    out = ""
    for i in range(12):
        out += (f'<line x1="{p.x(0.32 * COS12[i])}" y1="{p.y(0.32 * SIN12[i])}" x2="{p.x(0.47 * COS12[i])}" y2="{p.y(0.47 * SIN12[i])}" '
                f'stroke="{c}" stroke-width="{p.l(0.04)}" stroke-linecap="round"/>')
    out += f'<circle cx="{p.x(0)}" cy="{p.y(0)}" r="{p.l(0.27)}" fill="{c}" stroke="{shade(c, -30)}" stroke-width="{p.l(0.015)}"/>'
    return out


def draw_moon(p: Pen, c: str) -> str:
    d = shade(c, -25)
    return (
        f'<circle cx="{p.x(0)}" cy="{p.y(0)}" r="{p.l(0.45)}" fill="{c}"/>'
        f'<circle cx="{p.x(-0.15)}" cy="{p.y(-0.08)}" r="{p.l(0.08)}" fill="{d}"/>'
        f'<circle cx="{p.x(0.13)}" cy="{p.y(0.14)}" r="{p.l(0.11)}" fill="{d}"/>'
        f'<circle cx="{p.x(0.17)}" cy="{p.y(-0.2)}" r="{p.l(0.05)}" fill="{d}"/>'
        f'<circle cx="{p.x(-0.2)}" cy="{p.y(0.22)}" r="{p.l(0.04)}" fill="{d}"/>'
    )


def draw_star(p: Pen, c: str) -> str:
    fs = []
    for i in range(10):
        r = 0.5 if i % 2 == 0 else 0.2
        fs.extend((r * COS10[i], r * SIN10[i]))
    return f'<polygon points="{p.pts(*fs)}" fill="{c}" stroke="{shade(c, -40)}" stroke-width="{p.l(0.02)}" stroke-linejoin="round"/>'


def draw_cloud(p: Pen, c: str) -> str:
    return (
        f'<g fill="{c}" fill-opacity="0.95">'
        f'<circle cx="{p.x(-0.22)}" cy="{p.y(0.05)}" r="{p.l(0.18)}"/>'
        f'<circle cx="{p.x(0)}" cy="{p.y(-0.07)}" r="{p.l(0.25)}"/>'
        f'<circle cx="{p.x(0.22)}" cy="{p.y(0.05)}" r="{p.l(0.18)}"/>'
        f'<rect x="{p.x(-0.22)}" y="{p.y(0.04)}" width="{p.l(0.44)}" height="{p.l(0.19)}"/></g>'
    )


def draw_mountain(p: Pen, c: str) -> str:
    return (
        f'<polygon points="{p.pts(-0.5, 0.5, 0, -0.45, 0.5, 0.5)}" fill="{c}"/>'
        f'<polygon points="{p.pts(0, -0.45, 0.5, 0.5, 0.15, 0.5)}" fill="{shade(c, -25)}"/>'
        f'<polygon points="{p.pts(-0.13, -0.2, 0, -0.45, 0.13, -0.2, 0.05, -0.15, 0, -0.22, -0.05, -0.15)}" fill="#f4f4f4"/>'
    )


def draw_heart(p: Pen, c: str) -> str:
    return (
        f'<path d="M{p.x(0)},{p.y(0.4)} C{p.x(-0.5)},{p.y(0.05)} {p.x(-0.35)},{p.y(-0.42)} {p.x(0)},{p.y(-0.15)} '
        f'C{p.x(0.35)},{p.y(-0.42)} {p.x(0.5)},{p.y(0.05)} {p.x(0)},{p.y(0.4)} Z" fill="{c}" stroke="{shade(c, -50)}" stroke-width="{p.l(0.015)}"/>'
    )


DRAW = {
    "cat": draw_cat, "dog": draw_dog, "bird": draw_bird, "fish": draw_fish,
    "butterfly": draw_butterfly, "tree": draw_tree, "flower": draw_flower,
    "house": draw_house, "car": draw_car, "boat": draw_boat, "rocket": draw_rocket,
    "robot": draw_robot, "sun": draw_sun, "moon": draw_moon, "star": draw_star,
    "cloud": draw_cloud, "mountain": draw_mountain, "heart": draw_heart,
}


def draw(concept: str, cx: int, cy: int, s: int, color) -> str:
    return DRAW[concept](Pen(cx, cy, s), color or DEFAULT_COLORS[concept])


def _scaled(base: int, size) -> int:
    if size == "big":
        return math.floor(base * 1.25)
    if size == "small":
        return math.floor(base * 0.7)
    return base


def _foot(concept: str) -> float:
    return FOOT.get(concept, 0.5)


# ---------------------------------------------------------------- scene

def _gradient(gid: str, stops) -> str:
    out = f'<linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
    for off, col in stops:
        out += f'<stop offset="{off}" stop-color="{col}"/>'
    return out + "</linearGradient>"


SKY_STOPS = {
    "day": (("0", "#8fd3ff"), ("1", "#e6f6ff")),
    "night": (("0", "#0b1d3a"), ("1", "#27407a")),
    "space": (("0", "#050816"), ("1", "#1b1145")),
    "sunset": (("0", "#6e4aa8"), ("0.6", "#ff8a4c"), ("1", "#ffd27a")),
    "rain": (("0", "#9aa5b1"), ("1", "#d5dbe1")),
    "snow": (("0", "#c9d6e3"), ("1", "#eef3f8")),
}
GROUND_COLOR = {"day": "#7cc36b", "night": "#2f4f3a", "sunset": "#3b3b5c", "rain": "#6f9a62", "snow": "#f4f7fb", "space": "#7cc36b"}


def _stars(r: Rng, n: int, ymax: int) -> str:
    out = ""
    for _ in range(n):
        x = r.int(0, W - 1)
        y = r.int(0, ymax)
        rad = r.int(1, 2)
        op = OPACITY[r.int(0, 2)]
        out += f'<circle cx="{x}" cy="{y}" r="{rad}" fill="#ffffff" fill-opacity="{op}"/>'
    return out


def _abstract(r: Rng) -> str:
    bg = ABSTRACT_BG[r.int(0, len(ABSTRACT_BG) - 1)]
    out = f'<defs>{_gradient("bg", (("0", bg[0]), ("1", bg[1])))}</defs><rect width="{W}" height="{W}" fill="url(#bg)"/>'
    n = r.int(6, 9)
    for _ in range(n):
        kind = r.int(0, 2)
        col = PALETTE[r.int(0, len(PALETTE) - 1)]
        x = r.int(40, 470)
        y = r.int(40, 470)
        s = r.int(30, 110)
        if kind == 0:
            out += f'<circle cx="{x}" cy="{y}" r="{s // 2}" fill="{col}" fill-opacity="0.85"/>'
        elif kind == 1:
            out += f'<rect x="{x - s // 2}" y="{y - s // 2}" width="{s}" height="{s}" rx="{s // 8}" fill="{col}" fill-opacity="0.85"/>'
        else:
            out += f'<polygon points="{x},{y - s // 2} {x + s // 2},{y + s // 2} {x - s // 2},{y + s // 2}" fill="{col}" fill-opacity="0.85"/>'
    return out


def compose(text: str, seed: int = 0) -> dict:
    norm = normalize_prompt(text)
    r = Rng(fnv1a(norm if not seed else f"{norm}#{seed}"))
    info = parse(norm)
    mentions = info["mentions"]
    scenes = info["scenes"]
    concepts = [m["concept"] for m in mentions]
    head = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {W}" width="{W}" height="{W}"><title>{esc(norm)}</title>'
    if not mentions and not scenes:
        return {"svg": head + _abstract(r) + "</svg>", "subjects": [], "scenes": [], "layout": "abstract"}

    # ---- groups: relations first, then the remaining single mentions
    by_pos = {m["pos"]: m for m in mentions}
    groups = []
    used = set()
    for rel in info["relations"]:
        a, b = by_pos[rel["a"]], by_pos[rel["b"]]
        if rel["kind"] == "on":
            groups.append({"type": "on", "top": a, "base": b, "concept": b["concept"]})
        elif b["concept"] not in SKY:
            groups.append({"type": "under", "item": a, "base": b, "concept": b["concept"]})
        else:
            continue
        used.add(rel["a"])
        used.add(rel["b"])
    multi = len(mentions) > 1
    for m in mentions:
        if m["pos"] in used:
            continue
        n = m["count"]
        if n is None:
            n = 4 if (m["concept"] == "star" and multi) else 1
        for _ in range(min(5, n)):
            groups.append({"type": "single", "m": m, "concept": m["concept"]})

    # ---- scene
    if "space" in scenes:
        sky = "space"
    elif "night" in scenes:
        sky = "night"
    elif "sunset" in scenes:
        sky = "sunset"
    elif "rain" in scenes:
        sky = "rain"
    elif "snow" in scenes:
        sky = "snow"
    else:
        sky = "day"
        if "moon" in concepts and "sun" not in concepts:
            sky = "night"
        elif "rocket" in concepts and len(set(concepts)) == 1:
            sky = "space"
    if sky == "space":
        floor = "none"
    elif "sea" in scenes or "fish" in concepts or ("boat" in concepts and "car" not in concepts):
        floor = "sea"
    else:
        floor = "ground"
    hero = len(groups) == 1
    if hero and groups[0]["concept"] in SKY and floor == "ground" and not scenes:
        floor = "none"

    defs = _gradient("sky", SKY_STOPS[sky])
    if floor == "sea":
        defs += _gradient("water", (("0", "#4fb3e8"), ("1", "#0d4f8b")))
    bg = f'<defs>{defs}</defs><rect width="{W}" height="{W}" fill="url(#sky)"/>'
    if sky in ("night", "space"):
        bg += _stars(r, 60 if sky == "space" else 35, W - 1 if floor == "none" else GROUND_Y - 60)
    if sky == "sunset":
        bg += f'<circle cx="256" cy="{GROUND_Y if floor == "ground" else WATER_Y}" r="70" fill="#ffb347"/>'

    # ---- decor (not part of the matched subjects)
    decor = ""
    if not hero or groups[0]["concept"] not in SKY:
        has_light = "sun" in concepts or "moon" in concepts
        if sky == "day" and not has_light:
            decor += draw("sun", r.int(400, 440), r.int(70, 100), 100, None)
            decor += draw("cloud", r.int(90, 160), r.int(70, 110), r.int(100, 130), None)
        elif sky == "night" and not has_light:
            decor += draw("moon", r.int(410, 440), r.int(70, 95), 80, None)
        elif sky == "rain":
            decor += draw("cloud", r.int(110, 170), r.int(60, 90), 150, "#8b8d98")
            decor += draw("cloud", r.int(330, 400), r.int(70, 100), 130, "#a0a4ad")

    back = ""   # mountains
    floor_svg = ""
    if floor == "ground":
        bump = r.int(8, 20)
        floor_svg = f'<path d="M0,{GROUND_Y} Q128,{GROUND_Y - bump} 256,{GROUND_Y} T512,{GROUND_Y} L512,512 L0,512 Z" fill="{GROUND_COLOR[sky]}"/>'
    elif floor == "sea":
        floor_svg = f'<rect x="0" y="{WATER_Y}" width="{W}" height="{W - WATER_Y}" fill="url(#water)"/>'
        for k in range(3):
            wy = WATER_Y + 30 + k * 60 + r.int(0, 10)
            floor_svg += f'<path d="M0,{wy} Q64,{wy - 8} 128,{wy} T256,{wy} T384,{wy} T512,{wy}" fill="none" stroke="#ffffff" stroke-opacity="0.35" stroke-width="3"/>'

    sky_svg = ""
    mid = ""     # boats and fish
    front = ""   # ground objects
    ground_line = GROUND_Y + 8
    ground_groups = []
    lights = 0
    if floor == "sea":
        has_land = any(g["concept"] not in SKY and g["concept"] not in ("fish", "boat", "mountain") for g in groups)
        if has_land:
            floor_svg += f'<path d="M0,{SAND_Y} Q256,{SAND_Y - 40} 512,{SAND_Y} L512,512 L0,512 Z" fill="#f2d49b"/>'
        ground_line = SAND_Y + 14

    for g in groups:
        c = g["concept"]
        if g["type"] == "single":
            m = g["m"]
            if hero:
                if c in SKY or c == "rocket" and floor == "none":
                    s = _scaled(300, m["size"])
                    sky_svg += draw(c, 256, 250, s, m["color"])
                elif c == "fish" and floor == "sea":
                    mid += draw(c, 256, 390, _scaled(220, m["size"]), m["color"])
                elif c == "boat" and floor == "sea":
                    s = _scaled(260, m["size"])
                    mid += draw(c, 256, WATER_Y + 30 - math.floor(s * 0.32), s, m["color"])
                elif c == "mountain":
                    s = _scaled(340, m["size"])
                    back += draw(c, 256, ground_line - math.floor(s * 0.5), s, m["color"])
                else:
                    s = _scaled(280, m["size"])
                    if floor == "sea":
                        s = math.floor(s * 0.7)
                    front += draw(c, 256, ground_line - math.floor(s * _foot(c)), s, m["color"])
                continue
            if c in ("sun", "moon"):
                x = r.int(380, 430) if lights == 0 else r.int(80, 130)
                lights += 1
                sky_svg += draw(c, x, r.int(80, 110), _scaled(r.int(90, 110), m["size"]), m["color"])
            elif c == "star":
                sky_svg += draw(c, r.int(30, 480), r.int(30, 200), _scaled(r.int(28, 44), m["size"]), m["color"])
            elif c == "cloud":
                sky_svg += draw(c, r.int(70, 440), r.int(60, 150), _scaled(r.int(90, 130), m["size"]), m["color"])
            elif c == "bird":
                sky_svg += draw(c, r.int(60, 450), r.int(90, 200), _scaled(r.int(40, 60), m["size"]), m["color"])
            elif c == "butterfly":
                sky_svg += draw(c, r.int(60, 450), r.int(230, 320), _scaled(r.int(50, 70), m["size"]), m["color"])
            elif c == "heart":
                sky_svg += draw(c, r.int(80, 430), r.int(80, 180), _scaled(r.int(60, 90), m["size"]), m["color"])
            elif c == "rocket" and floor == "none":
                sky_svg += draw(c, r.int(100, 410), r.int(120, 380), _scaled(r.int(110, 150), m["size"]), m["color"])
            elif c == "mountain":
                s = _scaled(r.int(220, 300), m["size"])
                back += draw(c, r.int(100, 410), ground_line - math.floor(s * 0.5), s, m["color"])
            elif c == "fish" and floor == "sea":
                mid += draw(c, r.int(60, 450), r.int(WATER_Y + 60, 470), _scaled(r.int(60, 90), m["size"]), m["color"])
            elif c == "boat" and floor == "sea":
                s = _scaled(r.int(130, 170), m["size"])
                mid += draw(c, r.int(90, 420), WATER_Y + 20 - math.floor(s * 0.32), s, m["color"])
            else:
                ground_groups.append(g)
        else:
            if g["concept"] in SKY:
                bs = 290 if hero else 170
                bx, by = (256, 285) if hero else (r.int(150, 360), 170)
                sky_svg += _stack(g, bx, by, bs)
            else:
                ground_groups.append(g)

    n = len(ground_groups)
    if n:
        scale = 1.0 if n <= 2 else (0.8 if n == 3 else 0.65)
        if floor == "sea":
            scale = scale * 0.7
        placed = []
        for i, g in enumerate(ground_groups):
            base = GROUND_SIZE.get(g["concept"], 150)
            if hero:
                base = 260
            m = g["m"] if g["type"] == "single" else g["base"]
            s = math.floor(_scaled(base, m["size"]) * scale)
            x = 256 if hero else math.floor(W * (i + 1) / (n + 1)) + r.int(-12, 12)
            bottom = ground_line + (0 if hero else r.int(0, 14))
            placed.append((s, i, g, x, bottom))
        for s, i, g, x, bottom in sorted(placed, key=lambda t: (-t[0], t[1])):
            cy = bottom - math.floor(s * _foot(g["concept"]))
            if g["type"] == "single":
                front += draw(g["concept"], x, cy, s, g["m"]["color"])
            elif g["type"] == "on":
                front += _stack(g, x, cy, s)
            else:
                item = g["item"]
                isz = math.floor(s * 0.5)
                front += draw(g["concept"], x, cy, s, g["base"]["color"])
                front += draw(item["concept"], x + math.floor(s * 0.22), bottom - math.floor(isz * _foot(item["concept"])), isz, item["color"])

    weather = ""
    if "rain" in scenes:
        for _ in range(45):
            x = r.int(0, W - 1)
            y = r.int(0, W - 1)
            weather += f'<line x1="{x}" y1="{y}" x2="{x - 6}" y2="{y + 18}" stroke="#5eb1ef" stroke-opacity="0.6" stroke-width="2"/>'
    if "snow" in scenes:
        for _ in range(50):
            weather += f'<circle cx="{r.int(0, W - 1)}" cy="{r.int(0, W - 1)}" r="{r.int(2, 4)}" fill="#ffffff" fill-opacity="0.9"/>'

    body = bg + decor + sky_svg + back + floor_svg + mid + front + weather
    layout = "hero" if hero else "scene"
    return {"svg": head + body + "</svg>", "subjects": concepts, "scenes": scenes, "layout": layout}


def _stack(g: dict, cx: int, cy: int, s: int) -> str:
    base, top = g["base"], g["top"]
    out = draw(base["concept"], cx, cy, s, base["color"])
    ts = _scaled(math.floor(s * 0.45), top["size"])
    rest = cy + math.floor(s * SURFACE.get(base["concept"], -0.3))
    out += draw(top["concept"], cx, rest - math.floor(ts * _foot(top["concept"])), ts, top["color"])
    return out


def generate_svg(prompt: str, seed: int = 0) -> str:
    """Return SVG code for ``prompt`` (deterministic for a given seed)."""
    return compose(prompt, seed)["svg"]
