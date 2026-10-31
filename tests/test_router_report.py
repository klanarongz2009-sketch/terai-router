"""Tests for the reproducible local intent-router report."""
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("router_report", ROOT / "eval" / "router_report.py")
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)


def test_frozen_report_identifies_data_and_breaks_down_metrics():
    result = REPORT.evaluate(ROOT / "eval" / "heldout_v07.json", threshold=0.8)
    assert result["examples"] == 112
    assert result["sha256"] == "09619675cc391f761c5247d3795ed25565f64d80ff43fafb1132b16aacefdf70"
    assert result["correct"] == 111
    assert result["accuracy"] == 0.9911
    assert result["macro_accuracy_by_expected_intent"] <= 1.0
    assert "typo" in result["by_category"]
    assert "calc" in result["by_expected_intent"]
    assert result["selective"]["covered"] <= result["examples"]
    assert "not calibrated" in result["selective"]["note"]


def test_frozen_report_has_no_selective_claim_without_threshold():
    result = REPORT.evaluate(ROOT / "eval" / "test_set.json")
    assert result["examples"] == 124
    assert "selective" not in result


def test_invalid_case_fails_with_dataset_context(tmp_path):
    malformed = tmp_path / "bad.json"
    malformed.write_text('{"oops": [["not a pair"]]}', encoding="utf-8")
    try:
        REPORT.flatten(malformed)
    except ValueError as exc:
        assert "bad.json" in str(exc)
        assert "malformed case" in str(exc)
    else:
        raise AssertionError("malformed case was accepted")
