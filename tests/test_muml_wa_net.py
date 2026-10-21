"""MuML 1.0 WA network writer (v0.15): weights file, determinism, grammar, fallback, JS parity."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from terai_router import muml_wa
from terai_router.muml_wa import net

ROOT = Path(__file__).resolve().parents[1]
W = ROOT / 'docs' / net.WEIGHTS_NAME
needs = pytest.mark.skipif(not (net.numpy_available() and W.is_file()), reason='numpy or weights missing')


def test_weights_file_matches_pinned_hash():
    if not W.is_file():
        pytest.skip('weights not in this checkout')
    b = W.read_bytes()
    assert len(b) == net.WEIGHTS_BYTES
    assert hashlib.sha256(b).hexdigest() == net.WEIGHTS_SHA256


@needs
def test_header_describes_muml_1_0():
    n = net.load(str(W))
    assert n['cfg'] == {'vocab': 163, 'ctx': 512, 'd_model': 256, 'n_head': 4, 'n_layer': 4, 'dropout': 0.1} or \
        (n['cfg']['d_model'], n['cfg']['n_layer'], n['cfg']['ctx']) == (256, 4, 512)
    assert len(n['vocab']) == 163 and n['h']['epoch'] == 30


@needs
def test_net_song_is_deterministic_and_well_formed():
    a = muml_wa.generate('folk jig D major', 5, writer='net', weights=str(W))
    b = muml_wa.generate('folk jig D major', 5, writer='net', weights=str(W))
    c = muml_wa.generate('folk jig D major', 6, writer='net', weights=str(W))
    assert a == b and a['tokens'] != c['tokens']
    assert a['note_writer'] == 'muml-1.0-net' and a['model'] == 'MuML 1.0'
    t = a['tokens']
    assert t[:5] == ['BOS', 'M:6/8', 'T:jig', 'MODE:major', 'KEY:2'] and t[-1] == 'EOS'
    for i, x in enumerate(t):  # every note or rest is followed by a duration, durations only after notes
        if x.startswith('P:') or x == 'R':
            assert t[i + 1].startswith('D:')
        if x.startswith('D:'):
            assert t[i - 1].startswith('P:') or t[i - 1] == 'R'
    lead = next(tr for tr in a['tracks'] if tr['name'].startswith('lead'))
    assert lead['notes'] and a['total_ticks'] > 0
    assert muml_wa.to_midi(a)[:4] == b'MThd'


@needs
def test_length_follows_prompt():
    s = muml_wa.generate('rock 10 วินาที', 1, writer='net', weights=str(W))
    lng = muml_wa.generate('rock 1 นาที', 1, writer='net', weights=str(W))
    assert lng['total_ticks'] > 3 * s['total_ticks']


def test_auto_falls_back_to_markov_without_weights(monkeypatch, tmp_path):
    monkeypatch.setattr(net, 'find_weights', lambda: None)
    assert muml_wa.writer_available() == 'markov'
    assert muml_wa.generate('folk', 1)['note_writer'] == 'markov-v1'
    with pytest.raises(FileNotFoundError):
        muml_wa.generate('folk', 1, writer='net')


@needs
@pytest.mark.skipif(shutil.which('node') is None, reason='node not installed')
def test_js_writes_the_same_song():
    js = r"""
const fs = require('fs');
globalThis.MUMLWA = require(process.argv[1]);
const N = require(process.argv[2]);
const b = fs.readFileSync(process.argv[3]);
N.load(b.buffer.slice(b.byteOffset, b.byteOffset + b.length));
process.stdout.write(JSON.stringify(JSON.parse(process.argv[4]).map(([p, s, st]) => N.generate(p, s, st))));
"""
    items = [['sad waltz in A minor 20 seconds', 3, 'auto'], ['rock E minor 15 วินาที', 4, 'rock']]
    out = subprocess.run(['node', '-e', js, str(ROOT / 'docs' / 'muml_wa.js'), str(ROOT / 'docs' / 'muml_wa_net.js'), str(W),
                          json.dumps(items)], capture_output=True, text=True, check=True).stdout
    for (p, s, st), song in zip(items, json.loads(out)):
        assert json.loads(json.dumps(muml_wa.generate(p, s, st, writer='net', weights=str(W)), ensure_ascii=False)) == song
