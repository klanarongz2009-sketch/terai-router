"""Thai vocal "split" mode for MUML 1.0 HIQ: TTH (Wayu) voice over an ACE-Step instrumental.

ACE-Step 1.5 does not sing Thai clearly (2026-10-21 test: best variant C, CER 0.8411, 5/30 lyric words;
the instrumental alone scores CER 0.8972). Split mode renders the music as an instrumental, has the local
Wayu-Paxa-TTS-Edge voice say each lyric line, fits every line to two bars of the song's BPM (ffmpeg atempo),
optionally retunes it to the song's key with WORLD (pyworld), and mixes it on top with light sidechain ducking.
Same lyrics, seed 42, 90 BPM, 30 s: rap CER 0.2056 (21/30 words), snap 0.2710 (18/30), melody 0.3738 (11/30).

Styles:
  snap   - the voice's own pitch contour moved into a singing range and snapped to the key's scale (default)
  rap    - spoken in rhythm, natural pitch (most intelligible)
  melody - each voiced segment (about one syllable) set to the next note of a simple line in the key

Wayu weights are CC-BY-NC-4.0: audio made in this mode is for non-commercial use only (see NOTICE).
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

STYLES = ("snap", "rap", "melody")
DEFAULT_STYLE = "snap"
DEFAULT_VOICE = "f_young_clear"
DEFAULT_KEY = "C major"
MAJOR = (0, 2, 4, 5, 7, 9, 11)
MINOR = (0, 2, 3, 5, 7, 8, 10)
NOTE_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
# Scale-degree lines (0 = tonic) cycled over voiced segments in "melody" style, one per lyric line.
MELODY_DEGREES = (
    (2, 4, 5, 4, 2, 1, 2, 4, 5, 4, 2, 1),
    (1, 2, 3, 4, 3, 2, 1, 0, 1, 2, 1, 0),
    (4, 5, 7, 5, 4, 2, 4, 5, 7, 6, 5, 4),
    (5, 4, 2, 1, 2, 4, 2, 1, 0, 1, 2, 0),
)
LIMIT_ATEMPO = (0.8, 1.35)


class SplitError(RuntimeError):
    pass


def lyric_lines(lyrics: str) -> List[str]:
    """Sung lines: non-empty, [section] tags dropped."""
    return [l.strip() for l in (lyrics or "").splitlines() if l.strip() and not l.strip().startswith("[")]


def parse_key(keyscale: Optional[str]):
    """'C major' / 'A minor' / 'F# minor' / 'Bb major' -> (tonic pitch class, scale). Unknown -> C major."""
    m = re.match(r"\s*([A-Ga-g])\s*([#b\u266f\u266d]?)\s*(major|minor|maj|min|m)?", keyscale or "")
    if not m:
        return 0, MAJOR
    pc = NOTE_PC[m.group(1).upper()]
    if m.group(2) in ("#", "\u266f"):
        pc += 1
    elif m.group(2) in ("b", "\u266d"):
        pc -= 1
    q = (m.group(3) or "major").lower()
    return pc % 12, (MINOR if q in ("minor", "min", "m") else MAJOR)


def snap_to_scale(midi: float, tonic: int = 0, scale: Sequence[int] = MAJOR) -> int:
    """Round to the nearest semitone, then the nearest note in the key (ties go down)."""
    n = int(round(midi))
    for d in range(0, 7):
        for c in (n - d, n + d):
            if (c - tonic) % 12 in scale:
                return c
    return n


def degree_to_midi(degree: int, tonic: int = 0, scale: Sequence[int] = MAJOR, base_octave: int = 4) -> int:
    o, i = divmod(degree, len(scale))
    return 12 * (base_octave + 1 + o) + tonic + scale[i]


def line_starts(n_lines: int, bpm: float, duration: float, bars_per_line: int = 2, intro_bars: int = 1):
    """Start time (s) and slot length (s) for each line, on bar lines. Shrinks to 1 bar per line when needed."""
    bar = 4 * 60.0 / float(bpm)
    for bpl in (bars_per_line, 1):
        for intro in (intro_bars, 0):
            starts = [(intro + bpl * i) * bar for i in range(n_lines)]
            if not starts or starts[-1] + bpl * bar * 0.5 <= duration:
                return starts, bpl * bar - 0.5 * 60.0 / float(bpm)
    raise SplitError(f"{n_lines} lyric lines do not fit in {duration:.0f} s at {bpm:g} BPM; "
                     "use fewer lines or a longer --duration")


def atempo_factor(dur: float, slot: float) -> float:
    """ffmpeg atempo factor (>1 = faster) so a line fills its slot; clamped to keep the voice natural."""
    if dur <= 0 or slot <= 0:
        return 1.0
    if dur > slot:
        f = dur / slot
    elif dur < 0.7 * slot:
        f = dur / (0.9 * slot)
    else:
        f = 1.0
    return round(min(max(f, LIMIT_ATEMPO[0]), LIMIT_ATEMPO[1]), 4)


def _ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise SplitError("ffmpeg is needed for --thai-vocal split")
    return exe


def _atempo(x, sr: int, factor: float):
    import numpy as np
    if abs(factor - 1.0) < 0.01:
        return x
    p = subprocess.run([_ffmpeg(), "-v", "error", "-f", "f32le", "-ar", str(sr), "-ac", "1", "-i", "-",
                        "-af", "atempo=%.4f" % factor, "-f", "f32le", "-"],
                       input=np.asarray(x, dtype=np.float32).tobytes(), capture_output=True, check=True)
    return np.frombuffer(p.stdout, dtype=np.float32).copy()


def _trim(x, thr: float = 0.01):
    import numpy as np
    idx = np.where(np.abs(x) > thr)[0]
    return x[idx[0]:idx[-1] + 1] if len(idx) else x


def retune(x, sr: int, style: str, line_index: int, keyscale: str):
    """WORLD re-synthesis with a new f0 track (styles snap / melody)."""
    import numpy as np
    try:
        import pyworld as pw  # type: ignore
    except ImportError as e:
        raise SplitError("style %r needs pyworld (pip install pyworld 'setuptools<81'); "
                         "or use --split-style rap" % style) from e
    tonic, scale = parse_key(keyscale)
    xd = np.asarray(x, dtype=np.float64)
    f0, t = pw.harvest(xd, sr, f0_floor=70, f0_ceil=600, frame_period=5.0)
    sp = pw.cheaptrick(xd, f0, t, sr)
    ap = pw.d4c(xd, f0, t, sr)
    voiced = f0 > 0
    nf = np.zeros_like(f0)
    if style == "snap" and voiced.any():
        midi = 69 + 12 * np.log2(np.where(voiced, f0, 1.0) / 440.0)
        centre = snap_to_scale(64, tonic, scale)  # around E4: a comfortable female range
        midi = midi + (centre - np.median(midi[voiced]))
        for i in np.where(voiced)[0]:
            nf[i] = 440.0 * 2 ** ((snap_to_scale(midi[i], tonic, scale) - 69) / 12.0)
    elif style == "melody":
        degs = MELODY_DEGREES[line_index % len(MELODY_DEGREES)]
        i = k = 0
        prev = 0.0
        while i < len(f0):
            if not voiced[i]:
                i += 1
                continue
            j = i
            while j < len(f0) and voiced[j]:
                j += 1
            n = j - i
            if n >= 4:  # >= 20 ms counts as a syllable
                target = 440.0 * 2 ** ((degree_to_midi(degs[k % len(degs)], tonic, scale) - 69) / 12.0)
                curve = np.full(n, target)
                g = min(4, n)
                curve[:g] = np.linspace(prev or target, target, g)
                curve *= 1 + 0.008 * np.sin(2 * np.pi * 5.5 * np.arange(n) * 0.005)  # light vibrato
                nf[i:j] = curve
                prev = target
                k += 1
            i = j
    y = pw.synthesize(nf, sp, ap, sr, frame_period=5.0)
    return np.asarray(y, dtype=np.float32)


def make_vocal(lines: List[str], bpm: float, duration: float, keyscale: str, style: str = DEFAULT_STYLE,
               voice: str = DEFAULT_VOICE, seed: int = 42, tts=None):
    """Return (samples float32, sample_rate, per-line info) for the vocal track."""
    import numpy as np
    if style not in STYLES:
        raise SplitError(f"split style must be one of {', '.join(STYLES)}")
    if not lines:
        raise SplitError("--thai-vocal split needs lyrics")
    if tts is None:
        from ..tth import WayuEngine
        if not WayuEngine.available():
            raise SplitError('--thai-vocal split needs the local Wayu voice: pip install "terai-router[tth]"')
        tts = WayuEngine().load()
    from ..tth import prepare
    sr = int(tts.sample_rate)
    starts, slot = line_starts(len(lines), bpm, duration)
    total = int(round(duration * sr))
    voc = np.zeros(total, dtype=np.float32)
    info = []
    for i, (line, st) in enumerate(zip(lines, starts)):
        text = prepare(line, polite="ค่ะ").replace("\n", " ") or line
        x = _trim(np.asarray(tts(text, voice=voice, seed=seed + i, speed=1.0), dtype=np.float32))
        f = atempo_factor(len(x) / sr, slot)
        y = _atempo(x, sr, f)
        if style != "rap":
            y = retune(y, sr, style, i, keyscale)
        y = y / (float(np.max(np.abs(y))) + 1e-9) * 0.9
        a = int(round(st * sr))
        b = min(total, a + len(y))
        voc[a:b] += y[:b - a]
        info.append({"line": i, "start_s": round(st, 2), "raw_s": round(len(x) / sr, 2), "atempo": f,
                     "out_s": round(len(y) / sr, 2)})
    return voc, sr, info


def mix(instrumental: Path, vocal_wav: Path, out: Path, duration: float) -> None:
    """Music at 0.55, ducked by the vocal (sidechain, ratio 3), vocal on top, limited, trimmed to duration."""
    fc = ("[0:a]aresample=48000,volume=0.55[m];[1:a]aresample=48000,asplit=2[v1][v2];"
          "[m][v1]sidechaincompress=threshold=0.05:ratio=3:attack=20:release=300[md];"
          f"[md][v2]amix=inputs=2:duration=longest:normalize=0,alimiter=limit=0.95,"
          f"apad=whole_dur={duration:g},atrim=0:{duration:g}[o]")
    cmd = [_ffmpeg(), "-v", "error", "-y", "-i", str(instrumental), "-i", str(vocal_wav),
           "-filter_complex", fc, "-map", "[o]", "-ac", "2"]
    cmd += ["-b:a", "128k"] if out.suffix.lower() == ".mp3" else ["-c:a", "pcm_s16le"]
    subprocess.run(cmd + [str(out)], check=True, capture_output=True)


def generate_split(fields: Dict[str, object], thai_lyrics: str, out: Path, style: str = DEFAULT_STYLE,
                   voice: str = DEFAULT_VOICE, quant: Optional[str] = None, seed: int = 42, steps: int = 8,
                   generate_fn=None, tts=None) -> Dict[str, object]:
    """Instrumental from ACE-Step + Wayu vocal, mixed into ``out``."""
    import numpy as np
    from . import DEFAULT_QUANT
    from .engine import generate
    from ..tth import write_wav
    generate_fn = generate_fn or generate
    lines = lyric_lines(thai_lyrics)
    inst_fields = dict(fields)
    inst_fields["lyrics"] = "[Instrumental]"
    inst_fields["vocal_language"] = ""
    inst_fields["keyscale"] = fields.get("keyscale") or DEFAULT_KEY  # fixed key so the vocal can follow it
    cap = str(inst_fields.get("caption") or "")
    cap = ", ".join(p.strip() for p in cap.split(",")
                    if p.strip() and not re.search(r"\b(vocals?|singing|singer|sung|choir)\b", p, re.I))
    if "instrumental" not in cap.lower():
        cap = (cap + ", instrumental") if cap else "instrumental"
    inst_fields["caption"] = cap
    duration = float(inst_fields.get("duration") or 30.0)
    bpm = float(inst_fields.get("bpm") or 90)
    out = Path(out)
    with tempfile.TemporaryDirectory(prefix="muml-split-") as td:
        inst = Path(td) / "inst.wav"
        r = generate_fn(inst_fields, inst, quant=quant or DEFAULT_QUANT, seed=seed, steps=steps)
        t0 = time.time()
        voc, sr, info = make_vocal(lines, bpm, duration, str(inst_fields["keyscale"]), style, voice, seed, tts)
        vw = Path(td) / "vocal.wav"
        write_wav(str(vw), np.asarray(voc, dtype=np.float32), sr)
        out.parent.mkdir(parents=True, exist_ok=True)
        mix(inst, vw, out, duration)
        vocal_wall = round(time.time() - t0, 1)
    r = dict(r)
    r.update({"out": str(out), "thai_vocal": "split", "split_style": style, "voice": voice,
              "vocal_wall_s": vocal_wall, "lines": info,
              "license_note": "vocal by Wayu-Paxa-TTS-Edge (CC-BY-NC-4.0): non-commercial use only"})
    return r
