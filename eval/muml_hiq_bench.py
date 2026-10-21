"""Generate the MUML 1.0 HIQ eval set: base (raw prompt) vs HIQ (prompt adapter).

Both conditions use the same ACE-Step 1.5 turbo GGUF weights, seed and duration.
  base : caption = the user's prompt verbatim, no metadata (what you get when the
         prompt is handed to ACE-Step as-is, without its 5Hz LM planner)
  hiq  : caption/bpm/key/timesignature from terai_router.muml_hiq.adapter

One ace-synth process per song, so every timing is a cold run (model load
included) exactly like `terai muml --hiq`. Peak RSS from /usr/bin/time -v.
Before each run it waits until cgroup anonymous memory leaves room, so it
queues behind other heavy jobs on the 8 GB VM instead of competing with them.

Usage: python eval/muml_hiq_bench.py --bin ACE_SYNTH --models DIR --out DIR
       [--quant Q4_K_M] [--duration 15] [--seed 42] [--only base|hiq]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from terai_router.muml_hiq.adapter import adapt  # noqa: E402


def anon_bytes() -> int:
    try:
        for line in open("/sys/fs/cgroup/memory.stat"):
            if line.startswith("anon "):
                return int(line.split()[1])
    except OSError:
        pass
    return 0


def wait_for_ram(limit_gb: float, log) -> float:
    t0 = time.time()
    while anon_bytes() > limit_gb * 1e9:
        if time.time() - t0 > 3600:
            break
        time.sleep(15)
    waited = time.time() - t0
    if waited > 1:
        log(f"  waited {waited:.0f}s for RAM (anon now {anon_bytes()/1e9:.2f} GB)")
    return waited


def wav_ok(path: Path) -> tuple[bool, float]:
    try:
        with wave.open(str(path)) as w:
            n = w.getnframes()
            sr = w.getframerate()
            data = w.readframes(min(n, sr * 60))
        dur = n / float(sr)
        # silent output = failure
        nonzero = sum(1 for b in data[::97] if b not in (0, 255))
        return dur > 1.0 and nonzero > 10, dur
    except Exception:
        return False, 0.0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True)
    ap.add_argument("--models", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--quant", default="Q4_K_M")
    ap.add_argument("--duration", type=float, default=15.0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--only", choices=["base", "hiq"], default=None)
    ap.add_argument("--ram-limit-gb", type=float, default=4.5)
    ap.add_argument("--cases", default=str(HERE / "muml_hiq_cases.json"))
    a = ap.parse_args(argv)

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    cases = json.load(open(a.cases, encoding="utf-8"))
    results_path = out / "gen_results.jsonl"
    done = set()
    if results_path.exists():
        for line in results_path.open(encoding="utf-8"):
            r = json.loads(line)
            done.add((r["id"], r["cond"]))
    logf = (out / "gen.log").open("a", encoding="utf-8")

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + "\n")
        logf.flush()

    conds = [a.only] if a.only else ["base", "hiq"]
    for c in cases:
        for cond in conds:
            if (c["id"], cond) in done:
                continue
            if cond == "base":
                req = {"caption": c["prompt"], "lyrics": "[Instrumental]"}
            else:
                ad = adapt(c["prompt"], duration=a.duration)
                req = {k: ad[k] for k in ("caption", "lyrics", "bpm", "keyscale", "timesignature")}
                if ad["vocal_language"]:
                    req["vocal_language"] = ad["vocal_language"]
            req.update({
                "synth_model": f"acestep-v15-turbo-{a.quant}.gguf",
                "duration": a.duration, "seed": a.seed,
                "inference_steps": 8, "guidance_scale": 1.0, "shift": 3.0,
                "output_format": "wav16",
            })
            d = out / f"{c['id']}__{cond}"
            d.mkdir(exist_ok=True)
            for f in d.glob("*.wav"):
                f.unlink()
            (d / "request.json").write_text(json.dumps(req, ensure_ascii=False, indent=2), encoding="utf-8")
            log(f"[{c['id']} / {cond}] caption={req['caption']!r} bpm={req.get('bpm', 0)}")
            waited = wait_for_ram(a.ram_limit_gb, log)
            t0 = time.time()
            p = subprocess.run(["/usr/bin/time", "-v", a.bin, "--models", a.models, "--request", "request.json"],
                               cwd=d, capture_output=True, text=True, errors="replace")
            wall = time.time() - t0
            err = p.stderr
            (d / "stderr.log").write_text(err, encoding="utf-8")
            m = re.search(r"Maximum resident set size \(kbytes\): (\d+)", err)
            peak_mb = int(m.group(1)) / 1024 if m else None
            stage = {"load_ms": sum(float(x) for x in re.findall(r"\[Store\] Load [^:]+: ([\d.]+) ms", err))}
            mm = re.search(r"\[DiT-Generate\] Total: ([\d.]+) ms", err)
            if mm:
                stage["dit_ms"] = float(mm.group(1))
            mm = re.search(r"\[VAE-Decode[^\]]*\] Decode: ([\d.]+) ms", err)
            if mm:
                stage["vae_ms"] = float(mm.group(1))
            wavs = sorted(d.glob("*.wav"))
            ok, dur = (wav_ok(wavs[0]) if wavs else (False, 0.0))
            ok = ok and p.returncode == 0
            r = {"id": c["id"], "lang": c["lang"], "cond": cond, "prompt": c["prompt"], "target_bpm": c["bpm"],
                 "ref": c["ref"], "request": req, "rc": p.returncode, "ok": ok, "wall_s": round(wall, 1),
                 "peak_rss_mb": round(peak_mb, 0) if peak_mb else None, "audio_s": round(dur, 2),
                 "wav": str(wavs[0]) if wavs else None, "waited_s": round(waited, 0), **stage}
            with results_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            log(f"  rc={p.returncode} ok={ok} wall={wall:.1f}s peak={peak_mb} MB audio={dur:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
