"""MuML 1.0 network note writer for MuML 1.0 WA (Python reference for docs/muml_wa_net.js).

The trained MuML 1.0 network (decoder-only transformer: 4 layers, d_model 256, 4 heads, context 512, 163 MuML
tokens, 3,332,352 parameters, trained from scratch on the Nottingham Music Database for 30 epochs, best val loss
1.3780) writes the melody, chords and rhythm. Weights: muml-1.0-int8.bin (int8 per-row, written by
training/muml_wa/export_net.py). They are not in the Python package; ``terai muml-wa --setup`` downloads them and
checks the SHA-256. The web demo fetches the same file from GitHub Pages on first use.

The forward pass runs in float64 with a key/value cache, the same operations in the same order as the JavaScript
version. Sampling turns probabilities into integer weights (parts per million) and draws with the mulberry32 Rng of
muml_wa, so Python and the browser write the same tokens for the same prompt and seed.
Needs numpy. Without numpy or without the weight file, muml_wa falls back to the Markov v1 writer.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import struct
from pathlib import Path

NOTE_WRITER = 'muml-1.0-net'
MODEL_ID = 'MuML 1.0'
WEIGHTS_NAME = 'muml-1.0-int8.bin'
WEIGHTS_BYTES = 3421372
WEIGHTS_SHA256 = 'f8a6d1030476d80757f44c3a990a3975d230b2f186820f48481429365c144fef'
WEIGHTS_URLS = (
    'https://klanarongz2009-sketch.github.io/terai-router/' + WEIGHTS_NAME,
    'https://github.com/klanarongz2009-sketch/terai-router/releases/download/v0.15.0/' + WEIGHTS_NAME,
)
MAGIC = b'MUMLWA1\0'
# decoding settings (same in docs/muml_wa_net.js)
TEMPERATURE = 0.9
TOP_P_PCT = 95          # keep the smallest set of tokens holding 95 % of the weight
KEY_GUARD = 2.0         # logit penalty for a pitch outside the key's scale
PPM = 1000000
MAX_SEGMENTS = 12
SCALE = {'major': (0, 2, 4, 5, 7, 9, 11), 'minor': (0, 2, 3, 5, 7, 8, 10)}
TYPE_OF = {'4/4': 'reel', '6/8': 'jig', '3/4': 'waltz'}


def default_path() -> str:
    return os.environ.get('TERAI_MUML_WA_WEIGHTS') or os.path.join(
        os.path.expanduser('~'), '.cache', 'terai', 'muml', WEIGHTS_NAME)


def find_weights():
    """Path of a weight file with the right SHA-256, or None. Also looks in docs/ of a repository checkout."""
    for p in (default_path(), str(Path(__file__).resolve().parents[3] / 'docs' / WEIGHTS_NAME)):
        if os.path.isfile(p) and os.path.getsize(p) == WEIGHTS_BYTES:
            return p
    return None


def setup(path: str | None = None, quiet: bool = False) -> str:
    """Download the weights (3.4 MB) to the cache and check the SHA-256."""
    import urllib.request
    path = path or default_path()
    if os.path.isfile(path) and _sha(open(path, 'rb').read()) == WEIGHTS_SHA256:
        return path
    err = None
    for url in WEIGHTS_URLS:
        try:
            data = urllib.request.urlopen(url, timeout=60).read()
        except Exception as e:  # try the next mirror
            err = e
            continue
        if _sha(data) != WEIGHTS_SHA256:
            err = ValueError(f'SHA-256 mismatch from {url}')
            continue
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data)
        if not quiet:
            print(f'MuML 1.0 weights saved: {path} ({len(data):,} bytes)')
        return path
    raise RuntimeError(f'could not download {WEIGHTS_NAME}: {err}')


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def numpy_available() -> bool:
    try:
        import numpy  # noqa: F401
        return True
    except Exception:
        return False


_CACHE = {}


def load(path: str):
    if path in _CACHE:
        return _CACHE[path]
    import numpy as np
    b = open(path, 'rb').read()
    if b[:8] != MAGIC:
        raise ValueError('not a MuML WA weight file')
    hl = struct.unpack('<I', b[8:12])[0]
    h = json.loads(b[12:12 + hl].decode('utf-8'))
    base = 12 + hl
    w = {}
    for t in h['tensors']:
        shape = t['shape']
        if 'q' in t:
            q = np.frombuffer(b, np.int8, count=t['q']['bytes'], offset=base + t['q']['offset']).reshape(shape)
            s = np.frombuffer(b, '<f4', count=shape[0], offset=base + t['scale']['offset'])
            w[t['name']] = q.astype(np.float64) * s.astype(np.float64)[:, None]
        else:
            n = 1
            for d in shape:
                n *= d
            w[t['name']] = np.frombuffer(b, '<f4', count=n, offset=base + t['data']['offset']).astype(np.float64)
    net = {'h': h, 'w': w, 'cfg': h['config'], 'vocab': h['vocab']}
    _CACHE[path] = net
    return net


def _erf(x):
    # Abramowitz and Stegun 7.1.26 (|error| < 1.5e-7); same formula in JavaScript
    s = 1.0 if x >= 0 else -1.0
    x = abs(x)
    t = 1.0 / (1.0 + 0.3275911 * x)
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * math.exp(-x * x)
    return s * y


def _erf_np(np, x):
    s = np.sign(x)
    x = np.abs(x)
    t = 1.0 / (1.0 + 0.3275911 * x)
    y = 1.0 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * np.exp(-x * x)
    return s * y


class Runner:
    """One token at a time with a key/value cache."""

    def __init__(self, net):
        import numpy as np
        self.np = np
        self.net, self.w, self.cfg = net, net['w'], net['cfg']
        self.reset()

    def reset(self):
        self.k = [[] for _ in range(self.cfg['n_layer'])]
        self.v = [[] for _ in range(self.cfg['n_layer'])]
        self.pos = 0

    def _ln(self, x, name):
        np = self.np
        n = x.shape[0]
        mean = float(np.sum(x)) / n
        d = x - mean
        var = float(np.sum(d * d)) / n
        return d / math.sqrt(var + 1e-5) * self.w[name + '.weight'] + self.w[name + '.bias']

    def step(self, tid):
        np, w, cfg = self.np, self.w, self.cfg
        d, nh = cfg['d_model'], cfg['n_head']
        hd = d // nh
        x = w['tok.weight'][tid] + w['pos.weight'][self.pos]
        for li in range(cfg['n_layer']):
            p = f'blocks.{li}.'
            h = self._ln(x, p + 'ln1')
            qkv = w[p + 'qkv.weight'] @ h + w[p + 'qkv.bias']
            q, k, v = qkv[:d], qkv[d:2 * d], qkv[2 * d:]
            self.k[li].append(k)
            self.v[li].append(v)
            K = np.array(self.k[li])
            V = np.array(self.v[li])
            y = np.empty(d)
            for hh in range(nh):
                sl = slice(hh * hd, (hh + 1) * hd)
                sc = K[:, sl] @ q[sl] / math.sqrt(hd)
                e = np.exp(sc - np.max(sc))
                e = e / np.sum(e)
                y[sl] = e @ V[:, sl]
            x = x + (w[p + 'proj.weight'] @ y + w[p + 'proj.bias'])
            h = self._ln(x, p + 'ln2')
            a = w[p + 'mlp.0.weight'] @ h + w[p + 'mlp.0.bias']
            g = 0.5 * a * (1.0 + _erf_np(np, a / math.sqrt(2.0)))
            x = x + (w[p + 'mlp.2.weight'] @ g + w[p + 'mlp.2.bias'])
        self.pos += 1
        x = self._ln(x, 'ln')
        return (w['tok.weight'] @ x).tolist()


class Sampler:
    def __init__(self, vocab, tonic, mode):
        self.vocab = vocab
        self.dur = [i for i, t in enumerate(vocab) if t.startswith('D:')]
        cond = ('M', 'T', 'MODE', 'KEY')
        self.body = [i for i, t in enumerate(vocab)
                     if not t.startswith('D:') and t not in ('PAD', 'BOS') and t.split(':')[0] not in cond]
        self.note = set(i for i, t in enumerate(vocab) if t.startswith('P:') or t == 'R')
        sc = SCALE[mode]
        self.off_key = set(i for i, t in enumerate(vocab)
                           if t.startswith('P:') and (int(t[2:]) - tonic) % 12 not in sc)

    def weights(self, logits, prev):
        """Integer weights [[token id, weight], ...] (sorted by weight, then id) after mask, guard and top-p."""
        allowed = self.dur if prev in self.note else self.body
        z = []
        for i in allowed:
            v = logits[i]
            if i in self.off_key:
                v -= KEY_GUARD
            z.append(v / TEMPERATURE)
        m = max(z)
        e = [math.exp(v - m) for v in z]
        s = 0.0
        for v in e:
            s += v
        opts = []
        for i, v in zip(allowed, e):
            wt = math.floor(v / s * PPM + 0.5)
            if wt > 0:
                opts.append([i, wt])
        opts.sort(key=lambda o: (-o[1], o[0]))
        total = sum(o[1] for o in opts)
        keep, cum = [], 0
        for o in opts:
            if 100 * cum >= TOP_P_PCT * total:
                break
            keep.append(o)
            cum += o[1]
        return keep


def write(p: dict, rng, path: str):
    """Write the song body with the network. Returns (tokens, melody, harmony, total_ticks, segments)."""
    from . import METERS
    net = load(path)
    vocab = net['vocab']
    stoi = {t: i for i, t in enumerate(vocab)}
    ctx = net['cfg']['ctx']
    met = METERS[p['meter']]
    bpb = met['bar'] // met['beat']
    target = -(-(p['seconds'] * p['bpm']) // (60 * bpb)) * met['bar']
    tonic, mode = p['tonic'], p['mode']
    header = ['BOS', f"M:{p['meter']}", f"T:{TYPE_OF[p['meter']]}", f'MODE:{mode}', f'KEY:{tonic}']
    sampler = Sampler(vocab, tonic, mode)
    runner = Runner(net)
    bars = ('|', '|:', ':|', '[1', '[2')
    toks, melody, harmony = list(header), [], []
    tick = 0
    chord = [0, tonic, 'maj' if mode == 'major' else 'min']  # start tick, root, quality
    segments = 0
    done = False
    while not done and segments < MAX_SEGMENTS:
        segments += 1
        runner.reset()
        logits = None
        for t in header:
            logits = runner.step(stoi[t])
        body, prev = [], stoi[header[-1]]
        while runner.pos < ctx:
            nxt = rng.pick(sampler.weights(logits, prev))
            if vocab[nxt] == 'EOS':
                break
            body.append(vocab[nxt])
            prev = nxt
            logits = runner.step(nxt)
        if runner.pos >= ctx:  # cut a segment that filled the context at its last bar line
            last = max([i for i, t in enumerate(body) if t in bars], default=-1)
            body = body[:last + 1]
        added = 0
        i = 0
        while i < len(body):
            t = body[i]
            if t in bars:
                toks.append(t)
                if tick >= target:
                    done = True
                    break
            elif t.startswith('CH:'):
                _, r, q = t.split(':')
                if tick > chord[0]:
                    harmony.append([chord[0], tick - chord[0], chord[1], chord[2]])
                chord = [tick, int(r), q]
                toks.append(t)
            elif (t.startswith('P:') or t == 'R') and i + 1 < len(body) and body[i + 1].startswith('D:'):
                d = int(body[i + 1][2:])
                if t != 'R':
                    melody.append([tick, d, int(t[2:])])
                    added += 1
                toks += [t, body[i + 1]]
                tick += d
                i += 1
            i += 1
        if not added:
            break
        if not done and tick >= target:
            done = True
        if not done and toks[-1] not in bars:
            toks.append('|')
    if tick > chord[0]:
        harmony.append([chord[0], tick - chord[0], chord[1], chord[2]])
    toks.append('EOS')
    return toks, melody, harmony, tick, segments
