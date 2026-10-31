"""Run the small local TERAI1CIBETA smoke set. Results are observations, not a security certification."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from terai_router.brain.local import LocalLM
from terai_router.cibeta import CibetaAnalyzer


def main() -> int:
    suite = json.loads((ROOT / "eval" / "cibeta_fixtures.json").read_text(encoding="utf-8"))
    analyzer = CibetaAnalyzer(LocalLM(auto_download=False))
    rows = []
    for case in suite["cases"]:
        try:
            report = analyzer.analyze(case["mode"], case["source"], case["id"])
        except Exception as exc:
            print("local TERAI1 model unavailable or analysis failed: {}".format(exc), file=sys.stderr)
            return 2
        categories = [finding["category"] for finding in report["findings"]]
        expected = case["expected_category"]
        passed = (expected in categories) if expected else not categories
        rows.append({"id": case["id"], "expected_category": expected, "returned_categories": categories,
                     "abstained": report["abstained"], "fixture_match": passed})
    matched = sum(1 for row in rows if row["fixture_match"])
    print(json.dumps({"suite": suite["suite"], "matched_cases": matched, "case_count": len(rows),
                      "results": rows,
                      "caveat": "Synthetic smoke results only; not calibrated, exhaustive, or a security guarantee."},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
