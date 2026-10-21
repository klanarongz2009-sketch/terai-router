import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from terai_router.cli import main as terai_main
from terai_router.muml_hiq import DEFAULT_LM, DIT_FILES, LM_FILES, SHARED_FILES
from terai_router.muml_hiq.adapter import adapt, parse_bpm, parse_duration, parse_key, parse_timesig, strip_metadata
from terai_router.muml_hiq.cli import is_hiq_request, strip_hiq_flags
from terai_router.muml_hiq.engine import build_request, missing_files


def test_thai_genre_instruments_tempo():
    r = adapt("เพลงลูกทุ่งสนุกๆ มีพิณกับแคน จังหวะเร็ว")
    assert "luk thung" in r["caption"]
    assert "phin" in r["caption"] and "khaen" in r["caption"]
    assert r["bpm"] == 132
    assert r["lyrics"] == "[Instrumental]"


def test_explicit_bpm_wins_over_genre():
    assert adapt("ลูกทุ่ง จังหวะ 96")["bpm"] == 96
    assert adapt("อีดีเอ็ม ๑๒๘ bpm")["bpm"] == 128  # Thai digits
    assert adapt("ลูกทุ่ง", bpm=150)["bpm"] == 150


def test_genre_default_bpm():
    assert adapt("เพลงโลไฟ")["bpm"] == 82


def test_leading_vowel_is_not_a_match():
    # "ช้า" (slow) must not fire inside "เช้า" (morning)
    r = adapt("ดนตรีไทยเดิมตอนเช้า")
    assert "ช้า" not in r["matched"]
    assert r["bpm"] == 96
    assert "morning" in r["caption"]


def test_bpm_parse_bounds():
    assert parse_bpm("120 bpm") == 120
    assert parse_bpm("จังหวะ 90") == 90
    assert parse_bpm("999 bpm") is None
    assert parse_bpm("no tempo") is None


def test_duration_parse_and_clamp():
    assert parse_duration("30 วินาที") == 30
    assert parse_duration("1 นาที") == 60
    assert parse_duration("20 seconds") == 20
    assert adapt("piano 3 sec")["duration"] == 10.0
    assert adapt("piano")["duration"] == 30.0
    assert adapt("piano", duration=600)["duration"] == 240.0


def test_key_and_timesig():
    assert parse_key("in the key of bb major") == "Bb major"
    assert parse_key("คีย์ a ไมเนอร์") == "A minor"
    assert parse_key("a song") == ""
    assert parse_timesig("3/4 waltz") == "3"
    assert parse_timesig("เพลงวอลทซ์") == "3"


def test_english_prompt_kept_and_metadata_stripped():
    r = adapt("Jazz trio in the key of Bb major, 3/4, 30 sec")
    assert r["caption"].startswith("Jazz trio")
    assert "Bb" not in r["caption"] and "3/4" not in r["caption"]
    assert r["keyscale"] == "Bb major" and r["timesignature"] == "3" and r["duration"] == 30.0
    assert strip_metadata("Lo-fi, 85 BPM") == "Lo-fi"


def test_unknown_thai_kept_verbatim():
    r = adapt("ฟังแล้วคิดถึงบ้าน")
    assert "ฟังแล้วคิดถึงบ้าน" in r["caption"]
    assert r["bpm"] == 100


def test_vocals_flag():
    assert adapt("เพลงป๊อปมีเสียงร้อง")["lyrics"] == ""
    assert adapt("เพลงป๊อปบรรเลง")["lyrics"] == "[Instrumental]"


def test_adapter_is_deterministic():
    p = "เปียโนเศร้าๆ ตอนฝนตก 70 bpm"
    assert adapt(p) == adapt(p)


def test_hiq_flag_detection():
    assert is_hiq_request(["--hiq", "x"])
    assert is_hiq_request(["--model", "hiq", "x"])
    assert is_hiq_request(["--model=HIQ"])
    assert not is_hiq_request(["--model", "base", "x"])
    assert strip_hiq_flags(["--model", "hiq", "a", "--hiq", "-o", "s.mp3"]) == ["a", "-o", "s.mp3"]


def test_build_request_fields():
    req = build_request(adapt("rock 140 bpm", duration=15), "Q4_K_M", 7, 8, "mp3")
    assert req["synth_model"] == DIT_FILES["Q4_K_M"]
    assert req["bpm"] == 140 and req["duration"] == 15.0 and req["seed"] == 7
    assert req["output_format"] == "mp3" and req["inference_steps"] == 8
    assert "keyscale" not in req  # empty values are left for the model


def test_missing_files_lists_all(tmp_path, monkeypatch):
    monkeypatch.setenv("TERAI_MUML_HIQ_MODELS", str(tmp_path))
    assert missing_files("Q4_K_M") == [DIT_FILES["Q4_K_M"], *SHARED_FILES]


def test_cli_dry_run(capsys):
    assert terai_main(["muml", "--hiq", "--dry-run", "เปียโนเศร้า 70 bpm", "-o", "x.mp3"]) == 0
    req = json.loads(capsys.readouterr().out)
    assert req["bpm"] == 70 and req["output_format"] == "mp3" and "piano" in req["caption"]


def test_cli_model_hiq_and_alias(capsys):
    assert terai_main(["muml", "--model", "hiq", "--dry-run", "edm"]) == 0
    assert json.loads(capsys.readouterr().out)["bpm"] == 128
    assert terai_main(["muml-hiq", "--dry-run", "--raw", "อะไรก็ได้"]) == 0
    assert json.loads(capsys.readouterr().out)["caption"] == "อะไรก็ได้"


def test_cli_reports_missing_engine(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TERAI_MUML_HIQ_HOME", str(tmp_path))
    monkeypatch.setenv("TERAI_ACESTEP_BIN", str(tmp_path / "nope"))
    monkeypatch.setenv("PATH", str(tmp_path))
    assert terai_main(["muml", "--hiq", "rock", "-o", str(tmp_path / "s.mp3")]) == 1
    assert "setup" in capsys.readouterr().err


TH_LYRICS = "[verse]\nคืนนี้ฟ้าเงียบ มีแค่จอที่สว่าง\n\n[chorus]\nเธอเอไอ อยู่ข้างกันทุกคืน\n"
EN_LYRICS = "[verse]\nMidnight screen, a quiet glow\n"


def test_lyrics_language_follows_lyrics():
    from terai_router.muml_hiq.adapter import lyrics_language
    assert lyrics_language(TH_LYRICS) == "th"
    assert lyrics_language(EN_LYRICS) == "en"
    assert lyrics_language("[Instrumental]") == ""
    assert lyrics_language("") == ""
    assert lyrics_language("[verse]\n123 !!\n") == "unknown"


def test_prepare_lyrics_thai_modes():
    from terai_router.muml_hiq.adapter import prepare_lyrics
    ly, lang, _ = prepare_lyrics(TH_LYRICS, "native")
    assert ly == TH_LYRICS and lang == "th"
    pytest.importorskip("pythainlp")
    ly, lang, _ = prepare_lyrics(TH_LYRICS, "roman")
    assert lang == "unknown" and "[verse]" in ly and "[chorus]" in ly
    assert not any("\u0e00" <= ch <= "\u0e7f" for ch in ly)
    ly, lang, _ = prepare_lyrics(EN_LYRICS, "roman")
    assert ly == EN_LYRICS and lang == "en"


def test_cli_vocal_language_from_lyrics_not_prompt(capsys):
    # Thai prompt + English lyrics -> en; English prompt + Thai lyrics (native) -> th
    assert terai_main(["muml", "--hiq", "--dry-run", "เพลงป็อป 100 bpm", "--lyrics", EN_LYRICS]) == 0
    req = json.loads(capsys.readouterr().out)
    assert req["vocal_language"] == "en" and req["lm_model"] == LM_FILES[DEFAULT_LM]
    assert terai_main(["muml", "--hiq", "--dry-run", "pop ballad", "--thai-lyrics", "native",
                       "--lyrics", TH_LYRICS, "--lm-model", "1.7B"]) == 0
    req = json.loads(capsys.readouterr().out)
    assert req["vocal_language"] == "th" and req["lyrics"] == TH_LYRICS
    assert req["lm_model"] == LM_FILES["1.7B"]


def test_cli_thai_lyrics_default(capsys):
    pytest.importorskip("pythainlp")
    from terai_router.muml_hiq.adapter import THAI_LYRICS_LM, THAI_LYRICS_MODE
    assert terai_main(["muml", "--hiq", "--dry-run", "pop ballad", "--lyrics", TH_LYRICS]) == 0
    req = json.loads(capsys.readouterr().out)
    assert req["lm_model"] == LM_FILES[THAI_LYRICS_LM]
    assert req["vocal_language"] == ("unknown" if THAI_LYRICS_MODE == "roman" else "th")


def test_instrumental_has_no_lm(capsys):
    assert terai_main(["muml", "--hiq", "--dry-run", "rock 140 bpm"]) == 0
    assert "lm_model" not in json.loads(capsys.readouterr().out)


def _fake_bins(tmp_path):
    """ace-lm writes request0.json (adds audio_codes); ace-synth writes an mp3 and logs its request."""
    b = tmp_path / "bin"
    b.mkdir()
    lm = b / "ace-lm"
    lm.write_text("#!%s\nimport json,sys\nr=json.load(open(sys.argv[4]))\nr['audio_codes']='1,2,3'\n"
                  "json.dump(r,open('request0.json','w'))\nopen(%r,'a').write('lm ')\n"
                  % (sys.executable, str(tmp_path / "calls")))
    sy = b / "ace-synth"
    sy.write_text("#!%s\nimport json,sys\nr=json.load(open(sys.argv[4]))\nopen(%r,'a').write('synth:'+sys.argv[4]+':'"
                  "+str('audio_codes' in r)+' ')\nopen('request00.mp3','wb').write(b'x'*10)\n"
                  % (sys.executable, str(tmp_path / "calls")))
    for f in (lm, sy):
        f.chmod(0o755)
    m = tmp_path / "models"
    m.mkdir()
    for f in [*DIT_FILES.values(), *SHARED_FILES, *LM_FILES.values()]:
        (m / f).write_bytes(b"")
    return sy, m


def test_lyrics_run_lm_then_synth(tmp_path, monkeypatch):
    sy, m = _fake_bins(tmp_path)
    monkeypatch.setenv("TERAI_ACESTEP_BIN", str(sy))
    monkeypatch.setenv("TERAI_MUML_HIQ_MODELS", str(m))
    out = tmp_path / "s.mp3"
    assert terai_main(["muml", "--hiq", "pop 100 bpm", "--lyrics", EN_LYRICS, "-o", str(out)]) == 0
    assert out.read_bytes() == b"x" * 10
    assert (tmp_path / "calls").read_text() == "lm synth:request0.json:True "


def test_instrumental_skips_lm(tmp_path, monkeypatch):
    sy, m = _fake_bins(tmp_path)
    monkeypatch.setenv("TERAI_ACESTEP_BIN", str(sy))
    monkeypatch.setenv("TERAI_MUML_HIQ_MODELS", str(m))
    assert terai_main(["muml", "--hiq", "rock 140 bpm", "-o", str(tmp_path / "s.mp3")]) == 0
    assert (tmp_path / "calls").read_text() == "synth:request.json:False "


def test_missing_lm_binary_is_reported(tmp_path, monkeypatch, capsys):
    sy, m = _fake_bins(tmp_path)
    (sy.parent / "ace-lm").unlink()
    monkeypatch.setenv("TERAI_ACESTEP_BIN", str(sy))
    monkeypatch.setenv("TERAI_MUML_HIQ_MODELS", str(m))
    monkeypatch.setenv("TERAI_MUML_HIQ_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    assert terai_main(["muml", "--hiq", "pop", "--lyrics", EN_LYRICS, "-o", str(tmp_path / "s.mp3")]) == 1
    assert "ace-lm" in capsys.readouterr().err


@pytest.mark.skipif(not os.environ.get("TERAI_MUML_HIQ_E2E"), reason="set TERAI_MUML_HIQ_E2E=1 with models + ace-synth installed")
def test_e2e_generates_audio(tmp_path):
    out = tmp_path / "s.wav"
    assert terai_main(["muml", "--hiq", "--duration", "10", "เปียโน 80 bpm", "-o", str(out)]) == 0
    assert out.stat().st_size > 100_000
