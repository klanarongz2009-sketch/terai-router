"""Thai typo normalizer used before the intent model.

Steps, in this order (the JavaScript port in docs/index.html follows the same order):
  1. context regex rules (for typos that are only safe in context, e.g. ท่า -> ถ้า at a word start)
  2. known typo pairs, longest first, skipping an occurrence that already sits inside the
     correct word (พิม inside พิมพ์)
  3. collapse a character repeated 4+ times (อีกแล้ววววว -> อีกแล้ว)

skeleton() is a phonetic folding (tone and silent marks dropped, same-sound consonants and
long/short vowels merged). The model uses it as extra features, so typos that are not in the
typo table still land near the correct word.
"""
import json
import re
from importlib import resources

_DATA = None


def _load():
    global _DATA
    if _DATA is None:
        raw = json.loads(resources.files('terai_router').joinpath('data/typo_pairs.json').read_text(encoding='utf-8'))
        pairs = [(t, i) for t, i, *_ in raw.get('safe_pairs', [])]
        pairs += [(t, i) for t, i, *_ in raw.get('candidate_pairs', [])]
        # stable sort: longest typo first, ties keep file order (JS port does the same)
        pairs = sorted(pairs, key=lambda p: -len(p[0]))
        ctx = [(re.compile(p), r, lab) for p, r, lab in raw.get('ctx_rules', [])]
        _DATA = {'pairs': pairs, 'ctx': ctx, 'raw': raw}
    return _DATA


def _replace_guarded(text, typed, intended):
    offs = [k for k in range(len(intended) - len(typed) + 1) if intended.startswith(typed, k)]
    out, i, n = [], 0, 0
    while True:
        j = text.find(typed, i)
        if j < 0:
            out.append(text[i:])
            break
        if any(j - k >= 0 and text.startswith(intended, j - k) for k in offs):
            out.append(text[i:j + len(typed)])
        else:
            out.append(text[i:j] + intended)
            n += 1
        i = j + len(typed)
    return ''.join(out), n


_REPEAT = re.compile(r'(.)\1{3,}')


def normalize(text, return_changes=False):
    """Fix known typos. normalize('เส็ดยัง') -> 'เสร็จยัง'."""
    d = _load()
    out = text
    changes = []
    for pat, rep, label in d['ctx']:
        new = pat.sub(rep, out)
        if new != out:
            changes.append(label)
            out = new
    for typed, intended in d['pairs']:
        if typed in out:
            new, n = _replace_guarded(out, typed, intended)
            if n:
                changes.append(f'{typed}->{intended}')
                out = new
    new = _REPEAT.sub(r'\1', out)
    if new != out:
        changes.append('repeat-collapse')
        out = new
    return (out, changes) if return_changes else out


_DIGITS = re.compile(r'[0-9\u0E50-\u0E59]+')
_SPACE = re.compile(r'\s+')


def fold(text):
    """Lowercase, every run of digits (Arabic or Thai) -> '0', whitespace collapsed."""
    t = _DIGITS.sub('0', text.lower())
    return _SPACE.sub(' ', t).strip()


_DROP = dict.fromkeys(map(ord, '\u0E48\u0E49\u0E4A\u0E4B\u0E4C\u0E47\u0E3A\u0E4D'), None)
_FOLD = str.maketrans({
    'ภ': 'พ', 'ผ': 'พ', 'ฝ': 'ฟ', 'ฐ': 'ท', 'ถ': 'ท', 'ฑ': 'ท', 'ฒ': 'ท', 'ธ': 'ท', 'ณ': 'น', 'ญ': 'ย',
    'ข': 'ค', 'ฆ': 'ค', 'ศ': 'ส', 'ษ': 'ส', 'ซ': 'ส', 'ฎ': 'ด', 'ฏ': 'ต', 'ฬ': 'ล', 'ฮ': 'ห',
    'ใ': 'ไ', 'ฌ': 'ช', 'ฉ': 'ช',
    'ี': 'ิ', 'ู': 'ุ', 'ื': 'ึ',
})
_LEAD_H = re.compile(r'ห(?=[งญนมยรลว])')


def skeleton(text):
    """Phonetic folding: skeleton('หน่อย') == skeleton('น้อย') == 'นอย'."""
    t = text.lower().translate(_DROP).translate(_FOLD)
    t = _LEAD_H.sub('', t)
    return t.replace('ทร', 'ส')
