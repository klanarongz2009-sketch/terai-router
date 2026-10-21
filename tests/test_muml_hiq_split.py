"""MUML 1.0 HIQ --thai-vocal split (TTH Wayu voice over an ACE-Step instrumental)."""
import json
import shutil
import wave
from pathlib import Path

import pytest

from terai_router.cli import main as terai_main
from terai_router.muml_hiq import split
from terai_router.muml_hiq.split import (MAJOR, MINOR, SplitError, atempo_factor, degree_to_midi, line_starts,
                                         lyric_lines, parse_key, snap_to_scale)

LYRICS = "[verse]\nคืนนี้ฟ้าเงียบ มีแค่จอที่สว่าง\nโค้ดทีละบรรทัด พาฝันให้ค่อยๆ ชัด\n\n[chorus]\nเธอเอไอ อยู่ข้างกันทุกคืน\nแม้ใครหลับไป เรายังคงทำต่อ\n"


def test_lyric_lines_drop_tags_and_blanks():
    assert lyric_lines(LYRICS) == ["คืนนี้ฟ้าเงียบ มีแค่จอที่สว่าง", "โค้ดทีละบรรทัด พาฝันให้ค่อยๆ ชัด",
                                  "เธอเอไอ อยู่ข้างกันทุกคืน", "แม้ใครหลับไป เรายังคงทำต่อ"]


def test_parse_key():
    assert parse_key("C major") == (0, MAJOR)
    assert parse_key("A minor") == (9, MINOR)
    assert parse_key("F# minor") == (6, MINOR)
    assert parse_key("Bb major") == (10, MAJOR)
    assert parse_key("Am") == (9, MINOR)
    assert parse_key("") == (0, MAJOR)
    assert parse_key("weird") == (0, MAJOR)


def test_snap_to_scale_c_major_and_a_minor():
    assert snap_to_scale(61) == 60          # C#4 -> C4 (tie goes down)
    assert snap_to_scale(63.6) == 64        # rounds to E4 (64), already in the scale
    assert snap_to_scale(63.4) == 62        # rounds to D#4 (63) first, tie goes down to D4
    assert snap_to_scale(66) == 65          # F#4 -> F4
    assert snap_to_scale(64) == 64
    tonic, scale = parse_key("A minor")
    assert all((snap_to_scale(m, tonic, scale) - tonic) % 12 in scale for m in range(48, 84))
    tonic, scale = parse_key("E major")  # G -> G# or F#
    assert (snap_to_scale(67, tonic, scale) - tonic) % 12 in scale


def test_degree_to_midi():
    assert degree_to_midi(0) == 60
    assert degree_to_midi(2) == 64
    assert degree_to_midi(7) == 72
    assert degree_to_midi(0, *parse_key("A minor")) == 69
    assert degree_to_midi(2, *parse_key("A minor")) == 72


def test_line_starts_on_bars():
    starts, slot = line_starts(4, 90, 30.0)
    bar = 4 * 60 / 90
    assert [round(s, 3) for s in starts] == [round(bar * k, 3) for k in (1, 3, 5, 7)]
    assert slot == pytest.approx(2 * bar - 0.5 * 60 / 90)


def test_line_starts_shrink_and_fail():
    starts, slot = line_starts(10, 90, 30.0)  # 10 lines do not fit in 2 bars each -> 1 bar each
    assert slot == pytest.approx(4 * 60 / 90 - 0.5 * 60 / 90)
    assert starts[-1] + slot * 0.5 <= 30.0
    with pytest.raises(SplitError):
        line_starts(40, 90, 30.0)


def test_atempo_factor():
    assert atempo_factor(5.0, 5.0) == 1.0
    assert atempo_factor(10.0, 5.0) == 1.35      # clamped fast
    assert atempo_factor(5.5, 5.0) == pytest.approx(1.1)
    assert atempo_factor(1.0, 5.0) == 0.8        # clamped slow
    assert atempo_factor(3.0, 5.0) == pytest.approx(3.0 / 4.5, abs=1e-4) or atempo_factor(3.0, 5.0) == 0.8
    assert atempo_factor(0, 5.0) == 1.0


def test_cli_split_dry_run(capsys):
    rc = terai_main(["muml", "--hiq", "เพลงบัลลาดเปียโน 90 bpm", "--lyrics", LYRICS, "--thai-vocal", "split",
                     "--split-style", "rap", "--dry-run"])
    assert rc == 0
    cap = capsys.readouterr()
    d = json.loads(cap.out)
    assert d["thai_vocal"] == "split" and d["split_style"] == "rap"
    assert d["instrumental"]["lyrics"] == "[Instrumental]"
    assert "lm_model" not in d["instrumental"]          # no LM for an instrumental
    assert d["instrumental"]["keyscale"] == "C major"     # fixed key for the vocal
    assert d["instrumental"]["bpm"] == 90
    assert len(d["lines"]) == 4
    assert "CC-BY-NC-4.0" in cap.err


def test_cli_split_keeps_given_key(capsys):
    assert terai_main(["muml", "--hiq", "ballad", "--key", "A minor", "--lyrics", LYRICS,
                       "--thai-vocal", "split", "--dry-run"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["instrumental"]["keyscale"] == "A minor"
    assert d["split_style"] == "snap"


def test_cli_split_needs_thai_lyrics(capsys):
    assert terai_main(["muml", "--hiq", "ballad", "--lyrics", "hello world", "--thai-vocal", "split"]) == 2
    assert terai_main(["muml", "--hiq", "ballad", "--thai-vocal", "split"]) == 2


def test_cli_thai_vocal_sing_alias_is_ace(capsys):
    assert terai_main(["muml", "--hiq", "ballad", "--lyrics", LYRICS, "--thai-vocal", "sing", "--dry-run"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert "thai_vocal" not in d and d["lyrics"] != "[Instrumental]"


class FakeTTS:
    sample_rate = 24000

    def __call__(self, text, voice=None, seed=0, speed=1.0):
        import numpy as np
        t = np.arange(int(0.12 * len(text) * self.sample_rate)) / self.sample_rate
        return (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_generate_split_with_fakes(tmp_path):
    pytest.importorskip("numpy")
    seen = {}

    def fake_generate(fields, out, quant=None, seed=42, steps=8):
        import subprocess
        seen.update(fields)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=110:duration=12",
                        "-ar", "48000", str(out)], check=True)
        return {"out": str(out), "wall_s": 0.1, "request": dict(fields)}

    out = tmp_path / "song.wav"
    fields = {"caption": "Thai pop ballad, soft female vocal singing in Thai, piano", "bpm": 90,
              "duration": 12.0, "lyrics": "x"}
    r = split.generate_split(fields, LYRICS, out, style="rap", generate_fn=fake_generate, tts=FakeTTS())
    assert seen["lyrics"] == "[Instrumental]" and seen["keyscale"] == "C major"
    assert "vocal" not in seen["caption"] and seen["caption"].endswith("instrumental")
    assert seen["caption"].startswith("Thai pop ballad, piano")
    assert r["thai_vocal"] == "split" and len(r["lines"]) == 4
    assert "non-commercial" in r["license_note"]
    with wave.open(str(out)) as w:
        assert abs(w.getnframes() / w.getframerate() - 12.0) < 0.1
    starts = [x["start_s"] for x in r["lines"]]
    assert starts == sorted(starts) and starts[0] > 0


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
@pytest.mark.parametrize("style", ["snap", "melody"])
def test_make_vocal_retune_styles(style):
    np = pytest.importorskip("numpy")
    pytest.importorskip("pyworld")
    voc, sr, info = split.make_vocal(lyric_lines(LYRICS)[:2], 90, 12.0, "C major", style, tts=FakeTTS())
    assert sr == 24000 and len(voc) == 12 * sr and float(np.max(np.abs(voc))) > 0.1


def test_bad_style():
    with pytest.raises(SplitError):
        split.make_vocal(["ก"], 90, 10.0, "C major", "opera", tts=FakeTTS())


def test_notice_says_split_is_non_commercial():
    notice = (Path(__file__).resolve().parents[1] / "NOTICE").read_text(encoding="utf-8")
    assert "--thai-vocal split" in notice and "non-commercial" in notice
