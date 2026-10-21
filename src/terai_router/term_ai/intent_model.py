"""Tiny intent classifier of TERM AI: character n-gram Naive Bayes (the TER-AI-0.5 model).

Ported unchanged in behaviour from the original Terminal AI (2026-10-10). Pure Python, no
dependencies, CPU only. Thai has no spaces, so it uses binary character n-grams (1-3).
The bundled data/model.json is byte-identical to the original and is rebuilt exactly by
``train(load_samples())`` (checked by tests/test_term_ai.py).

  python -m terai_router.term_ai.intent_model eval             leave-one-out accuracy (101/149)
  python -m terai_router.term_ai.intent_model predict "text"   top intents with probabilities

Part of the TERM AI limited-time trial: removed on 2027-01-01 00:00:00 Asia/Bangkok (UTC+7).
"""
import json
import math
import os
import sys
from collections import Counter, defaultdict

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
DATA_PATH = os.path.join(DATA_DIR, 'train_data.json')
MODEL_PATH = os.path.join(DATA_DIR, 'model.json')
N_RANGE = (1, 3)
ALPHA = 0.01  # smoothing (best of the original grid search: n 1-4, alpha 0.01-0.5, binary/count)


def features(text):
    t = ' ' + text.lower().strip() + ' '
    out = []
    for n in range(N_RANGE[0], N_RANGE[1] + 1):
        out += [t[i:i + n] for i in range(len(t) - n + 1)]
    return list(dict.fromkeys(out))  # binary features: each n-gram counted once


def train(samples):
    """samples: list of (text, intent). Returns the model dict (without name/tagline)."""
    class_docs = Counter()
    counts = defaultdict(Counter)
    vocab = set()
    for text, intent in samples:
        class_docs[intent] += 1
        f = features(text)
        counts[intent].update(f)
        vocab.update(f)
    total_docs = sum(class_docs.values())
    model = {'V': len(vocab), 'alpha': ALPHA, 'n_range': list(N_RANGE), 'classes': {}}
    for c in class_docs:
        model['classes'][c] = {
            'prior': math.log(class_docs[c] / total_docs),
            'total': sum(counts[c].values()),
            'counts': dict(counts[c]),
        }
    return model


def predict(model, text, top=3):
    f = features(text)
    V, a = model['V'], model['alpha']
    scores = {}
    for c, d in model['classes'].items():
        denom = math.log(d['total'] + a * V)
        s = d['prior']
        for g in f:
            s += math.log(d['counts'].get(g, 0) + a) - denom
        scores[c] = s
    m = max(scores.values())
    exp = {c: math.exp(s - m) for c, s in scores.items()}
    z = sum(exp.values())
    ranked = sorted(((c, v / z) for c, v in exp.items()), key=lambda x: -x[1])
    return ranked[:top]


def load_samples():
    with open(DATA_PATH, encoding='utf-8') as f:
        data = json.load(f)
    return [(t, intent) for intent, texts in data.items() for t in texts]


def load_model():
    with open(MODEL_PATH, encoding='utf-8') as f:
        return json.load(f)


def leave_one_out(samples=None):
    """Returns (correct, total, misses)."""
    samples = load_samples() if samples is None else samples
    ok, wrong = 0, []
    for i, (t, y) in enumerate(samples):
        p = predict(train(samples[:i] + samples[i + 1:]), t, 1)[0][0]
        if p == y:
            ok += 1
        else:
            wrong.append((t, y, p))
    return ok, len(samples), wrong


def main(argv=None, now=None):
    from .trial import EXIT_TRIAL_ENDED, ended_message, trial_active
    if not trial_active(now):
        print(ended_message(), file=sys.stderr)
        return EXIT_TRIAL_ENDED
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else ''
    if cmd == 'eval':
        ok, n, wrong = leave_one_out()
        print(f'leave-one-out accuracy: {ok}/{n} = {ok / n:.1%}')
        for t, y, p in wrong:
            print(f'  miss {t!r}: true={y} pred={p}')
        return 0
    if cmd == 'predict':
        for c, p in predict(load_model(), ' '.join(argv[1:])):
            print(f'{c}\t{p:.3f}')
        return 0
    print(__doc__)
    return 0


if __name__ == '__main__':
    sys.exit(main())
