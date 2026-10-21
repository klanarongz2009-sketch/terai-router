"""YuE2-3B engine for songs with Thai lyrics (yue2.cpp ``yue-synth`` on CPU).

Chosen by Bogus on 2026-10-21 after listening: YuE2 sings the Thai script
(native, not romanised) more clearly than ACE-Step 1.5. Same lyrics, seed 42,
30 s, CPU 4 threads: CER 0.9065, 4/30 lyric words found in lyric order
(ACE-Step best C: 0.8411, 5/30 scattered), 14:38 wall, 3.22 GB peak RSS.

The weights are CC-BY-NC-4.0 (m-a-p): songs made with this engine are
non-commercial only. yue2.cpp itself is MIT. No weights live in this repo.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .engine import HiqError, home, models_dir, require_build_tools

MODEL_NAME = "YuE2-3B"
MODEL_URL = "https://huggingface.co/m-a-p/YuE2-3B"
VAE_URL = "https://huggingface.co/m-a-p/YuE2-Vae"
LICENSE = "CC-BY-NC-4.0"
LICENSE_URL = "https://creativecommons.org/licenses/by-nc/4.0/"
GGUF_REPO = "Serveurperso/YuE2-GGUF"
GGUF_URL = "https://huggingface.co/Serveurperso/YuE2-GGUF"
RUNTIME_REPO = "https://github.com/ServeurpersoCom/yue2.cpp"
RUNTIME_COMMIT = "8af01740686824ffd4a1839a457954f42e2a8ce7"  # 2026-10-16, "ggml: fork rebase"

MODEL_FILES = {
    "Q5_K_M": "YuE2-3B-Q5_K_M.gguf",
    "Q6_K": "YuE2-3B-Q6_K.gguf",
    "Q8_0": "YuE2-3B-Q8_0.gguf",
}
DEFAULT_QUANT = "Q5_K_M"
VAE_FILE = "YuE2-Vae-F32.gguf"
DEFAULT_STEPS = 32
# KV cache cap: model card, 65 s song in Q8_0 peaks at 5.8 GB with the full context, 3.8 GB with 8192.
MAX_SEQ = 8192
# Measured 2026-10-21 on an 8-vCPU / 8 GB VM (4 threads): 30 s song = 14:38 and 13:40.
MINUTES_PER_30S = 15
FRAME_RATE = 25  # semantic frames per second (yue2.cpp YUE2_FRAME_RATE)
# yue-synth caps the semantic stage at duration * 25 frames and stops there, mid-phrase if the song is longer.
# Rough song length from the lyrics, measured on the seed 42 plan of the 4-line Thai test song at 87 BPM:
# a 9 bar intro, then 10 bars for the 2 verse lines. Outro bars leave room for the song to end on its own.
INTRO_BARS = 9
BARS_PER_LINE = 5
OUTRO_BARS = 4
ESTIMATE_BPM = 90
MAX_DURATION = 240.0
# Context the prompt (tags, lyrics, the planned score) needs besides the semantic frames.
PROMPT_RESERVE = 3000

LICENSE_WARNING = ("license: YuE2-3B weights are CC-BY-NC-4.0 (m-a-p). The song made with this engine "
                   "is for NON-COMMERCIAL use only. Credit: YuE2-3B by m-a-p.")


def cpu_threads() -> int:
    """Threads yue2.cpp uses on CPU: one per physical core (logical / 2), set inside the runtime."""
    return max(1, (os.cpu_count() or 2) // 2)


def eta_minutes(duration: float) -> int:
    return max(1, round(MINUTES_PER_30S * float(duration) / 30.0))


def eta_message(duration: float) -> str:
    return (f"note: YuE2-3B on CPU takes about {MINUTES_PER_30S} min per 30 s of song "
            f"(this {float(duration):g} s song: ~{eta_minutes(duration)} min, {cpu_threads()} threads)")


def find_binary() -> Optional[Path]:
    """yue-synth: $TERAI_YUE2_BIN, on PATH, or in the --setup build."""
    env = os.environ.get("TERAI_YUE2_BIN")
    if env and Path(env).is_file():
        return Path(env)
    w = shutil.which("yue-synth")
    if w:
        return Path(w)
    p = home() / "yue2.cpp" / "build" / "yue-synth"
    return p if p.is_file() else None


def required_files(quant: str = DEFAULT_QUANT) -> List[str]:
    if quant not in MODEL_FILES:
        raise HiqError(f"unknown YuE2 quant {quant!r}; choose one of: {', '.join(MODEL_FILES)}")
    return [MODEL_FILES[quant], VAE_FILE]


def missing_files(quant: str = DEFAULT_QUANT) -> List[str]:
    d = models_dir()
    return [f for f in required_files(quant) if not (d / f).is_file()]


def status(quant: str = DEFAULT_QUANT) -> Dict[str, object]:
    b = find_binary()
    miss = missing_files(quant)
    return {"binary": str(b) if b else None, "models_dir": str(models_dir()), "missing_models": miss,
            "quant": quant, "runtime_commit": RUNTIME_COMMIT, "ready": bool(b) and not miss}


def _download(name: str, dest: Path, log) -> None:
    url = f"https://huggingface.co/{GGUF_REPO}/resolve/main/{name}"
    log(f"downloading {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url) as r, open(tmp, "wb") as f:  # noqa: S310 (fixed https host)
        shutil.copyfileobj(r, f, 1 << 20)
    tmp.replace(dest)


def setup(quant: str = DEFAULT_QUANT, build: bool = True, log=print) -> Dict[str, object]:
    """Fetch the YuE2 GGUF files and build yue2.cpp at the pinned commit (git, cmake, C++17)."""
    # Check git/cmake/C++ before the ~3.2 GB download: a clean machine often has no cmake
    # (2026-10-21 clean run: weights fetched, then "[Errno 2] No such file or directory: 'cmake'").
    need_build = build and not find_binary()
    tools = require_build_tools("yue2.cpp", "TERAI_YUE2_BIN") if need_build else {}
    d = models_dir()
    d.mkdir(parents=True, exist_ok=True)
    for name in missing_files(quant):
        log(f"fetching {name} from {GGUF_REPO}")
        _download(name, d / name, log)
    if need_build:
        git, cmake = tools["git"], tools["cmake"]
        src = home() / "yue2.cpp"
        if not src.exists():
            subprocess.run([git, "clone", RUNTIME_REPO, str(src)], check=True)
        subprocess.run([git, "checkout", RUNTIME_COMMIT], cwd=src, check=True)
        subprocess.run([git, "submodule", "update", "--init", "--recursive"], cwd=src, check=True)
        bdir = src / "build"
        bdir.mkdir(parents=True, exist_ok=True)
        subprocess.run([cmake, "..", "-DCMAKE_BUILD_TYPE=Release"], cwd=bdir, check=True)
        subprocess.run([cmake, "--build", ".", "--config", "Release", "-j", str(os.cpu_count() or 4),
                        "--target", "yue-synth"], cwd=bdir, check=True)
    return status(quant)


def lyric_sections(lyrics: str) -> List[Tuple[str, int]]:
    """(section tag, sung lines) in order; lines before any tag count as 'verse'."""
    out: List[Tuple[str, int]] = []
    for raw in (lyrics or "").splitlines():
        s = raw.strip()
        if not s:
            continue
        m = re.fullmatch(r"\[([^\]]+)\]", s)
        if m:
            out.append((m.group(1).strip().lower(), 0))
        else:
            if not out:
                out.append(("verse", 0))
            out[-1] = (out[-1][0], out[-1][1] + 1)
    return out


def recommended_duration(lyrics: str, bpm: Optional[int] = None) -> float:
    """Seconds a YuE2 song needs to sing every lyric line (intro + 5 bars a line + outro), 5 s steps, <= 240."""
    lines = sum(n for _, n in lyric_sections(lyrics))
    if not lines:
        return 30.0
    bars = INTRO_BARS + BARS_PER_LINE * lines + OUTRO_BARS
    sec = bars * 240.0 / float(bpm or ESTIMATE_BPM)
    return float(min(MAX_DURATION, max(30.0, 5 * math.ceil(sec / 5))))


def max_seq_for(duration: float) -> int:
    """KV context: 8192 unless the frames of a long song plus the prompt need more (1024 steps)."""
    need = int(float(duration) * FRAME_RATE) + PROMPT_RESERVE
    return max(MAX_SEQ, 1024 * math.ceil(need / 1024))


def plan_sections(abc: str) -> List[Dict[str, object]]:
    """Sections of the score YuE2 planned: name, start and length in seconds (bars of the vocal voice)."""
    m = re.search(r"^Q:\s*1/4\s*=\s*(\d+)", abc or "", re.M)
    if not m:
        return []
    bar_s = 4 * 60.0 / int(m.group(1))
    secs: List[Dict[str, object]] = []
    voice = None
    for line in abc.splitlines():
        s = line.strip()
        if s.startswith("%"):
            secs.append({"name": s[1:].strip(), "bars": 0})
            voice = None
        elif s.startswith("V:"):
            voice = "vocal" if s[2:].strip().startswith("Vocal") else "other"
        elif secs and voice == "vocal" and s and not re.match(r"^[A-Z]:", s):
            for tok in s.split("|"):
                tok = tok.strip()
                if not tok:
                    continue
                z = re.fullmatch(r"Z(\d*)", tok)
                secs[-1]["bars"] += int(z.group(1) or 1) if z else 1
    t = 0.0
    for sec in secs:
        sec["start_s"] = round(t, 1)
        sec["length_s"] = round(sec["bars"] * bar_s, 1)
        t += sec["bars"] * bar_s
    return secs


def reach_report(replay: Dict[str, object], duration: float) -> Dict[str, object]:
    """How far the song got: frames drawn, whether the duration cut it, and which planned sections fit."""
    toks = [t for t in str(replay.get("semantic_tokens") or "").split(",") if t.strip()]
    seconds = len(toks) / float(FRAME_RATE)
    budget = int(float(duration) * FRAME_RATE)
    plan = plan_sections(str(replay.get("abc") or ""))
    reached = []
    for sec in plan:
        start, end = float(sec["start_s"]), float(sec["start_s"]) + float(sec["length_s"])
        if start >= seconds:
            state = "not reached"
        elif end <= seconds + 0.5:
            state = "complete"
        else:
            state = f"cut at {seconds - start:.1f} of {end - start:.1f} s"
        reached.append({"section": sec["name"], "start_s": sec["start_s"], "length_s": sec["length_s"],
                        "state": state})
    # Lyric sections the score never planned are not sung at any duration (seed 42 test song: no chorus planned).
    planned = [str(s["name"]).lower() for s in plan]
    unplanned, i = [], 0
    for tag, _ in lyric_sections(str(replay.get("lyrics") or "")):
        j = planned.index(tag, i) if tag in planned[i:] else -1
        if j < 0:
            unplanned.append(tag)
        else:
            i = j + 1
    return {"frames": len(toks), "seconds": round(seconds, 2), "cut_by_duration": len(toks) >= budget > 0,
            "plan_s": round(sum(float(s["length_s"]) for s in plan), 1), "sections": reached,
            "unplanned_lyrics": unplanned}


def build_style(fields: Dict[str, object]) -> str:
    """YuE2 style tags from the adapter fields: caption, then BPM / key when set."""
    parts = [str(fields.get("caption") or "").strip().rstrip(",")]
    if fields.get("bpm"):
        parts.append(f"{int(fields['bpm'])} BPM")
    if fields.get("keyscale"):
        parts.append(str(fields["keyscale"]))
    return ", ".join(p for p in parts if p)


def build_request(fields: Dict[str, object], lyrics: str, seed: int = 42, steps: int = DEFAULT_STEPS,
                  fmt: str = "mp3") -> Dict[str, object]:
    """Request JSON for yue-synth. Lyrics go in verbatim (Thai script, section tags kept)."""
    return {"style": build_style(fields), "lyrics": lyrics, "duration": float(fields.get("duration") or 30.0),
            "lm_seed": int(seed), "seed": int(seed), "steps": int(steps), "output_format": fmt}


def build_argv(binary: Path, request_path: str, out_path: str, quant: str = DEFAULT_QUANT,
               max_seq: Optional[int] = None, duration: float = 30.0) -> List[str]:
    if max_seq is None:
        max_seq = max_seq_for(duration)
    d = models_dir()
    return [str(binary), "--model", str(d / MODEL_FILES[quant]), "--vae", str(d / VAE_FILE),
            "--max-seq", str(int(max_seq)), "--request", request_path, "--out", out_path]


def generate(fields: Dict[str, object], lyrics: str, out: Path, quant: str = DEFAULT_QUANT, seed: int = 42,
             steps: int = DEFAULT_STEPS) -> Dict[str, object]:
    b = find_binary()
    if not b:
        raise HiqError("yue-synth (yue2.cpp) not found. Run `terai muml --hiq --setup` (builds yue2.cpp at "
                       f"commit {RUNTIME_COMMIT[:7]}), or set TERAI_YUE2_BIN to a built yue-synth, "
                       "or use --vocal-engine ace|split.")
    miss = missing_files(quant)
    if miss:
        raise HiqError("YuE2 model files missing in %s: %s. Run `terai muml --hiq --setup` or download them from "
                       "%s into that folder (or set TERAI_MUML_HIQ_MODELS)." % (models_dir(), ", ".join(miss), GGUF_URL))
    out = Path(out)
    fmt = "mp3" if out.suffix.lower() == ".mp3" else "wav16"
    req = build_request(fields, lyrics, seed, steps, fmt)
    with tempfile.TemporaryDirectory(prefix="muml-yue2-") as td:
        rq = Path(td) / "request.json"
        rq.write_text(json.dumps(req, ensure_ascii=False), encoding="utf-8")
        tmp_out = Path(td) / ("song.mp3" if fmt == "mp3" else "song.wav")
        argv = build_argv(b, str(rq), str(tmp_out), quant, duration=float(req["duration"]))
        t0 = time.time()
        p = subprocess.run(argv, cwd=td, capture_output=True, text=True, errors="replace")
        wall = time.time() - t0
        if p.returncode != 0 or not tmp_out.is_file():
            tail = "\n".join(((p.stderr or "") + (p.stdout or "")).strip().splitlines()[-8:])
            raise HiqError(f"yue-synth failed (rc={p.returncode}):\n{tail}")
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp_out), str(out))
        reach = None
        side = tmp_out.with_suffix(".json")  # yue-synth writes the replay request (score + frames) beside the song
        if side.is_file():
            replay_path = out.with_name(out.stem + ".yue2.json")
            shutil.move(str(side), str(replay_path))
            try:
                reach = reach_report(json.loads(replay_path.read_text(encoding="utf-8")), float(req["duration"]))
                reach["replay"] = str(replay_path)
            except (ValueError, OSError):
                reach = None
    return {"out": str(out), "wall_s": round(wall, 1), "engine": "yue2", "quant": quant,
            "threads": cpu_threads(), "request": req, "license": LICENSE, "reach": reach}
