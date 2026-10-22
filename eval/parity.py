"""Check that the browser JavaScript gives the same results as the Python package.

1. Router: docs/terai.js vs terai_router.route on every intent eval sentence.
2. Chat: docs/chat.js (node) vs terai_router.chat.Chat on every turn of chat_eval_v08, chat_heldout_v08 and
   chat_regress_v08, with the files' fixed clock and seed. Replies must be identical, character for character.
3. Chat with web search on (v0.9): chat_web_v09 with every MediaWiki API request answered from the frozen
   eval/web_fixtures_v09.json (offline conversations get a network error), JS through Chat.replyAsync.
4. TTH text frontend (v0.10): docs/tth.js prepare()/chunk() vs terai_router.tth on eval/tth_cases_v10.json and on
   every Python chat reply from 2 and 3, with both politeness settings (ครับ and ค่ะ).
5. SANKPUP offline generator (v0.11): docs/sankpup.js vs terai_router.sankpup.offline, byte-identical SVG for the
   12 Gemma bench prompts, every tth_cases_v10 text and the intent eval sentences, seeds 0-3.
6. MuML 1.0 WA (prototype): docs/muml_wa.js vs terai_router.muml_wa, identical prompt reading, MuML tokens,
   arranged notes and .mid bytes for the SANKPUP prompt set plus music prompts, seeds 0-1, styles auto/folk/rock.

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


class OfflineError(Exception):
    pass


def web_key(url):
    import urllib.parse
    u = urllib.parse.urlparse(url)
    return u.netloc + '|' + urllib.parse.parse_qs(u.query).get('gsrsearch', [''])[0]


def python_web_chat(fix_path, spec_path):
    import tempfile
    from terai_router.chat import Chat
    from terai_router.websearch import WebSearch
    fix = json.loads(pathlib.Path(fix_path).read_text(encoding='utf-8'))['responses']
    spec = json.loads(pathlib.Path(spec_path).read_text(encoding='utf-8'))
    out = []
    for conv in spec['conversations']:
        now = conv.get('now', spec.get('now'))
        seed = conv.get('seed', spec.get('seed'))

        def fetch(url, offline=bool(conv.get('offline'))):
            if offline:
                raise OfflineError('network is unreachable')
            return fix.get(web_key(url), {'batchcomplete': True})

        with tempfile.TemporaryDirectory() as d:
            path = pathlib.Path(d) / 'session.json'
            mk = lambda: Chat(path, now=now, seed=seed, websearch=WebSearch(enabled=True, cache_dir=None, fetch=fetch))  # noqa: E731
            chat = mk()
            replies = []
            for t in conv['turns']:
                if t.get('restart'):
                    chat = mk()
                replies.append(chat.reply(t['user']))
            out.append(replies)
    return out


def web_parity():
    fix = str(ROOT / 'eval' / 'web_fixtures_v09.json')
    spec = str(ROOT / 'eval' / 'chat_web_v09.json')
    res = subprocess.run(['node', str(ROOT / 'eval' / 'chat_parity.js'), '--web', fix, spec], capture_output=True, text=True, check=True)
    js = json.loads(res.stdout)[spec]
    py = python_web_chat(fix, spec)
    n = bad = 0
    for ci, (pc, jc) in enumerate(zip(py, js)):
        for ti, (a, b) in enumerate(zip(pc, jc)):
            n += 1
            if a != b:
                bad += 1
                print('WEB_DIFF', f'conv={ci} turn={ti}', '\n  py:', a, '\n  js:', b)
        if len(pc) != len(jc):
            bad += 1
            print('WEB_LEN_DIFF', ci)
    web_turns = sum(1 for r in py for t in r if t.startswith('[ค้นเว็บ]'))
    print(f'web (mocked) chat_web_v09.json: turns={n} identical={n - bad} diff={bad} web_answers={web_turns}')
    return bad


TTH_JS = r"""
const T = require(process.argv[1]);
const items = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const out = [];
for (const [text, polite] of items) { const s = T.prepare(text, polite); out.push([s, T.chunk(s)]); }
process.stdout.write(JSON.stringify(out));
"""


def tth_corpus():
    texts_ = json.loads((ROOT / 'eval' / 'tth_cases_v10.json').read_text(encoding='utf-8'))['cases']
    for f in CHAT_FILES:
        for conv in python_chat(str(ROOT / 'eval' / f)):
            texts_.extend(conv)
    for conv in python_web_chat(str(ROOT / 'eval' / 'web_fixtures_v09.json'), str(ROOT / 'eval' / 'chat_web_v09.json')):
        texts_.extend(conv)
    return texts_


def tth_parity():
    from terai_router.tth import chunk, prepare
    texts_ = tth_corpus()
    items = [[t, p] for t in texts_ for p in ('ครับ', 'ค่ะ')]
    res = subprocess.run(['node', '-e', TTH_JS, str(ROOT / 'docs' / 'tth.js')], input=json.dumps(items, ensure_ascii=False),
                         capture_output=True, text=True, check=True)
    js = json.loads(res.stdout)
    bad = 0
    for (text, polite), (js_s, js_c) in zip(items, js):
        s = prepare(text, polite)
        c = chunk(s)
        if s != js_s or c != js_c:
            bad += 1
            print('TTH_DIFF', repr(text), polite, '\n  py:', s, c, '\n  js:', js_s, js_c)
    print(f'tth frontend: texts={len(texts_)} checks={len(items)} identical={len(items) - bad} diff={bad}')
    return bad


SANKPUP_JS = r"""
const fs = require('fs');
const S = require(process.argv[1]);
S.setLexicon(JSON.parse(fs.readFileSync(process.argv[2], 'utf8')));
const items = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(items.map(([p, s]) => S.generateSvg(p, s))));
"""


def sankpup_parity():
    from terai_router.sankpup import offline
    prompts = [p for _, p in _bench_prompts()]
    prompts += json.loads((ROOT / 'eval' / 'tth_cases_v10.json').read_text(encoding='utf-8'))['cases']
    prompts += texts(ROOT / 'eval' / 'test_set.json')
    items = [[p, s] for p in prompts for s in range(4)]
    lex = ROOT / 'src' / 'terai_router' / 'sankpup' / 'data' / 'lexicon.json'
    res = subprocess.run(['node', '-e', SANKPUP_JS, str(ROOT / 'docs' / 'sankpup.js'), str(lex)],
                         input=json.dumps(items, ensure_ascii=False), capture_output=True, text=True, check=True)
    js = json.loads(res.stdout)
    bad = 0
    for (p, s), j in zip(items, js):
        if offline.generate_svg(p, s) != j:
            bad += 1
            if bad <= 5:
                print('SANKPUP_DIFF', repr(p), s)
    print(f'sankpup offline: prompts={len(prompts)} checks={len(items)} identical={len(items) - bad} diff={bad}')
    return bad


MUML_WA_JS = r"""
const M = require(process.argv[1]);
M.setTable(JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8')));
const items = JSON.parse(require('fs').readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(items.map(([p, s, st]) => { const g = M.generate(p, s, st); return [g, Buffer.from(M.toMidi(g)).toString('hex')]; })));
"""


def muml_wa_parity():
    from terai_router import muml_wa
    prompts = [p for _, p in _bench_prompts()]
    prompts += json.loads((ROOT / 'eval' / 'tth_cases_v10.json').read_text(encoding='utf-8'))['cases']
    prompts += ['เพลงร็อกมันส์ๆ 140 bpm คีย์ E minor 20 วินาที', 'sad waltz in A minor 1 minute', 'calm reel key of G 45 seconds',
                'happy irish 6/8 key Bb 90 bpm', 'epic metal 180 bpm 2 นาที 10 วิ', 'คีย์ D ไมเนอร์ ร็อค 6/8', '']
    items = [[p, s, st] for p in prompts for s in (0, 1) for st in ('auto', 'folk', 'rock')]
    table = ROOT / 'src' / 'terai_router' / 'muml_wa' / 'data' / 'markov.json'
    res = subprocess.run(['node', '-e', MUML_WA_JS, str(ROOT / 'docs' / 'muml_wa.js'), str(table)],
                         input=json.dumps(items, ensure_ascii=False), capture_output=True, text=True, check=True)
    bad = 0
    for (p, s, st), (song, mid) in zip(items, json.loads(res.stdout)):
        py = muml_wa.generate(p, s, st, writer='markov')
        if json.loads(json.dumps(py, ensure_ascii=False)) != song or muml_wa.to_midi(py).hex() != mid:
            bad += 1
            if bad <= 5:
                print('MUML_WA_DIFF', repr(p), s, st)
    print(f'muml wa: prompts={len(prompts)} checks={len(items)} identical={len(items) - bad} diff={bad}')
    # v0.12: the web demo loads the table from docs/muml_wa_table.js (GPL-3.0 data file with a license header);
    # it must carry exactly the bytes of markov.json, or the browser would write different songs.
    page = (ROOT / 'docs' / 'muml_wa_table.js').read_text(encoding='utf-8')
    head, _, body = page.partition('window.MUML_WA_TABLE = ')
    same = body == table.read_text(encoding='utf-8') + ';\n' and 'GPL-3.0' in head and 'nottingham-dataset' in head
    print(f'muml wa: docs/muml_wa_table.js matches markov.json and has the GPL-3.0 header: {same}')
    return bad + (0 if same else 1)


MUML_WA_NET_JS = r"""
const fs = require('fs');
globalThis.MUMLWA = require(process.argv[1]);
const N = require(process.argv[2]);
const b = fs.readFileSync(process.argv[3]);
N.load(b.buffer.slice(b.byteOffset, b.byteOffset + b.length));
const items = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(items.map(([p, s, st]) => { const g = N.generate(p, s, st); return [g, Buffer.from(MUMLWA.toMidi(g)).toString('hex')]; })));
"""


def muml_wa_net_parity():
    """v0.15: the MuML 1.0 network writer, docs/muml_wa_net.js vs terai_router.muml_wa.net (needs numpy)."""
    from terai_router import muml_wa
    from terai_router.muml_wa import net
    path = ROOT / 'docs' / net.WEIGHTS_NAME
    if not net.numpy_available() or not path.is_file():
        print('muml wa net: SKIPPED (numpy or docs/muml-1.0-int8.bin missing)')
        return 0
    prompts = ['เพลงร็อกมันส์ๆ 140 bpm คีย์ E minor 20 วินาที', 'sad waltz in A minor 1 minute', 'calm reel key of G 45 seconds',
               'happy irish 6/8 key Bb 90 bpm', 'epic metal 180 bpm 2 นาที 10 วิ', 'คีย์ D ไมเนอร์ ร็อค 6/8', '',
               'เพลงเศร้า 3/4 คีย์ F', 'folk jig D major', 'rock 10 วินาที']
    items = [[p, s, st] for p in prompts for s, st in ((0, 'auto'), (1, 'folk'), (2, 'rock'))]
    res = subprocess.run(['node', '-e', MUML_WA_NET_JS, str(ROOT / 'docs' / 'muml_wa.js'), str(ROOT / 'docs' / 'muml_wa_net.js'),
                          str(path)], input=json.dumps(items, ensure_ascii=False), capture_output=True, text=True, check=True)
    bad = 0
    for (p, s, st), (song, mid) in zip(items, json.loads(res.stdout)):
        py = muml_wa.generate(p, s, st, writer='net', weights=str(path))
        if json.loads(json.dumps(py, ensure_ascii=False)) != song or muml_wa.to_midi(py).hex() != mid:
            bad += 1
            if bad <= 5:
                print('MUML_WA_NET_DIFF', repr(p), s, st)
    print(f'muml wa net: checks={len(items)} identical={len(items) - bad} diff={bad}')
    return bad


# v0.13: Temmo remix rules (docs/temmo/community.js vs src/terai_router/temmo/remix.py).
# Thai commands and the "background pink" order must read as before; English order is new.
REMIX_CASES = [
    # Thai commands (as before v0.13)
    'พื้นหลังสีชมพู ง่ายขึ้น', 'พื้นหลังสีชมพู กำแพงสีน้ำตาล ยากขึ้น', 'พื้นสีเทา พื้นหลังสีดำ ศัตรูสีแดง',
    'ชื่อเกม "แมวส้มตะลุยตลาด" กำแพงสีน้ำตาล และพื้นหลังสีฟ้า ยากขึ้น', 'คำโปรย: เก็บปลาทูให้ครบ', 'สีสวยขึ้น',
    'ผู้เล่นสีเขียว ประตูสีเหลือง เวลาเพิ่ม', 'ตัวละครสีม่วง ไอเทมสีส้ม เวลาน้อยลง', 'ของสีขาว ศัตรูสีดำ ง่ายลง',
    'ชื่อ <b>{x}</b>', 'แดง พื้นหลังสีชมพู', 'ขอสีแดงของผู้เล่น',
    # "background pink" order (as before v0.13)
    'background pink, harder', 'background pink, wall brown, harder', 'title: Market Cat, wall blue and enemy red',
    'player white, exit yellow; more time', 'floor grey, bg black, easier', 'red, background pink', 'wall brown background pink',
    'gem orange and exit purple, less time', 'tagline: collect every fish', 'enemy sky',
    # English order (new in v0.13)
    'pink background, harder', 'pink background', 'make the player blue', 'faster enemies', 'more levels', 'harder',
    'pink background, blue walls', 'pink background blue walls', 'blue player, red enemies, faster enemies',
    'green floor and yellow door', 'slower enemies, more time', 'add 3 levels', 'one more level', 'add 5 more levels',
    'make it easier with 2 extra levels', 'white gems, black exit', 'speed up the enemies', 'enemies move slower',
    'purple walls, pink background, harder, more levels', 'make the background brown and the walls gray',
]

REMIX_JS = r"""
const C = require(process.argv[1]);
const d = JSON.parse(require('fs').readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(d.cases.map((c) => { const r = C.remix(d.game, c); return [r.patch, r.game]; })));
"""


def remix_parity():
    from terai_router.temmo import remix as R
    game = R.read_game((ROOT / 'docs' / 'temmo' / 'games' / 'orange-cat-fish-collector.html').read_text(encoding='utf-8'))
    res = subprocess.run(['node', '-e', REMIX_JS, str(ROOT / 'docs' / 'temmo' / 'community.js')],
                         input=json.dumps({'game': game, 'cases': REMIX_CASES}, ensure_ascii=False),
                         capture_output=True, text=True, check=True)
    bad = 0
    for case, (patch, new) in zip(REMIX_CASES, json.loads(res.stdout)):
        py_new, py_patch, _ = R.remix(game, case)
        if json.loads(json.dumps([py_patch, py_new], ensure_ascii=False)) != [patch, new]:
            bad += 1
            if bad <= 5:
                print('REMIX_DIFF', repr(case), '\n  py:', py_patch, '\n  js:', patch)
    print(f'temmo remix: cases={len(REMIX_CASES)} identical={len(REMIX_CASES) - bad} diff={bad}')
    return bad


def _bench_prompts():
    import ast
    src = (ROOT / 'eval' / 'sankpup_gemma_bench.py').read_text(encoding='utf-8')
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], 'id', '') == 'PROMPTS':
            return ast.literal_eval(node.value)
    raise RuntimeError('PROMPTS not found in sankpup_gemma_bench.py')


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
    web_bad = web_parity()
    tth_bad = tth_parity()
    sankpup_bad = sankpup_parity()
    muml_wa_bad = muml_wa_parity()
    muml_wa_bad += muml_wa_net_parity()
    remix_bad = remix_parity()
    return 1 if intent_diff or norm_diff or chat_bad or web_bad or tth_bad or sankpup_bad or muml_wa_bad or remix_bad else 0


if __name__ == '__main__':
    sys.exit(main())
