#!/usr/bin/env python3
"""Evaluate the packaged model on the frozen eval sets -> eval/results_v07.json

usage: python training/evaluate.py [--model path/to/model.json]
"""
import argparse
import hashlib
import json
import os
import platform
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, 'src'))
from terai_router.model import IntentModel  # noqa: E402


def run(model, sets):
    out, rows = {}, []
    for sub, items in sets.items():
        ok = 0
        for text, gold in items:
            p = model.predict(text)
            ok += p['intent'] == gold
            rows.append({'subset': sub, 'text': text, 'gold': gold, 'pred': p['intent'], 'conf': round(p['confidence'], 4)})
        out[sub] = [ok, len(items)]
    tot = [sum(v[0] for v in out.values()), sum(v[1] for v in out.values())]
    out['total'] = tot
    return out, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model')
    a = ap.parse_args()
    m = IntentModel.load(a.model)
    res = {'model_version': m.meta['version'], 'python': platform.python_version()}
    for name in ('test_set.json', 'heldout_v07.json'):
        p = os.path.join(REPO, 'eval', name)
        raw = open(p, 'rb').read()
        sets = {k: v for k, v in json.loads(raw).items() if not k.startswith('_')}
        t = time.perf_counter()
        summ, rows = run(m, sets)
        dt = time.perf_counter() - t
        res[name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'subsets': summ,
                     'acc': round(summ['total'][0] / summ['total'][1], 4),
                     'latency_ms_mean_1thread': round(1000 * dt / summ['total'][1], 3),
                     'errors': [r for r in rows if r['pred'] != r['gold']]}
        print(name, summ, f"{100 * res[name]['acc']:.1f}%", f"{res[name]['latency_ms_mean_1thread']} ms/query")
    with open(os.path.join(REPO, 'eval/results_v07.json'), 'w', encoding='utf-8') as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)


if __name__ == '__main__':
    main()
