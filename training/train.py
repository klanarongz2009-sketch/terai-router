#!/usr/bin/env python3
"""Train the v0.7 intent model -> src/terai_router/data/model.json

multinomial logistic regression (softmax) over binary char n-gram features, L2, L-BFGS (scipy).
Weights are quantized to int8 with one global scale; inference uses the quantized weights only.
Model selection uses a 10% validation split of the training rows, never the eval sets.

usage: python training/train.py [--l2 1e-4] [--min-count 2]
"""
import argparse
import base64
import json
import os
import random
import sys
import time

import numpy as np
from scipy import sparse
from scipy.optimize import minimize

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, 'src'))
from terai_router.model import features  # noqa: E402

CFG = {'c': [1, 4], 'k': [2, 4]}


def build(rows, vocab):
    ind, ptr = [], [0]
    for s in rows:
        ind += [vocab[f] for f in features(s, CFG) if f in vocab]
        ptr.append(len(ind))
    return sparse.csr_matrix((np.ones(len(ind)), ind, ptr), shape=(len(rows), len(vocab)))


def fit(X, y, k, l2):
    n, d = X.shape
    Y = np.zeros((n, k))
    Y[np.arange(n), y] = 1

    def f(theta):
        W = theta[:d * k].reshape(d, k)
        b = theta[d * k:]
        Z = X @ W + b
        Z -= Z.max(1, keepdims=True)
        P = np.exp(Z)
        P /= P.sum(1, keepdims=True)
        loss = -np.log(P[Y > 0] + 1e-12).mean() + 0.5 * l2 * (W * W).sum()
        G = (P - Y) / n
        gW = X.T @ G + l2 * W
        return loss, np.concatenate([gW.ravel(), G.sum(0)])

    r = minimize(f, np.zeros(d * k + k), jac=True, method='L-BFGS-B', options={'maxiter': 400})
    return r.x[:d * k].reshape(d, k), r.x[d * k:]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--l2', type=float, default=None, help='skip the search and use this value')
    ap.add_argument('--min-count', type=int, default=2)
    ap.add_argument('--data', default='train_v07.json', help='rows file inside training/')
    a = ap.parse_args()
    data = json.load(open(os.path.join(HERE, a.data), encoding='utf-8'))['rows']
    classes = sorted({y for _, y, _ in data})
    cid = {c: i for i, c in enumerate(classes)}
    cnt = {}
    for s, _, _ in data:
        for f in features(s, CFG):
            cnt[f] = cnt.get(f, 0) + 1
    vocab_list = [f for f, c in cnt.items() if c >= a.min_count]
    vocab = {f: i for i, f in enumerate(vocab_list)}
    X = build([s for s, _, _ in data], vocab)
    y = np.array([cid[c] for _, c, _ in data])
    print('rows', X.shape[0], 'features', X.shape[1], flush=True)

    l2 = a.l2
    if l2 is None:
        idx = list(range(len(data)))
        random.Random(1).shuffle(idx)
        cut = len(idx) // 10
        va, tr = np.array(idx[:cut]), np.array(idx[cut:])
        best = None
        for cand in (3e-5, 1e-4, 3e-4):
            W, b = fit(X[tr], y[tr], len(classes), cand)
            acc = ((X[va] @ W + b).argmax(1) == y[va]).mean()
            print(f'l2={cand:g} val_acc={acc:.4f}', flush=True)
            if best is None or acc > best[0]:
                best = (acc, cand)
        l2 = best[1]
    t = time.time()
    W, b = fit(X, y, len(classes), l2)
    print(f'final fit l2={l2:g} {time.time() - t:.1f}s', flush=True)

    # drop features whose weights all quantize to 0, then int8
    scale = float(np.abs(W).max()) / 127.0
    Q = np.clip(np.rint(W / scale), -127, 127).astype(np.int8)
    keep = np.where(np.abs(Q).max(1) > 0)[0]
    Q = Q[keep]
    model = {
        'meta': {'name': 'TER-AI intent router', 'version': '0.7.0', 'trained_rows': int(X.shape[0]),
                 'l2': l2, 'min_count': a.min_count, 'features_before_prune': int(X.shape[1]),
                 'features': int(len(keep))},
        'classes': classes, 'features': CFG, 'scale': scale,
        'bias': [round(float(v), 6) for v in b],
        'vocab': [vocab_list[i] for i in keep],
        'weights_b64': base64.b64encode(Q.tobytes()).decode('ascii'),
    }
    out = os.path.join(REPO, 'src/terai_router/data/model.json')
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(model, fh, ensure_ascii=False, separators=(',', ':'))
    print('saved', out, os.path.getsize(out), 'bytes,', len(keep), 'features')


if __name__ == '__main__':
    main()
