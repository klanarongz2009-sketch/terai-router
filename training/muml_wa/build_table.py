"""Build the MuML 1.0 WA Markov table from the MuML 1.0 training data (Nottingham, tokenized).

Input : tunes.json written by training/muml/prepare.py (MuML token language, 24 ticks per quarter).
Output: src/terai_router/muml_wa/data/markov.json, shared byte-for-byte by the Python reference
        (terai_router.muml_wa) and the browser (docs/muml_wa.js).

What is counted (all relative to the tune's tonic, so the table is key-free):
  start[mode]          first melody pitch of each tune
  o1[mode][a]          next pitch after pitch a
  o2[mode][a,b]        next pitch after the pair (a, b)         (pairs seen >= MIN_O2 times)
  chords[mode][c]      next bar's chord after chord c           ('root:quality', root relative to tonic)
  rhythms[meter]       whole-bar rhythm patterns (durations in ticks), top TOP_RHYTHMS per meter

Every option list is an array of [value, count] sorted by value, so Python and JavaScript walk it
in the same order (JS objects reorder integer-like keys, arrays do not).

usage: python training/muml_wa/build_table.py [--data PATH] [--out PATH]
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA = Path('/home/sprite/muml-work/data/tunes.json')
DEFAULT_OUT = ROOT / 'src' / 'terai_router' / 'muml_wa' / 'data' / 'markov.json'
METER_MAP = {'4/4': '4/4', '2/2': '4/4', '6/8': '6/8', '3/4': '3/4'}
BAR = {'4/4': 96, '6/8': 72, '3/4': 72}
REL_MIN, REL_MAX = -12, 24
MIN_O2 = 2
TOP_RHYTHMS = 40
MAX_NOTES_PER_BAR = 12


def tonic_ref(tonic: int) -> int:
    return 60 + (tonic if tonic <= 6 else tonic - 12)


def opts(counter: Counter, key=lambda v: v):
    return [[v, c] for v, c in sorted(counter.items(), key=lambda kv: key(kv[0]))]


def build(tunes):
    start = defaultdict(Counter)
    o1 = defaultdict(lambda: defaultdict(Counter))
    o2 = defaultdict(lambda: defaultdict(Counter))
    chords = defaultdict(lambda: defaultdict(Counter))
    rhythms = defaultdict(Counter)
    used = Counter()
    for t in tunes:
        mode, ref = t['mode'], tonic_ref(t['tonic'])
        rels, bar_chords, bar, cur = [], [], [], None
        meter = METER_MAP.get(t['meter'])
        toks = t['body']
        i = 0
        while i < len(toks):
            x = toks[i]
            if x.startswith('CH:'):
                _, r, q = x.split(':')
                c = f"{(int(r) - t['tonic']) % 12}:{q}"
                if cur is None:
                    cur = c
                    bar_chords.append(c)
            elif x.startswith('P:') or x == 'R':
                d = int(toks[i + 1][2:])
                if x == 'R':
                    bar.append(-d)
                else:
                    rel = int(x[2:]) - ref
                    if REL_MIN <= rel <= REL_MAX:
                        rels.append(rel)
                    bar.append(d)
                i += 1
            else:  # bar line or ending
                if meter and bar and all(v > 0 for v in bar) and sum(bar) == BAR[meter] and len(bar) <= MAX_NOTES_PER_BAR:
                    rhythms[meter][tuple(bar)] += 1
                bar, cur = [], None
            i += 1
        if not rels:
            continue
        used[mode] += 1
        start[mode][rels[0]] += 1
        for a, b in zip(rels, rels[1:]):
            o1[mode][a][b] += 1
        for a, b, c in zip(rels, rels[1:], rels[2:]):
            o2[mode][(a, b)][c] += 1
        for a, b in zip(bar_chords, bar_chords[1:]):
            chords[mode][a][b] += 1
    ck = lambda c: (int(c.split(':')[0]), c.split(':')[1])
    out = {
        'format': 'muml-wa-markov-1',
        'source': 'Nottingham Music Database (jukedeck/nottingham-dataset, GPL-3.0), via MuML 1.0 tunes.json',
        'tunes': dict(sorted(used.items())),
        'rel_range': [REL_MIN, REL_MAX],
        'start': {m: opts(start[m]) for m in sorted(start)},
        'o1': {m: [[a, opts(o1[m][a])] for a in sorted(o1[m])] for m in sorted(o1)},
        'o2': {m: [[list(k), opts(v)] for k, v in sorted(o2[m].items()) if sum(v.values()) >= MIN_O2] for m in sorted(o2)},
        'chords': {m: [[a, opts(chords[m][a], ck)] for a in sorted(chords[m], key=ck)] for m in sorted(chords)},
        'rhythms': {m: [[list(p), c] for p, c in sorted(rhythms[m].items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_RHYTHMS]]
                    for m in sorted(rhythms)},
    }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', type=Path, default=DEFAULT_DATA)
    ap.add_argument('--out', type=Path, default=DEFAULT_OUT)
    a = ap.parse_args()
    table = build(json.loads(a.data.read_text(encoding='utf-8')))
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(table, separators=(',', ':')), encoding='utf-8')
    print('wrote', a.out, a.out.stat().st_size, 'bytes', 'tunes', table['tunes'],
          'o2 keys', {m: len(v) for m, v in table['o2'].items()}, 'rhythms', {m: len(v) for m, v in table['rhythms'].items()})


if __name__ == '__main__':
    main()
