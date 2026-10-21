"""docs/muml_wa.js must read prompts, write MuML tokens, arrange notes and write .mid bytes exactly like
terai_router.muml_wa (same seed -> same song)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from terai_router import muml_wa

ROOT = Path(__file__).resolve().parent.parent
TABLE = ROOT / 'src' / 'terai_router' / 'muml_wa' / 'data' / 'markov.json'
JS = r"""
const M = require(process.argv[1]);
M.setTable(JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8')));
const items = JSON.parse(require('fs').readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(items.map(([p, s, st]) => {
  const song = M.generate(p, s, st);
  return [song, Buffer.from(M.toMidi(song)).toString('hex')];
})));
"""

PROMPTS = [
    '', 'folk jig', 'เพลงโฟล์คสนุกๆ', 'เพลงร็อกมันส์ๆ 140 bpm คีย์ E minor 20 วินาที', 'sad waltz in A minor 1 minute',
    'calm reel key of G 45 seconds', 'dark rock in c# minor', 'เพลงเศร้า ไมเนอร์ 3/4', 'happy irish 6/8 key Bb 90 bpm',
    'epic metal 180 bpm 2 นาที 10 วิ', 'ชิลๆ คีย์ F เมเจอร์', 'energetic rock 4/4 key of f sharp', 'เพลงมืดๆ จิ๊ก',
    'rock 8s', 'xyzzy', '   ', 'บรรเลงสงบ 300 bpm 5 วินาที', 'a major chill', 'คีย์ D ไมเนอร์ ร็อค 6/8',
]


def _items():
    return [[p, s, st] for p in PROMPTS for s in (0, 1, 42, 4294967295) for st in ('auto', 'folk', 'rock')]


@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
def test_muml_wa_js_matches_python():
    items = _items()
    out = subprocess.run(['node', '-e', JS, str(ROOT / 'docs' / 'muml_wa.js'), str(TABLE)],
                         input=json.dumps(items, ensure_ascii=False), capture_output=True, text=True, check=True).stdout
    js = json.loads(out)
    bad = []
    for (p, s, st), (song, mid) in zip(items, js):
        py = muml_wa.generate(p, s, st, writer='markov')
        py_json = json.loads(json.dumps(py, ensure_ascii=False))
        if py_json != song or muml_wa.to_midi(py).hex() != mid:
            bad.append((p, s, st))
    assert not bad, bad[:5]
    assert len(items) == 228


def test_demo_table_file_is_markov_json_with_license_header():
    """The web demo loads docs/muml_wa_table.js; it must be a byte copy of markov.json behind a GPL-3.0 header."""
    page = (ROOT / 'docs' / 'muml_wa_table.js').read_text(encoding='utf-8')
    head, sep, body = page.partition('window.MUML_WA_TABLE = ')
    assert sep and body == TABLE.read_text(encoding='utf-8') + ';\n'
    assert 'GPL-3.0' in head and 'https://github.com/jukedeck/nottingham-dataset' in head
    assert (ROOT / 'docs' / 'LICENSE-GPL-3.0.txt').read_bytes() == (TABLE.parent / 'LICENSE-GPL-3.0.txt').read_bytes()


def test_table_declares_its_license():
    t = json.loads(TABLE.read_text(encoding='utf-8'))
    assert t['license']['spdx'] == 'GPL-3.0-only'
    assert t['license']['source_url'] == 'https://github.com/jukedeck/nottingham-dataset'
    gpl = (TABLE.parent / 'LICENSE-GPL-3.0.txt').read_text(encoding='utf-8')
    assert 'GNU GENERAL PUBLIC LICENSE' in gpl and 'Version 3, 29 June 2007' in gpl
    # the web page must not inline the GPL table into the MIT-licensed page any more
    assert 'window.MUML_WA_TABLE = {' not in (ROOT / 'docs' / 'index.html').read_text(encoding='utf-8')
