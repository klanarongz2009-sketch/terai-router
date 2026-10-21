"""MUML 1.0 HIQ song endings: --fade-out for songs cut at the duration, YuE2 duration from the lyrics."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from terai_router.cli import main as terai_main
from terai_router.muml_hiq import ending, yue2

TH4 = ("[verse]\nคืนนี้ฟ้าเงียบ มีแค่จอที่สว่าง\nโค้ดทีละบรรทัด พาฝันให้ค่อยๆ ชัด\n\n"
       "[chorus]\nเธอเอไอ อยู่ข้างกันทุกคืน\nแม้ใครหลับไป เรายังคงทำต่อ\n")
# Shape of the score YuE2 planned for TH4 at seed 42: Q 87, 9 bar intro, 10 bar verse, no chorus.
ABC = "\n".join([
    "X:1", "M:4/4", "L:1/16", "Q:1/4=87", "V: Vocal clef=treble", "V: Ins clef=treble", "K:D",
    "% intro", "V: Vocal", "Z|z16|z16|z16|", "V: Ins", "Z|f4z12|e16|d16|",
    "V: Vocal", "z16|z16|z16|z16|", "V: Ins", "a16|", "V: Vocal", "z16|",
    "% verse", "V: Vocal", "z2e2f2f2f2d4d2|c16|d16|f16|", "V: Ins", "Z4|",
    "V: Vocal", "d16|a16|f16|e16|", "V: Ins", "Z4|", "V: Vocal", "d16|z16|", "V: Ins", "Z2|", ""])
needs_ffmpeg = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg")


def _tone(path, volume, seconds=6.0):
    path = Path(path)
    codec = ["-c:a", "libmp3lame", "-b:a", "128k"] if path.suffix == ".mp3" else ["-c:a", "pcm_s16le"]
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=440:duration=%g:sample_rate=48000" % seconds, "-af", "volume=%g" % volume,
                    *codec, str(path)], check=True)
    return path


@needs_ffmpeg
@pytest.mark.parametrize("ext", [".mp3", ".wav"])
def test_loud_end_gets_faded(tmp_path, ext):
    f = _tone(tmp_path / ("s" + ext), 0.5)
    assert ending.tail_rms_db(f) > -30  # sine is -21 dB at full volume
    r = ending.finish_ending(f, 2.5)
    assert r["ending"] == "faded" and r["fade_out_s"] == 2.5
    assert r["tail_db_after"] < ending.QUIET_DB and ending.tail_rms_db(f) < -40
    assert abs(ending.audio_seconds(f) - 6.0) < 0.1


@needs_ffmpeg
def test_quiet_end_off_and_unreadable_are_left_alone(tmp_path):
    f = _tone(tmp_path / "q.wav", 0.0005)
    before = f.read_bytes()
    assert ending.finish_ending(f, 2.5)["ending"] == "already quiet" and f.read_bytes() == before
    g = _tone(tmp_path / "l.wav", 0.5)
    before = g.read_bytes()
    assert ending.finish_ending(g, 0)["ending"] == "fade off" and g.read_bytes() == before
    h = tmp_path / "fake.mp3"
    h.write_bytes(b"ID3" + b"x" * 7)
    assert ending.finish_ending(h, 2.5)["fade_out_s"] == 0.0 and h.read_bytes() == b"ID3" + b"x" * 7


def test_recommended_duration_and_context():
    assert yue2.lyric_sections(TH4) == [("verse", 2), ("chorus", 2)]
    assert yue2.recommended_duration(TH4, 90) == 90.0  # (9 + 5*4 + 4) bars * 2.667 s = 88 s -> 90
    assert yue2.recommended_duration(TH4, 120) == 70.0
    assert yue2.recommended_duration("", 90) == 30.0
    assert yue2.recommended_duration("line\n" * 40, 60) == 240.0
    assert yue2.max_seq_for(30) == 8192 and yue2.max_seq_for(90) == 8192 and yue2.max_seq_for(240) == 9216


def test_plan_and_reach_of_the_cut_song():
    secs = yue2.plan_sections(ABC)
    assert [(s["name"], s["bars"]) for s in secs] == [("intro", 9), ("verse", 10)]
    assert secs[1]["start_s"] == 24.8 and secs[1]["length_s"] == 27.6
    r = yue2.reach_report({"abc": ABC, "lyrics": TH4, "semantic_tokens": ",".join(["1"] * 750)}, 30.0)
    assert r["cut_by_duration"] and r["seconds"] == 30.0 and r["plan_s"] == 52.4
    assert [s["state"] for s in r["sections"]] == ["complete", "cut at 5.2 of 27.6 s"]
    assert r["unplanned_lyrics"] == ["chorus"]
    full = yue2.reach_report({"abc": ABC, "lyrics": TH4, "semantic_tokens": ",".join(["1"] * 1320)}, 90.0)
    assert not full["cut_by_duration"] and [s["state"] for s in full["sections"]] == ["complete", "complete"]


def test_cli_sizes_yue2_duration_from_lyrics(capsys):
    base = ["muml", "--hiq", "--raw", "Thai pop ballad", "--bpm", "90", "--lyrics", TH4, "--dry-run", "-o", "s.mp3"]
    assert terai_main(base) == 0
    cap = capsys.readouterr()
    d = json.loads(cap.out)
    assert d["request"]["duration"] == 90.0 and d["eta_min"] == 45 and d["fade_out_s"] == 2.5
    assert "duration 90 s from the lyrics" in cap.err
    assert terai_main(base + ["--duration", "30", "--fade-out", "3"]) == 0
    cap = capsys.readouterr()
    d = json.loads(cap.out)
    assert d["request"]["duration"] == 30.0 and d["fade_out_s"] == 3.0
    assert "Try --duration 90" in cap.err and "3 s fade-out" in cap.err


FAKE = """#!{py}
import json, sys
a = sys.argv[1:]
rq = json.load(open(a[a.index('--request') + 1]))
o = a[a.index('--out') + 1]
open(o, 'wb').write(b'ID3' + b'x' * 7)
rq.update(abc={abc!r}, semantic_tokens=','.join(['5'] * {frames}))
open(o.rsplit('.', 1)[0] + '.json', 'w').write(json.dumps(rq))
"""


def _fake_yue_with_replay(tmp_path, frames):
    b = tmp_path / "yue-synth"
    b.write_text(FAKE.format(py=sys.executable, abc=ABC, frames=frames))
    b.chmod(0o755)
    m = tmp_path / "models"
    m.mkdir(exist_ok=True)
    for f in (yue2.MODEL_FILES["Q5_K_M"], yue2.VAE_FILE):
        (m / f).write_bytes(b"")
    return b, m


def test_cli_reports_where_yue2_stopped(tmp_path, monkeypatch, capsys):
    b, m = _fake_yue_with_replay(tmp_path, 750)
    monkeypatch.setenv("TERAI_YUE2_BIN", str(b))
    monkeypatch.setenv("TERAI_MUML_HIQ_MODELS", str(m))
    out = tmp_path / "s.mp3"
    assert terai_main(["muml", "--hiq", "--raw", "Thai pop", "--duration", "30", "--lyrics", TH4,
                       "--json", "-o", str(out)]) == 0
    cap = capsys.readouterr()
    r = json.loads(cap.out)
    assert r["reach"]["cut_by_duration"] and r["reach"]["unplanned_lyrics"] == ["chorus"]
    assert Path(r["reach"]["replay"]) == tmp_path / "s.yue2.json" and (tmp_path / "s.yue2.json").is_file()
    assert "stopped at the 30.0 s duration" in cap.err and "unfinished: verse" in cap.err
    assert "not sung: chorus" in cap.err
    assert r["ending"]["fade_out_s"] == 0.0  # fake mp3 bytes: nothing to fade


@needs_ffmpeg
def test_cli_fades_ace_step_songs_too(tmp_path, monkeypatch, capsys):
    from terai_router.muml_hiq import cli as hiq_cli

    def fake_generate(fields, out, **kw):
        _tone(out, 0.5)
        return {"out": str(out), "wall_s": 0.1, "request": {"duration": fields["duration"]}}

    monkeypatch.setattr(hiq_cli, "generate", fake_generate)
    out = tmp_path / "i.wav"
    assert terai_main(["muml", "--hiq", "--raw", "lofi", "--duration", "10", "--json", "-o", str(out)]) == 0
    r = json.loads(capsys.readouterr().out)
    assert r["ending"]["ending"] == "faded" and r["ending"]["tail_db_after"] < -40
    assert terai_main(["muml", "--hiq", "--raw", "lofi", "--duration", "10", "--fade-out", "0", "--json",
                       "-o", str(out)]) == 0
    assert json.loads(capsys.readouterr().out)["ending"]["ending"] == "fade off"
