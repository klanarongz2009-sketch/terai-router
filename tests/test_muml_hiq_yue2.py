"""MUML 1.0 HIQ --vocal-engine yue2 (YuE2-3B through yue2.cpp; Thai lyrics default). yue-synth is mocked."""
import json
import sys
from pathlib import Path

import pytest

from terai_router.cli import main as terai_main
from terai_router.muml_hiq import engine, yue2
from terai_router.muml_hiq.cli import resolve_vocal_engine
from terai_router.muml_hiq.engine import HiqError

TH = "[verse]\nคืนนี้ฟ้าเงียบ มีแค่จอที่สว่าง\n\n[chorus]\nเธอเอไอ อยู่ข้างกันทุกคืน\n"
EN = "[verse]\nMidnight screen, a quiet glow\n"


def test_resolve_engine_defaults():
    assert resolve_vocal_engine(TH) == "yue2"
    assert resolve_vocal_engine(EN) == "ace"
    assert resolve_vocal_engine(None) == "ace"
    assert resolve_vocal_engine("[Instrumental]") == "ace"


def test_resolve_engine_explicit_and_alias():
    assert resolve_vocal_engine(TH, "ace") == "ace"
    assert resolve_vocal_engine(TH, "split") == "split"
    assert resolve_vocal_engine(EN, "yue2") == "yue2"  # asked for explicitly
    assert resolve_vocal_engine(TH, thai_vocal="sing") == "ace"
    assert resolve_vocal_engine(TH, thai_vocal="split") == "split"
    assert resolve_vocal_engine(TH, "yue2", thai_vocal="split") == "yue2"  # --vocal-engine wins
    for bad in [(None, "yue2"), (None, "split"), (EN, "split")]:
        with pytest.raises(ValueError):
            resolve_vocal_engine(*bad)


def test_cli_thai_lyrics_dry_run_is_yue2_native(capsys):
    assert terai_main(["muml", "--hiq", "--raw", "Thai pop ballad", "--bpm", "90", "--duration", "30",
                       "--lyrics", TH, "--dry-run", "-o", "s.mp3"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["engine"] == "yue2" and d["quant"] == "Q5_K_M" and d["license"] == "CC-BY-NC-4.0"
    rq = d["request"]
    assert rq["lyrics"] == TH  # Thai script verbatim, not romanised
    assert rq["style"] == "Thai pop ballad, 90 BPM"
    assert rq["steps"] == 32 and rq["seed"] == 42 and rq["lm_seed"] == 42 and rq["duration"] == 30.0
    assert rq["output_format"] == "mp3" and d["eta_min"] == 15
    assert "lm_model" not in rq


def test_cli_english_and_instrumental_stay_on_ace(capsys):
    assert terai_main(["muml", "--hiq", "--dry-run", "pop 100 bpm", "--lyrics", EN]) == 0
    d = json.loads(capsys.readouterr().out)
    assert "engine" not in d and d["vocal_language"] == "en" and "synth_model" in d
    assert terai_main(["muml", "--hiq", "--dry-run", "rock 140 bpm"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert "engine" not in d and "synth_model" in d


def test_cli_vocal_engine_flag(capsys):
    assert terai_main(["muml", "--hiq", "--dry-run", "ballad", "--lyrics", TH, "--vocal-engine", "ace"]) == 0
    assert "synth_model" in json.loads(capsys.readouterr().out)
    assert terai_main(["muml", "--hiq", "--dry-run", "ballad", "--lyrics", TH, "--vocal-engine", "split"]) == 0
    assert json.loads(capsys.readouterr().out)["thai_vocal"] == "split"
    assert terai_main(["muml", "--hiq", "--dry-run", "ballad", "--lyrics", TH, "--vocal-engine", "yue2",
                       "--yue2-quant", "Q8_0", "--steps", "16"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert d["quant"] == "Q8_0" and d["request"]["steps"] == 16 and d["argv"][2].endswith("YuE2-3B-Q8_0.gguf")
    assert terai_main(["muml", "--hiq", "ballad", "--vocal-engine", "yue2"]) == 2
    assert "needs --lyrics" in capsys.readouterr().err


def test_build_argv(tmp_path, monkeypatch):
    monkeypatch.setenv("TERAI_MUML_HIQ_MODELS", str(tmp_path))
    argv = yue2.build_argv(Path("/x/yue-synth"), "req.json", "out.mp3")
    assert argv == ["/x/yue-synth", "--model", str(tmp_path / "YuE2-3B-Q5_K_M.gguf"),
                    "--vae", str(tmp_path / "YuE2-Vae-F32.gguf"), "--max-seq", "8192",
                    "--request", "req.json", "--out", "out.mp3"]


def test_eta_and_threads(monkeypatch):
    assert yue2.eta_minutes(30) == 15 and yue2.eta_minutes(60) == 30 and yue2.eta_minutes(10) == 5
    monkeypatch.setattr(yue2.os, "cpu_count", lambda: 8)
    assert yue2.cpu_threads() == 4
    assert "15 min per 30 s" in yue2.eta_message(30)


def _no_runtime(tmp_path, monkeypatch):
    monkeypatch.setenv("TERAI_MUML_HIQ_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("TERAI_MUML_HIQ_MODELS", str(tmp_path / "models"))
    monkeypatch.setenv("TERAI_YUE2_BIN", str(tmp_path / "nope"))
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))


def test_missing_runtime_error_says_how_to_fix(tmp_path, monkeypatch, capsys):
    _no_runtime(tmp_path, monkeypatch)
    assert yue2.find_binary() is None
    with pytest.raises(HiqError) as e:
        yue2.generate({"caption": "x", "duration": 10}, TH, tmp_path / "s.mp3")
    msg = str(e.value)
    assert "--setup" in msg and "TERAI_YUE2_BIN" in msg and yue2.RUNTIME_COMMIT[:7] in msg
    assert terai_main(["muml", "--hiq", "ballad", "--lyrics", TH, "-o", str(tmp_path / "s.mp3")]) == 1
    err = capsys.readouterr().err
    assert "yue-synth" in err and "--setup" in err
    assert "15 min per 30 s" in err and "CC-BY-NC-4.0" in err and "NON-COMMERCIAL" in err


def _fake_bin(tmp_path, name):
    b = tmp_path / name
    b.write_text("#!/bin/sh\nexit 0\n")
    b.chmod(0o755)
    return b


def _fake_yue(tmp_path, rc=0):
    b = tmp_path / "yue-synth"
    b.write_text("#!%s\nimport json,sys\na=sys.argv[1:]\nopen(%r,'w').write(json.dumps({'argv':a,"
                 "'req':json.load(open(a[a.index('--request')+1]))}))\n"
                 "open(a[a.index('--out')+1],'wb').write(b'ID3'+b'x'*7)\nsys.exit(%d)\n"
                 % (sys.executable, str(tmp_path / "call.json"), rc))
    b.chmod(0o755)
    m = tmp_path / "models"
    m.mkdir(exist_ok=True)
    for f in (yue2.MODEL_FILES["Q5_K_M"], yue2.VAE_FILE):
        (m / f).write_bytes(b"")
    return b, m


def test_missing_weights_error(tmp_path, monkeypatch):
    b, m = _fake_yue(tmp_path)
    (m / yue2.VAE_FILE).unlink()
    monkeypatch.setenv("TERAI_YUE2_BIN", str(b))
    monkeypatch.setenv("TERAI_MUML_HIQ_MODELS", str(m))
    with pytest.raises(HiqError) as e:
        yue2.generate({"caption": "x", "duration": 10}, TH, tmp_path / "s.mp3")
    assert yue2.VAE_FILE in str(e.value) and "--setup" in str(e.value) and yue2.GGUF_URL in str(e.value)


def test_cli_runs_mocked_yue2(tmp_path, monkeypatch, capsys):
    b, m = _fake_yue(tmp_path)
    monkeypatch.setenv("TERAI_YUE2_BIN", str(b))
    monkeypatch.setenv("TERAI_MUML_HIQ_MODELS", str(m))
    out = tmp_path / "o" / "s.mp3"
    assert terai_main(["muml", "--hiq", "--raw", "Thai pop", "--duration", "20", "--lyrics", TH,
                       "--json", "-o", str(out)]) == 0
    assert out.read_bytes() == b"ID3" + b"x" * 7
    call = json.loads((tmp_path / "call.json").read_text())
    a = call["argv"]
    assert a[a.index("--model") + 1] == str(m / "YuE2-3B-Q5_K_M.gguf")
    assert a[a.index("--vae") + 1] == str(m / "YuE2-Vae-F32.gguf")
    assert a[a.index("--max-seq") + 1] == "8192"
    assert call["req"]["lyrics"] == TH and call["req"]["duration"] == 20.0 and call["req"]["steps"] == 32
    cap = capsys.readouterr()
    r = json.loads(cap.out)
    assert r["engine"] == "yue2" and r["license"] == "CC-BY-NC-4.0"
    assert "~10 min" in cap.err and "NON-COMMERCIAL" in cap.err


def test_runtime_failure_is_reported(tmp_path, monkeypatch, capsys):
    b, m = _fake_yue(tmp_path, rc=3)
    monkeypatch.setenv("TERAI_YUE2_BIN", str(b))
    monkeypatch.setenv("TERAI_MUML_HIQ_MODELS", str(m))
    assert terai_main(["muml", "--hiq", "ballad", "--lyrics", TH, "-o", str(tmp_path / "s.mp3")]) == 1
    assert "yue-synth failed (rc=3)" in capsys.readouterr().err


def test_setup_pins_commit(tmp_path, monkeypatch):
    _no_runtime(tmp_path, monkeypatch)
    m = tmp_path / "models"
    m.mkdir()
    for f in (yue2.MODEL_FILES["Q5_K_M"], yue2.VAE_FILE):
        (m / f).write_bytes(b"")
    calls = []
    monkeypatch.setattr(yue2, "require_build_tools", lambda *a: {"git": "git", "cmake": "cmake"})
    monkeypatch.setattr(yue2.subprocess, "run", lambda argv, **kw: calls.append(list(argv)))
    yue2.setup(log=lambda *_: None)
    assert ["git", "clone", yue2.RUNTIME_REPO, str(tmp_path / "home" / "yue2.cpp")] in calls
    assert ["git", "checkout", yue2.RUNTIME_COMMIT] in calls
    assert len(yue2.RUNTIME_COMMIT) == 40
    assert any(c[:2] == ["cmake", "--build"] and "yue-synth" in c for c in calls)


def test_setup_without_cmake_fails_before_download(tmp_path, monkeypatch):
    # Clean-machine run 2026-10-21: no cmake on PATH -> 3.2 GB fetched, then a bare
    # "[Errno 2] No such file or directory: 'cmake'". Now: clear error, nothing fetched or run.
    _no_runtime(tmp_path, monkeypatch)
    monkeypatch.setattr(engine.sys, "executable", str(tmp_path / "empty" / "python"))
    monkeypatch.delenv("CXX", raising=False)
    fetched, calls = [], []
    monkeypatch.setattr(yue2, "_download", lambda name, dest, log: fetched.append(name))
    monkeypatch.setattr(yue2.subprocess, "run", lambda argv, **kw: calls.append(list(argv)))
    with pytest.raises(HiqError) as e:
        yue2.setup(log=lambda *_: None)
    msg = str(e.value)
    assert "cmake" in msg and "git" in msg and "C++17" in msg
    assert "pip install cmake" in msg and "TERAI_YUE2_BIN" in msg
    assert fetched == [] and calls == []


def test_setup_without_cmake_cli_message(tmp_path, monkeypatch, capsys):
    _no_runtime(tmp_path, monkeypatch)
    monkeypatch.setattr(engine.sys, "executable", str(tmp_path / "empty" / "python"))
    monkeypatch.setenv("TERAI_ACESTEP_BIN", str(_fake_bin(tmp_path, "ace-synth")))
    m = tmp_path / "models"
    m.mkdir()
    for lm in engine.LM_FILES.values():
        (m / lm).write_bytes(b"")
    for f in [*engine.DIT_FILES.values(), *engine.SHARED_FILES]:
        (m / f).write_bytes(b"")
    monkeypatch.setattr(yue2, "_download", lambda *a: pytest.fail("downloaded before the cmake check"))
    assert terai_main(["muml", "--hiq", "--setup"]) == 1
    err = capsys.readouterr().err
    assert "setup failed: building yue2.cpp needs" in err and "pip install cmake" in err
    assert "Errno" not in err


def test_build_tool_found_next_to_python(tmp_path, monkeypatch):
    # `pip install cmake` in a venv that is not activated: cmake sits next to sys.executable.
    venv_bin = tmp_path / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    cm = venv_bin / "cmake"
    cm.write_text("#!/bin/sh\n")
    cm.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    monkeypatch.setattr(engine.sys, "executable", str(venv_bin / "python"))
    assert engine.build_tool("cmake") == str(cm)
    assert "cmake" not in engine.missing_build_tools()
    assert "git" in engine.missing_build_tools()


def test_notice_and_docs_name_yue2():
    root = Path(__file__).resolve().parents[1]
    notice = (root / "NOTICE").read_text(encoding="utf-8")
    assert "YuE2-3B" in notice and "m-a-p" in notice and "CC-BY-NC-4.0" in notice
    assert yue2.RUNTIME_COMMIT in notice and yue2.GGUF_URL in notice
    doc = (root / "docs" / "MUML-HIQ.md").read_text(encoding="utf-8")
    assert "--vocal-engine" in doc and "yue2" in doc
