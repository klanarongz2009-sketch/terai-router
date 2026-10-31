#!/usr/bin/env python3
"""Reproducible, local-only intent-router scorecard.

    python eval/router_report.py
    python eval/router_report.py --threshold 0.80 --json /tmp/router-report.json

The inputs are the repository's frozen test_set.json and heldout_v07.json.
This reports router classification only; it does not evaluate chat quality, model
reasoning, Thai speech/vision, generated SVG, or cyber capabilities.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from terai_router import __version__, route  # noqa: E402

DEFAULT_DATASETS = (ROOT / "eval" / "test_set.json", ROOT / "eval" / "heldout_v07.json")


def flatten(path: Path) -> list[tuple[str, str, str]]:
    """Return (category, text, expected-intent) rows, excluding metadata keys."""
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    rows = []
    for category, cases in data.items():
        if category.startswith("_"):
            continue
        if not isinstance(cases, list):
            raise ValueError(f"{path}: category {category!r} must be a list")
        for index, case in enumerate(cases):
            if not isinstance(case, list) or len(case) != 2:
                raise ValueError(f"{path}: malformed case {category}[{index}]")
            text, expected = case
            if not isinstance(text, str) or not isinstance(expected, str):
                raise ValueError(f"{path}: case {category}[{index}] must contain strings")
            rows.append((category, text, expected))
    if not rows:
        raise ValueError(f"{path}: no cases found")
    return rows


def evaluate(path: Path, threshold: float | None = None) -> dict:
    payload = path.read_bytes()
    rows = flatten(path)
    by_category: dict[str, list[dict]] = defaultdict(list)
    by_intent: dict[str, list[dict]] = defaultdict(list)
    scored = []
    for category, text, expected in rows:
        prediction = route(text)
        record = {"category": category, "expected": expected,
                  "predicted": prediction["intent"], "correct": prediction["intent"] == expected,
                  "confidence": prediction["confidence"], "coverage": prediction["coverage"]}
        scored.append(record)
        by_category[category].append(record)
        by_intent[expected].append(record)

    correct = sum(row["correct"] for row in scored)
    summary = {
        "dataset": path.name,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "examples": len(scored),
        "correct": correct,
        "accuracy": round(correct / len(scored), 4),
        "macro_accuracy_by_expected_intent": round(statistics.mean(
            sum(r["correct"] for r in group) / len(group) for group in by_intent.values()), 4),
        "mean_top1_confidence": round(statistics.mean(r["confidence"] for r in scored), 4),
        "mean_feature_coverage": round(statistics.mean(r["coverage"] for r in scored), 4),
        "by_category": _group_metrics(by_category),
        "by_expected_intent": _group_metrics(by_intent),
    }
    if threshold is not None:
        selected = [row for row in scored if row["confidence"] >= threshold]
        summary["selective"] = {
            "threshold": threshold,
            "covered": len(selected),
            "coverage_fraction": round(len(selected) / len(scored), 4),
            "accuracy_when_covered": round(sum(r["correct"] for r in selected) / len(selected), 4)
            if selected else None,
            "note": "Softmax confidence is not calibrated; this is a thresholded diagnostic, not a guarantee.",
        }
    return summary


def _group_metrics(groups: dict[str, list[dict]]) -> dict:
    return {key: {"examples": len(group),
                  "correct": sum(row["correct"] for row in group),
                  "accuracy": round(sum(row["correct"] for row in group) / len(group), 4),
                  "mean_top1_confidence": round(statistics.mean(row["confidence"] for row in group), 4)}
            for key, group in sorted(groups.items())}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("datasets", nargs="*", type=Path, default=list(DEFAULT_DATASETS),
                        help="frozen JSON datasets (default: test_set.json and heldout_v07.json)")
    parser.add_argument("--threshold", type=float, default=None,
                        help="optional top-1 confidence threshold for a selective-accuracy diagnostic")
    parser.add_argument("--json", type=Path, help="write machine-readable report to this path")
    args = parser.parse_args(argv)
    if args.threshold is not None and not 0.0 <= args.threshold <= 1.0:
        parser.error("--threshold must be between 0 and 1")
    report = {"router_version": __version__, "scope": "intent classification only; local, no network",
              "datasets": [evaluate(path, args.threshold) for path in args.datasets]}
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.json:
        args.json.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
