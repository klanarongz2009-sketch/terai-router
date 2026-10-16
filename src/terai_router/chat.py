"""Chat: an offline Thai chat session built on the TER-AI router, tools and knowledge pack.

    >>> from terai_router import Chat
    >>> c = Chat(now='2026-10-16T15:40:00', seed=7)
    >>> c.reply('ผมชื่อเอก')
    'ยินดีที่ได้รู้จักครับ/ค่ะ คุณเอก ผมจำชื่อไว้แล้ว'
    >>> c.reply('12*8 เท่าไร')
    '12 × 8 = 96'

There is no language model inside. Every reply comes from one of these, tried in order:
forget, memory questions, new facts, greeting / thanks / who / help / stats, date and time,
random, text tools, calculator, unit conversion, small talk, the Thai Wikipedia pack, and
the intent router for short commands. When none of them can answer, the reply says
'ไม่รู้' or 'ไม่มีข้อมูล' instead of guessing.

State (facts, history, follow-up context, random state) is a plain dict. With `path` set it is
loaded from and saved to that JSON file after every turn. docs/chat.js is a line-by-line port:
same rules, same order, same strings, so the demo answers exactly like this file.
"""
import datetime
import json
import os
import re

from . import tools as T
from .knowledge import Knowledge, squash
from .normalizer import normalize

VERSION = '0.8.0'
STATE_VERSION = 1
HISTORY_MAX = 200
CHITCHAT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'chitchat_th.json')

GREETINGS = ['มีอะไรให้ช่วยครับ/คะ', 'ให้ช่วยอะไรไหมครับ/คะ']  # Bogus: both, picked at random

ME = '(?:ผม|ฉัน|หนู|เรา|ดิฉัน|กู|เค้า|ข้า)'
Q = re.compile('อะไร|ไหน|เท่าไร|เท่าไหร่|กี่|ไหม|มั้ย|หรือเปล่า|รึเปล่า|ยังไง|อย่างไร|ทำไม|ใคร|เมื่อไร|เมื่อไหร่|\\?|'
               '(?:^| )(?:what|who|where|when|how|which)(?: |$)|^(?:is|are|do|does|can) ')
END = re.compile('(?: *(?:ครับ|คับ|ค่ะ|คะ|ค่า|จ้า|จ้ะ|จ๊ะ|นะ|น่ะ|ล่ะ|หล่ะ|เลย|แหละ|ด้วย|มากๆ|มาก ๆ|มาก|ที่สุด))+$')
NAME_END = re.compile('(?: *(?:ครับ|คับ|ค่ะ|คะ|ค่า|จ้า|จ้ะ|จ๊ะ|นะครับ|นะคะ|นะค่ะ| นะ))+$')
DAY_WORDS = [('มะรืนนี้', 2), ('มะรืน', 2), ('พรุ่งนี้', 1), ('วันนี้', 0), ('คืนนี้', 0), ('เย็นนี้', 0),
             ('เช้านี้', 0), ('บ่ายนี้', 0), ('เมื่อวานซืน', -2), ('เมื่อวาน', -1)]
WEEKDAY_RE = re.compile('วัน(จันทร์|อังคาร|พุธ|พฤหัสบดี|พฤหัส|ศุกร์|เสาร์|อาทิตย์)')
LIVE = re.compile('ราคา|ล่าสุด|ปัจจุบัน|ข่าว|หุ้น|ผลบอล|ผลฟุตบอล|ค่าเงิน|อัตราแลกเปลี่ยน|ตอนนี้|วันนี้|เมื่อวาน|พรุ่งนี้|today|latest|price')
PRONOUN = re.compile('^(?:แล้ว)? *(?:มัน|เขา|เค้า|ที่นั่น|ที่นี่|อันนี้|อันนั้น|เมืองนี้|ประเทศนี้|เรื่องนี้|คนนี้|it |he |she |they )')
GRADE = re.compile('(?:ชั้น *|ระดับชั้น *)?((?:ม|ป)\\. *[1-6]|(?:มัธยม|ประถม)(?:ศึกษา)?(?: *ปีที่)? *[1-6]|ปวช\\.? *[1-3]|ปวส\\.? *[1-2]|อนุบาล *[1-3]|มหาวิทยาลัย *ปี *[1-8]|grade *[0-9]{1,2})')
GRADE_Q = re.compile(ME + ' *(?:กำลัง)?(?:เรียน *)?(?:อยู่ *)?(?:ชั้น|ระดับชั้น|ม\\.|ป\\.) *(?:อะไร|ไหน|ไร|เท่าไร|เท่าไหร่|ที่เท่าไร|ที่เท่าไหร่)|' + ME + ' *เรียน(?:อยู่)? *(?:ชั้น)?(?:อะไร|ไหน|ไร)|what grade am i')
NO_PENDING = 'ต่อเรื่องไหนดีครับ/คะ ตอนนี้ไม่มีเรื่องค้างอยู่ ลองถามความรู้ เช่น ดาวอังคารคืออะไร แล้วพิมพ์ เล่าต่อ'
CONTINUE = re.compile('^(?:เล่าต่อ|ต่อเลย|ต่อสิ|ขยายความ|อีก|ต่อ|มีอีกไหม|มีอีกมั้ย|เพิ่มเติม|more|go on)$')


def _call(name):
    return 'คุณ' + ('' if re.search('^[\u0E00-\u0E7F]', name) else ' ') + name


def _clean(v):
    v = v.strip()
    v = END.sub('', v).strip()
    return v.strip(' "\'“”.,!')


def _clean_name(v):
    v = NAME_END.sub('', v.strip()).strip()
    return v.strip(' "\'“”.,!')


def _parse_now(now):
    if now is None:
        try:
            from zoneinfo import ZoneInfo
            return datetime.datetime.now(ZoneInfo('Asia/Bangkok')).replace(tzinfo=None)
        except Exception:  # no tz database: local wall time
            return datetime.datetime.now()
    if callable(now):
        return _parse_now(now())
    if isinstance(now, str):
        return datetime.datetime.fromisoformat(now)
    return now


def _empty_state(seed):
    return {'version': STATE_VERSION, 'name': None, 'likes': [], 'dislikes': [], 'plans': [], 'age': None,
            'location': None, 'grade': None, 'kv': [], 'history': [], 'turns': 0, 'rng': seed & 0xFFFFFFFF, 'last': None}


class Chat:
    """One conversation. reply(text) -> str. path: JSON file for the session (None = in memory).

    now: None (wall clock, Asia/Bangkok), an ISO string, a datetime, or a callable returning one.
    seed: random seed for dice, random numbers and the greeting variant (None = from the clock).
    """

    _knowledge = None
    _chitchat = None

    def __init__(self, path=None, now=None, seed=None, knowledge=None, web=False, searx=None, websearch=None):
        self.path = os.path.expanduser(path) if path else None
        # opt-in web search: off by default, and no network at all while off
        if websearch is not None:
            self.web = websearch
        elif web or searx:
            from .websearch import WebSearch
            self.web = WebSearch(enabled=True, searx=searx)
        else:
            self.web = None
        self._web_tried = False
        self._now = now
        if knowledge is not None:
            self.kb = knowledge
        else:
            if Chat._knowledge is None:
                Chat._knowledge = Knowledge()
            self.kb = Chat._knowledge
        if Chat._chitchat is None:
            with open(CHITCHAT_PATH, encoding='utf-8') as fh:
                Chat._chitchat = json.load(fh)['pairs']
        if seed is None:
            seed = int(datetime.datetime.now().timestamp() * 1000)
        self.state = _empty_state(seed)
        if self.path and os.path.exists(self.path):
            with open(self.path, encoding='utf-8') as fh:
                loaded = json.load(fh)
            self.state.update(loaded)

    # ------------------------------------------------------------------ persistence
    @classmethod
    def load(cls, path, **kw):
        return cls(path=path, **kw)

    def save(self, path=None):
        path = os.path.expanduser(path) if path else self.path
        if not path:
            return None
        d = os.path.dirname(os.path.abspath(path))
        os.makedirs(d, exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(self.state, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
        return path

    def forget(self):
        """Erase every fact and the history. The random state is kept."""
        rng = self.state['rng']
        self.state = _empty_state(0)
        self.state['rng'] = rng
        self.save()

    @property
    def facts(self):
        s = self.state
        return {'name': s['name'], 'likes': list(s['likes']), 'dislikes': list(s['dislikes']), 'age': s['age'],
                'location': s['location'], 'grade': s.get('grade'), 'plans': [dict(p) for p in s['plans']], 'kv': [list(p) for p in s['kv']]}

    @property
    def history(self):
        return list(self.state['history'])

    # ------------------------------------------------------------------ helpers
    def now(self):
        return _parse_now(self._now)

    def today(self):
        n = self.now()
        return T.days_from_civil(n.year, n.month, n.day)

    def _rand(self):
        self.state['rng'], x = T.rng_next(self.state['rng'])
        return x

    def _randint(self, lo, hi):
        return lo + int(self._rand() * (hi - lo + 1))

    def _nm(self):
        """' คุณ<name>' or ''."""
        return (' ' + _call(self.state['name'])) if self.state['name'] else ''

    def _fact_count(self):
        s = self.state
        return ((1 if s['name'] else 0) + len(s['likes']) + len(s['dislikes']) + len(s['plans'])
                + (1 if s['age'] else 0) + (1 if s['location'] else 0) + len(s['kv']))

    def _day_label(self, day):
        t = self.today()
        rel = {t: 'วันนี้', t + 1: 'พรุ่งนี้', t + 2: 'มะรืนนี้', t - 1: 'เมื่อวาน'}.get(day)
        return (rel + ' (' + T.th_date(day) + ')') if rel else T.th_date(day)

    def _plan_text(self, p):
        if p.get('day') is not None:
            return self._day_label(p['day']) + ' คุณจะ' + p['what']
        return ((p['when'] + ' ') if p.get('when') else '') + 'คุณจะ' + p['what']

    def _resolve_day(self, text):
        """-> (label, day number) for the first day word in text, or (None, None)."""
        for w, off in DAY_WORDS:
            if w in text:
                return w, self.today() + off
        m = WEEKDAY_RE.search(text)
        if m:
            name = 'พฤหัสบดี' if m.group(1) == 'พฤหัส' else m.group(1)
            t = self.today()
            k = T.TH_DAYS.index(name)
            ahead = (k - T.weekday(t)) % 7
            return m.group(0), t + (ahead if ahead else 7)
        for w in ('สัปดาห์หน้า', 'อาทิตย์หน้า', 'เดือนหน้า', 'ปีหน้า'):
            if w in text:
                return w, None
        return None, None

    # ------------------------------------------------------------------ main entry
    def reply(self, text):
        text = (text or '').strip()
        if not text:
            return 'พิมพ์ข้อความมาได้เลยครับ/ค่ะ'
        n = normalize(text)
        n = re.sub(' +', ' ', n).strip()
        self.state['turns'] += 1
        self._web_tried = False
        out = None
        for step in (self._forget, self._recall, self._learn, self._social, self._datetime, self._random,
                     self._textops, self._calc, self._units, self._continue, self._chitchat_reply,
                     self._knowledge_reply, self._router, self._unknown):
            out = step(text, n)
            if out is not None:
                break
        if self.state['turns'] == 0:  # forget ran: start counting again from this message
            self.state['turns'] = 1
        h = self.state['history']
        h.append({'t': self.now().isoformat(timespec='seconds'), 'user': text, 'bot': out})
        if len(h) > HISTORY_MAX:
            del h[:len(h) - HISTORY_MAX]
        self.save()
        return out

    __call__ = reply

    # ------------------------------------------------------------------ 1. forget
    def _forget(self, text, n):
        low = n.lower()
        if re.search('^(?:ช่วย)?(?:ลืม|ล้าง)(?:ความจำ|ทั้งหมด|ทุกอย่าง|หมดเลย|หมด|ทุกเรื่อง)|ล้างความจำ|^forget (?:everything|all)|^clear memory', low):
            self.forget()
            self.state['turns'] = 0
            return 'ล้างความจำทั้งหมดแล้วครับ/ค่ะ ตอนนี้ผมไม่รู้อะไรเกี่ยวกับคุณเลย เริ่มใหม่ได้'
        m = re.search('^(?:ช่วย)?ลืม(ชื่อ|สิ่งที่ชอบ|ที่ชอบ|ที่ไม่ชอบ|แผน|อายุ|ที่อยู่|ชั้นเรียน|ชั้น)', low)
        if m:
            k = m.group(1)
            if k == 'ชื่อ':
                self.state['name'] = None
            elif k in ('สิ่งที่ชอบ', 'ที่ชอบ'):
                self.state['likes'] = []
            elif k == 'ที่ไม่ชอบ':
                self.state['dislikes'] = []
            elif k == 'แผน':
                self.state['plans'] = []
            elif k == 'อายุ':
                self.state['age'] = None
            elif k in ('ชั้นเรียน', 'ชั้น'):
                self.state['grade'] = None
            else:
                self.state['location'] = None
            return 'ลืม' + k + 'ของคุณแล้วครับ/ค่ะ'
        return None

    # ------------------------------------------------------------------ 2. questions about the user
    def _recall(self, text, n):
        s = self.state
        low = n.lower()
        if re.search('(?:เมื่อกี้|เมื่อกี๊|เมื่อตะกี้|ก่อนหน้านี้|ล่าสุด).*(?:พูด|ถาม|พิมพ์|บอก|ส่ง).*(?:อะไร|ไร)|what did i (?:say|ask)', low):
            users = [h['user'] for h in s['history']]
            if not users:
                return 'ผมยังไม่มีข้อความก่อนหน้าของคุณในความจำครับ/ค่ะ (ไม่มีข้อมูล)'
            verb = 'ถาม' if 'ถาม' in low or 'ask' in low else 'พิมพ์'
            out = 'เมื่อกี้คุณ' + verb + 'ว่า "' + users[-1] + '"'
            if len(users) >= 2:
                out += ' ก่อนหน้านั้น: "' + users[-2] + '"'
            return out
        if re.search('จำอะไร.*(?:ผม|ฉัน|หนู|เรา).*ได้|รู้อะไรเกี่ยวกับ' + ME + '|จำอะไรได้บ้าง|what do you (?:know|remember)', low):
            return self._all_facts()
        if not re.search('ของ' + ME + ' *ชื่อ', low) and re.search(ME + ' *ชื่อ(?:อะไร|ไร)|ชื่อ(?:ของ)?' + ME + ' *(?:คือ)?(?:อะไร|ไร)|what(?: is|\'s) my name|do you know my name|ผมชื่ออะไร', low):
            if s['name']:
                return 'คุณชื่อ' + ('' if re.search('^[\u0E00-\u0E7F]', s['name']) else ' ') + s['name'] + 'ครับ/ค่ะ'
            return 'ผมยังไม่รู้ชื่อคุณครับ/ค่ะ บอกได้เลย เช่น ผมชื่อ... หรือ ฉันชื่อ...'
        if re.search(ME + ' *(?:ไม่ชอบ|เกลียด)(?:อะไร|ไร)', low):
            if s['dislikes']:
                return 'คุณไม่ชอบ' + ', '.join(s['dislikes']) + 'ครับ/ค่ะ'
            return 'ผมยังไม่รู้ว่าคุณไม่ชอบอะไร (ยังไม่มีข้อมูล) บอกได้ เช่น ผมไม่ชอบ...'
        if re.search(ME + ' *(?:ชอบ|รัก)(?:อะไร|ไร)|what do i like', low):
            if s['likes']:
                return 'คุณชอบ' + ', '.join(s['likes']) + 'ครับ/ค่ะ'
            return 'ผมยังไม่รู้ว่าคุณชอบอะไร (ยังไม่มีข้อมูล) บอกได้ เช่น ผมชอบ...'
        m = re.search('^(.*?)' + ME + '? *(?:จะ|ต้อง)? *(?:ทำ(?:อะไร|ไร)|ไปไหน|มีแผนอะไร|มีนัดอะไร|มีนัดไหม|มีแผนไหม)', low)
        if m and (re.search(ME, low) or self._resolve_day(m.group(1))[0]) and not re.search('เธอ|คุณจะ|บอท', low):
            label, day = self._resolve_day(low)
            plans = s['plans']
            if label and day is not None:
                hit = [p for p in plans if p.get('day') == day]
            elif label:
                hit = [p for p in plans if p.get('when') == label]
            else:
                hit = list(plans)
            if hit:
                return '; '.join(self._plan_text(p) for p in hit)
            out = 'ผมไม่มีข้อมูลว่า' + (label + 'คุณ' if label else 'คุณ') + 'จะทำอะไรครับ/ค่ะ'
            if plans:
                out += ' แผนที่ผมจำไว้: ' + '; '.join(self._plan_text(p) for p in plans)
            return out
        if re.search(ME + ' *อายุ *(?:เท่าไร|เท่าไหร่|กี่ปี|กี่ขวบ)|how old am i', low):
            if s['age']:
                return 'คุณอายุ ' + s['age'] + ' ปีครับ/ค่ะ'
            return 'ผมยังไม่รู้อายุคุณครับ/ค่ะ (ยังไม่มีข้อมูล)'
        if GRADE_Q.search(low):
            if s.get('grade'):
                return 'คุณเรียนอยู่ชั้น ' + s['grade'] + ' ครับ/ค่ะ'
            return 'ผมยังไม่รู้ว่าคุณเรียนอยู่ชั้นอะไรครับ/ค่ะ (ยังไม่มีข้อมูล) บอกได้ เช่น ผมอยู่ ม.4'
        if re.search(ME + ' *(?:อยู่|อาศัยอยู่|มาจาก) *(?:ที่)?(?:ไหน|จังหวัดอะไร|ที่ไหน)|บ้าน' + ME + 'อยู่(?:ที่)?ไหน|where do i live', low):
            if s['location']:
                return 'คุณอยู่' + s['location'] + 'ครับ/ค่ะ'
            return 'ผมยังไม่รู้ว่าคุณอยู่ที่ไหนครับ/ค่ะ (ยังไม่มีข้อมูล)'
        m = re.search('^(.+?) *ของ' + ME + ' *(?:คือ|เป็น|ชื่อ)? *(?:อะไร|ไร|เท่าไร|เท่าไหร่|ที่ไหน|ไหน|ใคร)', n)
        if m:
            key = squash(m.group(1))
            for k, v in s['kv']:
                if squash(k) == key or (len(key) >= 3 and (key in squash(k) or squash(k) in key)):
                    return k + 'ของคุณคือ ' + v + ' ครับ/ค่ะ'
            return 'ผมไม่รู้' + m.group(1).strip() + 'ของคุณครับ/ค่ะ (ยังไม่มีข้อมูล) ถ้าบอกผม เช่น "' + m.group(1).strip() + 'ของผมคือ ..." ผมจะจำไว้'
        if Q.search(low) and re.search('(?:บ้าน|ของ|แม่|พ่อ|พี่|น้อง|เพื่อน|ครู|แฟน|ห้อง|โรงเรียน)' + ME + '|' + ME + ' *(?:มี|เคย|ได้|เป็น)', low):
            return 'ผมไม่รู้ครับ/ค่ะ เรื่องนี้ของคุณผมยังไม่มีข้อมูล ถ้าบอกผม ผมจะจำไว้'
        return None

    def _all_facts(self):
        s = self.state
        parts = []
        if s['name']:
            parts.append('ชื่อ ' + s['name'])
        if s['age']:
            parts.append('อายุ ' + s['age'] + ' ปี')
        if s['location']:
            parts.append('อยู่' + s['location'])
        if s.get('grade'):
            parts.append('เรียนชั้น ' + s['grade'])
        if s['likes']:
            parts.append('ชอบ ' + ', '.join(s['likes']))
        if s['dislikes']:
            parts.append('ไม่ชอบ ' + ', '.join(s['dislikes']))
        for p in s['plans']:
            parts.append('แผน: ' + self._plan_text(p))
        for k, v in s['kv']:
            parts.append(k + ' = ' + v)
        if not parts:
            return 'ตอนนี้ผมยังไม่รู้อะไรเกี่ยวกับคุณเลยครับ/ค่ะ (ยังไม่มีข้อมูล) เล่าให้ฟังได้ เช่น ผมชื่อ... ผมชอบ...'
        return 'สิ่งที่ผมจำเกี่ยวกับคุณ: ' + '; '.join(parts)

    # ------------------------------------------------------------------ 3. new facts
    def _learn(self, text, n):
        s = self.state
        if Q.search(n.lower()):
            return None
        src = text if text.replace(' ', '') == n.replace(' ', '') else n
        src = re.sub(' +', ' ', src).strip()
        corr = False
        m = re.search('^(?:ไม่ใช่|ไม่ช่าย|ผิด|no)(?:ครับ|คับ|ค่ะ|คะ|นะ)?[ ,]*', src)
        if m and len(src) > len(m.group(0)):
            src, corr = src[len(m.group(0)):], True
        low = src.lower()
        said = []
        # key/value first: "รหัสล็อกเกอร์ของผมคือ 4821", "แมวของผมชื่อส้ม"
        m = re.search('^(.+?) *ของ' + ME + ' *(?:คือ|เป็น|ชื่อ) *(.+)$', src)
        if m:
            k, v = m.group(1).strip(), _clean(m.group(2))
            if k and v:
                kv = [p for p in s['kv'] if squash(p[0]) != squash(k)]
                kv.append([k, v])
                s['kv'] = kv
                return 'จำไว้แล้วครับ/ค่ะ: ' + k + 'ของคุณคือ ' + v
        m = (re.search('(?:^|[ ,])' + ME + ' *ชื่อ(?:เล่น)? *(?:ว่า)? *([^ ,]+)', src)
             or re.search('^(?:ชื่อ|เรียก' + ME + 'ว่า) *([^ ,]+)', src)
             or re.search('เรียก' + ME + ' *ว่า *([^ ,]+)', src)
             or re.search('(?:my name is|call me|i am called|i\'m called) +([^ ,.!]+)', low))
        if m:
            name = _clean_name(src[m.start(1):m.end(1)])
            if name and name not in ('อะไร', 'ไร') and len(name) <= 30:
                old = s['name']
                s['name'] = name
                if old == name:
                    said.append('ใช่ครับ/ค่ะ ' + _call(name) + ' ผมจำไว้อยู่แล้ว')
                elif old and (corr or old != name):
                    said.append('แก้ให้แล้วครับ/ค่ะ ต่อไปผมจะเรียกว่า' + _call(name))
                else:
                    said.append('ยินดีที่ได้รู้จักครับ/ค่ะ ' + _call(name) + ' ผมจำชื่อไว้แล้ว')
        has_me = re.search(ME, low) is not None or bool(said)
        m = re.search('(?:' + ME + ' *)?อายุ *([0-9]+) *(?:ปี|ขวบ)?', low)
        if m and has_me:
            s['age'] = m.group(1)
            said.append('จำไว้แล้วว่าคุณอายุ ' + m.group(1) + ' ปี')
        m = GRADE.search(src)
        if m and has_me and re.search(ME + ' *(?:กำลัง)?(?:เรียน|อยู่|เป็นนักเรียน|เป็นนักศึกษา|ขึ้น)', src):
            g = re.sub(' +', ' ', m.group(1)).strip()
            g = re.sub('^(ม|ป)\\. *', '\\1.', g)
            s['grade'] = g
            said.append('จำไว้แล้วว่าคุณเรียนอยู่ชั้น ' + g)
        m = re.search('(?:' + ME + ' *)?(?:อาศัยอยู่|อยู่|มาจาก) *(?:ที่|จังหวัด)? *([^ ,]+)', src)
        if m and has_me and not re.search('อยู่ *(?:กับ|บ้าน|ม\\.|ป\\.|ชั้น|ห้อง|ว่าง|ดี|เฉย|คนเดียว)', src):
            loc = _clean(m.group(1))
            if loc and not re.search('^(?:แล้ว|ตอนนี้|ใน|ที่นี่|นี่)$', loc):
                s['location'] = loc
                said.append('จำไว้แล้วว่าคุณอยู่' + loc)
        if not said:
            m = re.search('(?:^|[ ,])' + ME + ' *(?:ไม่ชอบ|เกลียด|ไม่ถูกกับ) *(.+)$', src)
            if m:
                v = _clean(m.group(1))
                if v:
                    if v not in s['dislikes']:
                        s['dislikes'].append(v)
                    s['likes'] = [x for x in s['likes'] if x != v]
                    return 'จำไว้แล้วครับ/ค่ะ ว่าคุณไม่ชอบ' + v
            m = re.search('(?:^|[ ,])' + ME + ' *(?:ชอบ|รัก|ชื่นชอบ|ติด) *(.+)$', src)
            if m:
                v = _clean(m.group(1))
                if v and v not in ('เธอ', 'คุณ', 'นาย', 'บอท'):
                    if v not in s['likes']:
                        s['likes'].append(v)
                    s['dislikes'] = [x for x in s['dislikes'] if x != v]
                    like_reply = 'จำไว้แล้วครับ/ค่ะ ว่าคุณชอบ' + v
                    return like_reply
            m = re.search('^(.*?)' + ME + ' *(?:จะ|ต้อง|มีนัด|มีแผน(?:จะ)?|กำลังจะ) *(.+)$', src)
            if m:
                what = _clean(m.group(2))
                rest = m.group(1) + ' ' + what
                label, day = self._resolve_day(rest)
                if label:
                    what = _clean(what.replace(label, '')) if label in what else what
                if what:
                    p = {'what': what, 'when': label, 'day': day}
                    s['plans'] = [x for x in s['plans'] if not (x['what'] == what and x.get('day') == day)] + [p]
                    return 'จำไว้แล้วครับ/ค่ะ: ' + self._plan_text(p)
        if said:
            return ' '.join(said)
        return None

    # ------------------------------------------------------------------ 4. greeting, thanks, who, help, stats
    def _social(self, text, n):
        low = n.lower()
        short = len(squash(low)) <= 20
        if re.search('^(?:สวัสดี|หวัดดี|ดีจ้า|ดีครับ|ดีค่ะ|ดีคับ|hello|hi|hey|สวัสดีตอน)', low) or (short and self._intent(n, 'greet')):
            v = GREETINGS[int(self._rand() * len(GREETINGS))]
            return 'สวัสดีครับ/ค่ะ' + self._nm() + ' ' + v
        if re.search('ขอบคุณ|ขอบใจ|thank|แต๊งกิ้ว|thx', low):
            return 'ยินดีครับ/ค่ะ' + self._nm() + ' มีอะไรให้ช่วยต่อบอกได้เลย'
        if re.search('^(?:เธอ|คุณ|นาย|แก|บอท|ตัวเอง)? *(?:เป็น|คือ)(?:ใคร|อะไร)|^(?:เธอ|คุณ|นาย|บอท) *ชื่อ(?:อะไร|ไร)|who are you|what are you|your name', low):
            return ('ผมคือ TER-AI (เธอ) v' + VERSION + ' แชทบอทภาษาไทยขนาดเล็กที่รัน offline บน CPU สร้างโดย Bogus (made with Sesame) '
                    'ไม่มี LLM ข้างใน ตอบจากเครื่องมือ (คิดเลข วันที่ แปลงหน่วย สุ่ม) ความจำของบทสนทนา และ Wikipedia ภาษาไทย')
        if re.search('(?:ช่วย|ทำ)อะไรได้บ้าง|ใช้ยังไง|ใช้งานยังไง|วิธีใช้|มีคำสั่งอะไร|^help$|^คำสั่ง$|^ช่วยด้วย$', low):
            return ('ผมทำได้: คิดเลข (เช่น (3+4)*2, 15% ของ 200, รากที่สองของ 144), บอกเวลาและวันที่ (อีก 10 วันเป็นวันที่เท่าไร), '
                    'แปลงหน่วย (100 กิโลเมตรเป็นกี่ไมล์), สุ่มเลข ทอยลูกเต๋า โยนเหรียญ, นับตัวอักษร กลับคำ ตัวพิมพ์ใหญ่, '
                    'ตอบความรู้จาก Wikipedia ภาษาไทย ' + format(len(self.kb.docs), ',') + ' บทความ (ถามต่อด้วย มัน... หรือ เล่าต่อ), '
                    'จำชื่อ อายุ ที่อยู่ สิ่งที่ชอบ/ไม่ชอบ แผน และข้อมูลที่บอก (ถาม จำอะไรเกี่ยวกับผมได้บ้าง, ลืมทั้งหมด = ล้างความจำ)')
        if re.search('คุย(?:กัน)?ไป(?:แล้ว)?กี่|คุยกันกี่|กี่ครั้งแล้ว|สถิติ|^stats$', low):
            return ('เราคุยกันไปแล้ว ' + str(self.state['turns']) + ' ครั้ง (นับข้อความของคุณ รวมครั้งนี้) '
                    'ผมจำเรื่องของคุณไว้ ' + str(self._fact_count()) + ' เรื่อง')
        return None

    def _intent(self, n, want, conf=0.9, cov=0.9):
        from . import route
        r = route(n)
        return r['intent'] == want and r['confidence'] >= conf and r['coverage'] >= cov

    # ------------------------------------------------------------------ 5. date and time
    def _datetime(self, text, n):
        low = n.lower()
        now = self.now()
        if re.search('กี่โมง|เวลาเท่าไร|เวลาเท่าไหร่|ตอนนี้เวลา|เวลาอะไร|what time', low):
            return 'ตอนนี้เวลา ' + '%02d:%02d' % (now.hour, now.minute) + ' น. ' + T.th_date(self.today()) + ' (เวลาเครื่อง)'
        if not re.search('วันอะไร|วันไหน|วันที่เท่า|วันที่อะไร|วันที่ไหน|เป็นวันที่|ตรงกับวัน|เดือนอะไร|ปีอะไร|ปีนี้ปี|ปี พ\\.ศ\\.|what day|what date|date today', low):
            return None
        t = self.today()
        label, off = 'วันนี้', 0
        m = re.search('อีก *([0-9]+) *(วัน|สัปดาห์|อาทิตย์)', low)
        m2 = re.search('([0-9]+) *(วัน|สัปดาห์|อาทิตย์)(?:ที่แล้ว|ก่อน)', low)
        if m:
            k = int(m.group(1)) * (7 if m.group(2) != 'วัน' else 1)
            label, off = 'อีก ' + m.group(1) + ' ' + m.group(2), k
        elif m2:
            k = int(m2.group(1)) * (7 if m2.group(2) != 'วัน' else 1)
            label, off = m2.group(1) + ' ' + m2.group(2) + 'ที่แล้ว', -k
        else:
            for w, o in DAY_WORDS:
                if w in low and w not in ('คืนนี้', 'เย็นนี้', 'เช้านี้', 'บ่ายนี้'):
                    label, off = w, o
                    break
        day = t + off
        if re.search('ปีอะไร|ปีนี้ปี|ปี พ\\.ศ\\.', low) and not re.search('วัน', low):
            y = T.civil_from_days(day)[0]
            return 'ปีนี้คือ พ.ศ. ' + str(y + 543) + ' (ค.ศ. ' + str(y) + ')'
        if 'เดือนอะไร' in low and not re.search('วัน', low):
            y, mth, _d = T.civil_from_days(day)
            return 'เดือนนี้คือเดือน' + T.TH_MONTHS[mth - 1] + ' ' + str(y + 543)
        verb = 'คือ' if off == 0 else ('ตรงกับ' if off > 0 else 'คือ')
        return label + verb + T.th_date(day)

    # ------------------------------------------------------------------ 6. random
    def _random(self, text, n):
        low = n.lower()
        if re.search('ลูกเต๋า|ทอยเต๋า|dice|roll a die', low):
            m = re.search('([0-9]+) *(?:ลูก|ครั้ง)', low)
            k = max(1, min(10, int(m.group(1)))) if m else 1
            rolls = [self._randint(1, 6) for _ in range(k)]
            self.state['last'] = {'kind': 'random'}
            if k == 1:
                return 'ทอยลูกเต๋าได้ ' + str(rolls[0])
            return 'ทอยลูกเต๋า ' + str(k) + ' ลูกได้ ' + ', '.join(str(r) for r in rolls) + ' รวม ' + str(sum(rolls))
        if re.search('โยนเหรียญ|หัวหรือก้อย|หัวก้อย|flip a coin|coin', low):
            self.state['last'] = {'kind': 'random'}
            return 'โยนเหรียญได้ ' + ('หัว' if self._rand() < 0.5 else 'ก้อย')
        if re.search('สุ่ม|random', low):
            m = re.search('(-?[0-9]+) *(?:ถึง|-|to|จนถึง|และ|กับ) *(-?[0-9]+)', low)
            lo, hi = (int(m.group(1)), int(m.group(2))) if m else (1, 100)
            if lo > hi:
                lo, hi = hi, lo
            v = self._randint(lo, hi)
            self.state['last'] = {'kind': 'random'}
            return 'สุ่มได้ ' + str(v) + ' (จาก ' + str(lo) + ' ถึง ' + str(hi) + ')'
        return None

    # ------------------------------------------------------------------ 7. text tools
    def _textops(self, text, n):
        ops = [('(?:นับ(?:จำนวน)?(?:ตัวอักษร|ตัวอักขระ|ตัวหนังสือ)|count (?:letters|characters|chars)(?: in)?)', 'count'),
               ('(?:กลับคำ|กลับด้าน|กลับหลัง|reverse)', 'rev'),
               ('(?:ตัวพิมพ์ใหญ่|เป็นพิมพ์ใหญ่|uppercase|upper case|upper)', 'up'),
               ('(?:ตัวพิมพ์เล็ก|เป็นพิมพ์เล็ก|lowercase|lower case|lower)', 'down')]
        for pat, op in ops:
            for src in (text, n):
                m = re.search('^(?:ช่วย|ขอ|ทำ|แปลง)? *(?:ให้)? *' + pat + ' *(?:ของ|คำว่า|ข้อความ)? *[:"“]? *(.+?)["”]?$', src, re.I)
                if m:
                    break
            if not m:
                continue
            arg = m.group(1).strip()
            self.state['last'] = {'kind': 'text'}
            if op == 'count':
                k = len(arg.replace(' ', ''))
                return '"' + arg + '" มี ' + str(k) + ' ตัวอักษร (นับสระและวรรณยุกต์เป็น 1 ตัว ไม่นับช่องว่าง)'
            if op == 'rev':
                return arg[::-1]
            if op == 'up':
                return arg.upper()
            return arg.lower()
        return None

    # ------------------------------------------------------------------ 8. calculator
    def _calc(self, text, n):
        low = n.lower()
        last = self.state['last'] or {}
        expr = None
        follow = re.sub('^(?:แล้ว|เอา|ถ้า|ต่อ) *', '', low)
        follow = re.sub('อีก|เข้าไป|ไป ', '', follow).strip()
        nums = re.findall('[0-9]+(?:\\.[0-9]+)?', follow)
        if (last.get('kind') == 'calc' and len(nums) == 1
                and re.search('^(?:บวก|ลบ|คูณ|หาร|ยกกำลัง|plus|minus|times|divided|[+\\-*/^x×÷])', follow)):
            expr = T.calc_prepare(T.fmt_num(last['value']) + ' ' + follow)
        if expr is None and last.get('kind') == 'calc' and last.get('expr'):
            bare = re.sub('^(?:แล้ว|ถ้า|เอา) *(?:ถ้า)? *(?:เป็น|เปลี่ยนเป็น)? *', '', low)
            bare = END.sub('', bare).strip()
            bare = re.sub(' *(?:ล่ะ|ละ|หล่ะ)$', '', bare).strip()
            if re.search('^-?[0-9]+(?:\\.[0-9]+)?$', bare) and bare != low.strip():
                nums_in = list(re.finditer('[0-9]+(?:\\.[0-9]+)?', last['expr']))
                if nums_in:
                    k = nums_in[-1]
                    expr = last['expr'][:k.start()] + bare + last['expr'][k.end():]
        if expr is None:
            expr = T.calc_prepare(low)
        if expr is None:
            return None
        try:
            v = T.calc_eval(expr)
        except T.CalcError as e:
            msg = str(e)
            if msg == 'div0':
                return T.pretty_expr(expr) + ': หารด้วยศูนย์ไม่ได้ครับ/ค่ะ (หารด้วย 0 ไม่ได้ ไม่มีคำตอบ)'
            if msg == 'sqrt of negative':
                return 'รากที่สองของจำนวนลบไม่มีคำตอบในจำนวนจริงครับ/ค่ะ'
            if msg == 'non-integer power':
                return 'ผมยกกำลังได้เฉพาะเลขชี้กำลังที่เป็นจำนวนเต็มครับ/ค่ะ'
            return 'โจทย์ "' + expr.strip() + '" ไม่ครบหรือรูปแบบไม่ถูก ผมคำนวณไม่ได้ครับ/ค่ะ'
        self.state['last'] = {'kind': 'calc', 'value': v, 'expr': expr}
        return T.pretty_expr(expr) + ' = ' + T.fmt_num(v)

    # ------------------------------------------------------------------ 9. units
    def _units(self, text, n):
        low = n.lower()
        last = self.state['last'] or {}
        found = T.find_units(low)
        uniq = []
        for f in found:
            if f[2] not in [u[2] for u in uniq]:
                uniq.append(f)
        num = None
        if len(uniq) >= 2:
            a, b = uniq[0], uniq[1]
            before = [m for m in re.finditer('-?[0-9]+(?:\\.[0-9]+)?', low) if m.end() <= a[0]]
            anyn = re.search('-?[0-9]+(?:\\.[0-9]+)?', low)
            num = before[-1].group(0) if before else (anyn.group(0) if anyn else '1')
            ua, ub = a[2], b[2]
        elif last.get('kind') == 'unit':
            stripped = re.sub('^(?:แล้ว|ถ้า|เอา) *', '', low)
            stripped = END.sub('', stripped).strip()
            stripped = re.sub(' *(?:ล่ะ|ละ|หล่ะ)$', '', stripped).strip()
            m = re.search('^(-?[0-9]+(?:\\.[0-9]+)?)$', stripped)
            if not m:
                return None
            num, ua, ub = m.group(1), last['from'], last['to']
        else:
            return None
        v = float(num)
        r = T.convert(v, ua, ub)
        if r is None:
            return T.UNITS[ua][3] + ' กับ ' + T.UNITS[ub][3] + ' เป็นหน่วยคนละชนิด แปลงกันไม่ได้ครับ/ค่ะ'
        self.state['last'] = {'kind': 'unit', 'from': ua, 'to': ub}
        places = 2 if abs(r) >= 1 else 6
        return T.fmt_num(v) + ' ' + T.UNITS[ua][3] + ' = ' + T.fmt_num(r, places) + ' ' + T.UNITS[ub][3]

    # ------------------------------------------------------------------ 10. continue the last article
    def _continue(self, text, n):
        last = self.state['last'] or {}
        t = END.sub('', n.lower()).strip()
        if not CONTINUE.search(t):
            return None
        if last.get('kind') != 'kb':
            return NO_PENDING
        ans, nxt = self.kb.answer(last['doc'], last['q'], start=last['next'])
        if ans is None:
            return 'เรื่อง "' + self.kb.docs[last['doc']][1] + '" ผมมีข้อมูลเท่านี้ครับ/ค่ะ ไม่มีข้อมูลเพิ่มแล้ว'
        last['next'] = nxt
        return ans + ' ' + self.kb.cite(last['doc'])

    # ------------------------------------------------------------------ 11. small talk
    def _chitchat_reply(self, text, n):
        s = squash(END.sub('', n.lower()))
        if not s:
            return None
        best, best_len = None, 0
        for pair in Chat._chitchat:
            for p in pair['p']:
                ps = squash(p.lower())
                if ps and ps in s and len(ps) * 10 >= 5 * len(s) and len(ps) > best_len:
                    best, best_len = pair, len(ps)
        if best is None:
            return None
        r = best['r'][self.state['turns'] % len(best['r'])]
        like = self.state['likes'][0] if self.state['likes'] else 'อะไรสักอย่าง'
        name = (' ' + _call(self.state['name'])) if self.state['name'] else ''
        r = r.replace('คุณ{name}', _call(self.state['name']) if self.state['name'] else 'คุณ')
        return r.replace('{name}', name).replace('{like}', like)

    # ------------------------------------------------------------------ 12. knowledge
    def _knowledge_reply(self, text, n):
        last = self.state['last'] or {}
        q = re.sub('^(?:แล้ว|และ|ส่วน) *', '', n)
        q = re.sub(' *(?:ล่ะ|หล่ะ|ละ)(?:ครับ|คับ|ค่ะ|คะ)?$', '', q).strip()
        if PRONOUN.search(n.lower() + ' ') and last.get('kind') == 'kb':
            doc = last['doc']
            ans, nxt = self.kb.answer(doc, n)
            if ans is not None:
                self.state['last'] = {'kind': 'kb', 'doc': doc, 'q': n, 'next': nxt}
                return ans + ' ' + self.kb.cite(doc)
        live = bool(Q.search(n.lower()) and LIVE.search(n.lower()))
        if live and self.web is not None:  # "current/latest" questions: the pack may be stale, ask the web first
            out = self._web_reply(text, q)
            if out is not None:
                return out
        hit = self.kb.find(q) if q else None
        if hit is None:
            if self.web is not None and Q.search(n.lower()) and not self._web_tried:
                out = self._web_reply(text, q)
                if out is not None:
                    return out
            if live:
                return ('ผมไม่มีข้อมูลแบบ real-time (ราคา ข่าว ผลการแข่งขัน หรือเรื่องที่เปลี่ยนทุกวัน) ครับ/ค่ะ '
                        'เพราะผมรัน offline และความรู้หยุดที่ Wikipedia ภาษาไทยวันที่ ' + self.kb.load().meta.get('retrieved', '') + ' เลยตอบไม่ได้')
            return None
        doc = hit['doc']
        miss = self.kb.numbers_missing(doc, n)
        title = self.kb.docs[doc][1]
        if miss:
            return ('ผมไม่มีข้อมูลเรื่อง ' + ', '.join(miss) + ' ใน "' + title + '" ครับ/ค่ะ ผมไม่รู้คำตอบ เลยไม่เดา '
                    '(ความรู้ของผมมาจาก Wikipedia ภาษาไทยวันที่ ' + self.kb.load().meta.get('retrieved', '') + ')')
        ans, nxt = self.kb.answer(doc, q)
        if ans is None:
            return None
        self.state['last'] = {'kind': 'kb', 'doc': doc, 'q': q, 'next': nxt}
        pre = ('(คิดว่าหมายถึง "' + title + '") ') if hit['how'] == 'fuzzy' else ''
        return pre + ans + ' ' + self.kb.cite(doc)

    def _web_reply(self, text, q):
        self._web_tried = True
        hit = self.web.search(q or text)
        if hit is None or not hit.get('answer'):
            return None
        self.state['last'] = {'kind': 'web', 'title': hit['title'], 'url': hit['url']}
        return '[ค้นเว็บ] ' + hit['answer'] + ' ' + self.web.cite(hit)

    # ------------------------------------------------------------------ 13. router for short commands
    def _router(self, text, n):
        if len(squash(n)) > 25:
            return None
        from . import route
        r = route(n)
        if r['confidence'] < 0.9 or r['coverage'] < 0.9:
            return None
        i = r['intent']
        last = self.state['last'] or {}
        if i == 'go_on':
            if last.get('kind') == 'kb':
                return self._continue(text, 'ต่อ')
            return NO_PENDING
        replies = {
            'refuse': 'ได้ครับ/ค่ะ ไม่ทำต่อแล้ว มีอะไรอื่นบอกได้เลย',
            'fix': 'ตรงไหนผิดบอกได้เลยครับ/ค่ะ ถ้าเป็นข้อมูลของคุณ พิมพ์แก้ได้ เช่น ไม่ใช่ ผมชื่อ...',
            'status': 'ตอนนี้ไม่มีงานค้างครับ/ค่ะ ผมตอบทันทีทุกข้อความ ไม่มีงานเบื้องหลัง',
            'calc': 'พิมพ์โจทย์เป็นตัวเลขมาได้เลยครับ/ค่ะ เช่น 12*8 หรือ 15% ของ 200',
            'forget': 'ถ้าต้องการล้างความจำทั้งหมด พิมพ์ ลืมทั้งหมด ครับ/ค่ะ',
            'set_name': 'บอกชื่อมาได้เลยครับ/ค่ะ เช่น ผมชื่อ... หรือ ฉันชื่อ...',
        }
        if i in replies:
            return replies[i]
        if i == 'time':
            return self._datetime(text, 'กี่โมง')
        if i == 'random':
            return self._random(text, 'สุ่ม')
        if i == 'get_name':
            return self._recall(text, 'ผมชื่ออะไร')
        if i in ('greet', 'thanks', 'who', 'help', 'stats'):
            probe = {'greet': 'สวัสดี', 'thanks': 'ขอบคุณ', 'who': 'เป็นใคร', 'help': 'ช่วยอะไรได้บ้าง', 'stats': 'สถิติ'}[i]
            return self._social(text, probe)
        return None

    # ------------------------------------------------------------------ 14. honest fallback
    def _unknown(self, text, n):
        if Q.search(n.lower()):
            base = ('ผมไม่รู้ครับ/ค่ะ ในความรู้ที่ผมมี (Wikipedia ภาษาไทย ' + format(len(self.kb.docs), ',') + ' บทความ) '
                    'ไม่มีข้อมูลที่ตอบคำถามนี้ได้')
            if self._web_tried and self.web is not None:
                if self.web.last_error:
                    return base + ' และค้นเว็บไม่สำเร็จ (' + self.web.last_error.split(':')[0] + ') ผมเลยไม่เดา'
                return base + ' ค้น Wikipedia ไทยและอังกฤษแล้วก็ไม่พบบทความที่ตรงพอ ผมเลยไม่เดา'
            return base + ' ผมเลยไม่เดา'
        return ('ผมยังไม่เข้าใจข้อความนี้ครับ/ค่ะ (ไม่รู้ว่าจะตอบยังไง) ลองถามความรู้ คิดเลข ถามวันเวลา '
                'หรือเล่าเรื่องของคุณให้ผมจำ เช่น ผมชื่อ... ผมชอบ... พิมพ์ ช่วยอะไรได้บ้าง เพื่อดูทั้งหมด')
