"""Check that docs/terai.js gives the same intent as the Python package on every eval sentence.

Usage: python eval/parity.py   (needs node on PATH)
"""
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from terai_router import route  # noqa: E402


def texts(path):
    data = json.loads(path.read_text(encoding='utf-8'))
    out = []
    for rows in data.values():
        for row in rows:
            out.append(row['text'] if isinstance(row, dict) else row[0])
    return out


def main():
    items = texts(ROOT / 'eval' / 'test_set.json') + texts(ROOT / 'eval' / 'heldout_v07.json')
    js = r"""
const fs = require('fs');
const T = require(process.argv[1]);
const m = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const t = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const r = T.create(m, t);
const items = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(items.map(x => { const p = r.predict(x); return [p.intent, p.confidence, p.normalized]; })));
"""
    data = ROOT / 'src' / 'terai_router' / 'data'
    res = subprocess.run(['node', '-e', js, str(ROOT / 'docs' / 'terai.js'), str(data / 'model.json'), str(data / 'typo_pairs.json')],
                         input=json.dumps(items, ensure_ascii=False), capture_output=True, text=True, check=True)
    js_out = json.loads(res.stdout)
    intent_diff = norm_diff = 0
    max_conf = 0.0
    for text, (ji, jc, jn) in zip(items, js_out):
        p = route(text)
        if p['intent'] != ji:
            intent_diff += 1
            print('INTENT_DIFF', text, p['intent'], ji)
        if p['normalized'] != jn:
            norm_diff += 1
            print('NORMALIZED_DIFF', text, p['normalized'], jn)
        max_conf = max(max_conf, abs(p['confidence'] - jc))
    print(f'n={len(items)} intent_diff={intent_diff} normalized_diff={norm_diff} max_confidence_diff={max_conf:.2e}')
    return 1 if intent_diff or norm_diff else 0


if __name__ == '__main__':
    sys.exit(main())
