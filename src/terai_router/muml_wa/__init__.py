"""MuML 1.0 WA (MuML 1.0 Web Audio API): the browser member of the MuML music family.

This module is the Python reference for docs/muml_wa.js. Both must produce the same prompt reading,
the same MuML tokens, the same arranged note events and the same .mid bytes for the same
(prompt, seed, style). tests/test_muml_wa_js_parity.py checks that.

Note writer (markov-v1, released in terai-router v0.12.0): a seeded Markov chain over the MuML 1.0 training data (Nottingham,
key-relative pitch order-2 with order-1 back-off, bar-level chord transitions, whole-bar rhythm
patterns), table in data/markov.json (GPL-3.0 data built from the Nottingham dataset, see DATA_LICENSE;
this module's code is MIT). It is NOT the trained MuML 1.0 network; it sits behind the same
interface (prompt + seed -> MuML tokens) so the network can replace it later.
Sound is made in the browser by docs/muml_wa.js with Web Audio oscillators, filters and noise.
No dependencies.
"""
from __future__ import annotations

import json
import re
import struct
from pathlib import Path

VERSION = '1.0'
NOTE_WRITER = 'markov-v1'
M32 = 0xFFFFFFFF
TABLE = json.loads((Path(__file__).parent / 'data' / 'markov.json').read_text(encoding='utf-8'))

METERS = {'4/4': {'bar': 96, 'beat': 24, 'type': 'reel'},
          '6/8': {'bar': 72, 'beat': 36, 'type': 'jig'},
          '3/4': {'bar': 72, 'beat': 24, 'type': 'waltz'}}
STYLES = ('folk', 'rock')
CHORD_IV = {'maj': (0, 4, 7), 'min': (0, 3, 7), '7': (0, 4, 7, 10), 'dim': (0, 3, 6)}
SCALE = {'major': (0, 2, 4, 5, 7, 9, 11), 'minor': (0, 2, 3, 5, 7, 8, 10)}
MEL_MIN, MEL_MAX = -5, 19
NOTE_PC = {'c': 0, 'd': 2, 'e': 4, 'f': 5, 'g': 7, 'a': 9, 'b': 11}
# (mood, words, mode or None, bpm change); first match wins
MOODS = (
    ('sad', ('เศร้า', 'เหงา', 'sad', 'melanchol', 'lonely'), 'minor', -20),
    ('dark', ('มืด', 'ดาร์ก', 'dark', 'scary', 'น่ากลัว'), 'minor', -5),
    ('calm', ('ผ่อนคลาย', 'สงบ', 'ชิล', 'calm', 'chill', 'relax', 'gentle', 'นุ่ม'), None, -25),
    ('energetic', ('มันส์', 'มัน ๆ', 'เร้าใจ', 'ดุ', 'energetic', 'epic', 'fast', 'เร็ว', 'hype'), None, 20),
    ('happy', ('สนุก', 'ร่าเริง', 'สดใส', 'มีความสุข', 'happy', 'joy', 'cheer', 'bright', 'fun'), 'major', 10),
)
PROGRAMS = {'lead_folk': 40, 'chords_folk': 24, 'bass_folk': 32, 'lead_rock': 30, 'power_rock': 29, 'bass_rock': 33, 'drums': 0}


class Rng:
    """mulberry32, bit-exact with the JavaScript version."""

    def __init__(self, seed: int):
        self.a = seed & M32

    def u32(self) -> int:
        self.a = (self.a + 0x6D2B79F5) & M32
        t = self.a
        t = ((t ^ (t >> 15)) * (t | 1)) & M32
        t ^= (t + (((t ^ (t >> 7)) * (t | 61)) & M32)) & M32
        return (t ^ (t >> 14)) & M32

    def pick(self, options):
        """options: [[value, weight], ...] with integer weights."""
        total = sum(w for _, w in options)
        r = self.u32() % total
        for v, w in options:
            if r < w:
                return v
            r -= w
        return options[-1][0]


def _has(text, words):
    return any(w in text for w in words)


def parse_prompt(text: str, style: str = 'auto') -> dict:
    """Read mood, style, meter, key, mode, BPM and length from a Thai or English prompt."""
    t = (text or '').lower()
    explicit = []
    if style not in STYLES:
        if _has(t, ('rock', 'ร็อก', 'ร็อค', 'ร๊อค', 'ร๊อก', 'metal', 'เมทัล')):
            style = 'rock'
            explicit.append('style')
        elif _has(t, ('folk', 'โฟล์ค', 'โฟล์ก', 'jig', 'reel', 'irish', 'ไอริช', 'จิ๊ก', 'รีล')):
            style = 'folk'
            explicit.append('style')
        else:
            style = 'folk'
    if _has(t, ('6/8', 'jig', 'จิ๊ก')):
        meter = '6/8'
        explicit.append('meter')
    elif _has(t, ('3/4', 'waltz', 'วอลทซ์', 'วอลซ์', 'วอลตซ์')):
        meter = '3/4'
        explicit.append('meter')
    elif _has(t, ('4/4', 'reel', 'รีล')):
        meter = '4/4'
        explicit.append('meter')
    else:
        meter = '6/8' if style == 'folk' else '4/4'
    mood, mood_mode, delta = 'neutral', None, 0
    for name, words, mm, d in MOODS:
        if _has(t, words):
            mood, mood_mode, delta = name, mm, d
            explicit.append('mood')
            break
    tonic, mode = None, None
    m = re.search(r'(?:key|คีย์|คีย์)[ ]*(?:of[ ]*)?([a-g])(#|b(?![a-z])|sharp|flat|ชาร์ป|แฟลต)?[ ]*(minor|major|maj|m(?![a-z])|ไมเนอร์|เมเจอร์)?', t)
    if not m:
        m = re.search(r'(?:^|[^a-z])([a-g])(#|b|sharp|flat)?[ ]*(minor|major|ไมเนอร์|เมเจอร์)(?![a-z])', t)
    if m:
        tonic = NOTE_PC[m.group(1)]
        acc = m.group(2) or ''
        if acc in ('#', 'sharp', 'ชาร์ป'):
            tonic = (tonic + 1) % 12
        elif acc in ('b', 'flat', 'แฟลต'):
            tonic = (tonic + 11) % 12
        q = m.group(3) or ''
        if q in ('minor', 'm', 'ไมเนอร์'):
            mode = 'minor'
        elif q in ('major', 'maj', 'เมเจอร์'):
            mode = 'major'
        explicit.append('key')
    if mode is None:
        if _has(t, ('ไมเนอร์', 'minor')):
            mode = 'minor'
        elif _has(t, ('เมเจอร์', 'major')):
            mode = 'major'
        else:
            mode = mood_mode or 'major'
    if tonic is None:
        tonic = (4 if mode == 'minor' else 9) if style == 'rock' else (9 if mode == 'minor' else 2)
    m = re.search(r'([0-9]{2,3})[ ]*(?:bpm|บีพีเอ็ม)', t)
    if m:
        bpm = int(m.group(1))
        explicit.append('bpm')
    else:
        base = {('folk', '6/8'): 100, ('folk', '4/4'): 110, ('folk', '3/4'): 120,
                ('rock', '6/8'): 100, ('rock', '4/4'): 120, ('rock', '3/4'): 120}[(style, meter)]
        bpm = base + delta
    bpm = max(50, min(200, bpm))
    seconds = 30
    m = re.search(r'([0-9]+)[ ]*(?:นาที|minutes?|mins?(?![a-z]))', t)
    if m:
        seconds = int(m.group(1)) * 60
        explicit.append('length')
    m = re.search(r'([0-9]+)[ ]*(?:วินาที|วิ|seconds?|secs?(?![a-z])|s(?![a-z]))', t)
    if m:
        seconds = (seconds if 'length' in explicit else 0) + int(m.group(1))
        if 'length' not in explicit:
            explicit.append('length')
    seconds = max(8, min(180, seconds))
    return {'style': style, 'meter': meter, 'mood': mood, 'mode': mode, 'tonic': tonic, 'bpm': bpm,
            'seconds': seconds, 'explicit': explicit}


def _lookup(table_list, key):
    for k, v in table_list:
        if k == key:
            return v
    return None


class _Writer:
    def __init__(self, p, rng):
        self.p, self.rng, self.mode = p, rng, p['mode']
        self.o1 = TABLE['o1'][self.mode]
        self.o2 = TABLE['o2'][self.mode]
        self.hist = []

    def candidates(self):
        h = self.hist
        levels = []
        if len(h) >= 2:
            levels.append(_lookup(self.o2, [h[-2], h[-1]]))
        if len(h) >= 1:
            levels.append(_lookup(self.o1, h[-1]))
        else:
            levels.append(TABLE['start'][self.mode])
        for opts in levels:
            if opts:
                ok = [[v, w] for v, w in opts if MEL_MIN <= v <= MEL_MAX]
                if ok:
                    return ok
        last = h[-1] if h else 0
        sc = SCALE[self.mode]
        ok = [[v, 1] for v in (last - 2, last - 1, last + 1, last + 2) if MEL_MIN <= v <= MEL_MAX and v % 12 in sc]
        return ok or [[0, 1]]

    def chord(self, prev):
        return self.rng.pick(_lookup(TABLE['chords'][self.mode], prev) or [[prev, 1]])

    def part(self, sampled_start):
        tonic_chord = '0:maj' if self.mode == 'major' else '0:min'
        bars = []
        prev = tonic_chord
        rhythms = TABLE['rhythms'][self.p['meter']]
        for b in range(8):
            if b == 0:
                ch = self.chord(prev) if sampled_start else tonic_chord
            elif b == 6:
                ch = '7:maj'
            elif b == 7:
                ch = tonic_chord
            else:
                ch = self.chord(prev)
            prev = ch
            root, q = ch.split(':')
            pcs = [(int(root) + iv) % 12 for iv in CHORD_IV[q]]
            pattern = self.rng.pick([[i, c] for i, (_, c) in enumerate(rhythms)])
            durs = rhythms[pattern][0]
            notes = []
            for i, d in enumerate(durs):
                if b == 7 and i == len(durs) - 1:
                    last = self.hist[-1] if self.hist else 0
                    rel = 0 if abs(last) <= abs(last - 12) else 12
                else:
                    opts = self.candidates()
                    if i == 0:
                        opts = [[v, w * 4 if v % 12 in pcs else w] for v, w in opts]
                    rel = self.rng.pick(opts)
                self.hist.append(rel)
                notes.append((rel, d))
            bars.append((ch, notes))
        return bars


def _form_blocks(p):
    m = METERS[p['meter']]
    bpb = m['bar'] // m['beat']
    num, den = p['seconds'] * p['bpm'], 60 * bpb
    bars = (num + den - 1) // den
    n8 = max(1, (bars + 4) // 8)
    if n8 <= 2:  # short songs still get both parts
        return list('AB'[:n8])
    return ['AABB'[i % 4] for i in range(n8)]


def _tonic_ref(tonic):
    return 60 + (tonic if tonic <= 6 else tonic - 12)


def generate(prompt: str = '', seed: int = 0, style: str = 'auto') -> dict:
    """prompt + seed -> {'prompt': reading, 'tokens': MuML tokens, 'tracks': arranged notes, ...}."""
    p = parse_prompt(prompt, style)
    rng = Rng(seed)
    w = _Writer(p, rng)
    parts = {'A': w.part(False)}
    parts['B'] = w.part(True)
    ref, tonic = _tonic_ref(p['tonic']), p['tonic']
    met = METERS[p['meter']]
    toks = ['BOS', f"M:{p['meter']}", f"T:{met['type']}", f"MODE:{p['mode']}", f'KEY:{tonic}']
    melody, harmony, tick = [], [], 0
    blocks = _form_blocks(p)
    for blk in blocks:
        for ch, notes in parts[blk]:
            root, q = ch.split(':')
            toks.append(f'CH:{(int(root) + tonic) % 12}:{q}')
            harmony.append([tick, met['bar'], (int(root) + tonic) % 12, q])
            for rel, d in notes:
                toks += [f'P:{ref + rel}', f'D:{d}']
                melody.append([tick, d, ref + rel])
                tick += d
            toks.append('|')
    toks.append('EOS')
    tracks = arrange(p, melody, harmony, tick)
    return {'version': VERSION, 'note_writer': NOTE_WRITER, 'seed': seed & M32, 'prompt': p, 'form': ''.join(blocks),
            'tokens': toks, 'total_ticks': tick, 'tracks': tracks}


def _fit(pc, lo):
    """Lowest MIDI pitch with pitch class pc that is >= lo."""
    return lo + (pc - lo) % 12


def arrange(p, melody, harmony, total):
    met = METERS[p['meter']]
    beat, half = met['beat'], met['beat'] // 2
    if p['style'] == 'folk':
        lead = {'name': 'lead_folk', 'channel': 0, 'notes': [[s, d, n, 96] for s, d, n in melody]}
        chords = {'name': 'chords_folk', 'channel': 1, 'notes': []}
        bass = {'name': 'bass_folk', 'channel': 2, 'notes': []}
        for s, d, root, q in harmony:
            nb = d // beat
            for k in range(nb):
                t0 = s + k * beat
                pc = root if k % 2 == 0 else (root + 7) % 12
                bass['notes'].append([t0, half, _fit(pc, 40), 84])
                for iv in CHORD_IV[q][:3]:
                    chords['notes'].append([t0 + half, half, _fit((root + iv) % 12, 55), 60])
        return [lead, chords, bass]
    lead = {'name': 'lead_rock', 'channel': 0, 'notes': [[s, d, n, 105] for s, d, n in melody]}
    power = {'name': 'power_rock', 'channel': 1, 'notes': []}
    bass = {'name': 'bass_rock', 'channel': 2, 'notes': []}
    drums = {'name': 'drums', 'channel': 9, 'notes': []}
    for s, d, root, q in harmony:
        r = _fit(root, 40)
        for t0 in range(s, s + d, 12):
            for pitch in (r, r + 7, r + 12):
                power['notes'].append([t0, 11, pitch, 88])
            bass['notes'].append([t0, 11, r - 12, 100])
    step = 6 if p['meter'] == '6/8' else 8
    kicks, snares = ((0, 4), (3,)) if step == 6 else ((0, 4, 5), (2, 6))
    for i, t0 in enumerate(range(0, total, 12)):
        pos = i % step
        drums['notes'].append([t0, 6, 42, 70])
        if pos in kicks:
            drums['notes'].append([t0, 12, 36, 110])
        if pos in snares:
            drums['notes'].append([t0, 12, 38, 115])
        if i % 64 == 0:
            drums['notes'].append([t0, 48, 49, 110])
    return [lead, power, bass, drums]


def _vlq(n):
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


def to_midi(song: dict) -> bytes:
    """Standard MIDI file, format 1, 24 ticks per quarter (the MuML tick)."""
    p = song['prompt']
    beat = METERS[p['meter']]['beat']
    tempo = 60000000 * 24 // (p['bpm'] * beat)
    num, den = p['meter'].split('/')
    dpow = {'4': 2, '8': 3}[den]
    head = bytearray(b'\x00\xff\x51\x03' + tempo.to_bytes(3, 'big'))
    head += b'\x00\xff\x58\x04' + bytes([int(num), dpow, 24, 8])
    head += b'\x00\xff\x2f\x00'
    chunks = [head]
    for tr in song['tracks']:
        ch = tr['channel']
        name = tr['name'].encode('ascii')
        data = bytearray(b'\x00\xff\x03' + _vlq(len(name)) + name)
        if ch != 9:
            data += bytes([0, 0xC0 | ch, PROGRAMS[tr['name']]])
        ev = []
        for s, d, n, v in tr['notes']:
            ev.append((s + d, 0, n, 0x80 | ch, 0))
            ev.append((s, 1, n, 0x90 | ch, v))
        ev.sort()
        last = 0
        for t, _, n, st, v in ev:
            data += _vlq(t - last) + bytes([st, n, v])
            last = t
        data += b'\x00\xff\x2f\x00'
        chunks.append(data)
    out = bytearray(b'MThd' + struct.pack('>IHHH', 6, 1, len(chunks), 24))
    for c in chunks:
        out += b'MTrk' + struct.pack('>I', len(c)) + c
    return bytes(out)
