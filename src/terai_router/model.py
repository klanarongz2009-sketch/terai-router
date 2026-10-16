"""TER-AI intent model: char n-gram features + linear softmax classifier with int8 weights.

Pure Python at inference time (no numpy). The same features and the same integer arithmetic
are implemented in JavaScript in docs/index.html, so browser and Python give identical results.

Features of a text t (after normalize() and fold()):
  c:<g>  every char n-gram g of ' ' + t + ' ' for n in [1, 4] (whitespace-only grams skipped)
  k:<g>  every char n-gram g of ' ' + skeleton(t) + ' ' for n in [2, 4]
Each distinct feature counts once (binary).

Score of class j = bias[j] + scale * sum(w8[f][j] for known features f); probabilities = softmax.
"""
import base64
import json
import math
from importlib import resources

from .normalizer import fold, normalize, skeleton


def features(text, cfg=None):
    cfg = cfg or {'c': [1, 4], 'k': [2, 4]}
    t = fold(normalize(text))
    out, seen = [], set()
    for prefix, src in (('c', t), ('k', skeleton(t))):
        lo, hi = cfg[prefix]
        s = ' ' + src + ' '
        for n in range(lo, hi + 1):
            for i in range(len(s) - n + 1):
                g = s[i:i + n]
                if not g.strip():
                    continue
                f = prefix + ':' + g
                if f not in seen:
                    seen.add(f)
                    out.append(f)
    return out


class IntentModel:
    """Load once, call predict() many times."""

    def __init__(self, data):
        self.meta = data['meta']
        self.classes = data['classes']
        self.scale = data['scale']
        self.bias = data['bias']
        self.cfg = data['features']
        k = len(self.classes)
        raw = base64.b64decode(data['weights_b64'])
        w = [b - 256 if b > 127 else b for b in raw]
        self.weights = {f: w[i * k:(i + 1) * k] for i, f in enumerate(data['vocab'])}

    @classmethod
    def load(cls, path=None):
        if path is None:
            txt = resources.files('terai_router').joinpath('data/model.json').read_text(encoding='utf-8')
        else:
            with open(path, encoding='utf-8') as fh:
                txt = fh.read()
        return cls(json.loads(txt))

    def scores(self, text):
        feats = features(text, self.cfg)
        k = len(self.classes)
        acc = [0] * k
        known = 0
        for f in feats:
            w = self.weights.get(f)
            if w is not None:
                known += 1
                for j in range(k):
                    acc[j] += w[j]
        logits = [self.bias[j] + self.scale * acc[j] for j in range(k)]
        return logits, known / max(1, len(feats))

    def predict(self, text, top=3):
        """-> dict(intent, confidence, coverage, normalized, ranking=[(intent, prob), ...])."""
        logits, cov = self.scores(text)
        m = max(logits)
        ex = [math.exp(x - m) for x in logits]
        z = sum(ex)
        ranked = sorted(zip(self.classes, (e / z for e in ex)), key=lambda p: -p[1])
        return {'intent': ranked[0][0], 'confidence': ranked[0][1], 'coverage': cov,
                'normalized': normalize(text), 'ranking': ranked[:top]}
