"""CLI pieces for TERAI1 (beta): `terai vision` and the model side of `terai chat`."""
from __future__ import annotations

import argparse
import json
import resource
import sys
import time

from ..versions import MODEL_ID, resolve_engine, version_line
from . import local as L
from .agent import BAD_IDENTITY, IDENTITY_RULE, identity_answer, spoken_name

DEFAULT_VISION_Q = 'อธิบายภาพนี้ และอ่านข้อความทั้งหมดที่เห็นในภาพ'
VISION_SYSTEM = ('คุณคือ TER-AI โมเดล TERAI1 ตอบเป็นภาษาไทย (ถ้าผู้ใช้ถามเป็นภาษาอังกฤษให้ตอบภาษาอังกฤษ) '
                 'บอกเฉพาะสิ่งที่เห็นในภาพจริง คัดลอกข้อความในภาพตามที่เขียน ถ้าอ่านไม่ออกหรือไม่แน่ใจให้บอกตรงๆ ห้ามเดา\n'
                 + IDENTITY_RULE)


def vision_main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='terai vision',
                                 description=f'{MODEL_ID}: read an image offline (describe it, read Thai/English text '
                                             'in it, answer a question) with local Gemma 4 on CPU')
    ap.add_argument('image', nargs='?', help='image file (PNG, JPEG, WebP, ...)')
    ap.add_argument('question', nargs='*', help='question about the image (default: describe it and read the text)')
    ap.add_argument('--model', default=None, help='Gemma 4 size: e2b (default, about 5.5 GB RAM) or e4b')
    ap.add_argument('--setup', action='store_true', help='download the model and the vision projector, then exit')
    ap.add_argument('--threads', type=int, default=None)
    ap.add_argument('--max-tokens', type=int, default=400)
    ap.add_argument('--json', action='store_true', help='print JSON with timing and memory')
    a = ap.parse_args(argv)
    model = (a.model or L.DEFAULT_MODEL).lower()
    if a.setup:
        try:
            for p in L.setup(model, vision=True):
                print(p)
        except Exception as e:
            print('terai vision: ' + str(e), file=sys.stderr)
            return 2
        return 0
    if not a.image:
        ap.error('give an image file (or --setup)')
    q = ' '.join(a.question).strip() or DEFAULT_VISION_Q
    lm = L.LocalLM(model=model, vision=True, threads=a.threads)
    try:
        t0 = time.time()
        lm.load()
        load_s = time.time() - t0
        t1 = time.time()
        out = lm.look(a.image, q, max_tokens=a.max_tokens, system=VISION_SYSTEM)
        if BAD_IDENTITY.search(out):  # identity guard (v0.17.0): retry once, then the fixed answer
            out = lm.look(a.image, q, max_tokens=a.max_tokens, system=VISION_SYSTEM)
            if BAD_IDENTITY.search(out):
                out = identity_answer(q, lm.model)
        out = spoken_name(out)
        secs = time.time() - t1
    except (L.LLMUnavailable, FileNotFoundError, ValueError) as e:
        print('terai vision: ' + str(e), file=sys.stderr)
        return 2
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
    if a.json:
        print(json.dumps({'model': MODEL_ID, 'backend': lm.label, 'image': a.image, 'question': q, 'answer': out,
                          'load_s': round(load_s, 2), 'seconds': round(secs, 2), 'peak_rss_mb': rss},
                         ensure_ascii=False))
    else:
        print(out)
        print(f'[{MODEL_ID} vision: {secs:.1f} s, load {load_s:.1f} s, peak RAM {rss} MB]', file=sys.stderr)
    return 0


def models_main(argv=None) -> int:
    from ..versions import models_table
    ap = argparse.ArgumentParser(prog='terai models', description='package version and the model ids it runs')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)
    if a.json:
        from ..versions import MODELS, REPO_VERSION
        print(json.dumps({'package': 'terai-router', 'version': REPO_VERSION, 'model': MODEL_ID, 'models': MODELS},
                         ensure_ascii=False, indent=1))
    else:
        print(models_table())
    return 0


def make_brain(chat, engine: str, model: str | None, threads: int | None, quiet: bool):
    """Return a Brain for `terai chat`, or None for the rule chat. engine: auto | terai1 | rules
    (terai1beta, the 0.16.0 name, still works and prints a deprecation notice)."""
    engine = resolve_engine(engine)
    if engine not in ('auto', 'terai1', 'rules'):
        raise ValueError('engine must be auto, terai1 or rules, not ' + repr(engine))
    if engine == 'rules':
        return None
    if engine == 'auto' and not L.available(model or L.DEFAULT_MODEL):
        if not quiet:
            print(f'[{MODEL_ID}] local model not installed, using the rule chat. Install: terai chat --setup',
                  file=sys.stderr)
        return None
    from .agent import Brain
    return Brain(chat=chat, lm=L.LocalLM(model=model, threads=threads))


def banner() -> str:
    return version_line()
