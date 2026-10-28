"""v0.17.0: model TERAI1BETA was renamed to TERAI1. The old names stay working aliases with a deprecation notice.

Also the rule chat's answer to "who made you" (it used to claim that TER-AI trained every model itself).
No real model is loaded here.
"""
import os
import subprocess
import sys
from pathlib import Path

import pytest

from terai_router import __version__
from terai_router.brain.agent import BAD_IDENTITY, Brain
from terai_router.brain.cli import make_brain
from terai_router.chat import Chat
from terai_router.versions import (ENGINE_ALIASES, MODEL_ID, MODEL_ID_ALIASES, MODELS, deprecation_notice,
                                   resolve_engine, resolve_model_id, version_line)

ROOT = Path(__file__).resolve().parents[1]
NOW = '2026-10-28T09:30:00'


def test_new_model_id_and_status():
    assert MODEL_ID == 'TERAI1'
    assert version_line() == f'terai-router {__version__} / model TERAI1'
    row = MODELS[0]
    assert row['id'] == 'TERAI1' and row['status'] == 'beta' and row['aliases'] == ['TERAI1BETA']
    assert row['since'] == '0.16.0'  # same model, only the name changed


def test_old_model_id_is_an_alias():
    assert MODEL_ID_ALIASES == {'TERAI1BETA': 'TERAI1'}
    assert resolve_model_id('TERAI1BETA') == 'TERAI1'
    assert resolve_model_id('terai1beta') == 'TERAI1'
    assert resolve_model_id('TERAI1') == 'TERAI1'
    assert resolve_model_id('MuML 1.0') == 'MuML 1.0'  # other ids are untouched


def test_engine_alias_prints_deprecation_notice(capsys):
    assert ENGINE_ALIASES == {'terai1beta': 'terai1'}
    assert resolve_engine('terai1beta') == 'terai1'
    err = capsys.readouterr().err
    assert err.strip() == deprecation_notice('terai1beta', 'terai1')
    assert 'deprecated' in err and "'terai1'" in err


@pytest.mark.parametrize('name', ['terai1', 'auto', 'rules'])
def test_current_engine_names_print_nothing(name, capsys):
    assert resolve_engine(name) == name
    assert capsys.readouterr().err == ''


def test_make_brain_new_name_and_alias(capsys):
    chat = Chat(now=NOW, seed=1)
    assert isinstance(make_brain(chat, 'terai1', None, 1, quiet=True), Brain)
    assert capsys.readouterr().err == ''
    assert isinstance(make_brain(chat, 'terai1beta', None, 1, quiet=True), Brain)
    assert 'deprecated' in capsys.readouterr().err
    assert make_brain(chat, 'rules', None, 1, quiet=True) is None
    with pytest.raises(ValueError):
        make_brain(chat, 'gemma', None, 1, quiet=True)


def _chat_cli(tmp_path, *args):
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
    return subprocess.run([sys.executable, '-m', 'terai_router.cli', 'chat', '--session', str(tmp_path / 's.json'),
                           *args], input='/quit\n', capture_output=True, text=True, env=env, timeout=120)


def test_cli_brain_terai1(tmp_path):
    out = _chat_cli(tmp_path, '--brain', 'terai1')
    assert out.returncode == 0, out.stderr
    assert 'deprecated' not in out.stderr


def test_cli_brain_terai1beta_alias(tmp_path):
    out = _chat_cli(tmp_path, '--brain', 'terai1beta')
    assert out.returncode == 0, out.stderr
    assert deprecation_notice('terai1beta', 'terai1') in out.stderr


def test_cli_help_lists_terai1():
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
    out = subprocess.run([sys.executable, '-m', 'terai_router.cli', 'chat', '--help'], capture_output=True,
                         text=True, env=env)
    assert 'terai1' in out.stdout and 'TERAI1 (beta' in out.stdout
    assert 'TERAI1BETA' not in out.stdout


def test_brain_eval_accepts_terai1_and_alias():
    src = (ROOT / 'eval' / 'brain_eval.py').read_text(encoding='utf-8')
    assert "'terai1', 'terai1beta'" in src and "if engine == 'terai1':" in src and 'resolve_engine' in src
    assert (ROOT / 'eval' / 'terai1beta_cases_v15.json').is_file()  # the test set keeps its original file name


# ---------------------------------------------------------------- rule chat identity (regression, v0.17.0)
WHO_MADE = ['ใครพัฒนาคุณ', 'ใครสร้างเธอ', 'ใครเป็นคนสร้าง', 'who made you', 'ใครพัฒนา']


@pytest.mark.parametrize('q', WHO_MADE)
def test_rule_chat_who_made_you_is_truthful(q):
    r = Chat(now=NOW, seed=1).reply(q)
    assert 'เทรนโมเดลเองทั้งหมด' not in r and 'ฝึกโมเดลเองทั้งหมด' not in r
    assert not BAD_IDENTITY.search(r), r
    assert 'Google' not in r and 'กูเกิล' not in r
    assert 'intent router' in r and 'ฝึกในโปรเจกต์นี้' in r  # TER-AI's own models are trained in-project
    assert 'TERAI1' in r and 'Gemma 4' in r and 'open model' in r and 'ไม่ได้ฝึก Gemma 4 เอง' in r


def test_web_demo_has_the_same_answer():
    html = (ROOT / 'docs' / 'index.html').read_text(encoding='utf-8')
    assert 'เทรนโมเดลเองทั้งหมด' not in html
    assert 'TER-AI ไม่ได้ฝึก Gemma 4 เอง' in html
