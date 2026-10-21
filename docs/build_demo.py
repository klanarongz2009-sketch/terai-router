"""Build docs/index.html: one self-contained file with terai.js, the model and the typo table inlined.

Usage: python docs/build_demo.py
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
DATA = ROOT / 'src' / 'terai_router' / 'data'
MUML_TABLE_HEADER = """/*
 * MuML 1.0 WA note table (Markov v1), used by the MuML tab of the TER-AI web demo.
 *
 * LICENSE: GNU General Public License v3.0 (GPL-3.0-only). Full text: LICENSE-GPL-3.0.txt (next to this file).
 * This file is DATA built from the Nottingham Music Database as cleaned by jukedeck/nottingham-dataset
 * (https://github.com/jukedeck/nottingham-dataset, commit 0992bb6c, GPL-3.0; original ABC files:
 * http://abc.sourceforge.net/NMD/). It holds counts only (which pitch follows which, which chord follows
 * which, which whole-bar rhythms occur); no tune is stored.
 * It is a byte copy of src/terai_router/muml_wa/data/markov.json, written by docs/build_demo.py.
 * The code of terai-router (including docs/muml_wa.js) is MIT; this file is not. See DATA_LICENSE.
 */
"""


def main():
    model_raw = (DATA / 'model.json').read_text(encoding='utf-8')
    typo_raw = (DATA / 'typo_pairs.json').read_text(encoding='utf-8')
    model = json.loads(model_raw)
    results = json.loads((ROOT / 'eval' / 'results_v07.json').read_text(encoding='utf-8'))
    acc = results['test_set.json']['acc']
    size_mb = (DATA / 'model.json').stat().st_size / 1e6
    html = (DOCS / 'demo_template.html').read_text(encoding='utf-8')
    html = (html.replace('__VERSION__', 'v' + results['model_version'])
                .replace('__CLASSES__', str(len(model['classes'])))
                .replace('__SIZE__', f'{size_mb:.1f} MB')
                .replace('__ACC__', f'{acc * 100:.1f}%')
                .replace('__TERAI_JS__', (DOCS / 'terai.js').read_text(encoding='utf-8'))
                .replace('__MODEL_JSON__', json.dumps(model, ensure_ascii=False, separators=(',', ':')))
                .replace('__TYPO_JSON__', json.dumps(json.loads(typo_raw), ensure_ascii=False, separators=(',', ':'))))
    # v0.10: docs/tth.js (TTH text frontend + Web Speech API th-TH) is inlined after chat.js.
    # v0.8 chat mode: chat.js and the small-talk pairs go inline; the Thai Wikipedia pack stays a separate
    # file (docs/knowledge_th.json, a byte copy of the package data) that the page fetches only when needed.
    import gzip
    import shutil
    import re
    chat_version = re.search(r"__version__ = '([^']+)'", (DATA.parent / '__init__.py').read_text(encoding='utf-8')).group(1)
    kb_src = DATA / 'knowledge_th.json'
    kb_dst = DOCS / 'knowledge_th.json'
    if not kb_dst.exists() or kb_dst.read_bytes() != kb_src.read_bytes():
        shutil.copyfile(kb_src, kb_dst)
    kb_bytes = kb_src.read_bytes()
    kb = json.loads(kb_bytes)
    kb_meta = {'count': len(kb['docs']), 'retrieved': kb.get('retrieved', ''), 'bytes': len(kb_bytes)}
    gz_mb = len(gzip.compress(kb_bytes, 6)) / 1e6
    chitchat = json.loads((DATA / 'chitchat_th.json').read_text(encoding='utf-8'))['pairs']
    html = (html.replace('__CHAT_VERSION__', 'v' + chat_version)
                .replace('__KB_COUNT__', f"{kb_meta['count']:,}")
                .replace('__KB_MB__', f'{len(kb_bytes) / 1e6:.1f}')
                .replace('__KB_GZ_MB__', f'{gz_mb:.1f}')
                .replace('__KB_META__', json.dumps(kb_meta, ensure_ascii=False))
                .replace('__CHITCHAT_JSON__', json.dumps(chitchat, ensure_ascii=False, separators=(',', ':')))
                .replace('__CHAT_JS__', (DOCS / 'chat.js').read_text(encoding='utf-8'))
                .replace('__TTH_JS__', (DOCS / 'tth.js').read_text(encoding='utf-8')))
    # v0.11: SANKPUP offline generator (docs/sankpup.js) and its lexicon are inlined for the SANKPUP tab.
    lex = json.loads((DATA.parent / 'sankpup' / 'data' / 'lexicon.json').read_text(encoding='utf-8'))
    html = (html.replace('__SANKPUP_LEXICON__', json.dumps(lex, ensure_ascii=False, separators=(',', ':')))
                .replace('__SANKPUP_JS__', (DOCS / 'sankpup.js').read_text(encoding='utf-8')))
    # v0.12: MuML 1.0 WA. The synth (docs/muml_wa.js, MIT) is inlined; the Markov table is GPL-3.0 data
    # (built from the Nottingham dataset), so it is NOT inlined: it ships as its own file,
    # docs/muml_wa_table.js, with a license header, next to docs/LICENSE-GPL-3.0.txt.
    mu_dir = DATA.parent / 'muml_wa' / 'data'
    mu_table = (mu_dir / 'markov.json').read_text(encoding='utf-8')
    (DOCS / 'muml_wa_table.js').write_text(MUML_TABLE_HEADER + 'window.MUML_WA_TABLE = ' + mu_table + ';\n', encoding='utf-8')
    gpl = mu_dir / 'LICENSE-GPL-3.0.txt'
    if not (DOCS / 'LICENSE-GPL-3.0.txt').exists() or (DOCS / 'LICENSE-GPL-3.0.txt').read_bytes() != gpl.read_bytes():
        shutil.copyfile(gpl, DOCS / 'LICENSE-GPL-3.0.txt')
    html = html.replace('__MUML_WA_JS__', (DOCS / 'muml_wa.js').read_text(encoding='utf-8'))
    (DOCS / 'index.html').write_text(html, encoding='utf-8')
    print('wrote', DOCS / 'index.html', round((DOCS / 'index.html').stat().st_size / 1e6, 2), 'MB')


if __name__ == '__main__':
    main()
