#!/usr/bin/env python3
"""Near-duplicate audit between training rows and the eval sets.

For every eval sentence, find the most similar training row (Jaccard over char 1-4 gram features
of the normalized text). Prints how many eval items have a training row at or above each
similarity level. With --strict T it writes training/train_v07_strict.json: the training rows
minus every row whose similarity to ANY eval sentence is >= T, so the model can be retrained
without near-duplicates and the accuracy compared honestly.
"""
import argparse
import json
import os
import sys

import numpy as np
from scipy import sparse

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, 'src'))
from terai_router.model import features  # noqa: E402

CFG = {'c': [1, 4], 'k': [2, 1]}  # char grams only (k range empty)


def mat(texts, vocab, grow):
    ind, ptr = [], [0]
    for t in texts:
        for f in features(t, CFG):
            if f not in vocab:
                if not grow:
                    continue
                vocab[f] = len(vocab)
            ind.append(vocab[f])
        ptr.append(len(ind))
    return ind, ptr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--strict', type=float)
    a = ap.parse_args()
    rows = json.load(open(os.path.join(HERE, 'train_v07.json'), encoding='utf-8'))['rows']
    ev = []
    for name in ('test_set.json', 'heldout_v07.json'):
        d = json.load(open(os.path.join(REPO, 'eval', name), encoding='utf-8'))
        ev += [(name, k, t) for k, v in d.items() if not k.startswith('_') for t, _ in v]
    vocab = {}
    ei, ep = mat([t for _, _, t in ev], vocab, True)
    ti, tp = mat([r[0] for r in rows], vocab, True)
    E = sparse.csr_matrix((np.ones(len(ei)), ei, ep), shape=(len(ev), len(vocab)))
    Tm = sparse.csr_matrix((np.ones(len(ti)), ti, tp), shape=(len(rows), len(vocab)))
    inter = (E @ Tm.T).toarray()
    ne = np.asarray(E.sum(1)).ravel()[:, None]
    nt = np.asarray(Tm.sum(1)).ravel()[None, :]
    jac = inter / np.maximum(ne + nt - inter, 1)
    best = jac.max(1)
    for name in ('test_set.json', 'heldout_v07.json'):
        m = np.array([e[0] == name for e in ev])
        b = best[m]
        print(name, 'n=%d' % m.sum(), ' '.join('>=%.1f:%d' % (th, (b >= th).sum()) for th in (0.5, 0.6, 0.7, 0.8, 0.9)),
              'median=%.2f' % np.median(b))
    if a.strict is not None:
        bad = jac.max(0) >= a.strict
        keep = [r for r, x in zip(rows, bad) if not x]
        json.dump({'n': len(keep), 'strict_threshold': a.strict, 'removed': int(bad.sum()), 'rows': keep},
                  open(os.path.join(HERE, 'train_v07_strict.json'), 'w', encoding='utf-8'), ensure_ascii=False)
        print('strict', a.strict, 'removed', int(bad.sum()), 'kept', len(keep))


if __name__ == '__main__':
    main()
