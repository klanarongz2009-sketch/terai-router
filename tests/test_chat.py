import json
import re

import pytest

from terai_router import Chat
from terai_router.chat import GREETINGS, NO_PENDING
from terai_router.cli import main

NOW = '2026-10-16T16:40:00'


def chat(tmp_path=None, **kw):
    kw.setdefault('now', NOW)
    kw.setdefault('seed', 7)
    if tmp_path is not None:
        kw.setdefault('path', str(tmp_path / 'session.json'))
    return Chat(**kw)


# ---------------------------------------------------------------- real tool answers
def test_calc():
    c = chat()
    assert c.reply('12*7') == '12 × 7 = 84'
    assert c.reply('(3+4)*2') == '(3 + 4) × 2 = 14'
    assert 'หารด้วยศูนย์ไม่ได้' in c.reply('10/0')


def test_time_with_fixed_clock():
    c = chat()
    assert '16:40' in c.reply('ตอนนี้กี่โมง')
    assert c.reply('วันนี้วันอะไร') == 'วันนี้คือวันศุกร์ที่ 16 ตุลาคม 2569'


def test_time_callable_clock():
    c = Chat(now=lambda: '2026-01-01T08:05:00', seed=1)
    assert '08:05' in c.reply('ตอนนี้กี่โมง')


def test_units_and_follow_up():
    c = chat()
    assert c.reply('5 กิโลเมตรเป็นกี่เมตร') == '5 กิโลเมตร = 5000 เมตร'
    assert c.reply('แล้ว 2 ล่ะ') == '2 กิโลเมตร = 2000 เมตร'
    assert c.reply('100 ฟาเรนไฮต์เป็นเซลเซียส') == '100 องศาฟาเรนไฮต์ = 37.78 องศาเซลเซียส'


# ---------------------------------------------------------------- knowledge
def test_knowledge_answer_cites_source_title():
    out = chat().reply('กรุงเทพมหานครคืออะไร')
    assert out.startswith('กรุงเทพมหานคร')
    assert 'Wikipedia ภาษาไทย' in out and '"กรุงเทพมหานคร"' in out and 'CC BY-SA 4.0' in out


def test_knowledge_continue_then_honest_end():
    c = chat()
    first = c.reply('ดาวอังคารคืออะไร')
    more = c.reply('ต่อ')
    assert more != first and 'ดาวอังคาร' in more


def test_honest_unknown():
    c = chat()
    assert 'ไม่รู้' in c.reply('ซาบาริโนวาลิกซ์คืออะไร')
    assert 'ไม่มีข้อมูล' in c.reply('ราคาทองวันนี้เท่าไร')


# ---------------------------------------------------------------- memory
def test_memory_facts_and_recall():
    c = chat()
    assert 'คุณบอส' in c.reply('ผมชื่อบอส')
    c.reply('ผมชอบแมว')
    c.reply('ผมอายุ 16')
    assert c.reply('ผมชื่ออะไร') == 'คุณชื่อบอสครับ/ค่ะ'
    assert c.reply('ผมชอบอะไร') == 'คุณชอบแมวครับ/ค่ะ'
    assert '16' in c.reply('ผมอายุเท่าไร')
    f = c.facts
    assert f['name'] == 'บอส' and f['likes'] == ['แมว'] and f['age'] == '16'


def test_grade_fact_bug_c():
    c = chat()
    assert 'ยังไม่มีข้อมูล' in c.reply('ผมอยู่ชั้นอะไร')
    assert c.reply('ผมอยู่ ม.4') == 'จำไว้แล้วว่าคุณเรียนอยู่ชั้น ม.4'
    assert 'ม.4' in c.reply('ผมอยู่ชั้นอะไร')
    assert 'ม.4' in c.reply('ผมเรียนชั้นไหน')
    assert c.facts['grade'] == 'ม.4'
    assert c.facts['location'] is None  # 'อยู่ ม.4' is not a place
    assert 'ป.6' in c.reply('หนูเรียนอยู่ ป. 6')
    c.reply('ลืมชั้นเรียน')
    assert c.facts['grade'] is None


# ---------------------------------------------------------------- follow-ups
def test_calc_bare_number_follow_up_bug_b():
    c = chat()
    c.reply('12*7')
    assert c.reply('แล้ว 5 ล่ะ') == '12 × 5 = 60'
    assert c.reply('แล้วถ้าเป็น 10 ล่ะ') == '12 × 10 = 120'
    c.reply('2^10')
    assert c.reply('แล้ว 3 ล่ะ') == '2 ^ 3 = 8'


def test_calc_operator_follow_up():
    c = chat()
    c.reply('12*7')
    assert c.reply('บวก 6') == '84 + 6 = 90'


def test_continue_with_nothing_pending_bug_a():
    c = chat()
    assert c.reply('ต่อ') == NO_PENDING
    c.reply('12*7')
    assert c.reply('ต่อเลย') == NO_PENDING


# ---------------------------------------------------------------- persistence, forget
def test_persistence_across_restart(tmp_path):
    c = chat(tmp_path)
    c.reply('ผมชื่อบอส')
    c.reply('ผมอยู่ ม.4')
    path = tmp_path / 'session.json'
    assert path.exists()
    state = json.loads(path.read_text(encoding='utf-8'))
    assert state['name'] == 'บอส' and len(state['history']) == 2
    c2 = chat(tmp_path)
    assert c2.reply('ผมชื่ออะไร') == 'คุณชื่อบอสครับ/ค่ะ'
    assert 'ม.4' in c2.reply('ผมอยู่ชั้นอะไร')
    assert len(c2.history) == 4


def test_forget_everything(tmp_path):
    c = chat(tmp_path)
    c.reply('ผมชื่อบอส')
    c.reply('ผมชอบแมว')
    assert 'ล้างความจำทั้งหมดแล้ว' in c.reply('ลืมทั้งหมด')
    assert 'ยังไม่รู้ชื่อ' in c.reply('ผมชื่ออะไร')
    c2 = chat(tmp_path)
    assert c2.facts['name'] is None and c2.facts['likes'] == []


def test_forget_one_fact():
    c = chat()
    c.reply('ผมชื่อบอส')
    c.reply('ผมชอบแมว')
    c.reply('ลืมชื่อ')
    assert c.facts['name'] is None and c.facts['likes'] == ['แมว']


# ---------------------------------------------------------------- greeting
def test_greeting_variants_keep_polite_form():
    seen = set()
    for seed in range(40):
        out = Chat(now=NOW, seed=seed).reply('สวัสดี')
        assert out.startswith('สวัสดีครับ/ค่ะ ')
        tail = out[len('สวัสดีครับ/ค่ะ '):]
        assert tail in GREETINGS
        seen.add(tail)
    assert seen == set(GREETINGS)
    assert all(g.endswith('ครับ/คะ') for g in GREETINGS)


# ---------------------------------------------------------------- CLI
def test_cli_chat_scripted(tmp_path, monkeypatch, capsys):
    import io
    s = str(tmp_path / 's.json')
    monkeypatch.setattr('sys.stdin', io.StringIO('ผมชื่อบอส\n12*7\nแล้ว 5 ล่ะ\n'))
    assert main(['chat', '--session', s]) == 0
    out = capsys.readouterr().out
    assert 'terai> 12 × 5 = 60' in out and 'คุณบอส' in out
    monkeypatch.setattr('sys.stdin', io.StringIO('ผมชื่ออะไร\n'))
    main(['chat', '--session', s])
    assert 'คุณชื่อบอส' in capsys.readouterr().out
    monkeypatch.setattr('sys.stdin', io.StringIO('ผมชื่ออะไร\n'))
    main(['chat', '--session', s, '--reset'])
    assert 'ยังไม่รู้ชื่อ' in capsys.readouterr().out


def test_cli_classifier_unchanged(capsys):
    assert main(['ไม่เอา']) == 0
    assert capsys.readouterr().out.startswith('refuse')
