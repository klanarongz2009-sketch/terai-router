"""Song endings: fade out a file that stops mid-phrase (any engine).

ACE-Step and YuE2 both stop at the requested duration whether the song has
ended or not: a YuE2 Thai song at 30 s ended at -19.6 dB RMS over its last
0.25 s, as loud as the middle of the song. The fade is applied only when the
last 0.25 s is louder than ``QUIET_DB``; a song that already ends quietly is
left alone. The fade is quadratic: on that YuE2 file a 2.5 s fade took the
last 0.25 s to -68.4 dB (a linear one only to -45.5 dB). Needs ffmpeg/ffprobe; without them the file is kept as is.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional

DEFAULT_FADE_S = 2.5
TAIL_S = 0.25
QUIET_DB = -40.0


def _have_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def audio_seconds(path: Path) -> Optional[float]:
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return float(p.stdout.strip())
    except ValueError:
        return None


def tail_rms_db(path: Path, seconds: float = TAIL_S) -> Optional[float]:
    """RMS level (dB FS, ffmpeg volumedetect mean_volume) of the last ``seconds``."""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-sseof", f"-{seconds}", "-i", str(path),
                        "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True)
    m = re.search(r"mean_volume:\s*(-?[\d.]+|-inf) dB", p.stderr)
    if not m:
        return None
    return float("-inf") if m.group(1) == "-inf" else float(m.group(1))


def apply_fade_out(path: Path, fade_s: float, total_s: float) -> None:
    path = Path(path)
    tmp = path.with_name(path.stem + ".fade" + path.suffix)
    codec = ["-c:a", "libmp3lame", "-b:a", "128k"] if path.suffix.lower() == ".mp3" else ["-c:a", "pcm_s16le"]
    start = max(0.0, total_s - fade_s)
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-y", "-i", str(path), "-af",
                        f"afade=t=out:st={start:.3f}:d={fade_s:.3f}:curve=qua", *codec, str(tmp)],
                       capture_output=True, text=True)
    if p.returncode != 0 or not tmp.is_file():
        tmp.unlink(missing_ok=True)
        raise RuntimeError("ffmpeg fade failed: " + " ".join(p.stderr.strip().splitlines()[-2:]))
    tmp.replace(path)


def finish_ending(path: Path, fade_s: float = DEFAULT_FADE_S) -> Dict[str, object]:
    """Fade the end of ``path`` in place when it stops while still loud. ``fade_s`` 0 turns it off."""
    info: Dict[str, object] = {"fade_out_s": 0.0}
    if fade_s <= 0:
        info["ending"] = "fade off"
        return info
    if not _have_ffmpeg():
        info["ending"] = "ffmpeg not found, no fade"
        return info
    total = audio_seconds(path)
    before = tail_rms_db(path) if total else None
    if not total or before is None:
        info["ending"] = "unreadable audio, no fade"
        return info
    info["tail_db_before"] = round(before, 1)
    if before <= QUIET_DB:
        info["ending"] = "already quiet"
        return info
    fade = min(float(fade_s), total / 2)
    apply_fade_out(path, fade, total)
    after = tail_rms_db(path)
    info.update({"ending": "faded", "fade_out_s": round(fade, 2),
                 "tail_db_after": None if after is None else round(after, 1)})
    return info
