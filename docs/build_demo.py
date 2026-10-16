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
    (DOCS / 'index.html').write_text(html, encoding='utf-8')
    print('wrote', DOCS / 'index.html', round((DOCS / 'index.html').stat().st_size / 1e6, 2), 'MB')


if __name__ == '__main__':
    main()
