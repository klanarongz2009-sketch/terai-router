"""TERAI1BETA chat: the rules are tools, a local Gemma 4 writes the reply, a grounding check guards it.

One turn:
1. The rule chat (chat.Chat) runs first. When a tool rule answers (memory, date and time, random, text tools,
   calculator, units, the Thai Wikipedia pack, web search) its answer is the evidence.
2. When no rule matched, the model picks a tool itself (JSON: tool + input, constrained by a grammar) and the
   tool runs on that input. This catches wordings the rules miss ("ห้าบวกเจ็ด", "ร้อยละ 20 ของ 500").
3. The model writes the reply from the evidence only (or chats freely when there is no question of fact).
4. Grounding check: every number in the reply must come from the evidence, the user's message or the memory;
   the tool's main number must be in the reply; a knowledge reply must overlap the source text; a reply with no
   source must say it does not know. A failed check is retried once at temperature 0, then the rule answer is
   used. The knowledge citation is added by code, never written by the model.
"""
from __future__ import annotations

import json
import re
import time

from ..chat import Chat
from ..normalizer import normalize
from .local import LocalLM

TOOL_OF_STEP = {
    '_forget': 'memory', '_recall': 'memory', '_learn': 'memory', '_datetime': 'datetime', '_random': 'random',
    '_textops': 'textops', '_calc': 'calculator', '_units': 'units', '_continue': 'knowledge',
    '_knowledge_reply': 'knowledge',
}
PLANNER_TOOLS = ('calculator', 'datetime', 'units', 'knowledge', 'none')
REFUSAL = re.compile('ไม่รู้|ไม่มีข้อมูล|ไม่เดา|ไม่แน่ใจ|ตอบไม่ได้|ไม่ทราบ|ไม่พบ')
QUESTION = re.compile(r'\?|อะไร|ไหน|ใคร|เมื่อไร|เมื่อไหร่|เท่าไร|เท่าไหร่|กี่|ทำไม|อย่างไร|ยังไง|หรือเปล่า|ไหม|มั้ย|หรือไม่|'
                      r'^(?:what|who|when|where|why|how|which)\b', re.I)
THAI_DIGITS = str.maketrans('๐๑๒๓๔๕๖๗๘๙', '0123456789')
NUM = re.compile(r'\d+(?:[.,]\d+)*')
URL = re.compile(r'https?://|www\.', re.I)
CITE = re.compile(r'\s*\(ที่มา: .*\)\s*$')

SYSTEM = (
    'คุณคือ TER-AI โมเดล TERAI1BETA ผู้ช่วยภาษาไทยที่รันในเครื่องของผู้ใช้แบบ offline '
    'แทนตัวเองว่า "ผม" และลงท้ายว่า "ครับ" ตอบเป็นภาษาไทยที่เป็นธรรมชาติ สั้นๆ ไม่เกินสามประโยค ไม่ใช้ markdown\n'
    'สิ่งที่คุณทำได้: คิดเลข บอกวันและเวลา แปลงหน่วย จำเรื่องที่ผู้ใช้เล่า ตอบความรู้จาก Wikipedia ภาษาไทยที่มีในเครื่อง '
    'ค้นเว็บเมื่อผู้ใช้เปิด --web และอ่านภาพ สิ่งที่ทำไม่ได้: แปลภาษา ข่าว ราคา และข้อมูลแบบ real-time\n'
    'กฎ: ข้อเท็จจริง ตัวเลข ชื่อ และวันที่ ใช้ได้เฉพาะที่อยู่ใน "ผลจากเครื่องมือ" หรือ "ความจำเกี่ยวกับผู้ใช้" เท่านั้น '
    'ห้ามเติมข้อมูลอื่น ห้ามเดา ถ้าไม่มีข้อมูลให้บอกตรงๆ ว่าไม่รู้ ห้ามใส่ลิงก์ ห้ามอ้างว่าทำสิ่งที่ไม่ได้ทำ'
)


def numbers(text: str) -> set:
    out = set()
    for m in NUM.findall((text or '').translate(THAI_DIGITS)):
        v = m.replace(',', '')
        v = v.rstrip('0').rstrip('.') if '.' in v else v
        out.add(v.lstrip('0') or '0')
    return out


def _trigrams(text: str) -> set:
    t = re.sub(r'\s+', '', text or '')
    return {t[i:i + 3] for i in range(len(t) - 2)}


def support(reply: str, source: str, question: str = '') -> float:
    """Share of the reply's new character trigrams (not copied from the question) found in the source (0..1)."""
    r = _trigrams(reply) - _trigrams(question)
    return (len(r & _trigrams(source)) / len(r)) if r else 1.0


def strip_politeness(text: str) -> str:
    return text.replace('ครับ/ค่ะ', 'ครับ').replace('ครับ/คะ', 'ครับ')


class Brain:
    """TERAI1BETA. reply(text, image=None) -> str. ``lm`` is a LocalLM (or anything with chat/look)."""

    def __init__(self, chat: Chat | None = None, lm: LocalLM | None = None, seed: int = 0, history_turns: int = 3,
                 min_support: float = 0.5, **chat_kw) -> None:
        self.chat = chat or Chat(**chat_kw)
        self.lm = lm or LocalLM()
        self.seed = seed
        self.history_turns = history_turns
        self.min_support = min_support
        self.last = {}

    # ------------------------------------------------------------------ helpers
    def memory_text(self) -> str:
        s = self.chat.state
        if not any([s.get('name'), s.get('likes'), s.get('dislikes'), s.get('plans'), s.get('age'),
                    s.get('location'), s.get('grade'), s.get('kv')]):
            return 'ยังไม่มี'
        return strip_politeness(self.chat._all_facts()).replace('สิ่งที่ผมจำเกี่ยวกับคุณ: ', '')

    def history_text(self) -> str:
        h = self.chat.state['history'][:-1][-self.history_turns:]
        return '\n'.join('ผู้ใช้: ' + x['user'] + '\nTER-AI: ' + (x['bot'] or '') for x in h) or 'ยังไม่มี'

    def _plan(self, text: str) -> tuple:
        """Ask the model which tool to call when no rule matched. Returns (tool, input)."""
        self._topic = ""
        schema = {'type': 'object', 'properties': {'tool': {'type': 'string', 'enum': list(PLANNER_TOOLS)},
                                                    'input': {'type': 'string'}, 'topic': {'type': 'string'}},
                  'required': ['tool', 'input', 'topic']}
        prompt = (
            'เลือกเครื่องมือหนึ่งตัวสำหรับข้อความของผู้ใช้ แล้วเขียน input ให้เครื่องมือนั้นเข้าใจ\n'
            '- calculator: โจทย์เลข เขียน input เป็นนิพจน์ตัวเลขอารบิก เช่น "5+7", "20% ของ 500", "sqrt(81)"\n'
            '- datetime: ถามวัน เวลา วันที่ เขียน input เช่น "วันนี้วันที่เท่าไร", "อีก 3 วันวันอะไร"\n'
            '- units: แปลงหน่วย เขียน input เช่น "5 กิโลเมตร เป็น เมตร"\n'
            '- knowledge: ถามความรู้ทั่วไป เขียน input เป็น "<ชื่อเรื่องหลัก>คืออะไร" เช่น "ปลาทองคืออะไร", "สุนทรภู่คือใคร"\n'
            '- none: คุยเล่น ทักทาย ความรู้สึก หรือไม่ต้องใช้เครื่องมือ\n'
            'topic: ชื่อเรื่องหลักของข้อความเป็นคำนามสั้นๆ เช่น "ดาวอังคาร", "ปลาทอง" (ไม่มีให้เว้นว่าง)\n'
            'ตอบเป็น JSON เท่านั้น\nข้อความของผู้ใช้: ' + text)
        raw = self.lm.chat([{'role': 'user', 'content': prompt}], max_tokens=80, temperature=0.0, seed=self.seed,
                           json_schema=schema)
        try:
            m = re.search(r'\{.*\}', raw, re.S)
            d = json.loads(m.group(0) if m else raw)
            tool = str(d.get('tool', 'none')).strip().lower()
            arg = str(d.get('input', '')).strip()
            self._topic = str(d.get('topic', '')).strip()
        except Exception:
            return 'none', ''
        return (tool if tool in PLANNER_TOOLS else 'none'), arg

    def _run_tool(self, tool: str, arg: str):
        if not arg:
            return None
        n = re.sub(' +', ' ', normalize(arg)).strip()
        c = self.chat
        step = {'calculator': c._calc, 'datetime': c._datetime, 'units': c._units,
                'knowledge': c._knowledge_reply}.get(tool)
        if step is None:
            return None
        try:
            out = step(arg, n)
            topic = getattr(self, '_topic', '')
            if tool == 'knowledge' and (out is None or REFUSAL.search(out)) and topic and topic not in ('', arg):
                q = topic + 'คืออะไร'  # the pack finds a topic by its title
                out2 = step(q, re.sub(' +', ' ', normalize(q)).strip())
                if out2 is not None and not REFUSAL.search(out2):
                    return out2
            return out
        except Exception:
            return None

    # ------------------------------------------------------------------ check
    def check(self, reply: str, kind: str, evidence: str, user: str) -> list:
        """Return the list of grounding problems (empty = passes)."""
        problems = []
        if not reply.strip():
            return ['empty reply']
        if URL.search(reply):
            problems.append('link in reply')
        reply = re.sub(r'TER-?AI ?1 ?BETA', 'TERAI', reply, flags=re.I)
        allowed = numbers(evidence) | numbers(user) | numbers(self.memory_text()) | numbers(self.history_text())
        extra = sorted(numbers(reply) - allowed)
        if extra:
            problems.append('numbers not in any source: ' + ', '.join(extra[:5]))
        if kind == 'tool':
            ev_nums = NUM.findall(CITE.sub('', evidence).translate(THAI_DIGITS))
            need = numbers(ev_nums[-1]) if self.last.get('tool') == 'calculator' and ev_nums else numbers(evidence)
            if ev_nums and not (need & numbers(reply)):
                problems.append('number from the tool result is missing: ' + ev_nums[-1])
            name = self.chat.state.get('name')
            if self.last.get('tool') == 'memory' and name and name in evidence and name not in reply:
                problems.append('name from memory is missing: ' + name)
        if kind == 'knowledge' and not (REFUSAL.search(reply) and not numbers(reply)):
            s = support(reply, CITE.sub('', evidence), user)
            if s < self.min_support:
                problems.append('reply not supported by the source (overlap %.2f)' % s)
        if kind == 'no_source' and not REFUSAL.search(reply):
            problems.append('no source but the reply does not say it does not know')
        if re.search('[\u0e00-\u0e7f]', user) and not re.search('[\u0e00-\u0e7f]', reply):
            problems.append('Thai question, reply not in Thai')
        if len(reply) > 600:
            problems.append('reply too long')
        return problems

    # ------------------------------------------------------------------ one turn
    def _messages(self, text: str, kind: str, tool: str, evidence: str, note: str = '') -> list:
        if kind in ('tool', 'knowledge'):
            task = ('ผลจากเครื่องมือ (' + tool + '): ' + strip_politeness(CITE.sub('', evidence)) + '\n'
                    'ตอบคำถามของผู้ใช้ให้ตรงประเด็นโดยใช้ผลนี้เท่านั้น เขียนตัวเลขให้ตรงกับผลทุกตัว ไม่ต้องบอกที่มา '
                    'ถ้าผลนี้ไม่ได้ตอบสิ่งที่ถาม ให้บอกว่าข้อมูลที่มีไม่ได้บอกเรื่องนั้น')
        elif kind == 'no_source':
            task = ('ผลจากเครื่องมือ: ค้นแล้วไม่พบข้อมูลเรื่องนี้ (' + strip_politeness(evidence) + ')\n'
                    'บอกผู้ใช้สั้นๆ ว่าไม่รู้เรื่องนี้ เพราะไม่มีข้อมูล ห้ามเดาคำตอบ')
        else:
            task = ('ไม่มีผลจากเครื่องมือ ข้อความนี้เป็นการคุยทั่วไป ตอบอย่างเป็นธรรมชาติและเป็นมิตร '
                    'ห้ามอ้างข้อเท็จจริง ตัวเลข หรือข่าว ถ้าเหมาะให้บอกว่าช่วยคิดเลข ถามวันเวลา แปลงหน่วย '
                    'ถามความรู้ จำเรื่องของผู้ใช้ หรืออ่านภาพได้')
        user = ('บทสนทนาก่อนหน้า:\n' + self.history_text() + '\n\nความจำเกี่ยวกับผู้ใช้: ' + self.memory_text() +
                '\n\n' + task + ('\n' + note if note else '') + '\n\nข้อความของผู้ใช้: ' + text)
        return [{'role': 'system', 'content': SYSTEM}, {'role': 'user', 'content': user}]

    def reply(self, text: str, image: str | None = None) -> str:
        t0 = time.time()
        if image:
            return self._image_reply(text, image, t0)
        rule = self.chat.reply(text)
        step = getattr(self.chat, 'last_step', '')
        tool = TOOL_OF_STEP.get(step, '')
        evidence = rule
        planned = None
        if tool and REFUSAL.search(rule) and tool == 'knowledge':
            kind = 'no_source'
        elif tool == 'knowledge':
            kind = 'knowledge'
        elif tool:
            kind = 'tool'
        else:  # social, chitchat, router or unknown: let the model pick a tool
            kind = 'free'
            if step in ('_unknown', '_chitchat_reply', '_router'):
                ptool, parg = self._plan(text)
                planned = (ptool, parg)
                out = self._run_tool(ptool, parg) if ptool != 'none' else None
                if out is not None and not REFUSAL.search(out):
                    tool, evidence = ptool, out
                    kind = 'knowledge' if ptool == 'knowledge' else 'tool'
            if kind == 'free' and step == '_unknown' and QUESTION.search(text):
                kind = 'no_source'
        self.last = {'step': step, 'tool': tool, 'kind': kind, 'planned': planned, 'rule': rule,
                     'evidence': evidence}
        cite = ''
        if kind == 'knowledge':
            m = CITE.search(evidence)
            cite = m.group(0).strip() if m else ''
        reply, problems, tries = '', [], 0
        for temp, note in ((0.4, ''), (0.0, None)):
            if note is None:
                note = 'คำตอบก่อนหน้าผิดกฎ (' + '; '.join(problems) + ') เขียนใหม่ให้ตรงกับผลจากเครื่องมือเท่านั้น'
            tries += 1
            reply = self.lm.chat(self._messages(text, kind, tool, evidence, note), max_tokens=220,
                                 temperature=temp, seed=self.seed + self.chat.state['turns'])
            reply = re.sub(r'\s+', ' ', reply).strip()
            reply = re.sub(r'TER-?AI ?1 ?BETA', 'TER-AI', reply, flags=re.I)
            problems = self.check(reply, kind, evidence, text)
            if not problems:
                break
        fallback = bool(problems)
        if fallback:
            final = strip_politeness(evidence)
        else:
            final = reply + (' ' + cite if cite and not REFUSAL.search(reply) else '')
        h = self.chat.state['history']
        if h:
            h[-1]['bot'] = final
            self.chat.save()
        self.last.update({'reply': reply, 'problems': problems, 'fallback': fallback, 'tries': tries,
                          'seconds': round(time.time() - t0, 2)})
        return final

    __call__ = reply

    def _image_reply(self, text: str, image: str, t0: float) -> str:
        q = (text or '').strip() or 'อธิบายภาพนี้ และอ่านข้อความทั้งหมดที่เห็นในภาพ'
        system = ('คุณคือ TER-AI โมเดล TERAI1BETA ตอบเป็นภาษาไทย แทนตัวเองว่าผม ลงท้ายว่าครับ '
                  'บอกเฉพาะสิ่งที่เห็นในภาพจริง ถ้าอ่านไม่ออกหรือไม่แน่ใจให้บอกตรงๆ ห้ามเดา')
        out = self.lm.look(image, q, system=system)
        out = re.sub(r'[ \t]+', ' ', out).strip()
        h = self.chat.state['history']
        h.append({'t': self.chat.now().isoformat(timespec='seconds'), 'user': '[ภาพ] ' + q, 'bot': out})
        self.chat.save()
        self.last = {'step': 'vision', 'tool': 'vision', 'kind': 'vision', 'reply': out, 'problems': [],
                     'fallback': False, 'tries': 1, 'seconds': round(time.time() - t0, 2)}
        return out
