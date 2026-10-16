"""Opt-in web search for TER-AI chat.

Off by default: a WebSearch(enabled=False) never opens a network connection.
When enabled it asks, in order:

  1. Thai Wikipedia   (MediaWiki API, search + intro extracts, free, no key)
  2. English Wikipedia (same API)
  3. a SearXNG instance, only if the user gives its base URL

The sources are data only. Ranking the results and picking the passage that
answers is done here, by TER-AI's own scoring (character trigram coverage of the
question's content words), not by the search engine. A result that does not
cover the question well enough is dropped, so a made-up word gets "I don't know"
instead of a random article.

    >>> ws = WebSearch(enabled=True)
    >>> hit = ws.search('ดาวอังคารคืออะไร')   # dict or None

hit = {'title', 'url', 'text', 'source', 'license', 'score'}
"""
import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request

from . import __version__
from .knowledge import CUES, Q_ANY, qtype, residual, squash

USER_AGENT = ('terai-router/' + __version__ +
              ' (offline Thai chat, opt-in web search; https://github.com/klanarongz2009-sketch/terai-router)')
WIKIS = [('th', 'Wikipedia ภาษาไทย'), ('en', 'Wikipedia ภาษาอังกฤษ')]
WIKI_LICENSE = 'CC BY-SA 4.0'
DEFAULT_CACHE = os.path.join('~', '.terai', 'webcache')
CACHE_TTL = 24 * 3600
CACHE_MAX = 200
MIN_COVER = 0.6          # share of the question's trigrams the result must contain
CURRENT = re.compile('ปัจจุบัน|ตอนนี้|ล่าสุด|current|incumbent|now|latest')
CUR_CUES = ['ปัจจุบัน', 'คนปัจจุบัน', 'ดำรงตำแหน่ง', 'current', 'incumbent']
TAIL = re.compile(r'(?: *(?:ครับ|คับ|ค่ะ|คะ|ค่า|จ้า|นะ|หรอ|เหรอ|ไหม|มั้ย|หน่อย|\?))+$')
# a passage never starts with these: they continue the clause before them
CONT = ('ๆ', 'ฯ', '(', ')', ']', ',', '.', ';', ':', 'และ', 'หรือ', 'ซึ่ง', 'โดย', 'แต่', 'ของ', 'จะ', 'เป็น', 'คือ',
        'ได้', 'ก็', 'จึง', 'เพื่อ', 'ทำให้', 'ตั้งแต่', 'กับ', 'แห่ง')
LAT_START = re.compile('[A-Za-z]')
LAT_END = re.compile('[A-Za-z0-9,]$')


def trigrams(s):
    return set(s[i:i + 3] for i in range(len(s) - 2)) if len(s) >= 3 else ({s} if s else set())


def query_text(question):
    """Search query: the question without question words and polite endings (spaces kept)."""
    t = TAIL.sub('', question.strip().lower())
    for p in Q_ANY:
        t = t.replace(p, ' ')
    t = re.sub(' +', ' ', t).strip()
    return t or question.strip()


def cover(question, text):
    """Share of the question's content trigrams found in text (0..1)."""
    g = trigrams(residual(question))
    if not g:
        return 0.0
    body = squash(text)
    return sum(1 for x in g if x in body) / len(g)


def _glue(prev, piece):
    """True when piece continues prev (same clause), so no passage may start at piece."""
    if prev.count('(') > prev.count(')') or prev.count('[') > prev.count(']'):
        return True
    if piece.startswith(CONT) or '0' <= piece[0] <= '9' or prev.split(' ')[-1] in CONT:
        return True
    return bool(LAT_START.match(piece) and prev[-1] not in '.!?' and LAT_END.search(prev))


def units(text):
    """Split text at spaces where a new clause can start (Thai has no sentence marks; spaces are the cue)."""
    out = []
    for piece in text.split(' '):
        if not piece:
            continue
        if out and _glue(out[-1], piece):
            out[-1] += ' ' + piece
        else:
            out.append(piece)
    return out


def passages(text):
    """Like knowledge.chunks (at least 50 characters each) but cut only at clause starts."""
    out, cur = [], ''
    for u in units(text):
        cur = (cur + ' ' + u) if cur else u
        if len(cur) >= 50:
            out.append(cur)
            cur = ''
    if cur:
        if out and len(cur) < 25:
            out[-1] += ' ' + cur
        else:
            out.append(cur)
    return out


def extract(question, text, limit=300):
    """Passage of text that answers the question: definition first, then the best passage."""
    cs = passages(text)
    if not cs:
        return ''
    cues = list(CUES[qtype(question)])
    if CURRENT.search(question.lower()):
        cues += CUR_CUES
    best = 0
    if cues:
        grams = trigrams(residual(question))
        best_s = -1
        for j, c in enumerate(cs):
            s = sum(1 for g in grams if g in squash(c)) + 3 * sum(1 for w in cues if w in c.lower())
            if s > best_s:
                best, best_s = j, s
    out = cs[best]
    if best > 0 and len(cs[0]) + 1 + len(out) <= limit + 60:
        out = cs[0] + ' ' + out
    k = best + 1
    while k < len(cs) and len(out) + 1 + len(cs[k]) <= limit:
        out += ' ' + cs[k]
        k += 1
    return out


class WebSearch:
    """enabled: False = no network ever. searx: optional SearXNG base URL.
    fetch: callable(url) -> parsed JSON (tests inject a fake). cache_dir: None = no disk cache."""

    def __init__(self, enabled=False, searx=None, timeout=5.0, cache_dir=DEFAULT_CACHE, fetch=None):
        self.enabled = bool(enabled)
        self.searx = searx.rstrip('/') if searx else None
        self.timeout = timeout
        self.cache_dir = os.path.expanduser(cache_dir) if cache_dir else None
        self._fetch = fetch
        self.last_error = None
        self.calls = 0

    # ---------------------------------------------------------------- network + cache
    def _cache_path(self, url):
        return os.path.join(self.cache_dir, hashlib.sha1(url.encode('utf-8')).hexdigest() + '.json')

    def get(self, url):
        if not self.enabled:
            raise RuntimeError('web search is disabled')
        if self.cache_dir:
            p = self._cache_path(url)
            try:
                with open(p, encoding='utf-8') as fh:
                    item = json.load(fh)
                if time.time() - item['t'] < CACHE_TTL:
                    return item['data']
            except (OSError, ValueError, KeyError):
                pass
        self.calls += 1
        if self._fetch is not None:
            data = self._fetch(url)
        else:
            req = urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'application/json'})
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                data = json.loads(r.read().decode('utf-8'))
        if self.cache_dir:
            self._cache_put(url, data)
        return data

    def _cache_put(self, url, data):
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            with open(self._cache_path(url), 'w', encoding='utf-8') as fh:
                json.dump({'t': time.time(), 'url': url, 'data': data}, fh, ensure_ascii=False)
            files = sorted((os.path.join(self.cache_dir, f) for f in os.listdir(self.cache_dir) if f.endswith('.json')),
                           key=os.path.getmtime)
            for f in files[:max(0, len(files) - CACHE_MAX)]:
                os.remove(f)
        except OSError:
            pass

    # ---------------------------------------------------------------- sources
    @staticmethod
    def wiki_url(lang, query, limit=5):
        params = {'action': 'query', 'format': 'json', 'formatversion': '2', 'generator': 'search',
                  'gsrsearch': query, 'gsrlimit': str(limit), 'prop': 'extracts|info', 'exintro': '1',
                  'explaintext': '1', 'exlimit': str(limit), 'inprop': 'url', 'redirects': '1'}
        return 'https://' + lang + '.wikipedia.org/w/api.php?' + urllib.parse.urlencode(params)

    def _wiki(self, lang, name, query):
        data = self.get(self.wiki_url(lang, query))
        pages = sorted((data.get('query') or {}).get('pages') or [], key=lambda p: p.get('index', 99))
        out = []
        for p in pages:
            text = (p.get('extract') or '').strip()
            if not text or p.get('missing'):
                continue
            url = p.get('fullurl') or ('https://' + lang + '.wikipedia.org/wiki/' + urllib.parse.quote(p['title'].replace(' ', '_')))
            out.append({'title': p['title'], 'url': url, 'text': re.sub('\\s+', ' ', text),
                        'source': name, 'license': WIKI_LICENSE})
        return out

    def _searx(self, query):
        url = self.searx + '/search?' + urllib.parse.urlencode({'q': query, 'format': 'json'})
        data = self.get(url)
        out = []
        for r in (data.get('results') or [])[:8]:
            if r.get('content') and r.get('url'):
                host = urllib.parse.urlparse(r['url']).netloc
                out.append({'title': r.get('title') or host, 'url': r['url'], 'text': re.sub('\\s+', ' ', r['content']),
                            'source': 'SearXNG (' + host + ')', 'license': 'ดูสัญญาอนุญาตที่หน้าต้นทาง'})
        return out

    # ---------------------------------------------------------------- ranking (our own model)
    @staticmethod
    def rank(question, results):
        """-> best result with 'score' and 'answer', or None when nothing covers the question."""
        best = None
        for i, r in enumerate(results):
            c_all = cover(question, r['title'] + ' ' + r['text'])
            if c_all < MIN_COVER:
                continue
            score = c_all + 0.5 * cover(question, r['title']) - 0.01 * i
            if best is None or score > best['score']:
                best = dict(r, score=score)
        if best is not None:
            best['score'] = round(best['score'], 3)  # rounded only for display; ranking used the exact value
            best['answer'] = extract(question, best['text'])
        return best

    def search(self, question):
        """Best answer for the question, or None (disabled, offline, error or no good match)."""
        self.last_error = None
        if not self.enabled:
            return None
        q = query_text(question)
        steps = [lambda lang=lang, name=name: self._wiki(lang, name, q) for lang, name in WIKIS]
        if self.searx:
            steps.append(lambda: self._searx(q))
        errors = 0
        for step in steps:
            try:
                hit = self.rank(question, step())
            except Exception as e:  # offline, timeout, bad JSON: try the next source
                errors += 1
                self.last_error = type(e).__name__ + ': ' + str(e)[:120]
                continue
            if hit is not None:
                self.last_error = None
                return hit
        if errors < len(steps):
            self.last_error = None  # at least one source answered; it just had nothing good
        return None

    @staticmethod
    def cite(hit):
        return '(ที่มา: ' + hit['source'] + ' "' + hit['title'] + '", ' + urllib.parse.unquote(hit['url']) + ', ' + hit['license'] + ')'
