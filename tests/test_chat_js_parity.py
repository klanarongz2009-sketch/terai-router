"""docs/chat.js must give the same replies as terai_router.chat.Chat (skipped when node is not installed)."""
import json
import pathlib
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'eval'))


@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
@pytest.mark.parametrize('name', ['chat_regress_v08.json', 'chat_eval_v08.json'])
def test_js_chat_matches_python(name):
    import parity
    path = str(ROOT / 'eval' / name)
    res = subprocess.run(['node', str(ROOT / 'eval' / 'chat_parity.js'), path], capture_output=True, text=True, check=True)
    js = json.loads(res.stdout)[path]
    py = parity.python_chat(path)
    assert js == py


def test_demo_page_has_chat_mode():
    html = (ROOT / 'docs' / 'index.html').read_text(encoding='utf-8')
    assert 'TERAI_CHAT' in html and 'id="pane-chat"' in html and 'knowledge_th.json' in html
    assert '__CHAT_JS__' not in html and '__KB_META__' not in html
    assert (ROOT / 'docs' / 'knowledge_th.json').read_bytes() == (ROOT / 'src' / 'terai_router' / 'data' / 'knowledge_th.json').read_bytes()


@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
def test_js_web_chat_matches_python():
    import parity
    fix, spec = str(ROOT / 'eval' / 'web_fixtures_v09.json'), str(ROOT / 'eval' / 'chat_web_v09.json')
    res = subprocess.run(['node', str(ROOT / 'eval' / 'chat_parity.js'), '--web', fix, spec], capture_output=True, text=True, check=True)
    js = json.loads(res.stdout)[spec]
    py = parity.python_web_chat(fix, spec)
    assert js == py
    flat = [r for conv in py for r in conv]
    assert any(r.startswith('[ค้นเว็บ]') for r in flat)
    assert any('ค้นเว็บไม่สำเร็จ (OfflineError)' in r for r in flat)


def test_demo_page_has_web_toggle():
    html = (ROOT / 'docs' / 'index.html').read_text(encoding='utf-8')
    assert 'id="webtoggle"' in html and 'terai.chat.web.v1' in html
