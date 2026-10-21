"""Before/after for MuML 1.0 WA note writers: Markov v1 (v0.12.0) vs the MuML 1.0 network (v0.15.0).

    python eval/muml_wa_writers.py            # writes eval/muml_wa_writers.json and prints a table

Fixed prompts x seeds, same for both writers. Metrics on the melody (pitch sequence):
  distinct-3 / distinct-4  unique pitch n-grams / all n-grams inside one song (higher = more variety)
  bar_repeat               share of bars whose (pitch, duration) content already appeared earlier in the song
  in_scale                 share of notes in the scale of the key the prompt asked for
  tonic_end                share of songs whose last note is the tonic
  len_ratio                written length / requested length
  sec_per_song             Python generation time (numpy, this machine)
"""
from __future__ import annotations

import json
import statistics as st
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from terai_router import muml_wa  # noqa: E402
from terai_router.muml_wa import METERS, net  # noqa: E402

PROMPTS = ['folk jig D major', 'sad waltz in A minor 1 minute', 'calm reel key of G 45 seconds',
           'happy irish 6/8 key Bb 90 bpm', 'เพลงร็อกมันส์ๆ 140 bpm คีย์ E minor 20 วินาที', 'คีย์ D ไมเนอร์ ร็อค 6/8',
           'เพลงเศร้า 3/4 คีย์ F', 'rock C major 120 bpm 30 วินาที', 'เพลงสนุก คีย์ A 4/4 40 วินาที', '']
SEEDS = (0, 1, 2)
SCALE = net.SCALE


def melody(song):
    return sorted(next(t['notes'] for t in song['tracks'] if t['name'].startswith('lead')))


def metrics(song):
    p = song['prompt']
    mel = melody(song)
    pitches = [n[2] for n in mel]
    out = {}
    for k in (3, 4):
        grams = [tuple(pitches[i:i + k]) for i in range(len(pitches) - k + 1)]
        out[f'distinct{k}'] = len(set(grams)) / len(grams) if grams else 0.0
    bar = METERS[p['meter']]['bar']
    bars = {}
    for t, d, n, *_ in mel:
        bars.setdefault(t // bar, []).append((t % bar, d, n))
    seen, rep = set(), 0
    for b in sorted(bars):
        key = tuple(bars[b])
        rep += key in seen
        seen.add(key)
    out['bar_repeat'] = rep / len(bars) if bars else 0.0
    sc = SCALE[p['mode']]
    out['in_scale'] = sum((n - p['tonic']) % 12 in sc for n in pitches) / len(pitches) if pitches else 0.0
    out['tonic_end'] = float(bool(pitches) and (pitches[-1] - p['tonic']) % 12 == 0)
    bpb = METERS[p['meter']]['bar'] // METERS[p['meter']]['beat']
    want = -(-(p['seconds'] * p['bpm']) // (60 * bpb)) * bar
    out['len_ratio'] = song['total_ticks'] / want
    out['notes'] = len(pitches)
    return out


def run(writer, **kw):
    rows = []
    for pr in PROMPTS:
        for s in SEEDS:
            t = time.time()
            g = muml_wa.generate(pr, s, 'auto', writer=writer, **kw)
            m = metrics(g)
            m['sec'] = time.time() - t
            rows.append(m)
    keys = ['distinct3', 'distinct4', 'bar_repeat', 'in_scale', 'tonic_end', 'len_ratio', 'notes', 'sec']
    return {k: round(st.mean(r[k] for r in rows), 4) for k in keys} | {'songs': len(rows)}


def main():
    path = str(ROOT / 'docs' / net.WEIGHTS_NAME)
    res = {'prompts': PROMPTS, 'seeds': list(SEEDS), 'markov-v1': run('markov'), 'muml-1.0-net': run('net', weights=path)}
    g0 = net.KEY_GUARD
    net.KEY_GUARD = 0.0
    res['muml-1.0-net (key guard off)'] = run('net', weights=path)
    net.KEY_GUARD = g0
    res['weights'] = {'file': net.WEIGHTS_NAME, 'bytes': net.WEIGHTS_BYTES, 'sha256': net.WEIGHTS_SHA256}
    (ROOT / 'eval' / 'muml_wa_writers.json').write_text(json.dumps(res, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    for k in ('markov-v1', 'muml-1.0-net', 'muml-1.0-net (key guard off)'):
        print(k.ljust(30), res[k])


if __name__ == '__main__':
    main()
