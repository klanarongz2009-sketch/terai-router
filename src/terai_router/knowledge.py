"""Offline knowledge answers over the bundled Thai Wikipedia pack (CC BY-SA 4.0).

Retrieval is entity lookup: the question is reduced to its content words, the longest article title
(or alias) found inside it picks the article, a typo-tolerant bigram match is the fallback, and the
answer is the passage of that article that best fits the question type. No match -> None, and Chat
says it does not know. All scoring is integer counting so docs/chat.js gives the same result.
"""
import json
import os
import re

PACK_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'knowledge_th.json')

PREFIXES = ['ประเทศ', 'จังหวัด', 'อำเภอ', 'เมือง', 'ภาษา', 'ศาสนา']
PREFIX_KEEP = ['ภาษา', 'ศาสนา']  # stripped alias only if nothing else owns it
# question words / fillers removed anywhere (longest first), then short particles at the edges of each piece
Q_ANY = sorted([
    'คืออะไร', 'คือใคร', 'เป็นใคร', 'เป็นอะไร', 'หมายถึงอะไร', 'หมายถึง', 'อะไร', 'ใคร', 'ที่ไหน', 'ไหน',
    'เมื่อไร', 'เมื่อไหร่', 'เท่าไร', 'เท่าไหร่', 'ยังไง', 'อย่างไร', 'ทำไม', 'หรือเปล่า', 'บอก', 'เกี่ยวกับ',
    'อยากรู้', 'รู้จัก', 'อธิบาย', 'เล่าเรื่อง', 'ขอข้อมูล', 'ช่วย', 'คือ', 'กี่',
    'what is', 'who is', 'who was', 'tell me about', 'what', 'who', 'where',
], key=lambda s: -len(s))
Q_EDGE = ['ครับ', 'คับ', 'ค่ะ', 'คะ', 'นะ', 'หรอ', 'เหรอ', 'ไหม', 'มั้ย', 'หน่อย', 'ได้', 'ให้ฟัง', 'ว่า', 'คุณ', 'เธอ',
          'ผม', 'ฉัน', 'ข้อมูล', 'the', 'a']
WHERE = re.compile(r'ที่ไหน|อยู่ไหน|อยู่(?:ภาค|ทวีป|ประเทศ|จังหวัด)|ตั้งอยู่|where')
WHEN = re.compile(r'เมื่อไร|เมื่อไหร่|ปีอะไร|ปีไหน|ปีไร|when')
NUMBER = re.compile(r'เท่าไร|เท่าไหร่|กี่(?!ย)|how many|how much')
CUES = {
    'where': ['ตั้งอยู่', 'อยู่', 'ภาค', 'ทวีป', 'ประเทศ', 'ทิศ', 'เอเชีย', 'ยุโรป', 'แอฟริกา', 'อเมริกา', 'โอเชียเนีย'],
    'when': ['พ.ศ.', 'ค.ศ.', 'ปี', 'เมื่อ', 'วันที่', 'ศตวรรษ'],
    'number': ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'ล้าน', 'พัน'],
    'what': [],
}
_SQUASH = re.compile(r'[ \-_.,·()"\'“”!?:;/]')


def squash(s):
    return _SQUASH.sub('', s.lower())


def qtype(text):
    t = text.lower()
    if WHERE.search(t):
        return 'where'
    if WHEN.search(t):
        return 'when'
    if NUMBER.search(t):
        return 'number'
    return 'what'


def residual(text):
    """Content words of a question, squashed (no spaces)."""
    t = text.lower()
    for p in Q_ANY:
        t = t.replace(p, ' ')
    out = []
    for part in t.split(' '):
        part = squash(part)
        changed = True
        while changed and part:
            changed = False
            for e in Q_EDGE:
                if part.startswith(e) and len(part) > len(e):
                    part, changed = part[len(e):], True
                if part.endswith(e) and len(part) >= len(e):
                    part, changed = part[:len(part) - len(e)], True
        out.append(part)
    return ''.join(out)


def bigrams(s):
    return set(s[i:i + 2] for i in range(len(s) - 1))


def chunks(text):
    """Split a lead into passages at spaces, each at least 50 characters."""
    out, cur = [], ''
    for piece in text.split(' '):
        cur = (cur + ' ' + piece) if cur else piece
        if len(cur) >= 50:
            out.append(cur)
            cur = ''
    if cur:
        if out and len(cur) < 25:
            out[-1] += ' ' + cur
        else:
            out.append(cur)
    return out


class Knowledge:
    def __init__(self, path=PACK_PATH):
        self.path = path
        self._docs = None

    # ------------------------------------------------------------ loading / index
    def load(self):
        if self._docs is not None:
            return self
        with open(self.path, encoding='utf-8') as fh:
            pack = json.load(fh)
        self.meta = {k: v for k, v in pack.items() if k != 'docs'}
        self._docs = pack['docs']
        best = {}  # alias -> (priority, len(title), index)

        def put(a, pri, i):
            if len(a) < 2:
                return
            cand = (pri, len(self._docs[i][1]), i)
            if a not in best or cand < best[a]:
                best[a] = cand

        for i, (_id, title, _text) in enumerate(self._docs):
            base = re.sub(r' \([^()]*\)$', '', title)
            put(squash(base), 0, i)
            for p in PREFIXES:
                if base.startswith(p) and len(base) - len(p) >= 2:
                    put(squash(base[len(p):]), 2 if p in PREFIX_KEEP else 1, i)
            words = base.split(' ')
            if len(words) >= 2 and len(words[-1]) >= 4:
                put(squash(words[-1]), 3, i)
        self.alias = {a: v[2] for a, v in best.items()}
        self.maxlen = max(len(a) for a in self.alias)
        self.fuzzy = {}  # bigram -> sorted alias list
        self._abg = {}
        for a in sorted(self.alias):
            if len(a) >= 3:
                g = bigrams(a)
                self._abg[a] = len(g)
                for b in g:
                    self.fuzzy.setdefault(b, []).append(a)
        return self

    @property
    def docs(self):
        return self.load()._docs

    # ------------------------------------------------------------ lookup
    def find(self, text):
        """-> dict(doc=index, alias=str, how='title'|'fuzzy', resid=str) or None."""
        self.load()
        r = residual(text)
        if len(r) < 2:
            return None
        hits = []  # (start, alias)
        for i in range(len(r)):
            for L in range(min(self.maxlen, len(r) - i), 1, -1):
                a = r[i:i + L]
                if a in self.alias and (L >= 3 or L == len(r)):
                    hits.append((i, a))
                    break
        if hits:
            k = r.find('ของ')
            after = [h for h in hits if k >= 0 and h[0] > k]
            pool = after if after else hits
            start, a = max(pool, key=lambda h: (len(h[1]), -h[0]))
            tail = len(r) - k - 3 if after else len(r)
            if len(a) * 10 >= 4 * len(r) or (after and len(a) * 10 >= 8 * tail):
                return {'doc': self.alias[a], 'alias': a, 'how': 'title', 'resid': r}
        if len(r) >= 3:
            rg = bigrams(r)
            count = {}
            for b in sorted(rg):
                for a in self.fuzzy.get(b, ()):
                    count[a] = count.get(a, 0) + 1
            best, best_num, best_den = None, 0, 1
            for a in sorted(count):
                num, den = 2 * count[a], self._abg[a] + len(rg)
                if num * best_den > best_num * den:
                    best, best_num, best_den = a, num, den
            if best is not None and best_num * 10 >= 7 * best_den:
                return {'doc': self.alias[best], 'alias': best, 'how': 'fuzzy', 'resid': r}
        return None

    def passage(self, doc, text, start=0):
        """Best passage index for the question text, searching chunks[start:]."""
        cs = chunks(self.docs[doc][2])
        qt = qtype(text)
        if start >= len(cs):
            return cs, None
        if qt == 'what' and start == 0:
            return cs, 0
        title_sq = squash(self.docs[doc][1])
        r = residual(text)
        extra = r.replace(title_sq, '')
        grams = set(extra[i:i + 3] for i in range(len(extra) - 2))
        best, best_s = start, -1
        for j in range(start, len(cs)):
            c = squash(cs[j])
            s = sum(1 for g in sorted(grams) if g in c)
            s += 3 * sum(1 for w in CUES[qt] if w in cs[j])
            if s > best_s:
                best, best_s = j, s
        return cs, best

    def answer(self, doc, text, start=0, limit=260):
        """-> (answer_text, next_chunk_index) or (None, start) when the article has nothing more."""
        cs, j = self.passage(doc, text, start)
        if j is None:
            return None, start
        out, k = cs[j], j + 1
        if j > start and j > 0 and start == 0 and len(cs[0]) + 1 + len(out) <= limit + 60:
            out = cs[0] + ' ' + out  # definition first, then the passage that answers
        while k < len(cs) and len(out) + 1 + len(cs[k]) <= limit:
            out += ' ' + cs[k]
            k += 1
        title = self.docs[doc][1]
        if j > 0 and squash(title) not in squash(out):
            out = title + ': ' + out
        return out, k

    def cite(self, doc):
        return '(ที่มา: Wikipedia ภาษาไทย "' + self.docs[doc][1] + '", CC BY-SA 4.0)'

    def numbers_missing(self, doc, text):
        """Numbers asked about that the article never mentions (e.g. a future year) -> list."""
        body = self.docs[doc][2].replace(',', '')
        return [n for n in re.findall(r'[0-9]+', text.replace(',', '')) if n not in body]
