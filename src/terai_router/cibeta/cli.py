"""Command line for local, read-only TERAI1CIBETA analysis."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from ..brain.local import DEFAULT_MODEL, LLMUnavailable, LocalLM
from . import CibetaAnalyzer, CibetaInputError, CibetaOutputError, MAX_SOURCE_CHARS


def _read_input(path: str) -> tuple:
    try:
        if path == "-":
            text = sys.stdin.read(MAX_SOURCE_CHARS + 1)
            name = "stdin"
        else:
            p = Path(path).expanduser()
            with p.open("r", encoding="utf-8") as f:
                text = f.read(MAX_SOURCE_CHARS + 1)
            name = p.name
    except (OSError, UnicodeError) as exc:
        raise CibetaInputError("Could not read the provided UTF-8 input file.") from exc
    if len(text) > MAX_SOURCE_CHARS:
        raise CibetaInputError("Source is too large for this prototype; split it into smaller, relevant excerpts.")
    return text, name


def _text_report(report: dict) -> str:
    lines = ["TERAI1CIBETA — " + ("source-code review" if report["mode"] == "source_review" else "log/alert triage"),
             report["summary"]]
    if report["abstained"]:
        lines.append("Status: abstained / insufficient verified evidence")
    if report["findings"]:
        lines.append("Findings:")
        for finding in report["findings"]:
            refs = ", ".join(str(n) for n in finding["evidence_lines"])
            lines.append("- [{}] {} (lines {})".format(finding["severity"], finding["title"], refs))
            lines.append("  Evidence: " + finding["evidence_excerpt"])
            lines.append("  Why: " + finding["explanation"])
            lines.append("  Suggested safe fix: " + finding["recommendation"])
            lines.append("  Regression test: " + finding["regression_test"])
            lines.append("  Model confidence: " + finding["confidence"] + " (not calibrated)")
    else:
        lines.append("No findings returned.")
    if report["limitations"]:
        lines.append("Limitations: " + " ".join(report["limitations"]))
    lines.append("Analysis only: no files changed and no system action taken.")
    return "\n".join(lines)


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        prog="terai cibeta",
        description="TERAI1CIBETA v0.1 prototype: local read-only review of authorized code or provided logs",
    )
    ap.add_argument("mode", choices=("code", "logs"), help="code: defensive source review; logs: provided-log triage")
    ap.add_argument("input", help="UTF-8 file to analyze, or - for standard input")
    ap.add_argument("--model", default=None, help="installed TERAI Gemma size, e2b by default")
    ap.add_argument("--threads", type=int, default=None)
    ap.add_argument("--json", action="store_true", help="print structured JSON")
    args = ap.parse_args(argv)
    try:
        source, source_name = _read_input(args.input)
        # Important: no implicit download/network access; setup is an explicit separate command.
        lm = LocalLM(model=args.model or DEFAULT_MODEL, threads=args.threads, auto_download=False)
        report = CibetaAnalyzer(lm).analyze("source_review" if args.mode == "code" else "log_triage",
                                           source, source_name)
    except (CibetaInputError, CibetaOutputError, LLMUnavailable, FileNotFoundError, ValueError) as exc:
        print("terai cibeta: " + str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print("terai cibeta: local analysis failed: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else _text_report(report))
    return 0
