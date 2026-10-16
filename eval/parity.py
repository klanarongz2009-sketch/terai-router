"""Check that the browser JavaScript gives the same results as the Python package.

1. Router: docs/terai.js vs terai_router.route on every intent eval sentence.
2. Chat: docs/chat.js (node) vs terai_router.chat.Chat on every turn of chat_eval_v08, chat_heldout_v08 and
   chat_regress_v08, with the files' fixed clock and seed. Replies must be identical, character for character.

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


CHAT_FILES = ['chat_eval_v08.json', 'chat_heldout_v08.json', 'chat_regress_v08.json', 'chat_parity_probe_v08.json']


def python_chat(spec_path):
    import tempfile
    from terai_router.chat import Chat
    spec = json.loads(pathlib.Path(spec_path).read_text(encoding='utf-8'))
    out = []
    for conv in spec['conversations']:
        now = conv.get('now', spec.get('now'))
        seed = conv.get('seed', spec.get('seed'))
        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / 'session.json'
            chat = Chat(path, now=now, seed=seed)
            replies = []
            for t in conv['turns']:
                if t.get('restart'):
                    chat = Chat(path, now=now, seed=seed)
                replies.append(chat.reply(t['user']))
            out.append(replies)
    return out


def chat_parity():
    files = [str(ROOT / 'eval' / f) for f in CHAT_FILES]
    res = subprocess.run(['node', str(ROOT / 'eval' / 'chat_parity.js')] + files, capture_output=True, text=True, check=True)
    js_all = json.loads(res.stdout)
    bad_total = n_total = 0
    for f in files:
        py = python_chat(f)
        js = js_all[f]
        n = bad = 0
        for ci, (pc, jc) in enumerate(zip(py, js)):
            for ti, (a, b) in enumerate(zip(pc, jc)):
                n += 1
                if a != b:
                    bad += 1
                    print('CHAT_DIFF', pathlib.Path(f).name, f'conv={ci} turn={ti}', '\n  py:', a, '\n  js:', b)
            if len(pc) != len(jc):
                bad += 1
                print('CHAT_LEN_DIFF', pathlib.Path(f).name, ci)
        print(f'chat {pathlib.Path(f).name}: turns={n} identical={n - bad} diff={bad}')
        n_total += n
        bad_total += bad
    print(f'chat total: turns={n_total} identical={n_total - bad_total} diff={bad_total}')
    return bad_total


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
    chat_bad = chat_parity()
    return 1 if intent_diff or norm_diff or chat_bad else 0


if __name__ == '__main__':
    sys.exit(main())
