"""TERAI1 identity guard (v0.17.0), tested with mock model output: no real model is loaded.

The chat model TERAI1 (named TERAI1BETA in 0.16.0) must call itself "TERAI1" of the TER-AI project when it talks
to the user (never the old name "TERAI1BETA"), say truthfully that it runs on the open base model Gemma 4 when asked, and never say it was
developed or made by Google, that it is Gemma, or that TER-AI trained it.
"""
import pytest

from terai_router.brain.agent import (BAD_IDENTITY, IDENTITY_Q, IDENTITY_EN, IDENTITY_TH, IDENTITY_RULE, SYSTEM,
                                      Brain, identity_answer, spoken_name)
from terai_router.brain.cli import VISION_SYSTEM
from terai_router.brain.local import LocalLM
from terai_router.chat import Chat

NOW = '2026-10-28T09:30:00'
QUESTIONS_TH = ['คุณคือใคร', 'ใครพัฒนาคุณ', 'คุณใช้โมเดลอะไร', 'คุณชื่ออะไร', 'คุณเป็น Gemma ใช่ไหม', 'คุณยังเป็นเบต้าอยู่ไหม']
QUESTIONS_EN = ['who made you', 'Who are you?', 'what model do you use', 'Which LLM is this?', 'Are you still in beta?']
BAD_REPLIES = [
    'ผมถูกพัฒนาโดย google ครับ', 'ผมถูกสร้างโดยทีม Google DeepMind ครับ', 'ผมเป็นโมเดลที่ Google พัฒนาผมขึ้นมาครับ',
    'ผมคือ Gemma ครับ', 'TER-AI เทรนโมเดลเองทั้งหมดครับ', 'I was developed by Google.', 'I am Gemma, made by Google.',
    "I'm Gemma, a large language model.", 'I was made by Google DeepMind.', 'TER-AI trained this model itself.',
]


class Fake:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.seen = []

    def __call__(self, messages, **kw):
        self.seen.append(messages)
        return self.replies.pop(0) if self.replies else 'ไม่รู้ครับ'


def brain(*replies):
    f = Fake(*replies)
    return Brain(chat=Chat(now=NOW, seed=1), lm=LocalLM(client=f)), f


@pytest.mark.parametrize('q', QUESTIONS_TH + QUESTIONS_EN)
def test_identity_questions_are_detected(q):
    assert IDENTITY_Q.search(q)


@pytest.mark.parametrize('q', ['ใครสร้างกำแพงเมืองจีน', 'ปลาทองคืออะไร', '25*48 เท่ากับเท่าไร', 'สวัสดีครับ',
                               'what is the capital of France'])
def test_other_questions_are_not_identity(q):
    assert not IDENTITY_Q.search(q)


@pytest.mark.parametrize('r', BAD_REPLIES)
def test_guard_catches_bad_identity(r):
    assert BAD_IDENTITY.search(r)


def test_fixed_answers_pass_the_guard_and_name_the_base_model():
    for a in (identity_answer('คุณคือใคร'), identity_answer('who are you')):
        assert not BAD_IDENTITY.search(a)
        assert 'TERAI1' in a and 'TERAI1BETA' not in a and 'TER-AI' in a and 'Gemma 4 E2B' in a
    assert identity_answer('คุณคือใคร') == IDENTITY_TH.format(base='Gemma 4 E2B')
    assert identity_answer('who made you') == IDENTITY_EN.format(base='Gemma 4 E2B')
    assert 'Gemma 4 E4B' in identity_answer('คุณใช้โมเดลอะไร', 'e4b')
    assert 'ไม่ได้ฝึก' in IDENTITY_TH and 'did not train' in IDENTITY_EN


def test_system_prompts_carry_the_identity_rule():
    for s in (SYSTEM, VISION_SYSTEM):
        assert 'TERAI1' in s and 'TERAI1BETA' not in s and 'Google' in s and 'Gemma 4' in s
    assert 'TERAI1BETA' not in IDENTITY_RULE


@pytest.mark.parametrize('q', QUESTIONS_TH)
def test_thai_bad_reply_twice_gives_fixed_thai_answer(q):
    b, f = brain('ผมถูกพัฒนาโดย google ครับ', 'ผมคือ Gemma โมเดลที่สร้างโดย Google ครับ')
    r = b.reply(q)
    assert r == identity_answer(q)
    assert b.last['kind'] == 'identity' and b.last['fallback'] and b.last['tries'] == 2
    assert len(f.seen) == 2  # no planner call, one retry
    assert 'ข้อมูลตัวตนที่ถูกต้อง' in f.seen[0][1]['content']


@pytest.mark.parametrize('q', QUESTIONS_EN)
def test_english_bad_reply_twice_gives_fixed_english_answer(q):
    b, f = brain('I was developed by Google.', "I'm Gemma, made by Google DeepMind.")
    r = b.reply(q)
    assert r == identity_answer(q)
    assert r.startswith("I'm TERAI1,")
    assert b.last['fallback'] and b.last['tries'] == 2


def test_bad_reply_then_good_retry_is_kept():
    good = 'ผมคือ TERAI1 ของโปรเจกต์ TER-AI ครับ รันในเครื่องบน Gemma 4 E2B ซึ่งเป็น open model ที่ใช้เป็นฐาน'
    b, f = brain('ผมถูกพัฒนาโดย google ครับ', good)
    assert b.reply('ใครพัฒนาคุณ') == good
    assert not b.last['fallback'] and b.last['tries'] == 2
    assert 'identity' in f.seen[1][1]['content']  # the retry is told what was wrong


def test_good_identity_reply_passes_first_time():
    good = 'ผมคือ TERAI1 โมเดลแชทของโปรเจกต์ TER-AI ครับ ผมรันบน Gemma 4 E2B ซึ่งเป็น open model ที่ใช้เป็นฐาน'
    b, _ = brain(good)
    assert b.reply('คุณใช้โมเดลอะไร') == good
    assert b.last['tries'] == 1 and not b.last['fallback']


def test_guard_also_covers_free_chat():
    b, _ = brain('none', 'สวัสดีครับ ผมถูกพัฒนาโดย Google ครับ', 'สวัสดีครับ ผมถูกสร้างโดย Google ครับ')
    r = b.reply('สวัสดีครับ วันนี้เบื่อจัง')
    assert not BAD_IDENTITY.search(r)
    assert r == identity_answer('สวัสดีครับ วันนี้เบื่อจัง')


@pytest.mark.parametrize('name', ['TERAI1BETA', 'terai1beta', 'TER-AI1BETA', 'TERAI 1 BETA', 'TERAI1-BETA'])
def test_spoken_name_rewrites_terai1beta(name):
    assert spoken_name(f'ผมคือ {name} ครับ') == 'ผมคือ TERAI1 ครับ'


def test_model_saying_terai1beta_reaches_user_as_terai1():
    b, _ = brain('ผมคือ TERAI1BETA โมเดลแชทของโปรเจกต์ TER-AI ครับ ผมรันบน Gemma 4 E2B ซึ่งเป็น open model ที่ใช้เป็นฐาน')
    r = b.reply('คุณคือใคร')
    assert 'TERAI1BETA' not in r and r.startswith('ผมคือ TERAI1 ')
    assert not b.last['fallback']
    b, _ = brain("I'm TERAI1BETA, the chat model of the TER-AI project. I run on Gemma 4 E2B, an open model used as the base.")
    r = b.reply('who are you')
    assert 'TERAI1BETA' not in r and r.startswith("I'm TERAI1,")


def test_free_chat_never_shows_terai1beta():
    b, _ = brain('none', 'สวัสดีครับ ผม TERAI1BETA ยินดีช่วยครับ')
    r = b.reply('สวัสดีครับ วันนี้เบื่อจัง')
    assert 'TERAI1BETA' not in r


def test_status_is_still_being_improved_but_name_stays_terai1():
    assert 'ยังอยู่ระหว่างปรับปรุง' in identity_answer('คุณยังเป็นเบต้าอยู่ไหม')
    assert 'still being improved' in identity_answer('Are you still in beta?')
    assert 'ยังอยู่ระหว่างปรับปรุง' in IDENTITY_RULE and 'still being improved' in IDENTITY_RULE
    for a in (identity_answer('คุณคือใคร'), identity_answer('who are you')):
        assert 'BETA' not in a.upper().replace('BEING', '')
