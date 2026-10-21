"""Score the MUML 1.0 HIQ eval set: BPM adherence (librosa beat tracking) and CLAP.

Needs librosa, torch and transformers (not TER-AI runtime deps).
Usage: python eval/muml_hiq_score.py OUT_DIR [--clap laion/larger_clap_music]
Writes OUT_DIR/scores.jsonl and OUT_DIR/summary.json.

BPM: librosa.beat.beat_track on the generated audio.
  strict  = |est - target| / target <= 5%
  octave  = same, but est*2 and est/2 also count (beat trackers often lock to
            half or double time)
CLAP: cosine similarity between the audio embedding and an English reference
description of what the prompt asked for (the same text for base and HIQ).
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path


def bpm_scores(est: float, target: float):
    err = abs(est - target) / target
    best = min(abs(e - target) / target for e in (est, est * 2, est / 2))
    return err, best


def _emb(x):
    # transformers 4.x returns a tensor, 5.x a ModelOutput
    if hasattr(x, "norm"):
        return x
    for k in ("pooler_output", "audio_embeds", "text_embeds"):
        v = getattr(x, k, None)
        if v is not None:
            return v
    return x[0]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--clap", default="laion/larger_clap_music")
    ap.add_argument("--no-clap", action="store_true")
    a = ap.parse_args(argv)
    out = Path(a.out)
    rows = [json.loads(l) for l in (out / "gen_results.jsonl").open(encoding="utf-8")]

    import librosa
    import numpy as np

    model = proc = None
    if not a.no_clap:
        import torch
        from transformers import ClapModel, ClapProcessor
        torch.set_num_threads(4)
        model = ClapModel.from_pretrained(a.clap).eval()
        proc = ClapProcessor.from_pretrained(a.clap)

    scored = []
    for r in rows:
        s = dict(r)
        if r["ok"] and r.get("wav"):
            y, sr = librosa.load(r["wav"], sr=22050, mono=True)
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            est = float(np.atleast_1d(tempo)[0])
            err, best = bpm_scores(est, r["target_bpm"])
            s.update(est_bpm=round(est, 1), bpm_err=round(err, 4), bpm_err_octave=round(best, 4),
                     bpm_strict=err <= 0.05, bpm_octave=best <= 0.05)
            if model is not None:
                import torch
                y48, _ = librosa.load(r["wav"], sr=48000, mono=True)
                with torch.no_grad():
                    ai = proc(audio=[y48], sampling_rate=48000, return_tensors="pt")
                    ae = _emb(model.get_audio_features(**ai))
                    ti = proc(text=[r["ref"]], return_tensors="pt", padding=True)
                    te = _emb(model.get_text_features(**ti))
                    ae = ae / ae.norm(dim=-1, keepdim=True)
                    te = te / te.norm(dim=-1, keepdim=True)
                s["clap"] = round(float((ae * te).sum()), 4)
        scored.append(s)
        print(r["id"], r["cond"], s.get("est_bpm"), r["target_bpm"], s.get("clap"), flush=True)

    with (out / "scores.jsonl").open("w", encoding="utf-8") as f:
        for s in scored:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    def agg(sel):
        okr = [s for s in sel if s["ok"]]
        d = {"n": len(sel), "success": len(okr)}
        if okr:
            d.update(
                bpm_strict_acc=round(sum(s["bpm_strict"] for s in okr) / len(okr), 3),
                bpm_octave_acc=round(sum(s["bpm_octave"] for s in okr) / len(okr), 3),
                bpm_err_octave_median=round(st.median(s["bpm_err_octave"] for s in okr), 4),
                wall_s_median=round(st.median(s["wall_s"] for s in okr), 1),
                wall_s_max=max(s["wall_s"] for s in okr),
                peak_rss_mb_max=max((s["peak_rss_mb"] or 0) for s in okr),
                dit_ms_median=round(st.median(s.get("dit_ms", 0) for s in okr), 0),
                vae_ms_median=round(st.median(s.get("vae_ms", 0) for s in okr), 0),
                load_ms_median=round(st.median(s.get("load_ms", 0) for s in okr), 0),
            )
            if all("clap" in s for s in okr):
                d["clap_mean"] = round(st.mean(s["clap"] for s in okr), 4)
        return d

    summary = {}
    for cond in ("base", "hiq"):
        sel = [s for s in scored if s["cond"] == cond]
        summary[cond] = {"all": agg(sel),
                         "th": agg([s for s in sel if s["lang"] == "th"]),
                         "en": agg([s for s in sel if s["lang"] == "en"])}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
