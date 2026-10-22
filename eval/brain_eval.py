"""TERAI1BETA vs the rule chat on the fixed Thai question set (eval/terai1beta_cases_v15.json).

    python eval/brain_eval.py --engine rules            # fast, no model
    python eval/brain_eval.py --engine terai1beta       # needs llama-cpp-python + Gemma 4 E2B (terai chat --setup)
    python eval/brain_eval.py --engine both --out eval/terai1beta_results_v15.json

Metrics: accuracy on cases with an expected answer; hallucination rate = share of cases where the reply states
something with no source (must_refuse cases answered without saying it does not know, no_numbers cases with a
number, or any reply number that is in no tool result, user message or memory); scripted-ness on the chitchat
cases = distinct replies / cases and the mean trigram overlap of replies within a paraphrase group (the rule chat
answers paraphrases with the same template); latency per scored turn; peak RSS.
"""
from __future__ import annotations

import argparse
import json
import os
import resource
import statistics
import sys
import time
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from terai_router.chat import Chat  # noqa: E402
from terai_router.brain.agent import REFUSAL, numbers, _trigrams  # noqa: E402

CASES = ROOT / 'eval' / 'terai1beta_cases_v15.json'


def norm(s: str) -> str:
    return (s or '').replace(',', '').translate(str.maketrans('๐๑๒๓๔๕๖๗๘๙', '0123456789'))


def jacc(a: str, b: str) -> float:
    x, y = _trigrams(a), _trigrams(b)
    return len(x & y) / len(x | y) if x | y else 1.0


def run(engine: str, data: dict, model: str | None = None, verbose: bool = False) -> dict:
    lm = None
    if engine == 'terai1beta':
        from terai_router.brain import Brain, LocalLM
        lm = LocalLM(model=model, auto_download=False)
    rows = []
    for c in data['cases']:
        chat = Chat(now=data['now'], seed=1)
        bot = Brain(chat=chat, lm=lm) if lm else None
        sources = ''
        for i, t in enumerate(c['turns']):
            t0 = time.time()
            r = bot.reply(t) if bot else chat.reply(t)
            dt = time.time() - t0
            sources += ' ' + t + ' ' + ((bot.last.get('evidence') or '') if bot else r)
        sources += ' ' + (chat._all_facts() if hasattr(chat, '_all_facts') else '')
        rn = norm(r)
        ok = None
        if c.get('expect_all') or c.get('expect_any'):
            ok = all(norm(e) in rn for e in c.get('expect_all', [])) and \
                (not c.get('expect_any') or any(norm(e) in rn for e in c['expect_any']))
        halluc = []
        if c.get('must_refuse') and not REFUSAL.search(r):
            halluc.append('answered with no source')
        if c.get('no_numbers') and numbers(r) and not REFUSAL.search(r):
            halluc.append('number with no source')
        extra = numbers(r) - numbers(sources)
        if extra:
            halluc.append('numbers in no source: ' + ','.join(sorted(extra)))
        row = {'id': c['id'], 'cat': c['cat'], 'group': c.get('group'), 'q': c['turns'][-1], 'reply': r,
               'ok': ok, 'hallucination': halluc, 'seconds': round(dt, 2)}
        if bot:
            row.update({k: bot.last.get(k) for k in ('kind', 'tool', 'step', 'planned', 'fallback', 'problems')})
        rows.append(row)
        if verbose:
            print(f"{c['id']:8} ok={ok} h={bool(halluc)} {dt:5.1f}s | {r[:120]}", file=sys.stderr)
    scored = [x for x in rows if x['ok'] is not None]
    chit = [x for x in rows if x['cat'] == 'chitchat']
    groups = {}
    for x in chit:
        groups.setdefault(x['group'], []).append(x['reply'])
    sims = [jacc(a, b) for g in groups.values() for a, b in combinations(g, 2)]
    lat = sorted(x['seconds'] for x in rows)
    by_cat = {}
    for x in scored:
        d = by_cat.setdefault(x['cat'], [0, 0])
        d[0] += bool(x['ok'])
        d[1] += 1
    summary = {
        'engine': engine, 'model': (lm.label if lm else 'rules (chat.py)'), 'cases': len(rows),
        'accuracy': f"{sum(bool(x['ok']) for x in scored)}/{len(scored)}",
        'accuracy_by_cat': {k: f'{a}/{b}' for k, (a, b) in by_cat.items()},
        'hallucination': f"{sum(bool(x['hallucination']) for x in rows)}/{len(rows)}",
        'refused_when_no_source': f"{sum(1 for x in rows if x['cat'] == 'unanswerable' and REFUSAL.search(x['reply']))}"
                                  f"/{sum(1 for x in rows if x['cat'] == 'unanswerable')}",
        'chitchat_distinct': f"{len(set(x['reply'] for x in chit))}/{len(chit)}",
        'chitchat_group_overlap': round(statistics.mean(sims), 3) if sims else None,
        'median_reply_chars': int(statistics.median(len(x['reply']) for x in rows)),
        'latency_p50_s': round(statistics.median(lat), 2),
        'latency_p95_s': round(lat[min(len(lat) - 1, int(0.95 * len(lat)))], 2),
        'peak_rss_mb': resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024,
    }
    if lm:
        summary['fallback_to_rules'] = f"{sum(1 for x in rows if x.get('fallback'))}/{len(rows)}"
        summary['model_load_s'] = lm.load_seconds
        summary['threads'] = lm.threads
    return {'summary': summary, 'rows': rows}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--engine', choices=['rules', 'terai1beta', 'both'], default='rules')
    ap.add_argument('--model', default=None, help='Gemma 4 size for terai1beta (default e2b)')
    ap.add_argument('--out', default=None)
    ap.add_argument('-v', '--verbose', action='store_true')
    a = ap.parse_args(argv)
    data = json.loads(CASES.read_text(encoding='utf-8'))
    engines = ['rules', 'terai1beta'] if a.engine == 'both' else [a.engine]
    res = {e: run(e, data, a.model, a.verbose) for e in engines}
    for e in engines:
        print(json.dumps(res[e]['summary'], ensure_ascii=False))
    if a.out:
        Path(a.out).write_text(json.dumps(res, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
