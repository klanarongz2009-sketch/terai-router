"""``terai muml --hiq`` / ``terai muml --model hiq`` / ``terai muml-hiq``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from . import CREDITS, DEFAULT_LM, DEFAULT_QUANT, DIT_FILES, LM_FILES, NAME, VERSION
from .adapter import THAI_LYRICS_LM, adapt, lyrics_language, parse_duration, prepare_lyrics
from .engine import HiqError, generate, setup, status
from .ending import DEFAULT_FADE_S, finish_ending
from .split import DEFAULT_KEY as SPLIT_DEFAULT_KEY, SplitError, generate_split, lyric_lines
from .split import DEFAULT_STYLE as SPLIT_DEFAULT_STYLE, DEFAULT_VOICE as SPLIT_DEFAULT_VOICE, STYLES as SPLIT_STYLES
from . import yue2

VOCAL_ENGINES = ("yue2", "ace", "split")


def resolve_vocal_engine(lyrics: Optional[str], vocal_engine: Optional[str] = None,
                         thai_vocal: Optional[str] = None) -> str:
    """Which engine renders the song.

    Thai lyrics -> yue2 by default (Bogus' pick, 2026-10-21); instrumental and
    English lyrics -> ace. --vocal-engine wins; the older --thai-vocal sing|split
    maps to ace|split. Raises ValueError for a combination that cannot work.
    """
    eng = vocal_engine or {"sing": "ace", "split": "split"}.get(thai_vocal or "", None)
    lang = lyrics_language(lyrics) if lyrics else ""
    if eng is None:
        return "yue2" if lang == "th" else "ace"
    if eng in ("yue2", "split") and not lyrics:
        raise ValueError(f"--vocal-engine {eng} needs --lyrics")
    if eng == "split" and lang != "th":
        raise ValueError("--vocal-engine split (--thai-vocal split) needs Thai lyrics")
    return eng


def is_hiq_request(argv: List[str]) -> bool:
    """True when a ``terai muml ...`` argv asks for the HIQ model."""
    if "--hiq" in argv:
        return True
    for i, a in enumerate(argv):
        if a == "--model" and i + 1 < len(argv) and argv[i + 1].lower() == "hiq":
            return True
        if a.lower() == "--model=hiq":
            return True
    return False


def strip_hiq_flags(argv: List[str]) -> List[str]:
    out, skip = [], False
    for i, a in enumerate(argv):
        if skip:
            skip = False
            continue
        if a == "--hiq" or a.lower() == "--model=hiq":
            continue
        if a == "--model" and i + 1 < len(argv) and argv[i + 1].lower() == "hiq":
            skip = True
            continue
        out.append(a)
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="terai muml --hiq",
                                description=f"{NAME}: text-to-music audio (ACE-Step 1.5 on CPU, Thai/English prompts)")
    p.add_argument("prompt", nargs="*", help="music prompt in Thai or English")
    p.add_argument("-o", "--out", default="song.mp3", help="output .mp3 or .wav (default song.mp3)")
    p.add_argument("--duration", type=float, default=None, help="seconds, 10-240 (default: from prompt or 30)")
    p.add_argument("--bpm", type=int, default=None, help="override BPM")
    p.add_argument("--key", default="", help='override key, e.g. "A minor"')
    p.add_argument("--lyrics", default=None, help="lyrics text or path to a .txt file (default instrumental)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--steps", type=int, default=None,
                   help=f"diffusion steps (default: ACE-Step turbo 8, YuE2 {yue2.DEFAULT_STEPS})")
    p.add_argument("--quant", choices=sorted(DIT_FILES), default=DEFAULT_QUANT, help="DiT GGUF quantisation")
    p.add_argument("--lm-model", choices=sorted(LM_FILES), default=None,
                   help=f"lyric LM run before synthesis when --lyrics is given (default {DEFAULT_LM}; "
                        f"Thai lyrics {THAI_LYRICS_LM})")
    p.add_argument("--thai-lyrics", choices=("roman", "native"), default=None,
                   help="Thai lyrics: romanise before singing (default) or keep Thai script")
    p.add_argument("--vocal-engine", choices=VOCAL_ENGINES, default=None,
                   help="who sings the lyrics. Default: yue2 for Thai lyrics (YuE2-3B sings the Thai script, "
                        "~15 min per 30 s on CPU, CC-BY-NC-4.0 = non-commercial), ace (ACE-Step 1.5) for "
                        "English lyrics and instrumentals; split = ACE-Step instrumental + the local TTH Wayu "
                        "voice (CC-BY-NC-4.0)")
    p.add_argument("--yue2-quant", choices=sorted(yue2.MODEL_FILES), default=yue2.DEFAULT_QUANT,
                   help=f"YuE2-3B GGUF quantisation (default {yue2.DEFAULT_QUANT})")
    p.add_argument("--thai-vocal", choices=("sing", "split"), default=None,
                   help="older alias: sing = --vocal-engine ace, split = --vocal-engine split")
    p.add_argument("--split-style", choices=SPLIT_STYLES, default=SPLIT_DEFAULT_STYLE,
                   help="with --thai-vocal split: snap = voice pitch snapped to the key (default), rap = spoken "
                        "in rhythm, melody = one note per syllable")
    p.add_argument("--voice", default=SPLIT_DEFAULT_VOICE, help="Wayu voice for --thai-vocal split")
    p.add_argument("--fade-out", type=float, default=DEFAULT_FADE_S, metavar="SECONDS",
                   help=f"fade the end when the song stops while still loud (default {DEFAULT_FADE_S:g}; 0 = off)")
    p.add_argument("--raw", action="store_true", help="skip the prompt adapter (prompt goes in verbatim)")
    p.add_argument("--dry-run", action="store_true", help="print the request that would be sent, generate nothing")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--setup", action="store_true", help="download weights and build acestep.cpp and yue2.cpp")
    p.add_argument("--status", action="store_true", help="show engine/model readiness")
    p.add_argument("--credits", action="store_true", help="show licences and credits")
    return p


def main(argv: Optional[List[str]] = None) -> int:
    argv = strip_hiq_flags(list(sys.argv[1:] if argv is None else argv))
    a = build_parser().parse_args(argv)
    if a.credits:
        print(CREDITS)
        return 0
    if a.status:
        st = status(a.quant)
        st["yue2"] = yue2.status(a.yue2_quant)
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0
    if a.setup:
        try:
            for lmname in ([a.lm_model] if a.lm_model else sorted({DEFAULT_LM, THAI_LYRICS_LM})):
                st = setup(a.quant, log=lambda m: print(m, file=sys.stderr), lm=lmname)
            if a.vocal_engine in (None, "yue2"):
                print(f"setting up {yue2.MODEL_NAME} (yue2.cpp {yue2.RUNTIME_COMMIT[:7]}); {yue2.LICENSE_WARNING}",
                      file=sys.stderr)
                st["yue2"] = yue2.setup(a.yue2_quant, log=lambda m: print(m, file=sys.stderr))
        except Exception as e:  # pragma: no cover - network/build
            print(f"setup failed: {e}", file=sys.stderr)
            return 1
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0 if st["ready"] and st.get("yue2", {"ready": True})["ready"] else 1

    prompt = " ".join(a.prompt).strip()
    if not prompt:
        print("terai muml --hiq: give a prompt, e.g. terai muml --hiq \"เพลงลูกทุ่งสนุกๆ จังหวะ 130\" -o song.mp3",
              file=sys.stderr)
        return 2

    lyrics = None
    lm = a.lm_model or DEFAULT_LM
    if a.lyrics:
        lp = Path(a.lyrics)
        try:
            is_file = "\n" not in a.lyrics and lp.is_file()
        except OSError:  # lyrics text longer than a file name
            is_file = False
        lyrics = lp.read_text(encoding="utf-8") if is_file else a.lyrics
    lang = ""
    split_lyrics = None
    yue2_lyrics = None
    try:
        engine = resolve_vocal_engine(lyrics, a.vocal_engine, a.thai_vocal)
    except ValueError as e:
        print(f"terai muml --hiq: {e}", file=sys.stderr)
        return 2
    if engine == "split":
        split_lyrics, lyrics = lyrics, None  # ACE-Step renders the instrumental; Wayu says the lines
        print("note: split vocal uses Wayu-Paxa-TTS-Edge (CC-BY-NC-4.0): this song is non-commercial only",
              file=sys.stderr)
    elif engine == "yue2":
        yue2_lyrics, lyrics = lyrics, None  # Thai script goes to YuE2 verbatim (no romanisation, no ace-lm)
    steps = a.steps if a.steps is not None else (yue2.DEFAULT_STEPS if engine == "yue2" else 8)
    if lyrics:
        if lyrics_language(lyrics) == "th" and not a.lm_model:
            lm = THAI_LYRICS_LM
        lyrics, lang, note = prepare_lyrics(lyrics, a.thai_lyrics)
        if note:
            print(f"note: {note}", file=sys.stderr)

    if a.raw:
        fields = {"caption": prompt, "lyrics": lyrics or "[Instrumental]",
                  "duration": a.duration or 30.0, "bpm": a.bpm, "keyscale": a.key}
        if lyrics:
            fields["vocal_language"] = lang
    else:
        fields = adapt(prompt, duration=a.duration, bpm=a.bpm, key=a.key,
                       vocals=True if (lyrics or yue2_lyrics) else None)
        if lyrics:
            fields["lyrics"] = lyrics
            # vocal_language follows the lyrics, not the prompt.
            fields["vocal_language"] = lang
        elif split_lyrics:
            fields["lyrics"] = "[Instrumental]"
            fields["vocal_language"] = ""
        elif yue2_lyrics:
            fields["lyrics"] = yue2_lyrics
        elif not fields["lyrics"]:
            # vocals asked for but no lyrics: this prototype renders without the LM
            # lyric writer, so fall back to instrumental and say so.
            print("note: vocals need --lyrics in this prototype; rendering instrumental.", file=sys.stderr)
            fields["lyrics"] = "[Instrumental]"
            fields["vocal_language"] = ""

    if split_lyrics and not fields.get("keyscale"):
        fields["keyscale"] = SPLIT_DEFAULT_KEY  # fixed key so the vocal can follow it
    if yue2_lyrics and not fields.get("duration"):
        fields["duration"] = 30.0
    if yue2_lyrics:
        # yue-synth stops at the duration, mid-phrase if the lyrics need longer: size it from the lyrics.
        rec = yue2.recommended_duration(yue2_lyrics, fields.get("bpm"))
        given = a.duration is not None or (not a.raw and parse_duration(prompt) is not None)
        if not given and rec > float(fields["duration"]):
            print(f"note: duration {rec:g} s from the lyrics ({float(fields['duration']):g} s would stop "
                  "before the last line); set --duration to change it", file=sys.stderr)
            fields["duration"] = rec
        elif rec > float(fields["duration"]):
            print(f"warning: these lyrics need about {rec:g} s; at {float(fields['duration']):g} s the song stops "
                  f"before the last line (it gets a {a.fade_out:g} s fade-out). Try --duration {rec:g}.",
                  file=sys.stderr)
    if a.dry_run:
        from .engine import build_request
        fmt = "mp3" if a.out.lower().endswith(".mp3") else "wav16"
        if yue2_lyrics:
            req = yue2.build_request(fields, yue2_lyrics, a.seed, steps, fmt)
            b = yue2.find_binary() or Path("yue-synth")
            print(json.dumps({"engine": "yue2", "quant": a.yue2_quant, "threads": yue2.cpu_threads(), "eta_min": yue2.eta_minutes(req["duration"]),
                              "license": yue2.LICENSE, "request": req,
                              "fade_out_s": a.fade_out,
                              "argv": yue2.build_argv(b, "request.json", a.out, a.yue2_quant,
                                                      duration=req["duration"])},
                             ensure_ascii=False, indent=2))
            return 0
        req = build_request(fields, a.quant, a.seed, steps, fmt, lm=lm)
        if split_lyrics:
            req = {"instrumental": req, "thai_vocal": "split", "split_style": a.split_style, "voice": a.voice,
                   "lines": lyric_lines(split_lyrics)}
        print(json.dumps(req, ensure_ascii=False, indent=2))
        return 0
    if yue2_lyrics:
        # Say the cost and the licence before a ~15 min render starts.
        print(yue2.eta_message(fields["duration"]), file=sys.stderr)
        print(yue2.LICENSE_WARNING, file=sys.stderr)
    try:
        if yue2_lyrics:
            r = yue2.generate(fields, yue2_lyrics, Path(a.out), quant=a.yue2_quant, seed=a.seed, steps=steps)
        elif split_lyrics:
            r = generate_split(fields, split_lyrics, Path(a.out), style=a.split_style, voice=a.voice,
                               quant=a.quant, seed=a.seed, steps=steps)
        else:
            r = generate(fields, Path(a.out), quant=a.quant, seed=a.seed, steps=steps, lm=lm)
    except (HiqError, SplitError) as e:
        print(f"terai muml --hiq: {e}", file=sys.stderr)
        return 1
    try:
        r["ending"] = finish_ending(Path(r["out"]), a.fade_out)
    except RuntimeError as e:
        r["ending"] = {"ending": f"fade failed: {e}", "fade_out_s": 0.0}
    reach = r.get("reach")
    if reach and reach.get("cut_by_duration"):
        left = [s["section"] for s in reach["sections"] if s["state"] != "complete"]
        print(f"note: yue2 stopped at the {r['request'].get('duration')} s duration before the song ended (planned {reach['plan_s']:g} s; "
              f"unfinished: {', '.join(left) or '-'}); a longer --duration lets it finish", file=sys.stderr)
    if a.json:
        print(json.dumps(r, ensure_ascii=False))
    else:
        rq = r["request"]
        q = a.yue2_quant if yue2_lyrics else a.quant
        print(f"{r['out']}  {rq.get('duration')}s  bpm={rq.get('bpm', '-')}  {engine}  {q}  {r['wall_s']}s  "
              f"({NAME} {VERSION})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
