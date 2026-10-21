"""Temmo before/after bench on a fixed set of Thai and English game prompts.

  before: --mode template  (Gemma fills a design JSON into the maze template; the old pipeline)
  after:  --mode code      (Gemma writes the rules and the game code; playtest, repair/retry, template fallback)

Metrics: playable rate (passes its automatic playtest), distinct mechanics among playable games, seconds per
game, fallback rate, and for code mode how far apart the generated programs are (token Jaccard).
Run with a Python that has llama-cpp-python and playwright, e.g.
  TERAI_MODELS_DIR=... TEMMO_GEMMA_THREADS=4 python eval/temmo_codegen_bench.py --mode code --out /tmp/bench
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

PROMPTS = [
    ("th1", "กบกระโดดข้ามถนนที่มีรถวิ่งเพื่อไปถึงบ่อน้ำ"),
    ("th2", "ยานอวกาศยิงอุกกาบาตที่ตกลงมา"),
    ("th3", "แมวรับปลาที่ตกจากฟ้า ห้ามรับระเบิด"),
    ("en1", "a paddle bounces a ball to break bricks"),
    ("en2", "a snake eats apples and grows longer"),
    ("en3", "a runner jumps over cactus obstacles in the desert"),
]


def tokens(code: str) -> set:
    return set(re.findall(r"[A-Za-z_]\w+", code))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["code", "template"], required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--provider", default="local")
    ap.add_argument("--only", default="", help="comma list of prompt ids")
    ap.add_argument("--attempts", type=int, default=3)
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for pid, idea in PROMPTS:
        if a.only and pid not in a.only.split(","):
            continue
        t = time.time()
        d = out / a.mode / pid
        try:
            row = run_one(a, pid, idea, d)
        except Exception as e:  # a crash counts as not playable
            row = {"id": pid, "idea": idea, "engine": a.mode if a.mode == "template" else "crash", "playable": False,
                   "mechanic": None, "error": f"{type(e).__name__}: {str(e)[:200]}"}
        row["seconds"] = round(time.time() - t, 1)
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        (out / f"{a.mode}.json").write_text(json.dumps({"rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
    return summarize(a, out, rows)


def run_one(a, pid, idea, d):
    if a.mode == "code":
        from terai_router.temmo import codegen
        r = codegen.build(idea, d, provider=a.provider, attempts=a.attempts)
        row = {"id": pid, "idea": idea, "engine": r["engine"], "playable": r["passed"], "mechanic": r.get("mechanic"),
               "title": r.get("title"), "attempts": len(r["attempts"]),
               "attempt_errors": [x.get("error") for x in r["attempts"]],
               "ends": (r.get("test") or {}).get("checks", {}).get("ends"), "fallback_error": r.get("fallback_error")}
    else:
        from terai_router.temmo.pipeline import build
        r = build(idea, d, roles={k: a.provider for k in ("design", "code", "repair", "review")}, voice=False,
                  screenshots=False)
        tt = r.get("test") or {}
        row = {"id": pid, "idea": idea, "engine": "template", "playable": bool(tt.get("passed")), "mechanic": "maze",
               "title": r["gdd"]["title"], "result": tt.get("result")}
    return row


def summarize(a, out, rows):
    n = len(rows)
    play = [r for r in rows if r["playable"]]
    summary = {
        "mode": a.mode, "games": n,
        "playable": len(play), "playable_rate": round(len(play) / n, 3) if n else 0,
        "code_mode_playable": sum(1 for r in rows if r["engine"] == "code" and r["playable"]),
        "fallback": sum(1 for r in rows if a.mode == "code" and r["engine"] == "template"),
        "distinct_mechanics": sorted({r["mechanic"] for r in play}),
        "seconds_mean": round(sum(r["seconds"] for r in rows) / n, 1) if n else 0,
        "seconds_max": max((r["seconds"] for r in rows), default=0),
    }
    if a.mode == "code":
        codes = [(out / "code" / r["id"] / "game.js").read_text(encoding="utf-8") for r in rows
                 if r["engine"] == "code" and (out / "code" / r["id"] / "game.js").exists()]
        sims = [len(tokens(x) & tokens(y)) / max(1, len(tokens(x) | tokens(y))) for x, y in itertools.combinations(codes, 2)]
        summary["code_jaccard_mean"] = round(sum(sims) / len(sims), 3) if sims else None
    (out / f"{a.mode}.json").write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1),
                                        encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
