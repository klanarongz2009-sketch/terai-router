"""docs/tth.js must say exactly what terai_router.tth says (same spoken text, same chunks)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from terai_router.tth import chunk, prepare

ROOT = Path(__file__).resolve().parent.parent
JS = r"""
const T = require(process.argv[1]);
const items = JSON.parse(require('fs').readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(items.map(([t, p]) => { const s = T.prepare(t, p); return [s, T.chunk(s)]; })));
"""


@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
def test_tth_js_matches_python_on_cases():
    cases = json.loads((ROOT / 'eval' / 'tth_cases_v10.json').read_text(encoding='utf-8'))['cases']
    items = [[t, p] for t in cases for p in ('ครับ', 'ค่ะ')]
    out = subprocess.run(['node', '-e', JS, str(ROOT / 'docs' / 'tth.js')], input=json.dumps(items),
                         capture_output=True, text=True, check=True).stdout
    js = json.loads(out)
    py = [[prepare(t, p), chunk(prepare(t, p))] for t, p in items]
    assert js == py


def test_demo_inlines_tth():
    html = (ROOT / 'docs' / 'index.html').read_text(encoding='utf-8')
    assert 'TERAI_TTH' in html and 'speaktoggle' in html and '__TTH_JS__' not in html
