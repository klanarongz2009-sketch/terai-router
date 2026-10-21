"""Prompt adapter for MUML 1.0 HIQ.

ACE-Step 1.5 was trained on English-style music captions plus explicit metadata
(BPM, key, time signature, duration). A free-form Thai prompt such as
"เพลงลูกทุ่งสนุกๆ จังหวะเร็ว" reaches its text encoder as Thai text with no
metadata, so tempo is left to chance. This adapter rewrites a Thai or English
prompt into the fields ACE-Step reads: an English caption made of music tags,
plus bpm, keyscale, timesignature, duration and lyrics.

It is a conditioning adapter. It does not change any model weights.
Pure standard library, deterministic.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

# (match words, English tag, default bpm or None). Longer Thai words first so
# that "ลูกทุ่ง" wins over shorter overlaps.
GENRES: List[Tuple[Tuple[str, ...], str, Optional[int]]] = [
    (("ลูกทุ่ง", "luk thung", "luk-thung"), "Thai luk thung country pop with phin and khaen", 120),
    (("หมอลำ", "mor lam", "molam"), "Isan mor lam folk dance music with khaen and phin", 130),
    (("ลูกกรุง",), "Thai luk krung retro big band ballad", 84),
    (("ไทยเดิม", "ดนตรีไทย", "thai classical"), "traditional Thai classical ensemble with ranat and khong wong", 96),
    (("โลไฟ", "โลว์ไฟ", "lo-fi", "lofi", "lo fi"), "lo-fi hip hop beat with dusty drums and warm keys", 82),
    (("ฮิปฮอป", "hip hop", "hiphop"), "hip hop beat with punchy kick and snare", 92),
    (("แร็ป", "rap"), "rap beat with heavy 808 bass", 95),
    (("แทร็ป", "trap"), "trap beat with rolling hi-hats and 808 bass", 140),
    (("อีดีเอ็ม", "edm", "electronic dance"), "EDM electronic dance track with big synth leads", 128),
    (("เฮาส์", "house music", "deep house"), "deep house groove with four-on-the-floor kick", 122),
    (("เทคโน", "techno"), "driving techno with hypnotic synths", 130),
    (("ซินธ์เวฟ", "synthwave", "80s"), "80s synthwave with retro analog synths", 105),
    (("ร็อค", "ร็อก", "rock"), "rock band with electric guitars, bass and live drums", 124),
    (("เมทัล", "metal"), "heavy metal with distorted guitars and double kick drums", 160),
    (("แจ๊ส", "แจ๊ซ", "jazz"), "jazz combo with upright bass, brushed drums and piano", 110),
    (("บลูส์", "blues"), "blues with slide guitar and shuffle rhythm", 90),
    (("ฟังก์", "funk"), "funk groove with slap bass and clavinet", 108),
    (("เร็กเก้", "reggae"), "reggae with offbeat guitar skank", 75),
    (("ป๊อป", "ป็อป", "pop"), "modern pop production", 115),
    (("บัลลาด", "ballad"), "emotional ballad", 72),
    (("คลาสสิก", "คลาสสิค", "classical", "orchestra", "ออเคสตร้า", "ออร์เคสตรา"), "cinematic orchestral piece with strings and brass", 90),
    (("ภาพยนตร์", "หนัง", "cinematic", "epic", "อลังการ"), "epic cinematic score with big drums and choir pads", 100),
    (("แอมเบียนต์", "ambient"), "ambient soundscape with evolving pads", 70),
    (("ชิปทูน", "8-bit", "8 bit", "chiptune", "เกม", "game music"), "8-bit chiptune video game music", 140),
    (("อะคูสติก", "acoustic"), "acoustic folk with fingerpicked guitar", 96),
    (("ละติน", "latin", "บอสซา", "bossa"), "bossa nova with nylon guitar and soft percussion", 120),
]

INSTRUMENTS: List[Tuple[Tuple[str, ...], str]] = [
    (("เปียโน", "piano"), "piano"),
    (("กีตาร์ไฟฟ้า", "electric guitar"), "electric guitar"),
    (("กีตาร์", "guitar"), "acoustic guitar"),
    (("เบส", "bass"), "bass"),
    (("กลอง", "drum"), "drums"),
    (("ไวโอลิน", "violin"), "violin"),
    (("เชลโล", "cello"), "cello"),
    (("เครื่องสาย", "strings"), "string section"),
    (("แซกโซโฟน", "แซ็กโซโฟน", "แซก", "sax"), "saxophone"),
    (("ทรัมเป็ต", "trumpet"), "trumpet"),
    (("ฟลุต", "flute"), "flute"),
    (("ซินธ์", "ซินธิไซเซอร์", "synth"), "synthesizer"),
    (("ระนาด", "ranat"), "ranat Thai xylophone"),
    (("ขลุ่ย", "khlui"), "khlui Thai bamboo flute"),
    (("พิณ", "phin"), "phin Isan lute"),
    (("แคน", "khaen"), "khaen mouth organ"),
    (("ซอ",), "saw Thai fiddle"),
    (("ฆ้อง", "khong"), "khong wong gong circle"),
    (("จะเข้", "jakhe"), "jakhe Thai zither"),
    (("ฉิ่ง", "ching"), "ching finger cymbals"),
]

MOODS: List[Tuple[Tuple[str, ...], str, int]] = [
    # (words, tag, bpm nudge used only when no genre and no tempo is given)
    (("เศร้า", "sad", "เหงา", "lonely"), "sad, melancholic", -25),
    (("สนุก", "fun", "happy", "มีความสุข", "ร่าเริง", "สดใส"), "happy, upbeat, bright", 20),
    (("ผ่อนคลาย", "relax", "chill", "ชิล", "สบายๆ", "calm", "สงบ"), "relaxing, calm, chill", -20),
    (("โรแมนติก", "romantic", "รัก", "love"), "romantic, tender", -15),
    (("มันส์", "energetic", "ฮึกเหิม", "ปลุกใจ", "powerful"), "energetic, powerful", 25),
    (("น่ากลัว", "scary", "horror", "สยองขวัญ"), "dark, eerie, suspenseful", -10),
    (("ลึกลับ", "mysterious"), "mysterious", -10),
    (("อบอุ่น", "warm"), "warm", 0),
    (("หวาน", "sweet"), "sweet, gentle", -10),
    (("เท่", "cool"), "cool, stylish", 0),
    (("ตื่นเต้น", "exciting"), "exciting, driving", 20),
    (("ฝัน", "dreamy"), "dreamy", -15),
]

SCENES: List[Tuple[Tuple[str, ...], str]] = [
    (("ฝนตก", "สายฝน", "rain"), "rainy day atmosphere"),
    (("ทะเล", "ชายหาด", "beach", "ocean", "sea"), "seaside summer vibe"),
    (("กลางคืน", "ยามค่ำ", "night"), "late night"),
    (("เช้า", "morning"), "fresh morning"),
    (("ภูเขา", "mountain"), "wide open mountain landscape"),
    (("เมือง", "city"), "urban city"),
    (("วัด", "temple"), "Thai temple atmosphere"),
    (("สงกรานต์", "songkran"), "festive Thai Songkran celebration"),
    (("ลอยกระทง", "loy krathong"), "Thai Loy Krathong festival"),
    (("วันเกิด", "birthday"), "birthday party"),
    (("อ่านหนังสือ", "study", "ทำงาน", "focus"), "for studying and focus"),
    (("วิ่ง", "workout", "ออกกำลัง", "running"), "workout"),
]

TEMPO_WORDS: List[Tuple[Tuple[str, ...], int]] = [
    (("ช้ามาก", "very slow"), 62),
    (("เร็วมาก", "very fast"), 150),
    (("ช้า", "slow"), 72),
    (("ปานกลาง", "กลางๆ", "medium tempo", "mid-tempo", "midtempo"), 100),
    (("เร็ว", "fast", "uptempo", "up-tempo"), 132),
]

VOCAL_WORDS = ("ร้อง", "เนื้อร้อง", "นักร้อง", "vocal", "vocals", "singing", "sung", "lyrics", "เนื้อเพลง")
INSTRUMENTAL_WORDS = ("บรรเลง", "instrumental", "no vocal", "ไม่มีเสียงร้อง", "ไม่มีเนื้อร้อง")

NOTE_NAMES = {"c", "c#", "db", "d", "d#", "eb", "e", "f", "f#", "gb", "g", "g#", "ab", "a", "a#", "bb", "b"}
THAI_RE = re.compile(r"[\u0E00-\u0E7F]")
LEADING_VOWELS = "\u0e40\u0e41\u0e42\u0e43\u0e44"

MIN_BPM, MAX_BPM = 40, 220
MIN_DURATION, MAX_DURATION = 10.0, 240.0
DEFAULT_DURATION = 30.0
DEFAULT_BPM = 100


def _has(text: str, words) -> Optional[str]:
    for w in words:
        if THAI_RE.search(w):
            # A Thai leading vowel belongs to the next consonant: "ช้า" inside "เช้า" is not a match.
            for m in re.finditer(re.escape(w), text):
                if m.start() == 0 or text[m.start() - 1] not in LEADING_VOWELS:
                    return w
        else:
            if re.search(r"(?<![a-z0-9])" + re.escape(w) + r"(?![a-z0-9])", text):
                return w
    return None


def _thai_digits(s: str) -> str:
    return s.translate(str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789"))


def parse_bpm(text: str) -> Optional[int]:
    m = re.search(r"(\d{2,3})\s*(?:bpm|บีพีเอ็ม|บีพีเอม)", text)
    if not m:
        m = re.search(r"(?:bpm|tempo|จังหวะ|เทมโป)\s*[:=]?\s*(\d{2,3})", text)
    if m:
        v = int(m.group(1))
        if MIN_BPM <= v <= MAX_BPM:
            return v
    return None


def parse_duration(text: str) -> Optional[float]:
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:นาที|min|mins|minute|minutes)(?![a-z])", text)
    if m:
        return float(m.group(1)) * 60.0
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:วินาที|วิ(?![ก-๙])|s|sec|secs|second|seconds)(?![a-z])", text)
    if m:
        return float(m.group(1))
    return None


def parse_key(text: str) -> str:
    m = re.search(r"(?:key|คีย์)\s*([a-g](?:#|b)?)\s*(major|minor|เมเจอร์|ไมเนอร์|m(?![a-z]))?", text)
    if not m:
        m = re.search(r"(?<![a-z])([a-g](?:#|b)?)\s*(major|minor|เมเจอร์|ไมเนอร์)", text)
    if not m:
        return ""
    note = m.group(1)
    if note not in NOTE_NAMES:
        return ""
    q = m.group(2) or "major"
    scale = "minor" if q in ("minor", "ไมเนอร์", "m") else "major"
    return note[0].upper() + note[1:] + " " + scale


def parse_timesig(text: str) -> str:
    m = re.search(r"(?<!\d)([2-7])\s*/\s*(4|8)(?!\d)", text)
    if m:
        return m.group(1)
    if _has(text, ("waltz", "วอลทซ์", "วอลซ์")):
        return "3"
    return ""


_META_RES = [
    r"\d{2,3}\s*bpm", r"(?:bpm|tempo)\s*[:=]?\s*\d{2,3}",
    r"\d+(?:\.\d+)?\s*(?:s|sec|secs|seconds?|mins?|minutes?)(?![a-z])",
    r"(?:in\s+(?:the\s+)?)?(?:key\s*(?:of\s*)?)?(?<![a-z])[a-g](?:#|b)?\s*(?:major|minor)",
    r"(?<!\d)[2-7]\s*/\s*(?:4|8)(?!\d)",
]


def strip_metadata(text: str) -> str:
    out = text
    for r in _META_RES:
        out = re.sub(r, "", out, flags=re.IGNORECASE)
    out = re.sub(r"\s*,\s*(,\s*)+", ", ", out)
    return out.strip(" ,.;")


LATIN_RE = re.compile(r"[A-Za-z]")
THAI_CHAR_RE = re.compile(r"[\u0e00-\u0e7f]")


def _lyric_body(lyrics: str) -> str:
    """Lyrics without [section] tag lines."""
    return "\n".join(l for l in (lyrics or "").splitlines() if not l.strip().startswith("["))


def lyrics_language(lyrics: Optional[str]) -> str:
    """vocal_language for ACE-Step, read from the lyrics (not the prompt).

    "" for no lyrics / instrumental, "th" when Thai letters dominate, "en" for
    Latin script, "unknown" otherwise.
    """
    body = _lyric_body(lyrics or "")
    if not body.strip():
        return ""
    th = len(THAI_CHAR_RE.findall(body))
    lat = len(LATIN_RE.findall(body))
    if th and th >= lat:
        return "th"
    if lat:
        return "en"
    return "unknown"


def romanize_thai(lyrics: str) -> Optional[str]:
    """Thai lyrics -> Royal Institute romanisation, line by line, tags kept.

    Needs PyThaiNLP (optional). Returns None when it is not installed.
    """
    try:
        from pythainlp.tokenize import word_tokenize  # type: ignore
        from pythainlp.transliterate import romanize  # type: ignore
    except ImportError:
        return None
    out = []
    for line in (lyrics or "").splitlines():
        if not THAI_CHAR_RE.search(line) or line.strip().startswith("["):
            out.append(line)
            continue
        words = [w for w in word_tokenize(line, keep_whitespace=False) if w.strip()]
        out.append(" ".join(romanize(w, engine="royin") if THAI_CHAR_RE.search(w) else w for w in words))
    return "\n".join(out) + ("\n" if (lyrics or "").endswith("\n") else "")


# Default handling of Thai lyrics (set from the 2026-10-21 Thai-vocal CER test, see docs/MUML-HIQ.md).
THAI_LYRICS_MODE = "roman"
THAI_LYRICS_LM = "1.7B"  # variant C: 1.7B + romanised scored best (CER 0.8411, 5/30 lyric words)


def prepare_lyrics(lyrics: str, thai_mode: Optional[str] = None):
    """Return (lyrics, vocal_language, note) ready for ACE-Step.

    vocal_language follows the lyrics. Thai lyrics in "roman" mode are romanised
    and sent as vocal_language "unknown"; "native" keeps Thai script with "th".
    """
    lang = lyrics_language(lyrics)
    mode = thai_mode or THAI_LYRICS_MODE
    if lang == "th" and mode == "roman":
        rom = romanize_thai(lyrics)
        if rom is None:
            return lyrics, "th", "PyThaiNLP not installed: Thai lyrics sent in Thai script (pip install pythainlp)"
        return rom, "unknown", "Thai lyrics romanised (royin) for singing"
    return lyrics, lang, ""


def adapt(prompt: str, duration: Optional[float] = None, bpm: Optional[int] = None,
          key: str = "", vocals: Optional[bool] = None) -> Dict[str, object]:
    """Rewrite a Thai/English music prompt into ACE-Step request fields.

    Explicit arguments override what is read from the prompt.
    Returns a dict with caption, bpm, duration, keyscale, timesignature,
    lyrics, vocal_language and a ``matched`` list for debugging.
    """
    raw = (prompt or "").strip()
    text = _thai_digits(raw).lower()
    matched: List[str] = []
    tags: List[str] = []

    genre_bpm: Optional[int] = None
    for words, tag, gbpm in GENRES:
        w = _has(text, words)
        if w:
            matched.append(w)
            tags.append(tag)
            if genre_bpm is None:
                genre_bpm = gbpm
            if len([t for t in tags]) >= 2:
                break

    inst = []
    for words, tag in INSTRUMENTS:
        w = _has(text, words)
        if w and tag not in inst:
            # "กีตาร์" also matches inside "กีตาร์ไฟฟ้า"; keep the specific one only.
            if tag == "acoustic guitar" and "electric guitar" in inst:
                continue
            matched.append(w)
            inst.append(tag)
    mood_nudge = 0
    moods = []
    for words, tag, nudge in MOODS:
        w = _has(text, words)
        if w:
            matched.append(w)
            moods.append(tag)
            mood_nudge += nudge
    scenes = []
    for words, tag in SCENES:
        w = _has(text, words)
        if w:
            matched.append(w)
            scenes.append(tag)

    tempo_word_bpm = None
    for words, v in TEMPO_WORDS:
        w = _has(text, words)
        if w:
            matched.append(w)
            tempo_word_bpm = v
            break

    if bpm is None:
        bpm = parse_bpm(text)
    if bpm is None:
        if tempo_word_bpm is not None:
            bpm = tempo_word_bpm
        elif genre_bpm is not None:
            bpm = genre_bpm
        else:
            bpm = DEFAULT_BPM + max(-35, min(35, mood_nudge))
    bpm = int(max(MIN_BPM, min(MAX_BPM, bpm)))

    if duration is None:
        duration = parse_duration(text)
    if duration is None:
        duration = DEFAULT_DURATION
    duration = float(max(MIN_DURATION, min(MAX_DURATION, duration)))

    keyscale = key or parse_key(text)
    timesig = parse_timesig(text) or "4"

    if vocals is None:
        vocals = bool(_has(text, VOCAL_WORDS)) and not _has(text, INSTRUMENTAL_WORDS)

    parts: List[str] = []
    if not THAI_RE.search(raw):
        # English prompts already speak the caption language: keep the user's words,
        # minus the metadata that now travels in its own fields.
        head = strip_metadata(raw)
        if head:
            parts.append(head)
        tags, inst, moods, scenes = [], [], [], []
        tempo_word_bpm = None
    parts.extend(tags)
    if inst:
        parts.append("featuring " + ", ".join(inst))
    parts.extend(moods)
    parts.extend(scenes)
    if tempo_word_bpm is not None:
        parts.append("slow tempo" if tempo_word_bpm < 90 else ("fast tempo" if tempo_word_bpm > 120 else "medium tempo"))
    if not parts:
        # Nothing recognised: keep the user's words so the multilingual text encoder
        # still sees them, framed as a music caption.
        parts.append("instrumental music" if not vocals else "song")
        parts.append(raw)
    parts.append("high quality studio mix")
    if not vocals:
        parts.append("instrumental")
    caption = ", ".join(p for p in parts if p)

    return {
        "caption": caption,
        "bpm": bpm,
        "duration": duration,
        "keyscale": keyscale,
        "timesignature": timesig,
        "lyrics": "" if vocals else "[Instrumental]",
        "vocal_language": ("th" if THAI_RE.search(raw) else "en") if vocals else "",
        "matched": matched,
    }
