"""Build docs/index.html: one self-contained file with terai.js, the model and the typo table inlined.

Usage: python docs/build_demo.py
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
DATA = ROOT / 'src' / 'terai_router' / 'data'


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
    (DOCS / 'index.html').write_text(html, encoding='utf-8')
    print('wrote', DOCS / 'index.html', round((DOCS / 'index.html').stat().st_size / 1e6, 2), 'MB')


if __name__ == '__main__':
    main()
