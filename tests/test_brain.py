"""TERAI1 (brain/) without the real model: a fake client stands in for Gemma 4."""
import json
import subprocess
import sys

import pytest

from terai_router import __version__
from terai_router.brain.agent import Brain, numbers, support, REFUSAL
from terai_router.brain.local import LocalLM, clean_reply, image_data_uri
from terai_router.chat import Chat
from terai_router.versions import MODEL_ID, version_line, MODELS

NOW = '2026-10-22T09:30:00'


class Fake:
    """Returns scripted replies in order; records the messages it got."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.seen = []

    def __call__(self, messages, **kw):
        self.seen.append(messages)
        return self.replies.pop(0) if self.replies else 'ไม่รู้ครับ'


def brain(*replies):
    f = Fake(*replies)
    return Brain(chat=Chat(now=NOW, seed=1), lm=LocalLM(client=f)), f


def test_version_line_has_repo_and_model():
    assert MODEL_ID == 'TERAI1'
    assert version_line() == f'terai-router {__version__} / model TERAI1'
    assert __version__.startswith('0.')  # the repository stays 0.X.Y; 1.0 criteria unchanged
    assert MODELS[0]['id'] == 'TERAI1'


def test_cli_version_prints_both():
    out = subprocess.run([sys.executable, '-m', 'terai_router.cli', '--version'], capture_output=True, text=True)
    assert 'model TERAI1' in (out.stdout + out.stderr)
    assert 'TERAI1BETA' not in (out.stdout + out.stderr)


def test_numbers_normalises_commas_and_thai_digits():
    assert numbers('ได้ 1,200 บาท และ ๑๒ คน 3.50') == {'1200', '12', '3.5'}


def test_support_overlap():
    assert support('เชียงใหม่อยู่ภาคเหนือ', 'เชียงใหม่ เป็นจังหวัดในภาคเหนือของประเทศไทย') > 0.6
    assert support('ดาวอังคารมีสิ่งมีชีวิต', 'เชียงใหม่ เป็นจังหวัดในภาคเหนือ') < 0.3


def test_tool_answer_is_rewritten_by_the_model():
    b, f = brain('25 คูณ 48 ได้ 1,200 ครับ')
    r = b.reply('25*48 เท่ากับเท่าไร')
    assert r == '25 คูณ 48 ได้ 1,200 ครับ'
    assert b.last['kind'] == 'tool' and b.last['tool'] == 'calculator' and not b.last['fallback']
    assert '1,200' in f.seen[0][1]['content'] or '1200' in f.seen[0][1]['content']


def test_made_up_number_falls_back_to_the_rule_answer():
    b, f = brain('ได้ 1,250 ครับ', 'ได้ 1,300 ครับ')
    r = b.reply('25*48 เท่ากับเท่าไร')
    assert b.last['fallback'] and b.last['tries'] == 2
    assert '1,200' in r or '1200' in r
    assert any('numbers not in any source' in p for p in b.last['problems'])


def test_retry_fixes_the_reply():
    b, f = brain('ได้ 1,250 ครับ', 'ได้ 1,200 ครับ')
    assert b.reply('25*48 เท่ากับเท่าไร') == 'ได้ 1,200 ครับ'
    assert not b.last['fallback'] and b.last['tries'] == 2


def test_no_source_must_say_it_does_not_know():
    b, f = brain(json.dumps({'tool': 'none', 'input': ''}), 'ชื่อนายสมหมายครับ',
                 'ชื่อนายสมหมายครับ')
    r = b.reply('ประธานาธิบดีคนแรกของดาวอังคารชื่ออะไร')
    assert b.last['kind'] == 'no_source' and b.last['fallback']
    assert REFUSAL.search(r) and 'สมหมาย' not in r


def test_no_source_refusal_from_model_is_kept():
    b, f = brain(json.dumps({'tool': 'none', 'input': ''}), 'ผมไม่รู้เรื่องนี้ครับ เพราะไม่มีข้อมูล')
    assert b.reply('ประธานาธิบดีคนแรกของดาวอังคารชื่ออะไร') == 'ผมไม่รู้เรื่องนี้ครับ เพราะไม่มีข้อมูล'


def test_planner_calls_a_rule_as_a_tool():
    b, f = brain(json.dumps({'tool': 'calculator', 'input': '5+7'}), 'ห้าบวกเจ็ดได้ 12 ครับ')
    r = b.reply('ห้าบวกเจ็ดได้เท่าไหร่')
    assert r == 'ห้าบวกเจ็ดได้ 12 ครับ'
    assert b.last['planned'] == ('calculator', '5+7') and b.last['tool'] == 'calculator'


def test_chitchat_is_written_by_the_model_and_kept_in_history():
    b, f = brain('สวัสดีครับ วันนี้อยากคุยเรื่องอะไรดีครับ')
    r = b.reply('สวัสดีครับ')
    assert r.startswith('สวัสดีครับ')
    assert b.chat.state['history'][-1]['bot'] == r


def test_link_in_reply_is_rejected():
    b, f = brain('ดูที่ https://example.com ครับ', 'ดูที่ www.example.com ครับ')
    b.reply('สวัสดีครับ')
    assert b.last['fallback']


def test_knowledge_citation_added_by_code():
    b, f = brain(json.dumps({'tool': 'none', 'input': ''}), 'x')
    rule_chat = Chat(now=NOW, seed=1)
    rule = rule_chat.reply('จังหวัดเชียงใหม่อยู่ภาคไหน')
    if '(ที่มา:' not in rule:
        pytest.skip('knowledge pack has no citation for this question')
    f.replies = ['เชียงใหม่อยู่ภาคเหนือของประเทศไทยครับ']
    r = b.reply('จังหวัดเชียงใหม่อยู่ภาคไหน')
    assert b.last['kind'] == 'knowledge'
    assert r.startswith('เชียงใหม่อยู่ภาคเหนือ') and '(ที่มา:' in r


def test_image_reply_uses_vision(tmp_path):
    img = tmp_path / 'a.png'
    img.write_bytes(b'\x89PNG\r\n\x1a\n' + b'0' * 20)
    f = Fake('ในภาพมีข้อความว่า OPEN ครับ')
    b = Brain(chat=Chat(now=NOW, seed=1), lm=LocalLM(client=f, vision=True))
    r = b.reply('อ่านภาพนี้', image=str(img))
    assert 'OPEN' in r and b.last['kind'] == 'vision'
    content = f.seen[0][-1]['content']
    assert content[0]['type'] == 'image_url' and content[0]['image_url']['url'].startswith('data:image/png;base64,')


def test_image_helpers(tmp_path):
    with pytest.raises(FileNotFoundError):
        image_data_uri(str(tmp_path / 'missing.png'))
    t = tmp_path / 'x.txt'
    t.write_text('hi')
    with pytest.raises(ValueError):
        image_data_uri(str(t))
    assert clean_reply('<think>x</think> สวัสดี<end_of_turn>') == 'สวัสดี'


def test_rule_chat_output_unchanged():
    a, b = Chat(now=NOW, seed=1), Chat(now=NOW, seed=1)
    for q in ['สวัสดี', '25*48', 'วันนี้วันที่เท่าไร']:
        assert a.reply(q) == b.reply(q)
    assert a.last_step == '_datetime'
