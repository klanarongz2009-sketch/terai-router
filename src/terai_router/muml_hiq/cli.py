"""``terai muml --hiq`` / ``terai muml --model hiq`` / ``terai muml-hiq``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import List, Optional

from . import CREDITS, DEFAULT_LM, DEFAULT_QUANT, DIT_FILES, LM_FILES, NAME, VERSION
from .adapter import THAI_LYRICS_LM, adapt, lyrics_language, prepare_lyrics
from .engine import HiqError, generate, setup, status
from .split import DEFAULT_KEY as SPLIT_DEFAULT_KEY, SplitError, generate_split, lyric_lines
from .split import DEFAULT_STYLE as SPLIT_DEFAULT_STYLE, DEFAULT_VOICE as SPLIT_DEFAULT_VOICE, STYLES as SPLIT_STYLES


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
    p.add_argument("--steps", type=int, default=8, help="turbo diffusion steps (default 8)")
    p.add_argument("--quant", choices=sorted(DIT_FILES), default=DEFAULT_QUANT, help="DiT GGUF quantisation")
    p.add_argument("--lm-model", choices=sorted(LM_FILES), default=None,
                   help=f"lyric LM run before synthesis when --lyrics is given (default {DEFAULT_LM}; "
                        f"Thai lyrics {THAI_LYRICS_LM})")
    p.add_argument("--thai-lyrics", choices=("roman", "native"), default=None,
                   help="Thai lyrics: romanise before singing (default) or keep Thai script")
    p.add_argument("--thai-vocal", choices=("sing", "split"), default="sing",
                   help="Thai lyrics: sing = ACE-Step sings them (default); split = instrumental from ACE-Step + "
                        "the local TTH Wayu voice on top, much clearer (CER 0.27 vs 0.84). Wayu weights are "
                        "CC-BY-NC-4.0, so split songs are non-commercial only")
    p.add_argument("--split-style", choices=SPLIT_STYLES, default=SPLIT_DEFAULT_STYLE,
                   help="with --thai-vocal split: snap = voice pitch snapped to the key (default), rap = spoken "
                        "in rhythm, melody = one note per syllable")
    p.add_argument("--voice", default=SPLIT_DEFAULT_VOICE, help="Wayu voice for --thai-vocal split")
    p.add_argument("--raw", action="store_true", help="skip the prompt adapter (prompt goes in verbatim)")
    p.add_argument("--dry-run", action="store_true", help="print the request that would be sent, generate nothing")
    p.add_argument("--json", action="store_true", help="machine-readable output")
    p.add_argument("--setup", action="store_true", help="download weights and build acestep.cpp")
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
        print(json.dumps(status(a.quant), ensure_ascii=False, indent=2))
        return 0
    if a.setup:
        try:
            for lmname in ([a.lm_model] if a.lm_model else sorted({DEFAULT_LM, THAI_LYRICS_LM})):
                st = setup(a.quant, log=lambda m: print(m, file=sys.stderr), lm=lmname)
        except Exception as e:  # pragma: no cover - network/build
            print(f"setup failed: {e}", file=sys.stderr)
            return 1
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0 if st["ready"] else 1

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
    if lyrics and a.thai_vocal == "split":
        if lyrics_language(lyrics) != "th":
            print("terai muml --hiq: --thai-vocal split needs Thai lyrics", file=sys.stderr)
            return 2
        split_lyrics, lyrics = lyrics, None  # ACE-Step renders the instrumental; Wayu says the lines
        print("note: split vocal uses Wayu-Paxa-TTS-Edge (CC-BY-NC-4.0): this song is non-commercial only",
              file=sys.stderr)
    elif a.thai_vocal == "split":
        print("terai muml --hiq: --thai-vocal split needs --lyrics", file=sys.stderr)
        return 2
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
                       vocals=True if lyrics else None)
        if lyrics:
            fields["lyrics"] = lyrics
            # vocal_language follows the lyrics, not the prompt.
            fields["vocal_language"] = lang
        elif split_lyrics:
            fields["lyrics"] = "[Instrumental]"
            fields["vocal_language"] = ""
        elif not fields["lyrics"]:
            # vocals asked for but no lyrics: this prototype renders without the LM
            # lyric writer, so fall back to instrumental and say so.
            print("note: vocals need --lyrics in this prototype; rendering instrumental.", file=sys.stderr)
            fields["lyrics"] = "[Instrumental]"
            fields["vocal_language"] = ""

    if split_lyrics and not fields.get("keyscale"):
        fields["keyscale"] = SPLIT_DEFAULT_KEY  # fixed key so the vocal can follow it
    if a.dry_run:
        from .engine import build_request
        fmt = "mp3" if a.out.lower().endswith(".mp3") else "wav16"
        req = build_request(fields, a.quant, a.seed, a.steps, fmt, lm=lm)
        if split_lyrics:
            req = {"instrumental": req, "thai_vocal": "split", "split_style": a.split_style, "voice": a.voice,
                   "lines": lyric_lines(split_lyrics)}
        print(json.dumps(req, ensure_ascii=False, indent=2))
        return 0
    try:
        if split_lyrics:
            r = generate_split(fields, split_lyrics, Path(a.out), style=a.split_style, voice=a.voice,
                               quant=a.quant, seed=a.seed, steps=a.steps)
        else:
            r = generate(fields, Path(a.out), quant=a.quant, seed=a.seed, steps=a.steps, lm=lm)
    except (HiqError, SplitError) as e:
        print(f"terai muml --hiq: {e}", file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(r, ensure_ascii=False))
    else:
        rq = r["request"]
        print(f"{r['out']}  {rq.get('duration')}s  bpm={rq.get('bpm', '-')}  {a.quant}  {r['wall_s']}s  ({NAME} {VERSION})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
