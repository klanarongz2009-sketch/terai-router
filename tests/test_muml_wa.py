"""MuML 1.0 WA reference: prompt reading, token validity, structure, .mid layout."""
import struct

import pytest

from terai_router import muml_wa as m

VOCAB_PREFIXES = ('BOS', 'EOS', 'M:', 'T:', 'MODE:', 'KEY:', 'CH:', 'P:', 'D:', '|')
DURATIONS = {2, 3, 4, 6, 8, 9, 12, 16, 18, 24, 30, 32, 36, 42, 48, 60, 64, 72, 84, 96, 108, 120, 144, 168, 192}


def test_rng_known_values():
    r = m.Rng(0)
    assert [r.u32() for _ in range(3)] == [1144304738, 1416247, 958946056]


@pytest.mark.parametrize('text,want', [
    ('เพลงร็อกมันส์ๆ 140 bpm คีย์ E minor 20 วินาที', dict(style='rock', mood='energetic', bpm=140, tonic=4, mode='minor', seconds=20)),
    ('sad waltz in A minor 1 minute', dict(style='folk', meter='3/4', mood='sad', tonic=9, mode='minor', seconds=60, bpm=100)),
    ('', dict(style='folk', meter='6/8', mode='major', tonic=2, bpm=100, seconds=30)),
    ('happy irish 6/8 key Bb 90 bpm', dict(meter='6/8', tonic=10, mode='major', bpm=90)),
    ('ชิลๆ คีย์ F เมเจอร์', dict(mood='calm', tonic=5, mode='major')),
    ('epic metal 180 bpm 2 นาที 10 วิ', dict(style='rock', seconds=130, bpm=180)),
    ('บรรเลงสงบ 300 bpm 5 วินาที', dict(bpm=200, seconds=8)),
])
def test_parse_prompt(text, want):
    p = m.parse_prompt(text)
    for k, v in want.items():
        assert p[k] == v, (k, p)


def test_style_override():
    assert m.parse_prompt('rock', 'folk')['style'] == 'folk'
    assert m.parse_prompt('folk', 'rock')['style'] == 'rock'


@pytest.mark.parametrize('prompt', ['', 'rock 140 bpm', 'sad waltz', 'calm reel key of G 45 seconds', 'dark rock in c# minor 2 minutes'])
@pytest.mark.parametrize('seed', [0, 5, 99])
def test_tokens_valid_and_bars_full(prompt, seed):
    s = m.generate(prompt, seed, writer='markov')
    toks = s['tokens']
    assert toks[0] == 'BOS' and toks[-1] == 'EOS'
    assert all(t.startswith(VOCAB_PREFIXES) for t in toks)
    bar = m.METERS[s['prompt']['meter']]['bar']
    acc, bars = 0, 0
    for t in toks[5:-1]:
        if t.startswith('P:'):
            assert 48 <= int(t[2:]) <= 96
        elif t.startswith('D:'):
            assert int(t[2:]) in DURATIONS
            acc += int(t[2:])
        elif t == '|':
            assert acc == bar
            acc, bars = 0, bars + 1
    assert bars % 8 == 0 and bars == len(s['form']) * 8
    # every part ends on the tonic
    last_p = [t for t in toks if t.startswith('P:')][-1]
    assert int(last_p[2:]) % 12 == s['prompt']['tonic']


def test_deterministic_and_seed_changes_song():
    a, b, c = m.generate('folk', 3, writer='markov'), m.generate('folk', 3, writer='markov'), m.generate('folk', 4, writer='markov')
    assert a == b and a['tokens'] != c['tokens']


def test_length_follows_prompt():
    short = m.generate('rock 10 วินาที', 1, writer='markov')
    long = m.generate('rock 2 นาที', 1, writer='markov')
    spt = 60 / (120 * 24)
    assert short['total_ticks'] * spt < long['total_ticks'] * spt
    assert abs(long['total_ticks'] * spt - 120) <= 8 * 2  # within one 8-bar block


def test_rock_arrangement_matches_rockify_layout():
    s = m.generate('rock', 0, writer='markov')
    names = [t['name'] for t in s['tracks']]
    assert names == ['lead_rock', 'power_rock', 'bass_rock', 'drums']
    drums = s['tracks'][3]['notes']
    assert {n[2] for n in drums} == {36, 38, 42, 49}
    assert sum(1 for n in drums if n[2] == 42) == s['total_ticks'] // 12


def test_midi_layout():
    s = m.generate('rock 12 วินาที', 2, writer='markov')
    b = m.to_midi(s)
    assert b[:4] == b'MThd'
    _, fmt, ntrk, tpq = struct.unpack('>IHHH', b[4:14])
    assert (fmt, ntrk, tpq) == (1, 5, 24)
    pos, ons = 14, 0
    for _ in range(ntrk):
        assert b[pos:pos + 4] == b'MTrk'
        ln = struct.unpack('>I', b[pos + 4:pos + 8])[0]
        chunk = b[pos + 8:pos + 8 + ln]
        assert chunk.endswith(b'\x00\xff\x2f\x00')
        ons += sum(1 for i in range(len(chunk) - 2) if chunk[i] & 0xF0 == 0x90 and chunk[i + 2] > 0 and chunk[i + 1] < 128)
        pos += 8 + ln
    assert pos == len(b)
    assert ons >= sum(len(t['notes']) for t in s['tracks'])
