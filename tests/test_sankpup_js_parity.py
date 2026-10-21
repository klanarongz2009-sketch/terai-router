"""docs/sankpup.js must draw byte-identical SVG to terai_router.sankpup.offline."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from terai_router.sankpup import offline

ROOT = Path(__file__).resolve().parent.parent
LEX = ROOT / 'src' / 'terai_router' / 'sankpup' / 'data' / 'lexicon.json'
JS = r"""
const S = require(process.argv[1]);
S.setLexicon(JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8')));
const items = JSON.parse(require('fs').readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(items.map(([p, s]) => S.generateSvg(p, s))));
"""

CASES = [
    'แมวสีส้มนั่งบนดวงจันทร์', 'บ้านหลังเล็กกับต้นไม้สองต้น ตอนกลางคืน', 'เรือใบสีแดงกลางทะเล', 'หุ่นยนต์ถือดอกไม้',
    'ภูเขากับพระอาทิตย์ตก', 'จรวดบินไปดาวอังคาร', 'หมาสามตัวใต้ต้นไม้ใหญ่', 'ปลาสีฟ้าในทะเล', 'ฝนตกบนบ้าน', 'หิมะตกบนภูเขา',
    'an orange cat sitting on the moon', 'a small house with two trees at night', 'a red sailboat on the sea',
    'a robot holding a flower', 'mountains at sunset', 'a rocket flying to Mars', 'three big red hearts',
    'a green car under a cloud', 'butterflies and flowers in the rain', 'snowy night with stars',
    'xyzzy', '', '  แมว   cat  ', 'ดาว' * 300,
]


@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
def test_sankpup_js_matches_python():
    items = [[p, s] for p in CASES for s in (0, 1, 7, 12345)]
    out = subprocess.run(['node', '-e', JS, str(ROOT / 'docs' / 'sankpup.js'), str(LEX)],
                         input=json.dumps(items, ensure_ascii=False), capture_output=True, text=True, check=True).stdout
    js = json.loads(out)
    py = [offline.generate_svg(p, s) for p, s in items]
    bad = [(items[i], a[:120], b[:120]) for i, (a, b) in enumerate(zip(py, js)) if a != b]
    assert not bad, bad[:3]
