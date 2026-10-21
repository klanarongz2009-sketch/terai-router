"""TERM AI chatbot: regex rules first, then the tiny trained intent model (no network).

This is the original Terminal AI program (term_ai.py, 2026-10-10, with the TER-AI-0.5 intent
model), packaged so it runs from terai-router. Behaviour is kept as it was: the same rules,
replies (in Thai), thresholds (model confidence >= 0.9 and n-gram coverage > 0.5) and
fallbacks. What changed for the package: the clock and the random generator can be injected,
the memory file path is a parameter, and every reply checks the trial time limit.

Part of the TERM AI limited-time trial: removed on 2027-01-01 00:00:00 Asia/Bangkok (UTC+7).
"""
import ast
import json
import operator
import os
import random
import re
from datetime import datetime, timezone

from . import intent_model
from .trial import BANGKOK, check_trial

DEFAULTS = {
    'bot_name': 'TERM AI',
    'tagline': 'made with Sesame',
    'user_prompt': 'you',
    'model_threshold': 0.9,
    'min_coverage': 0.5,
    'debug': False,
    'greetings': ['สวัสดี{name}', 'หวัดดี{name} มีอะไรให้ช่วย', 'Hello{name}'],
    'who_reply': 'ฉันคือ {bot} chatbot ใน terminal ใช้กฎ + โมเดล intent classifier เล็กๆ ที่เทรนเอง ({tagline})',
    'thanks_reply': 'ยินดี',
    'fallback': ['ยังไม่มีกฎสำหรับข้อความนี้ พิมพ์ \'ช่วย\' เพื่อดูคำสั่ง', 'ไม่เข้าใจ ลองพิมพ์ \'help\''],
}

# ---------- safe calculator ----------
OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod, ast.Pow: operator.pow, ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def safe_eval(expr):
    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            if isinstance(node.op, ast.Pow) and abs(ev(node.right)) > 100:
                raise ValueError('exponent too large')
            return OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
            return OPS[type(node.op)](ev(node.operand))
        raise ValueError('unsupported')
    return ev(ast.parse(expr, mode='eval'))


THAI_OPS = [('บวก', '+'), ('plus', '+'), ('ลบ', '-'), ('minus', '-'), ('คูณ', '*'),
            ('times', '*'), ('หาร', '/'), ('divided by', '/'), ('ยกกำลัง', '**')]


def load_config(path=None):
    """DEFAULTS, overridden by known keys from a JSON file (as config.json did on the VM)."""
    cfg = dict(DEFAULTS)
    if path:
        with open(path, encoding='utf-8') as f:
            user = json.load(f)
        cfg.update({k: v for k, v in user.items() if k in DEFAULTS})
    return cfg


class TermAI:
    """The TERM AI bot. ``reply(text)`` returns one reply string.

    clock:       callable returning a timezone-aware datetime (default: real clock, UTC)
    memory_path: JSON file for the user name and turn count; None keeps memory in RAM only
    seed:        seed for the random replies and the number picker
    """

    def __init__(self, memory_path=None, config=None, clock=None, seed=None, debug=None):
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        check_trial(self.clock())
        self.cfg = dict(DEFAULTS) if config is None else dict(config)
        self.bot = self.cfg['bot_name']
        self.memory_path = memory_path
        self.rng = random.Random(seed)
        self.debug = bool(self.cfg['debug']) if debug is None else bool(debug)
        self.model = intent_model.load_model()
        self.mem = self._load_mem()
        self.help = (
            f'คำสั่งที่ {self.bot} เข้าใจ:\n'
            '- สวัสดี / hello\n'
            '- ฉันชื่อ <ชื่อ>  |  ฉันชื่ออะไร\n'
            '- คำนวณ <นิพจน์>  เช่น คำนวณ (12+8)*3\n'
            '- กี่โมง / วันนี้วันที่เท่าไร\n'
            '- สุ่ม 1-100\n'
            '- กลับคำ <ข้อความ>  |  นับ <ข้อความ>\n'
            '- สถิติ  |  ลืมทั้งหมด\n'
            '- ช่วย / help  |  ออก / exit'
        )
        self.rules = [
            (r'^(help|ช่วย(ด้วย)?|คำสั่ง|\?)$|ทำอะไรได้', self.help),
            (r'^(สวัสดี|หวัดดี|ดีจ้า|hello|hi\b|hey)', self.h_greet),
            (r"(ฉัน|ผม|เรา)\s*ชื่ออะไร|what'?s my name", self.h_get_name),
            (r'^(?:(?:ฉัน|ผม|เรา)\s*ชื่อ|my name is)\s*(?P<name>\S.*)$', self.h_set_name),
            (r'^(คำนวณ|calc|=)\s*(?P<expr>[\d\s+\-*/%().x×÷]+)$', self.h_calc),
            (r'^(?P<expr>[\d\s+\-*/%().×÷]*\d[\d\s+\-*/%().×÷]*[+\-*/%×÷][\d\s+\-*/%().×÷]+)$', self.h_calc),
            (r'กี่โมง|เวลา|วันนี้วันที่|time|date', self.h_time),
            (r'^สุ่ม\s*(?P<a>-?\d+)\s*[-–ถึง]+\s*(?P<b>-?\d+)', self.h_random),
            (r'^(กลับคำ|reverse)\s+(?P<text>.+)$', self.h_reverse),
            (r'^(นับ|count)\s+(?P<text>.+)$', self.h_count),
            (r'^(สถิติ|stats)$', self.h_stats),
            (r'^(ลืมทั้งหมด|forget all)$', self.h_forget),
            (r'(เป็นใคร|who are you|ชื่ออะไร)', self.fill(self.cfg['who_reply'])),
            (r'(ขอบคุณ|thank)', self.cfg['thanks_reply']),
        ]

    # ---------- memory ----------
    def _load_mem(self):
        if self.memory_path:
            try:
                with open(self.memory_path, encoding='utf-8') as f:
                    mem = json.load(f)
                if isinstance(mem, dict):
                    return mem
            except (OSError, ValueError):
                pass
        return {'name': None, 'turns': 0}

    def save(self):
        if not self.memory_path:
            return
        d = os.path.dirname(os.path.abspath(self.memory_path))
        os.makedirs(d, exist_ok=True)
        with open(self.memory_path, 'w', encoding='utf-8') as f:
            json.dump(self.mem, f, ensure_ascii=False, indent=2)

    def fill(self, s):
        return s.replace('{bot}', self.bot).replace('{tagline}', self.cfg['tagline'])

    # ---------- handlers ----------
    def h_calc(self, m):
        expr = m.group('expr').replace('x', '*').replace('×', '*').replace('÷', '/')
        try:
            val = safe_eval(expr)
        except Exception:
            return 'คำนวณไม่ได้: ใช้ได้แค่ตัวเลขกับ + - * / // % ** ( )'
        if isinstance(val, float) and val.is_integer():
            val = int(val)
        return f'{expr.strip()} = {val}'

    def h_time(self, m=None):
        now = self.clock().astimezone(BANGKOK)
        return now.strftime('ตอนนี้ %H:%M น. วันที่ %d/%m/%Y (เวลาไทย)')

    def h_set_name(self, m):
        name = m.group('name').strip()
        self.mem['name'] = name
        return f'จำแล้ว: ชื่อ {name}'

    def h_get_name(self, m=None):
        n = self.mem.get('name')
        return f'คุณชื่อ {n}' if n else "ยังไม่รู้ชื่อ พิมพ์ว่า 'ฉันชื่อ ...' ได้"

    def h_greet(self, m=None):
        who = f" {self.mem['name']}" if self.mem.get('name') else ''
        return self.rng.choice(self.cfg['greetings']).replace('{name}', who)

    def h_stats(self, m=None):
        return f"คุยกันมาแล้ว {self.mem.get('turns', 0)} ข้อความ (นับรวมข้อความนี้)"

    def h_reverse(self, m):
        return m.group('text').strip()[::-1]

    def h_count(self, m):
        t = m.group('text').strip()
        return f'{len(t)} ตัวอักษร, {len(t.split())} คำ (นับตามช่องว่าง)'

    def h_random(self, m):
        a, b = int(m.group('a')), int(m.group('b'))
        if a > b:
            a, b = b, a
        return f'สุ่มได้ {self.rng.randint(a, b)} (ช่วง {a}-{b})'

    def h_forget(self, m=None):
        self.mem.clear()
        self.mem.update({'name': None, 'turns': 0})
        return 'ลบความจำทั้งหมดแล้ว'

    # ---------- model layer ----------
    def by_intent(self, intent, text):
        """Run a handler from a predicted intent, pulling arguments out loosely."""
        if intent == 'greet':
            return self.h_greet()
        if intent == 'help':
            return self.help
        if intent == 'time':
            return self.h_time()
        if intent == 'get_name':
            return self.h_get_name()
        if intent == 'set_name':
            name = None
            m = re.search(r'(?:name is|call me)\s+(\S+)', text, re.I)
            if m:
                name = m.group(1)
            elif 'ชื่อ' in text:
                name = text.rsplit('ชื่อ', 1)[1]
            elif 'ว่า' in text:
                name = text.rsplit('ว่า', 1)[1]
            if name:
                name = re.sub(r'^(ของ)?(ผม|ฉัน|เรา)?\s*(คือ|ว่า|เป็น)?\s*', '', name).strip()
                name = re.sub(r'\s*(นะ|ครับ|ค่ะ|จ้า)+$', '', name).strip()
            if name:
                self.mem['name'] = name
                return f'จำแล้ว: ชื่อ {name}'
            return "จะให้จำชื่ออะไร พิมพ์ว่า 'ผมชื่อ ...'"
        if intent == 'calc':
            t = text.lower()
            for w, op in THAI_OPS:
                t = t.replace(w, op)
            exprs = re.findall(r'[\d\s+\-*/%().]*\d[\d\s+\-*/%().]*', t)
            exprs = [e.strip() for e in exprs if re.search(r'\d\s*[+\-*/%]', e)]
            if exprs:
                return self.h_calc(re.match(r'(?P<expr>.*)', max(exprs, key=len)))
            return 'จะให้คำนวณอะไร พิมพ์เลขมาด้วย เช่น คำนวณ 12*8'
        if intent == 'random':
            nums = [int(n) for n in re.findall(r'-?\d+', text)]
            if 'เต๋า' in text or 'dice' in text.lower():
                nums = [1, 6]
            a, b = (nums[0], nums[1]) if len(nums) >= 2 else (1, 100)
            return self.h_random(re.match(r'(?P<a>-?\d+) (?P<b>-?\d+)', f'{a} {b}'))
        if intent == 'stats':
            return self.h_stats()
        if intent == 'forget':
            return self.h_forget()
        if intent == 'who':
            return self.fill(self.cfg['who_reply'])
        if intent == 'thanks':
            return self.cfg['thanks_reply']
        return None

    def reply(self, text):
        """One reply. Raises TrialEnded at or after 2027-01-01 00:00:00 UTC+7."""
        check_trial(self.clock())
        text = text.strip()
        self.mem['turns'] = self.mem.get('turns', 0) + 1
        # 1) exact rules first (fast, precise)
        for pattern, action in self.rules:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                out = action(m) if callable(action) else action
                return out + (' [rule]' if self.debug else '')
        # 2) no rule matched -> ask the trained model
        intent, p = intent_model.predict(self.model, text, 1)[0]
        # out-of-domain guard: share of the input's 3+ char n-grams the class has seen
        grams = [g for g in intent_model.features(text) if len(g) >= 3]
        seen = sum(1 for g in grams if g in self.model['classes'][intent]['counts'])
        coverage = seen / max(1, len(grams))
        if p >= self.cfg['model_threshold'] and coverage > self.cfg['min_coverage']:
            out = self.by_intent(intent, text)
            if out:
                return out + (f' [model: {intent} p={p:.2f} cov={coverage:.2f}]' if self.debug else '')
        return self.rng.choice(self.cfg['fallback'] or DEFAULTS['fallback'])
