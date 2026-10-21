"""Measure SANKPUP with a real local Gemma 4 model (not run by pytest).

Usage:
    TERAI_MODELS_DIR=/path/to/models python eval/sankpup_gemma_bench.py --model e2b --out bench.jsonl

For every prompt it records whether the first reply was valid SVG as-is,
valid after repair, valid after a retry, the time and the token count, and
renders the result to PNG and JPG so the pictures can be inspected.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from terai_router.sankpup import gemma, save  # noqa: E402
from terai_router.sankpup import Artwork  # noqa: E402
from terai_router.sankpup.sanitize import SvgError  # noqa: E402

PROMPTS = [
    ("th", "แมวสีส้มนั่งบนดวงจันทร์"),
    ("th", "บ้านหลังเล็กกับต้นไม้สองต้น ตอนกลางคืน"),
    ("th", "เรือใบสีแดงกลางทะเล"),
    ("th", "หุ่นยนต์ถือดอกไม้"),
    ("th", "ภูเขากับพระอาทิตย์ตก"),
    ("th", "จรวดบินไปดาวอังคาร"),
    ("en", "an orange cat sitting on the moon"),
    ("en", "a small house with two trees at night"),
    ("en", "a red sailboat on the sea"),
    ("en", "a robot holding a flower"),
    ("en", "mountains at sunset"),
    ("en", "a rocket flying to Mars"),
]


def failure_type(message: str) -> str:
    m = message.lower()
    for key, kind in (("timed out", "timeout"), ("invalid xml", "invalid_xml"), ("draws nothing", "draws_nothing"),
                      ("no <svg", "no_svg"), ("not <svg>", "no_svg"), ("doctype", "doctype"), ("limit", "too_big")):
        if key in m:
            return kind
    return "other"


def is_blank(png_path: Path) -> bool:
    """Valid means the render is not one flat colour (luma spread of at least 8)."""
    from PIL import Image
    lo, hi = Image.open(png_path).convert("L").getextrema()
    return hi - lo < 8


def summarize(path: str) -> dict:
    """valid-SVG rate (XML parses, sanitizer accepts, renders, not blank), latency p50/p95, failure types."""
    import statistics
    rows = [json.loads(line) for line in open(path, encoding="utf-8")]
    head = [r for r in rows if "model" in r]
    runs = [r for r in rows if "i" in r]
    secs = sorted(r["seconds"] for r in runs)
    p95 = secs[max(0, -(-len(secs) * 95 // 100) - 1)] if secs else None
    fails: dict = {}
    for r in runs:
        if not r["ok"]:
            kind = r.get("failure") or failure_type(r.get("error", ""))
            fails[kind] = fails.get(kind, 0) + 1
    by_lang = {lang: f"{sum(r['ok'] for r in runs if r['lang'] == lang)}/{sum(r['lang'] == lang for r in runs)}"
               for lang in ("th", "en")}
    return {"model": head[-1]["model"] if head else None, "load_s": head[-1].get("load_s") if head else None,
            "valid": f"{sum(r['ok'] for r in runs)}/{len(runs)}", "by_lang": by_lang,
            "p50_s": statistics.median(secs) if secs else None, "p95_s": p95,
            "peak_rss_mb": max((r.get("peak_rss_mb") or 0) for r in runs) or None, "failures": fails}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="e2b")
    ap.add_argument("--out", default="sankpup_bench.jsonl")
    ap.add_argument("--images", default="sankpup_bench_images")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--start", type=int, default=1, help="first prompt number (1-based)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--summarize", metavar="JSONL", help="print the summary of an earlier run and exit")
    a = ap.parse_args()
    if a.summarize:
        print(json.dumps(summarize(a.summarize), ensure_ascii=False, indent=2))
        return 0
    backend = gemma.GemmaBackend(model=a.model, auto_download=False)
    t0 = time.time()
    backend._load()
    load_s = round(time.time() - t0, 2)
    out = open(a.out, "a", encoding="utf-8")
    out.write(json.dumps({"model": backend.label, "load_s": load_s}) + "\n")
    imgs = Path(a.images)
    first = max(1, a.start)
    prompts = PROMPTS[first - 1:]
    if a.limit:
        prompts = prompts[: a.limit]
    for i, (lang, prompt) in enumerate(prompts, first):
        start = time.time()
        row = {"i": i, "lang": lang, "prompt": prompt}
        try:
            svg, info = gemma.draw_svg(backend, prompt, attempts=2, seed=a.seed, timeout=a.timeout)
            row.update(ok=True, attempts=info["attempts"])
            art = Artwork(prompt, svg, "gemma", backend.label)
            png = save(art, imgs / f"{i:02d}-{lang}.png", save_code=True)[0]
            save(art, imgs / f"{i:02d}-{lang}.jpg")
            if is_blank(png):
                row.update(ok=False, failure="blank_render", error="render is one flat colour")
        except SvgError as exc:
            row.update(ok=False, failure=failure_type(str(exc)), error=str(exc))
        row["seconds"] = round(time.time() - start, 2)
        try:
            import resource
            row["peak_rss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
        except Exception:
            pass
        out.write(json.dumps(row, ensure_ascii=False) + "\n")
        out.flush()
        print(json.dumps(row, ensure_ascii=False)[:300], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
