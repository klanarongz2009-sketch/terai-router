"""TERM AI limited-time trial: cutoff behaviour (clock injected, never today's date) and the bot.

Removed together with src/terai_router/term_ai/ on 2027-01-01 00:00:00 Asia/Bangkok (UTC+7).
"""
import hashlib
import io
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from terai_router import cli as top_cli
from terai_router.term_ai import (BANGKOK, EXIT_TRIAL_ENDED, REMOVAL_PATHS, REMOVAL_EDITS, TRIAL_END, TermAI,
                                  TrialEnded, check_trial, ended_message, intent_model, notice_line,
                                  time_left, trial_active)
from terai_router.term_ai import cli as term_cli

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BEFORE = datetime(2026, 12, 31, 23, 59, 59, tzinfo=BANGKOK)
AT = datetime(2027, 1, 1, 0, 0, 0, tzinfo=BANGKOK)
AFTER = datetime(2027, 3, 1, 12, 0, tzinfo=BANGKOK)
EARLY = datetime(2026, 10, 22, 9, 30, tzinfo=BANGKOK)


def fixed(dt):
    return lambda: dt


# ---------- trial clock ----------
def test_cutoff_constant_is_bangkok_midnight():
    assert TRIAL_END == datetime(2026, 12, 31, 17, 0, 0, tzinfo=timezone.utc)
    assert TRIAL_END.utcoffset() == timedelta(hours=7)


@pytest.mark.parametrize('now,active', [
    (EARLY, True),
    (BEFORE, True),
    (AT - timedelta(microseconds=1), True),
    (AT, False),
    (AT + timedelta(seconds=1), False),
    (AFTER, False),
    (datetime(2026, 12, 31, 16, 59, 59, tzinfo=timezone.utc), True),   # same instants in UTC
    (datetime(2026, 12, 31, 17, 0, 0, tzinfo=timezone.utc), False),
    (datetime(2026, 12, 31, 12, 0, 0, tzinfo=timezone(timedelta(hours=-5))), False),  # 17:00 UTC
])
def test_trial_active(now, active):
    assert trial_active(now) is active


def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        trial_active(datetime(2026, 12, 1))


def test_time_left_and_notice():
    assert time_left(AT) == timedelta(0)
    assert time_left(AFTER) == timedelta(0)
    assert time_left(BEFORE) == timedelta(seconds=1)
    line = notice_line(EARLY)
    assert '\n' not in line
    assert '2027-01-01 00:00:00 Asia/Bangkok (UTC+7)' in line and 'removed' in line
    assert '70 days left' in line
    assert 'less than 1 day left' in notice_line(BEFORE)
    assert '1 day left' in notice_line(AT - timedelta(days=1, hours=1))


def test_check_trial():
    check_trial(BEFORE)
    with pytest.raises(TrialEnded) as e:
        check_trial(AT)
    assert '2027-01-01 00:00:00 Asia/Bangkok (UTC+7)' in str(e.value)


# ---------- CLI before / at / after the cutoff ----------
def run(argv, now, monkeypatch, capsys, stdin=None):
    if stdin is not None:
        monkeypatch.setattr(sys, 'stdin', io.StringIO(stdin))
    rc = term_cli.main(argv, clock=now if callable(now) else fixed(now))
    out, err = capsys.readouterr()
    return rc, out, err


def test_cli_before_cutoff_prints_notice_then_runs(tmp_path, monkeypatch, capsys):
    mem = tmp_path / 'm.json'
    rc, out, err = run(['--memory', str(mem), 'คำนวณ', '(12+8)*3'], BEFORE, monkeypatch, capsys)
    assert rc == 0
    assert err.strip() == notice_line(BEFORE)
    assert out == 'TERM AI> (12+8)*3 = 60\n'
    assert json.loads(mem.read_text(encoding='utf-8'))['turns'] == 1


@pytest.mark.parametrize('now', [AT, AT + timedelta(seconds=1), AFTER])
@pytest.mark.parametrize('argv', [[], ['สวัสดี'], ['--help'], ['--trial-info'], ['--unknown-flag']])
def test_cli_at_or_after_cutoff_refuses(now, argv, tmp_path, monkeypatch, capsys):
    mem = tmp_path / 'm.json'
    rc, out, err = run(argv + ['--memory', str(mem)], now, monkeypatch, capsys, stdin='สวัสดี\n')
    assert rc == EXIT_TRIAL_ENDED == 3
    assert out == ''
    assert err.strip() == ended_message()
    assert not mem.exists()


def test_top_level_dispatch(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(term_cli, 'main', lambda argv, clock=None: ('called', argv))
    assert top_cli.main(['term', 'x']) == ('called', ['x'])


def test_trial_info_before(monkeypatch, capsys):
    rc, out, err = run(['--trial-info'], EARLY, monkeypatch, capsys)
    assert rc == 0 and out == '' and '2027-01-01 00:00:00' in err


def test_interactive_session(tmp_path, monkeypatch, capsys):
    rc, out, err = run(['--memory', str(tmp_path / 'm.json')], EARLY, monkeypatch, capsys,
                       stdin='ผมชื่อบอส\nผมชื่ออะไร\n12*8\nออก\nไม่ควรถึงบรรทัดนี้\n')
    assert rc == 0
    assert 'TERM AI> จำแล้ว: ชื่อ บอส' in out and 'TERM AI> คุณชื่อ บอส' in out
    assert 'TERM AI> 12*8 = 96' in out and out.rstrip().endswith('จบการทำงาน')
    assert 'ไม่ควร' not in out


def test_session_crossing_the_cutoff_stops_cleanly(tmp_path, monkeypatch, capsys):
    times = iter([BEFORE, BEFORE, BEFORE, BEFORE, AT, AT, AT])
    rc, out, err = run(['--memory', str(tmp_path / 'm.json')], lambda: next(times), monkeypatch, capsys,
                       stdin='12*8\n1+1\n2+2\n')
    assert rc == 3
    assert 'TERM AI> 12*8 = 96' in out and '1 + 1' not in out and '1+1 = 2' not in out
    assert err.strip().splitlines() == [notice_line(BEFORE), ended_message()]


def test_reset_and_bad_config(tmp_path, monkeypatch, capsys):
    mem = tmp_path / 'm.json'
    mem.write_text(json.dumps({'name': 'A', 'turns': 9}), encoding='utf-8')
    rc, out, _ = run(['--memory', str(mem), '--reset', 'ผมชื่ออะไร'], EARLY, monkeypatch, capsys)
    assert rc == 0 and 'ยังไม่รู้ชื่อ' in out
    with pytest.raises(SystemExit) as e:
        run(['--config', str(tmp_path / 'missing.json'), 'hi'], EARLY, monkeypatch, capsys)
    assert e.value.code == 2


def test_corrupt_memory_file_does_not_crash(tmp_path, monkeypatch, capsys):
    mem = tmp_path / 'm.json'
    mem.write_text('{not json', encoding='utf-8')
    rc, out, _ = run(['--memory', str(mem), 'สถิติ'], EARLY, monkeypatch, capsys)
    assert rc == 0 and '1 ข้อความ' in out


# ---------- library ----------
def test_library_refuses_after_cutoff():
    with pytest.raises(TrialEnded):
        TermAI(clock=fixed(AT))
    times = iter([BEFORE, BEFORE, AFTER])
    bot = TermAI(clock=lambda: next(times))
    assert bot.reply('1+2') == '1+2 = 3'
    with pytest.raises(TrialEnded):
        bot.reply('1+2')


def test_intent_model_cli_respects_cutoff(capsys):
    assert intent_model.main(['predict', 'x'], now=AT) == 3
    assert intent_model.main(['predict', 'สวัสดี'], now=EARLY) == 0
    assert capsys.readouterr().out.startswith('greet')


# ---------- replies (same as the original Terminal AI) ----------
@pytest.mark.parametrize('text,expected', [
    ('คำนวณ (12+8)*3', '(12+8)*3 = 60 [rule]'),
    ('ช่วยคิดเลข 3 คูณ 4', '3 * 4 = 12 [model: calc p=1.00 cov=0.72]'),
    ('100 ลบ 37 เท่ากับ', '100 - 37 = 63 [model: calc p=1.00 cov=1.00]'),
    ('เรียกผมว่าต้น', 'จำแล้ว: ชื่อ ต้น [model: set_name p=1.00 cov=0.85]'),
    ('ขอบใจนะ', 'ยินดี [model: thanks p=1.00 cov=1.00]'),
    ('คุณเป็นใคร', 'ฉันคือ TERM AI chatbot ใน terminal ใช้กฎ + โมเดล intent classifier เล็กๆ ที่เทรนเอง (made with Sesame) [rule]'),
    ('นับ สวัสดี ครับ', '11 ตัวอักษร, 2 คำ (นับตามช่องว่าง) [rule]'),
    ('กลับคำ abc', 'cba [rule]'),
    ('2**200', 'คำนวณไม่ได้: ใช้ได้แค่ตัวเลขกับ + - * / // % ** ( ) [rule]'),
    ('__import__("os")', None),  # not a calc: falls back, never evaluated
])
def test_replies_match_original(text, expected):
    bot = TermAI(clock=fixed(EARLY), seed=0, debug=True)
    out = bot.reply(text)
    if expected is None:
        assert out in bot.cfg['fallback']
    else:
        assert out == expected


def test_time_reply_uses_injected_clock_in_thai_time():
    bot = TermAI(clock=fixed(datetime(2026, 12, 31, 16, 30, tzinfo=timezone.utc)))
    assert bot.reply('กี่โมงแล้ว') == 'ตอนนี้ 23:30 น. วันที่ 31/12/2026 (เวลาไทย)'


def test_random_is_seeded_and_in_range():
    a = TermAI(clock=fixed(EARLY), seed=7).reply('สุ่ม 1-6')
    b = TermAI(clock=fixed(EARLY), seed=7).reply('สุ่ม 1-6')
    assert a == b and a.startswith('สุ่มได้ ') and a.endswith('(ช่วง 1-6)')


# ---------- the bundled model is the original, rebuilt exactly from the data ----------
MODEL_SHA256 = '5f36d291b8e514755ffceaa591f5ba1431155e062c7a8d52d9293b7e47165abd'


def test_model_rebuilds_from_training_data():
    samples = intent_model.load_samples()
    assert len(samples) == 149
    model = intent_model.load_model()
    assert model['name'] == 'TER-AI-0.5'
    assert len(model['classes']) == 11
    rebuilt = intent_model.train(samples)
    for k in ('V', 'alpha', 'n_range', 'classes'):
        assert rebuilt[k] == model[k]


def test_model_file_hash():
    with open(intent_model.MODEL_PATH, 'rb') as f:
        assert hashlib.sha256(f.read()).hexdigest() == MODEL_SHA256


def test_leave_one_out_accuracy():
    ok, n, _ = intent_model.leave_one_out()
    assert (ok, n) == (101, 149)


# ---------- removal list stays accurate ----------
def test_removal_paths_exist_and_nothing_else_imports_term_ai():
    for p in REMOVAL_PATHS + REMOVAL_EDITS:
        assert os.path.exists(os.path.join(ROOT, p)), p
    src = os.path.join(ROOT, 'src', 'terai_router')
    users = []
    for dirpath, _, files in os.walk(src):
        if os.path.join('terai_router', 'term_ai') in dirpath:
            continue
        for fn in files:
            if fn.endswith('.py'):
                with open(os.path.join(dirpath, fn), encoding='utf-8') as f:
                    if 'term_ai' in f.read():
                        users.append(fn)
    assert users == ['cli.py']


def test_real_entry_point_runs_or_refuses():
    """`python -m terai_router term` end to end; the expected result follows the real clock."""
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, 'src'), HOME=os.path.join(ROOT, '.pytest_cache'))
    p = subprocess.run([sys.executable, '-m', 'terai_router', 'term', '--memory',
                        os.path.join(ROOT, '.pytest_cache', 'term_ai_test.json'), '1+1'],
                       capture_output=True, text=True, encoding='utf-8', env=env, timeout=60)
    if trial_active(datetime.now(timezone.utc)):
        assert p.returncode == 0 and p.stdout == 'TERM AI> 1+1 = 2\n' and '2027-01-01 00:00:00' in p.stderr
    else:
        assert p.returncode == 3 and p.stdout == '' and 'trial ended' in p.stderr
