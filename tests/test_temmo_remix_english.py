"""v0.13: Temmo remix rules read English word order too; Thai and "background pink" read as before."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from terai_router.temmo import remix as R

ROOT = Path(__file__).resolve().parents[1]
GAME = R.read_game((ROOT / "docs" / "temmo" / "games" / "orange-cat-fish-collector.html").read_text(encoding="utf-8"))
PINK, BLUE, BROWN, RED = "#f06292", "#1e88e5", "#6d4c41", "#e53935"


@pytest.mark.parametrize("text, want", [
    # rule_patch results from before v0.13 (f14294d), unchanged
    ("พื้นหลังสีชมพู กำแพงสีน้ำตาล ยากขึ้น", {"palette": {"bg": PINK, "wall": BROWN}, "time_delta": -15, "enemy_speed": "faster"}),
    ("พื้นสีเทา พื้นหลังสีดำ ศัตรูสีแดง", {"palette": {"floor": "#607d8b", "bg": "#0b0d10", "enemy": RED}}),
    ("พื้นหลังสีชมพู ง่ายขึ้น", {"palette": {"bg": PINK}, "time_delta": 20, "enemy_speed": "slower"}),
    ("แดง พื้นหลังสีชมพู", {"palette": {"bg": PINK}}),
    ("ขอสีแดงของผู้เล่น", {}),
    ("สีสวยขึ้น", {}),
    ("background pink, harder", {"palette": {"bg": PINK}, "time_delta": -15, "enemy_speed": "faster"}),
    ("background pink, wall brown, harder", {"palette": {"bg": PINK, "wall": BROWN}, "time_delta": -15, "enemy_speed": "faster"}),
    ("red, background pink", {"palette": {"bg": PINK}}),
    ("wall brown background pink", {"palette": {"wall": BROWN, "bg": PINK}}),
    ("player white, exit yellow; more time", {"palette": {"player": "#f5f5f5", "exit": "#fdd835"}, "time_delta": 20, "enemy_speed": "slower"}),
])
def test_old_commands_read_as_before(text, want):
    assert R.rule_patch(text) == want


@pytest.mark.parametrize("text, want", [
    ("pink background, harder", {"palette": {"bg": PINK}, "time_delta": -15, "enemy_speed": "faster"}),
    ("pink background", {"palette": {"bg": PINK}}),
    ("make the player blue", {"palette": {"player": BLUE}}),
    ("faster enemies", {"enemy_speed": "faster"}),
    ("enemies move slower", {"enemy_speed": "slower"}),
    ("more levels", {"add_levels": 2}),
    ("one more level", {"add_levels": 1}),
    ("add 3 levels", {"add_levels": 3}),
    ("harder", {"time_delta": -15, "enemy_speed": "faster"}),
    ("pink background, blue walls", {"palette": {"bg": PINK, "wall": BLUE}}),
    ("pink background blue walls", {"palette": {"bg": PINK, "wall": BLUE}}),
    ("blue player, red enemies, faster enemies", {"palette": {"player": BLUE, "enemy": RED}, "enemy_speed": "faster"}),
    ("green floor and yellow door", {"palette": {"floor": "#43a047", "exit": "#fdd835"}}),
])
def test_english_order(text, want):
    assert R.rule_patch(text) == want


def test_more_levels_mirrors_and_caps():
    n = len(GAME["levels"])
    new, patch, _ = R.remix(GAME, "pink background, harder, add 5 more levels")
    assert patch["add_levels"] == 3 and len(new["levels"]) == n + 3
    first = new["levels"][n]
    assert first["grid"] == [row[::-1] for row in GAME["levels"][0]["grid"]]
    assert first["name"] == GAME["levels"][0]["name"] + " (mirror)"
    src = (GAME["levels"] * 4)[:n + 3]  # added levels copy levels 0, 1, 2 (cycling)
    assert [lv["time"] for lv in new["levels"]] == [max(40, min(180, int(lv.get("time", 90)) - 15)) for lv in src]
    assert len(GAME["levels"]) == n  # original untouched
    big = dict(GAME, levels=GAME["levels"] * 3)
    assert len(R.apply_patch(big, {"add_levels": 3})["levels"]) == max(len(big["levels"]), R.MAX_LEVELS)
    assert R.validate_patch({"add_levels": 0}) == {} and R.validate_patch({"add_levels": "x"}) == {}


def test_remix_parity_cases_js_equals_python():
    if not shutil.which("node"):
        pytest.skip("node not installed")
    sys.path.insert(0, str(ROOT / "eval"))
    import parity
    assert len(parity.REMIX_CASES) >= 30
    assert parity.remix_parity() == 0
