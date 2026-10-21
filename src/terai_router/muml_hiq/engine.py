"""Run ACE-Step 1.5 through acestep.cpp's ``ace-synth`` on CPU."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Dict, Optional

from . import DEFAULT_LM, DEFAULT_QUANT, DIT_FILES, GGUF_REPO, LM_FILES, RUNTIME_COMMIT, RUNTIME_REPO, SHARED_FILES


class HiqError(RuntimeError):
    pass


def home() -> Path:
    return Path(os.environ.get("TERAI_MUML_HIQ_HOME", Path.home() / ".cache" / "terai" / "muml-hiq"))


def models_dir() -> Path:
    return Path(os.environ.get("TERAI_MUML_HIQ_MODELS", home() / "models"))


def find_binary() -> Optional[Path]:
    env = os.environ.get("TERAI_ACESTEP_BIN")
    if env and Path(env).is_file():
        return Path(env)
    w = shutil.which("ace-synth")
    if w:
        return Path(w)
    p = home() / "acestep.cpp" / "build" / "ace-synth"
    return p if p.is_file() else None


def find_lm_binary() -> Optional[Path]:
    """ace-lm: $TERAI_ACESTEP_LM_BIN, next to ace-synth, on PATH, or in the setup build."""
    env = os.environ.get("TERAI_ACESTEP_LM_BIN")
    if env and Path(env).is_file():
        return Path(env)
    s = find_binary()
    if s and (s.parent / "ace-lm").is_file():
        return s.parent / "ace-lm"
    w = shutil.which("ace-lm")
    if w:
        return Path(w)
    p = home() / "acestep.cpp" / "build" / "ace-lm"
    return p if p.is_file() else None


def needs_lm(fields: Dict[str, object]) -> bool:
    """Songs with lyrics need ace-lm first (it writes the audio codes the vocals follow)."""
    ly = str(fields.get("lyrics") or "").strip()
    return bool(ly) and ly.lower() != "[instrumental]"


def required_files(quant: str = DEFAULT_QUANT, lm: Optional[str] = None):
    if quant not in DIT_FILES:
        raise HiqError(f"unknown quant {quant!r}; choose one of: {', '.join(DIT_FILES)}")
    files = [DIT_FILES[quant], *SHARED_FILES]
    if lm:
        if lm not in LM_FILES:
            raise HiqError(f"unknown LM {lm!r}; choose one of: {', '.join(LM_FILES)}")
        files.append(LM_FILES[lm])
    return files


def missing_files(quant: str = DEFAULT_QUANT, lm: Optional[str] = None):
    d = models_dir()
    return [f for f in required_files(quant, lm) if not (d / f).is_file()]


def status(quant: str = DEFAULT_QUANT) -> Dict[str, object]:
    b = find_binary()
    return {"binary": str(b) if b else None, "models_dir": str(models_dir()),
            "missing_models": missing_files(quant), "quant": quant,
            "ready": bool(b) and not missing_files(quant)}


def _download(name: str, dest: Path, log) -> None:
    try:
        from huggingface_hub import hf_hub_download  # type: ignore
        hf_hub_download(GGUF_REPO, name, local_dir=str(dest.parent))
        return
    except ImportError:
        pass
    url = f"https://huggingface.co/{GGUF_REPO}/resolve/main/{name}"
    log(f"downloading {url}")
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url) as r, open(tmp, "wb") as f:  # noqa: S310 (fixed https host)
        shutil.copyfileobj(r, f, 1 << 20)
    tmp.replace(dest)


def setup(quant: str = DEFAULT_QUANT, build: bool = True, log=print, lm: Optional[str] = DEFAULT_LM) -> Dict[str, object]:
    """Fetch the GGUF weights and build ace-synth/ace-lm (needs git, cmake, a C++17 compiler)."""
    d = models_dir()
    d.mkdir(parents=True, exist_ok=True)
    for name in missing_files(quant, lm):
        log(f"fetching {name} from {GGUF_REPO}")
        _download(name, d / name, log)
    if build and not find_binary():
        src = home() / "acestep.cpp"
        if not src.exists():
            subprocess.run(["git", "clone", "--recurse-submodules", RUNTIME_REPO, str(src)], check=True)
            subprocess.run(["git", "checkout", RUNTIME_COMMIT], cwd=src, check=True)
            subprocess.run(["git", "submodule", "update", "--init", "--recursive"], cwd=src, check=True)
        bdir = src / "build"
        bdir.mkdir(exist_ok=True)
        subprocess.run(["cmake", "..", "-DGGML_BLAS=OFF", "-DCMAKE_BUILD_TYPE=Release"], cwd=bdir, check=True)
        subprocess.run(["cmake", "--build", ".", "--config", "Release", "-j", str(os.cpu_count() or 4)],
                       cwd=bdir, check=True)
    return status(quant)


def build_request(fields: Dict[str, object], quant: str, seed: int, steps: int, fmt: str,
                  lm: Optional[str] = None) -> Dict[str, object]:
    req = {k: fields[k] for k in ("caption", "lyrics", "bpm", "duration", "keyscale", "timesignature")
           if k in fields and fields[k] not in (None, "")}
    if fields.get("vocal_language"):
        req["vocal_language"] = fields["vocal_language"]
    req.update({"synth_model": DIT_FILES[quant], "seed": int(seed), "inference_steps": int(steps),
                "guidance_scale": 1.0, "shift": 3.0, "output_format": fmt})
    if lm and needs_lm(fields):
        req["lm_model"] = LM_FILES[lm]
    return req


# VAE tile size in latent frames (25 per second). acestep.cpp defaults to 1024
# (one tile for a 40 s song); 256 keeps a 30 s song near the RAM of a 10-15 s one.
DEFAULT_VAE_CHUNK = int(os.environ.get("TERAI_MUML_HIQ_VAE_CHUNK", "256"))


def generate(fields: Dict[str, object], out: Path, quant: str = DEFAULT_QUANT, seed: int = 42,
             steps: int = 8, vae_chunk: int = DEFAULT_VAE_CHUNK, lm: str = DEFAULT_LM) -> Dict[str, object]:
    """Render one song. ``fields`` comes from adapter.adapt(). Returns timing info.

    With lyrics, ace-lm runs first (writes audio codes + metadata into a new request
    JSON) and ace-synth renders that; without lyrics ace-synth runs alone.
    """
    b = find_binary()
    if not b:
        raise HiqError("ace-synth not found. Run `terai muml --hiq --setup` or set TERAI_ACESTEP_BIN.")
    use_lm = needs_lm(fields)
    lmb = None
    if use_lm:
        lmb = find_lm_binary()
        if not lmb:
            raise HiqError("ace-lm not found (needed for lyrics). Build acestep.cpp or set TERAI_ACESTEP_LM_BIN.")
    miss = missing_files(quant, lm if use_lm else None)
    if miss:
        raise HiqError("model files missing in %s: %s. Run `terai muml --hiq --setup`%s." % (
            models_dir(), ", ".join(miss), f" --lm-model {lm}" if use_lm else ""))
    out = Path(out)
    ext = out.suffix.lower()
    fmt = "mp3" if ext == ".mp3" else "wav16"
    req = build_request(fields, quant, seed, steps, fmt, lm=lm if use_lm else None)
    lm_wall = None
    with tempfile.TemporaryDirectory(prefix="muml-hiq-") as td:
        rq = Path(td) / "request.json"
        rq.write_text(json.dumps(req, ensure_ascii=False), encoding="utf-8")
        synth_req = rq.name
        if use_lm:
            t0 = time.time()
            p = subprocess.run([str(lmb), "--models", str(models_dir()), "--request", rq.name],
                               cwd=td, capture_output=True, text=True, errors="replace")
            lm_wall = round(time.time() - t0, 1)
            made = sorted(x.name for x in Path(td).iterdir() if x.suffix == ".json" and x.name != rq.name)
            if p.returncode != 0 or not made:
                tail = "\n".join((p.stderr or "").strip().splitlines()[-8:])
                raise HiqError(f"ace-lm failed (rc={p.returncode}):\n{tail}")
            synth_req = made[0]
        t0 = time.time()
        p = subprocess.run([str(b), "--models", str(models_dir()), "--request", synth_req,
                            "--vae-chunk", str(int(vae_chunk))],
                           cwd=td, capture_output=True, text=True, errors="replace")
        wall = time.time() - t0
        produced = sorted(x for x in Path(td).iterdir() if x.suffix in (".mp3", ".wav"))
        if p.returncode != 0 or not produced:
            tail = "\n".join((p.stderr or "").strip().splitlines()[-8:])
            raise HiqError(f"ace-synth failed (rc={p.returncode}):\n{tail}")
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(produced[0]), str(out))
    r = {"out": str(out), "wall_s": round(wall, 1), "request": req, "vae_chunk": int(vae_chunk)}
    if use_lm:
        r.update({"lm": lm, "lm_wall_s": lm_wall})
    return r
