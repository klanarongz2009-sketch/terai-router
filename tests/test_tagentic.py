"""Tagentic (Tagentic1, beta): thinking + agentic loop, session, memory. The model is a mock: no weights.

No test checks a reply word for word: every reply the user reads must be what the (mock) model generated, unchanged.
Identity is set by Systemprompt.md only; there is no output guard.
"""
import io
import json
import os
import re
import uuid
from pathlib import Path

import pytest

from terai_router.tagentic import agent as A
from terai_router.tagentic import cli as C
from terai_router.tagentic import memory as M
from terai_router.tagentic.tools import Toolbox
from terai_router.tagentic.workspace import SandboxError, Workspace

PKG = Path(A.__file__).resolve().parent


class FakeLM:
    """Returns the scripted replies in order (str, or a function of the messages). Records every call."""
    model = 'e2b'

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages, **kw):
        self.calls.append({'messages': [dict(m) for m in messages], **kw})
        r = self.replies.pop(0) if self.replies else final('-')
        return r(messages) if callable(r) else r


def final(answer, think='ok'):
    return json.dumps({'think': think, 'tool': 'final', 'answer': answer}, ensure_ascii=False)


def step(tool, args, think='step'):
    return json.dumps({'think': think, 'tool': tool, 'args': args}, ensure_ascii=False)


def token():
    return 'gen-' + uuid.uuid4().hex[:10]


@pytest.fixture
def env(tmp_path):
    ws = tmp_path / 'ws'
    ws.mkdir()
    (ws / 'hello.py').write_text('def add(a, b):\n    return a - b\n', encoding='utf-8')
    home = tmp_path / 'home'
    M.init_home(home)
    return ws, home


def make(env, lm, yes=True, confirm=None, **kw):
    ws, home = env
    box = Toolbox(Workspace(ws), home=home, yes=yes, confirm=confirm)
    return A.Tagentic(lm, box, home=home, **kw)


# ------------------------------------------------------------------------------------------------ system prompt
def test_system_prompt_carries_the_greeting_and_profile_instructions(env):
    sp = make(env, FakeLM()).system_prompt()
    for must in ('[session_start]', 'ภาษาอังกฤษ', 'สวัสดี', 'ภาษาไทย', 'TAGENTIC', 'Klanarongz2009', 'GitHub', 'ชื่อ', 'อาชีพ',
                 'file="User.md"', 'ไม่ต้องถาม', 'ไม่ต้องตอบตรงคำ', 'ประวัติ'):
        assert must in sp, must


def test_history_facts_are_in_a_file_the_model_reads(env):
    sp = make(env, FakeLM()).system_prompt()
    for fact in ('ส่วนหนึ่งของ TER-AI', 'thinking + agentic', 'Gemma 4', 'open model', 'beta', 'memory 4 ไฟล์', 'ไม่ได้ฝึก'):
        assert fact in sp, fact


def test_shipped_files_hold_no_personal_data_of_the_maintainer():
    text = '\n'.join(p.read_text(encoding='utf-8') for p in (PKG / 'data').rglob('*.md'))
    text += '\n'.join(p.read_text(encoding='utf-8') for p in PKG.glob('*.py'))
    assert not M.PHONE.search(text)
    # The words to look for are personal too, so they stay out of the repository: a private list (one per line)
    # in $TERAI_PRIVACY_WORDS, checked when it is set.
    words = os.environ.get('TERAI_PRIVACY_WORDS')
    if words and Path(words).is_file():
        for word in filter(None, (w.strip() for w in Path(words).read_text(encoding='utf-8').splitlines())):
            assert word not in text, 'a private word is in the shipped files'


def test_memory_load_order_and_skill_included(env):
    ws, home = env
    files = M.load_memory(home)
    assert [f.name for f in files] == list(M.MEMORY_ORDER)
    skill = next(f for f in files if f.name == 'Systemskill.md').text
    assert 'ai-memory-continuity' in skill and '<!-- include' not in skill


# ------------------------------------------------------------------------------------------------ no canned replies
def test_no_fixed_reply_texts_in_the_package():
    assert not (PKG / 'greeting.py').exists()
    src = '\n'.join(p.read_text(encoding='utf-8') for p in PKG.glob('*.py'))
    for canned in ('สวัสดีครับ', 'ผมคือ TAGENTIC', 'คุณชื่ออะไร', 'อาชีพอะไร', 'บอกมาได้ครับ', 'ยังไม่มีคำตอบ',
                   'หยุดก่อนได้คำตอบ', "Hi, I'm", 'Type a task to start'):
        assert canned not in src, canned


@pytest.mark.parametrize('path', ['final', 'plain_text', 'max_steps', 'timeout', 'empty_final'])
def test_every_reply_is_the_models_own_text(env, path):
    t = token()
    if path == 'final':
        lm, kw = FakeLM(final(t)), {}
    elif path == 'plain_text':
        lm, kw = FakeLM(t), {}
    elif path == 'max_steps':
        lm, kw = FakeLM(step('list_files', {}), step('list_files', {}), final(t)), {'max_steps': 2}
    elif path == 'timeout':
        clock = iter([0.0, 1000.0, 1000.0, 1000.0])
        lm, kw = FakeLM(final(t)), {'timeout': 5, 'clock': lambda: next(clock)}
    else:
        lm, kw = FakeLM(json.dumps({'think': 'x', 'tool': 'final'}), final(t)), {}
    res = make(env, lm, **kw).run('ทำงาน')
    assert res.final == t


def test_bad_json_twice_gives_the_models_text_not_a_made_up_one(env):
    res = make(env, FakeLM('{"broken', '{"broken 2')).run('ทำงาน')
    assert res.stopped == 'error' and res.final == '{"broken 2'


# ------------------------------------------------------------------------------------------------ session
def test_session_opens_with_a_model_generated_turn(env):
    t = token()
    lm = FakeLM(final(t))
    out = io.StringIO()
    sess = C.Session(make(env, lm), out)
    res = sess.open()
    assert res.final == t and t in out.getvalue()
    msgs = lm.calls[0]['messages']
    assert msgs[0]['role'] == 'system' and msgs[-1] == {'role': 'user', 'content': A.SESSION_START}
    assert sess.history == [{'role': 'user', 'content': A.SESSION_START}, {'role': 'assistant', 'content': t}]


def test_thai_greeting_is_answered_by_the_model_with_history(env):
    g, t = token(), token()
    lm = FakeLM(final(g), final(t))
    out = io.StringIO()
    sess = C.Session(make(env, lm), out)
    sess.open()
    res = sess.handle('สวัสดี')
    assert res.final == t and out.getvalue().rstrip().endswith(t)
    msgs = lm.calls[1]['messages']
    assert msgs[-1] == {'role': 'user', 'content': 'สวัสดี'}
    assert {'role': 'assistant', 'content': g} in msgs


def test_model_saves_name_and_occupation_in_user_md(env):
    ws, home = env
    lm = FakeLM(final(token()),
                step('remember', {'fact': 'ชื่อ: บอส', 'file': 'User.md'}),
                step('remember', {'fact': 'อาชีพ: นักเรียน', 'file': 'User.md'}),
                final(token()))
    sess = C.Session(make(env, lm), io.StringIO())
    sess.open()
    res = sess.handle('ผมชื่อบอส เป็นนักเรียน')
    assert [s.tool for s in res.trace.steps] == ['remember', 'remember'] and all(s.ok for s in res.trace.steps)
    user = (home / 'User.md').read_text(encoding='utf-8')
    assert '- ชื่อ: บอส' in user and '- อาชีพ: นักเรียน' in user
    assert 'บอส' not in (home / 'Memory.md').read_text(encoding='utf-8')
    # the next turn: the model sees the saved name in User.md, so it can skip the question
    lm.replies.append(final(token()))
    sess.handle('สวัสดี')
    assert 'ชื่อ: บอส' in lm.calls[-1]['messages'][0]['content']


def test_cli_session_greets_first_then_chats(env):
    ws, home = env
    g, t = token(), token()
    lm = FakeLM(final(g), final(t))
    out = io.StringIO()
    rc = C.main(['-w', str(ws), '--memory-dir', str(home), '--yes'], lm=lm, stdin=io.StringIO('สวัสดี\n'), stdout=out)
    text = out.getvalue()
    assert rc == 0 and text.index(g) < text.index(t)
    assert lm.calls[0]['messages'][-1]['content'] == A.SESSION_START


def test_cli_one_task_has_no_greeting_turn(env):
    ws, home = env
    t = token()
    lm = FakeLM(final(t))
    out = io.StringIO()
    assert C.main(['-w', str(ws), '--memory-dir', str(home), 'สรุป', 'README'], lm=lm, stdout=out) == 0
    assert len(lm.calls) == 1 and lm.calls[0]['messages'][-1]['content'] == 'สรุป README' and t in out.getvalue()


# ------------------------------------------------------------------------------------------------ memory tool
def test_remember_user_md_updates_by_key(env):
    ws, home = env
    box = Toolbox(Workspace(ws), home=home, yes=True)
    assert box.call('remember', {'fact': 'ชื่อ: บอส', 'file': 'User.md'}).ok
    assert box.call('remember', {'fact': 'ชื่อ: บอสใหญ่', 'file': 'User.md'}).ok
    user = (home / 'User.md').read_text(encoding='utf-8')
    assert user.count('- ชื่อ:') == 1 and '- ชื่อ: บอสใหญ่' in user and '## Profile' in user


def test_remember_rejects_phone_and_needs_confirmation(env):
    ws, home = env
    box = Toolbox(Workspace(ws), home=home, yes=True)
    assert not box.call('remember', {'fact': 'เบอร์: 0812345678', 'file': 'User.md'}).ok
    asked = []
    deny = Toolbox(Workspace(ws), home=home, confirm=lambda tool, s: asked.append(tool) or False)
    assert not deny.call('remember', {'fact': 'อาชีพ: ครู', 'file': 'User.md'}).ok
    assert asked == ['remember'] and 'ครู' not in (home / 'User.md').read_text(encoding='utf-8')


def test_remember_default_still_goes_to_memory_md(env):
    ws, home = env
    Toolbox(Workspace(ws), home=home, yes=True).call('remember', {'fact': 'repo ใช้ pytest'})
    assert 'repo ใช้ pytest' in (home / 'Memory.md').read_text(encoding='utf-8')


# ------------------------------------------------------------------------------------------------ identity
def test_identity_is_set_in_systemprompt_md(env):
    text = (PKG / 'data' / 'Systemprompt.md').read_text(encoding='utf-8')
    ident = text[text.index('## ตัวตน'):text.index('## ประวัติ')]
    for must in ('Tagentic', 'TAGENTIC', 'TER-AI', 'Klanarongz2009', 'GitHub', 'Google', 'Gemma 4', 'open model'):
        assert must in ident, must
    assert 'ห้ามบอกว่าคุณถูกพัฒนาหรือสร้างโดย Google' in ident
    assert ident in make(env, FakeLM()).system_prompt()


def test_no_output_guard_in_the_package():
    assert not (PKG / 'identity.py').exists()
    src = '\n'.join(p.read_text(encoding='utf-8') for p in PKG.glob('*.py'))
    for name in ('BAD_IDENTITY', 'spoken_name', 'cut_bad_sentences', '_guard', 'IDENTITY_RULE'):
        assert name not in src, name


@pytest.mark.parametrize('reply', [
    'ผมถูกพัฒนาโดย Google ' + token(),
    "I'm TERAI1BETA, made by Google. " + token(),
    'Tagentic1 (beta) here.\n\n  spaced   text ' + token(),
])
def test_replies_reach_the_user_unchanged(env, reply):
    out = io.StringIO()
    lm = FakeLM(final(reply), final(reply))
    sess = C.Session(make(env, lm), out)
    assert sess.open().final == reply
    assert sess.handle('คุณคือใคร').final == reply
    assert len(lm.calls) == 2 and out.getvalue().count(reply) == 2


def test_bad_claim_in_a_thinking_line_is_kept(env):
    lm = FakeLM(step('list_files', {}, think='Google สร้างผม ดูไฟล์'), final(token()))
    res = make(env, lm).run('ดูไฟล์')
    assert res.trace.steps[0].think == 'Google สร้างผม ดูไฟล์'


# ------------------------------------------------------------------------------------------------ tools and loop
def test_loop_reads_edits_and_tests_code(env):
    ws, home = env
    lm = FakeLM(step('read_file', {'path': 'hello.py'}, 'อ่านโค้ด'),
                step('edit_file', {'path': 'hello.py', 'old': 'a - b', 'new': 'a + b'}, 'แก้เครื่องหมาย'),
                step('run_python', {'code': 'from hello import add; print(add(2, 3))'}, 'เช็ก'),
                final(token()))
    res = make(env, lm).run('แก้ add')
    assert [s.tool for s in res.trace.steps] == ['read_file', 'edit_file', 'run_python']
    assert all(s.ok for s in res.trace.steps)
    assert 'a + b' in (ws / 'hello.py').read_text(encoding='utf-8')
    assert '5' in lm.calls[3]['messages'][-1]['content']
    for s in res.trace.steps:
        assert len(s.think) <= 120 and '\n' not in s.compact()


def test_writes_are_gated(env):
    ws, home = env
    lm = FakeLM(step('write_file', {'path': 'x.txt', 'content': 'x'}), final(token()))
    res = make(env, lm, yes=False, confirm=lambda tool, s: False).run('เขียน')
    assert not res.trace.steps[0].ok and not (ws / 'x.txt').exists()


def test_sandbox_blocks_paths_outside_the_workspace(env):
    ws, home = env
    with pytest.raises(SandboxError):
        Workspace(ws).resolve('../home/User.md')
    res = Toolbox(Workspace(ws), home=home, yes=True).call('read_file', {'path': '/etc/passwd'})
    assert not res.ok


def test_parse_step_tolerates_fences():
    obj = A.parse_step('```json\n{"think": "a", "tool": "list_files"}\n```')
    assert obj['tool'] == 'list_files' and obj['args'] == {}
    assert A.parse_step('no json') is None


def test_session_history_is_sent_back_each_turn(env):
    lm = FakeLM(*[final(token()) for _ in range(4)])
    sess = C.Session(make(env, lm), io.StringIO())
    sess.open()
    sess.handle('หนึ่ง')
    sess.handle('สอง')
    roles = [m['role'] for m in lm.calls[2]['messages']]
    assert roles[:6] == ['system', 'user', 'assistant', 'user', 'assistant', 'user']


# ------------------------------------------------------------------------------------------------ relay mode
def relay(env, lm, *argv):
    ws, home = env
    out = io.StringIO()
    rc = C.main(['-w', str(ws), '--memory-dir', str(home), *argv], lm=lm, stdout=out)
    return rc, json.loads(out.getvalue().strip().splitlines()[-1])


def test_relay_start_is_a_model_greeting_and_history_persists_on_disk(env):
    ws, home = env
    g, t = token(), token()
    rc, r = relay(env, FakeLM(final(g)), '--session', 's1', '--start', '--json')
    assert rc == 0 and r['answer'] == g and r['pending_action'] is None and r['trace'] == []
    assert isinstance(r['timing_s'], float)
    saved = json.loads((home / 'sessions' / 's1.json').read_text(encoding='utf-8'))
    assert saved['history'][0]['content'] == A.SESSION_START and saved['history'][1]['content'] == g
    lm = FakeLM(final(t))   # a new process: only the file carries the conversation
    rc, r = relay(env, lm, '--session', 's1', '--message', 'สวัสดี', '--json')
    assert rc == 0 and r['answer'] == t
    sent = lm.calls[0]['messages']
    assert [m['content'] for m in sent[1:]] == [A.SESSION_START, g, 'สวัสดี']


def test_relay_trace_has_think_tool_args_result_short(env):
    t = token()
    rc, r = relay(env, FakeLM(step('read_file', {'path': 'hello.py'}, think='อ่านโค้ด'), final(t)),
                  '--session', 's2', '--message', 'ดู hello.py', '--json')
    assert rc == 0 and r['answer'] == t
    assert r['trace'][0]['think'] == 'อ่านโค้ด' and r['trace'][0]['tool'] == 'read_file'
    assert r['trace'][0]['args'] == {'path': 'hello.py'} and r['trace'][0]['result_short']


def test_relay_pending_action_then_approve_runs_it(env):
    ws, home = env
    t = token()
    rc, r = relay(env, FakeLM(step('write_file', {'path': 'new.txt', 'content': 'hi'})),
                  '--session', 's3', '--message', 'เขียนไฟล์', '--json')
    assert rc == 0 and r['answer'] is None and r['pending_action']['tool'] == 'write_file'
    assert r['pending_action']['args'] == {'path': 'new.txt', 'content': 'hi'} and not (ws / 'new.txt').exists()
    rc, err = relay(env, FakeLM(), '--session', 's3', '--message', 'อีกเรื่อง', '--json')
    assert rc == 2 and 'error' in err
    lm = FakeLM(final(t))
    rc, r = relay(env, lm, '--session', 's3', '--approve', '--json')
    assert rc == 0 and r['answer'] == t and (ws / 'new.txt').read_text(encoding='utf-8') == 'hi'
    assert r['trace'][0]['tool'] == 'write_file' and r['trace'][0]['args']['path'] == 'new.txt'
    assert lm.calls[0]['messages'][-1]['content'].startswith('ผลจาก write_file (ok)')
    saved = json.loads((home / 'sessions' / 's3.json').read_text(encoding='utf-8'))
    assert saved['pending'] is None and saved['history'][-1]['content'] == t


def test_relay_deny_tells_the_model_and_nothing_runs(env):
    ws, home = env
    t = token()
    relay(env, FakeLM(step('run_shell', {'command': 'touch x'})), '--session', 's4', '--message', 'รัน', '--json')
    lm = FakeLM(final(t))
    rc, r = relay(env, lm, '--session', 's4', '--deny', '--json')
    assert rc == 0 and r['answer'] == t and not (ws / 'x').exists()
    assert 'error' in lm.calls[0]['messages'][-1]['content'] and r['trace'][0]['result_short'] == 'ผู้ใช้ไม่อนุญาต'
    rc, err = relay(env, FakeLM(), '--session', 's4', '--approve', '--json')
    assert rc == 2 and 'error' in err


def test_relay_reset_deletes_the_session(env):
    ws, home = env
    relay(env, FakeLM(final(token())), '--session', 's5', '--start', '--json')
    assert (home / 'sessions' / 's5.json').exists()
    rc, r = relay(env, FakeLM(), '--session', 's5', '--reset')
    assert rc == 0 and r['reset'] and r['existed'] and not (home / 'sessions' / 's5.json').exists()


def test_relay_session_name_cannot_leave_the_sessions_folder(env):
    rc, r = relay(env, FakeLM(), '--session', '../x', '--start', '--json')
    assert rc == 2 and 'error' in r
