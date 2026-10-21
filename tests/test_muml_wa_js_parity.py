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
        py = muml_wa.generate(p, s, st)
        py_json = json.loads(json.dumps(py, ensure_ascii=False))
        if py_json != song or muml_wa.to_midi(py).hex() != mid:
            bad.append((p, s, st))
    assert not bad, bad[:5]
    assert len(items) == 228
