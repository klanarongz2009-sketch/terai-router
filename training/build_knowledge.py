#!/usr/bin/env python3
"""Build the offline knowledge pack -> src/terai_router/data/knowledge_th.json

Source: lead sections of Thai Wikipedia articles (CC BY-SA 4.0). Article list:
  1. English Wikipedia "Vital articles" level 3 and level 4 pages, mapped to Thai with langlinks
  2. Thai-specific seeds (provinces, and a few Thai topics) listed in SEEDS_TH
Each entry keeps the Thai title, the page id and the first part of the plain-text lead,
cut at a sentence gap (space) to at most MAX_CHARS characters. Raw API answers are cached.

usage: python training/build_knowledge.py [--cache DIR]
"""
import argparse
import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
UA = 'TER-AI-knowledge-builder/0.8 (https://github.com/klanarongz2009-sketch/terai-router; klanarongz2009@gmail.com)'
MAX_CHARS = 600
EN_PAGES = ['Wikipedia:Vital articles/Level/3'] + ['Wikipedia:Vital articles/Level/4/' + s for s in (
    'People', 'History', 'Geography', 'Arts', 'Philosophy and religion', 'Everyday life',
    'Society and social sciences', 'Biology and health sciences', 'Physical sciences', 'Technology', 'Mathematics')]
SEEDS_TH_CATEGORIES = ['หมวดหมู่:จังหวัดของประเทศไทย']
SEEDS_TH = ['ประเทศไทย', 'กรุงเทพมหานคร', 'ภาษาไทย', 'อักษรไทย', 'สงกรานต์', 'ลอยกระทง', 'ต้มยำ', 'ส้มตำ', 'มวยไทย',
            'พระบรมมหาราชวัง', 'วัดพระศรีรัตนศาสดาราม', 'แม่น้ำเจ้าพระยา', 'ดอยอินทนนท์', 'อาณาจักรสุโขทัย',
            'อาณาจักรอยุธยา', 'อาณาจักรธนบุรี', 'กรุงรัตนโกสินทร์', 'สุนทรภู่', 'ช้างไทย', 'ทุเรียน', 'มะม่วง',
            'ปัญญาประดิษฐ์', 'การเรียนรู้ของเครื่อง', 'ภาษาไพทอน', 'จาวาสคริปต์', 'ลินุกซ์', 'อินเทอร์เน็ต',
            'วิกิพีเดีย', 'กูเกิล', 'สมาร์ตโฟน', 'แอนดรอยด์ (ระบบปฏิบัติการ)', 'ปลากัด', 'หมูกระทะ', 'เพชรบุรี',
            'จังหวัดเพชรบุรี', 'ขนมหม้อแกง', 'ชะอำ', 'แก่งกระจาน', 'อุทยานแห่งชาติแก่งกระจาน']


def api(host, params, cache, key):
    path = os.path.join(cache, key + '.json')
    if os.path.exists(path):
        return json.load(open(path, encoding='utf-8'))
    params = dict(params, format='json', formatversion='2')
    url = f'https://{host}/w/api.php?' + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA})
            data = json.loads(urllib.request.urlopen(req, timeout=60).read().decode('utf-8'))
            break
        except Exception as e:  # network hiccup: back off and retry
            print('retry', key, e, flush=True)
            time.sleep(2 + 3 * attempt)
    else:
        raise RuntimeError('failed ' + key)
    json.dump(data, open(path, 'w', encoding='utf-8'), ensure_ascii=False)
    time.sleep(1.0)
    return data


def en_titles(cache):
    out = []
    for page in EN_PAGES:
        d = api('en.wikipedia.org', dict(action='parse', page=page, prop='links', redirects=1),
                cache, 'enparse_' + re.sub(r'\W+', '_', page))
        out += [l['title'] for l in d.get('parse', {}).get('links', []) if l['ns'] == 0]
    return list(dict.fromkeys(out))


def to_thai(titles, cache):
    th = []
    for i in range(0, len(titles), 50):
        chunk = titles[i:i + 50]
        d = api('en.wikipedia.org', dict(action='query', prop='langlinks', lllang='th', lllimit='max', titles='|'.join(chunk), redirects=1),
                cache, f'll_{i}')
        for p in d['query'].get('pages', []):
            for l in p.get('langlinks', []):
                th.append(l['title'])
    return th


def th_category(cat, cache):
    # province categories hold one sub-category per province: 'หมวดหมู่:จังหวัดX' -> article 'จังหวัดX'
    d = api('th.wikipedia.org', dict(action='query', list='categorymembers', cmtitle=cat, cmlimit='max'), cache,
            'cat2_' + re.sub(r'\W+', '_', cat))
    out = []
    for m in d['query']['categorymembers']:
        t = m['title'].split(':', 1)[-1]
        if t.startswith('จังหวัด') and 'ของประเทศไทย' not in t and 'สัญลักษณ์' not in t:
            out.append(t)
    return out


def cut(text):
    for _ in range(3):  # drop (pronunciations; dates; romanisations), inner brackets first
        text = re.sub(r' ?\([^()]{0,300}\)', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    text = re.sub(r' +([,.])', r'\1', text)
    if len(text) <= MAX_CHARS:
        return text
    j = text.rfind(' ', 0, MAX_CHARS)
    return text[:j if j > 200 else MAX_CHARS].strip()


def _pages(d, out, asked):
    q = d.get('query', {})
    alias = {}
    for k in ('normalized', 'redirects'):
        for m in q.get(k, []):
            alias[m['to']] = alias.get(m['from'], []) + [m['from']]
    for p in q.get('pages', []):
        if 'title' not in p:
            continue
        for t in [p['title']] + alias.get(p['title'], []):
            asked.add(t)
        ex = (p.get('extract') or '').strip()
        if p.get('missing') or len(ex) < 60:
            continue
        out[p['title']] = {'id': p['pageid'], 'title': p['title'], 'text': cut(ex)}


def extracts(titles, cache):
    """Reuse every cached extract answer, then fetch only titles not seen yet (20 per request)."""
    out, asked = {}, set()
    for f in sorted(os.listdir(cache)):
        if f.startswith('ex'):
            _pages(json.load(open(os.path.join(cache, f), encoding='utf-8')), out, asked)
    todo = [t for t in titles if t not in asked]
    print('extracts cached', len(out), 'to fetch', len(todo), flush=True)
    for i in range(0, len(todo), 20):
        chunk = todo[i:i + 20]
        d = api('th.wikipedia.org', dict(action='query', prop='extracts', exintro=1, explaintext=1, exlimit=20, titles='|'.join(chunk), redirects=1),
                cache, 'ex2_' + hashlib.md5('|'.join(chunk).encode('utf-8')).hexdigest())
        _pages(d, out, asked)
    keep = set(titles)
    return {t: v for t, v in out.items() if t in keep or t in asked}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--cache', default='/root/work/terminal-ai/v0.8/wiki_cache')
    a = ap.parse_args()
    os.makedirs(a.cache, exist_ok=True)
    en = en_titles(a.cache)
    print('english vital titles', len(en), flush=True)
    th = to_thai(en, a.cache)
    print('thai langlinks', len(th), flush=True)
    for c in SEEDS_TH_CATEGORIES:
        th += th_category(c, a.cache)
    th += SEEDS_TH
    th = sorted(dict.fromkeys(th))
    docs = extracts(th, a.cache)
    docs = sorted(docs.values(), key=lambda d: d['title'])
    pack = {
        'name': 'TER-AI Thai knowledge pack',
        'version': '0.8.0',
        'source': 'Thai Wikipedia (th.wikipedia.org), lead sections, plain text, shortened',
        'license': 'CC BY-SA 4.0 (https://creativecommons.org/licenses/by-sa/4.0/). Text by Wikipedia contributors; '
                   'each entry links back to its article: https://th.wikipedia.org/?curid=<id>',
        'retrieved': time.strftime('%Y-%m-%d'),
        'docs': [[d['id'], d['title'], d['text']] for d in docs],
    }
    out = os.path.join(REPO, 'src/terai_router/data/knowledge_th.json')
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(pack, fh, ensure_ascii=False, separators=(',', ':'))
    print('docs', len(docs), 'bytes', os.path.getsize(out))


if __name__ == '__main__':
    main()
