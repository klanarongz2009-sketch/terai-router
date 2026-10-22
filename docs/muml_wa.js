/* MuML 1.0 WA (MuML 1.0 Web Audio API) for the TER-AI web demo.
 * Note writer: seeded Markov chain over the MuML 1.0 training data (same table and same output as the
 * Python reference terai_router.muml_wa; tests/test_muml_wa_js_parity.py checks tokens, notes and .mid bytes).
 * Sound: Web Audio API only (oscillators, biquad filters, WaveShaper distortion, noise buffers, ADSR).
 * No soundfont, no server, no cloud API. Works in browsers and (generation / .mid only) in Node.
 */
(function (root) {
  'use strict';
  const VERSION = '1.0', NOTE_WRITER = 'markov-v1';
  let TABLE = null;
  const METERS = { '4/4': { bar: 96, beat: 24, type: 'reel' }, '6/8': { bar: 72, beat: 36, type: 'jig' }, '3/4': { bar: 72, beat: 24, type: 'waltz' } };
  const STYLES = ['folk', 'rock'];
  const CHORD_IV = { maj: [0, 4, 7], min: [0, 3, 7], '7': [0, 4, 7, 10], dim: [0, 3, 6] };
  const SCALE = { major: [0, 2, 4, 5, 7, 9, 11], minor: [0, 2, 3, 5, 7, 8, 10] };
  const MEL_MIN = -5, MEL_MAX = 19;
  const NOTE_PC = { c: 0, d: 2, e: 4, f: 5, g: 7, a: 9, b: 11 };
  const MOODS = [
    ['sad', ['เศร้า', 'เหงา', 'sad', 'melanchol', 'lonely'], 'minor', -20],
    ['dark', ['มืด', 'ดาร์ก', 'dark', 'scary', 'น่ากลัว'], 'minor', -5],
    ['calm', ['ผ่อนคลาย', 'สงบ', 'ชิล', 'calm', 'chill', 'relax', 'gentle', 'นุ่ม'], null, -25],
    ['energetic', ['มันส์', 'มัน ๆ', 'เร้าใจ', 'ดุ', 'energetic', 'epic', 'fast', 'เร็ว', 'hype'], null, 20],
    ['happy', ['สนุก', 'ร่าเริง', 'สดใส', 'มีความสุข', 'happy', 'joy', 'cheer', 'bright', 'fun'], 'major', 10],
  ];
  const PROGRAMS = { lead_folk: 40, chords_folk: 24, bass_folk: 32, lead_rock: 30, power_rock: 29, bass_rock: 33, drums: 0 };

  function setTable(t) { TABLE = t; }

  function Rng(seed) { this.a = seed >>> 0; }
  Rng.prototype.u32 = function () {
    this.a = (this.a + 0x6D2B79F5) >>> 0;
    let t = this.a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return (t ^ (t >>> 14)) >>> 0;
  };
  Rng.prototype.pick = function (options) {
    let total = 0;
    for (const o of options) total += o[1];
    let r = this.u32() % total;
    for (const o of options) { if (r < o[1]) return o[0]; r -= o[1]; }
    return options[options.length - 1][0];
  };

  const has = (t, words) => words.some(w => t.includes(w));

  function parsePrompt(text, style) {
    const t = String(text || '').toLowerCase();
    const explicit = [];
    if (!STYLES.includes(style)) {
      if (has(t, ['rock', 'ร็อก', 'ร็อค', 'ร๊อค', 'ร๊อก', 'metal', 'เมทัล'])) { style = 'rock'; explicit.push('style'); }
      else if (has(t, ['folk', 'โฟล์ค', 'โฟล์ก', 'jig', 'reel', 'irish', 'ไอริช', 'จิ๊ก', 'รีล'])) { style = 'folk'; explicit.push('style'); }
      else style = 'folk';
    }
    let meter;
    if (has(t, ['6/8', 'jig', 'จิ๊ก'])) { meter = '6/8'; explicit.push('meter'); }
    else if (has(t, ['3/4', 'waltz', 'วอลทซ์', 'วอลซ์', 'วอลตซ์'])) { meter = '3/4'; explicit.push('meter'); }
    else if (has(t, ['4/4', 'reel', 'รีล'])) { meter = '4/4'; explicit.push('meter'); }
    else meter = style === 'folk' ? '6/8' : '4/4';
    let mood = 'neutral', moodMode = null, delta = 0;
    for (const [name, words, mm, d] of MOODS) {
      if (has(t, words)) { mood = name; moodMode = mm; delta = d; explicit.push('mood'); break; }
    }
    let tonic = null, mode = null;
    let m = /(?:key|คีย์|คีย์)[ ]*(?:of[ ]*)?([a-g])(#|b(?![a-z])|sharp|flat|ชาร์ป|แฟลต)?[ ]*(minor|major|maj|m(?![a-z])|ไมเนอร์|เมเจอร์)?/.exec(t);
    if (!m) m = /(?:^|[^a-z])([a-g])(#|b|sharp|flat)?[ ]*(minor|major|ไมเนอร์|เมเจอร์)(?![a-z])/.exec(t);
    if (m) {
      tonic = NOTE_PC[m[1]];
      const acc = m[2] || '';
      if (acc === '#' || acc === 'sharp' || acc === 'ชาร์ป') tonic = (tonic + 1) % 12;
      else if (acc === 'b' || acc === 'flat' || acc === 'แฟลต') tonic = (tonic + 11) % 12;
      const q = m[3] || '';
      if (q === 'minor' || q === 'm' || q === 'ไมเนอร์') mode = 'minor';
      else if (q === 'major' || q === 'maj' || q === 'เมเจอร์') mode = 'major';
      explicit.push('key');
    }
    if (mode === null) {
      if (has(t, ['ไมเนอร์', 'minor'])) mode = 'minor';
      else if (has(t, ['เมเจอร์', 'major'])) mode = 'major';
      else mode = moodMode || 'major';
    }
    if (tonic === null) tonic = style === 'rock' ? (mode === 'minor' ? 4 : 9) : (mode === 'minor' ? 9 : 2);
    let bpm;
    m = /([0-9]{2,3})[ ]*(?:bpm|บีพีเอ็ม)/.exec(t);
    if (m) { bpm = parseInt(m[1], 10); explicit.push('bpm'); }
    else {
      const base = { 'folk|6/8': 100, 'folk|4/4': 110, 'folk|3/4': 120, 'rock|6/8': 100, 'rock|4/4': 120, 'rock|3/4': 120 }[style + '|' + meter];
      bpm = base + delta;
    }
    bpm = Math.max(50, Math.min(200, bpm));
    let seconds = 30;
    m = /([0-9]+)[ ]*(?:นาที|minutes?|mins?(?![a-z]))/.exec(t);
    if (m) { seconds = parseInt(m[1], 10) * 60; explicit.push('length'); }
    m = /([0-9]+)[ ]*(?:วินาที|วิ|seconds?|secs?(?![a-z])|s(?![a-z]))/.exec(t);
    if (m) {
      seconds = (explicit.includes('length') ? seconds : 0) + parseInt(m[1], 10);
      if (!explicit.includes('length')) explicit.push('length');
    }
    seconds = Math.max(8, Math.min(180, seconds));
    return { style, meter, mood, mode, tonic, bpm, seconds, explicit };
  }

  function lookup(list, key) {
    const k = Array.isArray(key) ? key.join(',') : key;
    for (const [a, v] of list) if ((Array.isArray(a) ? a.join(',') : a) === k) return v;
    return null;
  }
  const mod12 = x => ((x % 12) + 12) % 12;

  function Writer(p, rng) {
    this.p = p; this.rng = rng; this.mode = p.mode;
    this.o1 = TABLE.o1[this.mode]; this.o2 = TABLE.o2[this.mode]; this.hist = [];
  }
  Writer.prototype.candidates = function () {
    const h = this.hist, levels = [];
    if (h.length >= 2) levels.push(lookup(this.o2, [h[h.length - 2], h[h.length - 1]]));
    if (h.length >= 1) levels.push(lookup(this.o1, h[h.length - 1])); else levels.push(TABLE.start[this.mode]);
    for (const opts of levels) {
      if (opts) { const ok = opts.filter(o => o[0] >= MEL_MIN && o[0] <= MEL_MAX); if (ok.length) return ok; }
    }
    const last = h.length ? h[h.length - 1] : 0, sc = SCALE[this.mode];
    const ok = [last - 2, last - 1, last + 1, last + 2].filter(v => v >= MEL_MIN && v <= MEL_MAX && sc.includes(mod12(v))).map(v => [v, 1]);
    return ok.length ? ok : [[0, 1]];
  };
  Writer.prototype.chord = function (prev) { return this.rng.pick(lookup(TABLE.chords[this.mode], prev) || [[prev, 1]]); };
  Writer.prototype.part = function (sampledStart) {
    const tonicChord = this.mode === 'major' ? '0:maj' : '0:min';
    const bars = [], rhythms = TABLE.rhythms[this.p.meter];
    let prev = tonicChord;
    for (let b = 0; b < 8; b++) {
      let ch;
      if (b === 0) ch = sampledStart ? this.chord(prev) : tonicChord;
      else if (b === 6) ch = '7:maj';
      else if (b === 7) ch = tonicChord;
      else ch = this.chord(prev);
      prev = ch;
      const [root, q] = ch.split(':');
      const pcs = CHORD_IV[q].map(iv => (parseInt(root, 10) + iv) % 12);
      const pattern = this.rng.pick(rhythms.map((r, i) => [i, r[1]]));
      const durs = rhythms[pattern][0], notes = [];
      for (let i = 0; i < durs.length; i++) {
        let rel;
        if (b === 7 && i === durs.length - 1) {
          const last = this.hist.length ? this.hist[this.hist.length - 1] : 0;
          rel = Math.abs(last) <= Math.abs(last - 12) ? 0 : 12;
        } else {
          let opts = this.candidates();
          if (i === 0) opts = opts.map(o => [o[0], pcs.includes(mod12(o[0])) ? o[1] * 4 : o[1]]);
          rel = this.rng.pick(opts);
        }
        this.hist.push(rel);
        notes.push([rel, durs[i]]);
      }
      bars.push([ch, notes]);
    }
    return bars;
  };

  function formBlocks(p) {
    const m = METERS[p.meter], bpb = m.bar / m.beat;
    const num = p.seconds * p.bpm, den = 60 * bpb;
    const bars = Math.floor((num + den - 1) / den);
    const n8 = Math.max(1, Math.floor((bars + 4) / 8));
    if (n8 <= 2) return 'AB'.slice(0, n8).split('');  // short songs still get both parts
    const out = [];
    for (let i = 0; i < n8; i++) out.push('AABB'[i % 4]);
    return out;
  }
  const tonicRef = t => 60 + (t <= 6 ? t : t - 12);
  const fit = (pc, lo) => lo + mod12(pc - lo);

  function generate(prompt, seed, style) {
    if (!TABLE) throw new Error('MuML WA: call setTable(markov.json) first');
    seed = (seed || 0) >>> 0;
    const p = parsePrompt(prompt, style || 'auto');
    const rng = new Rng(seed), w = new Writer(p, rng);
    const parts = { A: w.part(false) };
    parts.B = w.part(true);
    const ref = tonicRef(p.tonic), tonic = p.tonic, met = METERS[p.meter];
    const toks = ['BOS', 'M:' + p.meter, 'T:' + met.type, 'MODE:' + p.mode, 'KEY:' + tonic];
    const melody = [], harmony = [];
    let tick = 0;
    const blocks = formBlocks(p);
    for (const blk of blocks) {
      for (const [ch, notes] of parts[blk]) {
        const [root, q] = ch.split(':'), r = (parseInt(root, 10) + tonic) % 12;
        toks.push('CH:' + r + ':' + q);
        harmony.push([tick, met.bar, r, q]);
        for (const [rel, d] of notes) { toks.push('P:' + (ref + rel), 'D:' + d); melody.push([tick, d, ref + rel]); tick += d; }
        toks.push('|');
      }
    }
    toks.push('EOS');
    return { version: VERSION, note_writer: NOTE_WRITER, seed, prompt: p, form: blocks.join(''), tokens: toks, total_ticks: tick, tracks: arrange(p, melody, harmony, tick) };
  }

  function arrange(p, melody, harmony, total) {
    const met = METERS[p.meter], beat = met.beat, half = beat / 2;
    if (p.style === 'folk') {
      const lead = { name: 'lead_folk', channel: 0, notes: melody.map(([s, d, n]) => [s, d, n, 96]) };
      const chords = { name: 'chords_folk', channel: 1, notes: [] }, bass = { name: 'bass_folk', channel: 2, notes: [] };
      for (const [s, d, root, q] of harmony) {
        const nb = Math.floor(d / beat);
        for (let k = 0; k < nb; k++) {
          const t0 = s + k * beat, pc = k % 2 === 0 ? root : (root + 7) % 12;
          bass.notes.push([t0, half, fit(pc, 40), 84]);
          for (const iv of CHORD_IV[q].slice(0, 3)) chords.notes.push([t0 + half, half, fit((root + iv) % 12, 55), 60]);
        }
      }
      return [lead, chords, bass];
    }
    const lead = { name: 'lead_rock', channel: 0, notes: melody.map(([s, d, n]) => [s, d, n, 105]) };
    const power = { name: 'power_rock', channel: 1, notes: [] }, bass = { name: 'bass_rock', channel: 2, notes: [] }, drums = { name: 'drums', channel: 9, notes: [] };
    for (const [s, d, root] of harmony) {
      const r = fit(root, 40);
      for (let t0 = s; t0 < s + d; t0 += 12) {
        for (const pitch of [r, r + 7, r + 12]) power.notes.push([t0, 11, pitch, 88]);
        bass.notes.push([t0, 11, r - 12, 100]);
      }
    }
    const step = p.meter === '6/8' ? 6 : 8;
    const kicks = step === 6 ? [0, 4] : [0, 4, 5], snares = step === 6 ? [3] : [2, 6];
    for (let i = 0, t0 = 0; t0 < total; i++, t0 += 12) {
      const pos = i % step;
      drums.notes.push([t0, 6, 42, 70]);
      if (kicks.includes(pos)) drums.notes.push([t0, 12, 36, 110]);
      if (snares.includes(pos)) drums.notes.push([t0, 12, 38, 115]);
      if (i % 64 === 0) drums.notes.push([t0, 48, 49, 110]);
    }
    return [lead, power, bass, drums];
  }

  // ------------------------------------------------------------------ .mid (format 1, 24 ticks per quarter)
  function vlq(n) { const out = [n & 0x7F]; n >>>= 7; while (n) { out.push((n & 0x7F) | 0x80); n >>>= 7; } return out.reverse(); }
  function u32be(n) { return [(n >>> 24) & 255, (n >>> 16) & 255, (n >>> 8) & 255, n & 255]; }
  function cmp(a, b) { for (let i = 0; i < a.length; i++) { if (a[i] !== b[i]) return a[i] < b[i] ? -1 : 1; } return 0; }
  function toMidi(song) {
    const p = song.prompt, beat = METERS[p.meter].beat;
    const tempo = Math.floor(60000000 * 24 / (p.bpm * beat));
    const [num, den] = p.meter.split('/');
    const head = [0, 0xFF, 0x51, 3, (tempo >> 16) & 255, (tempo >> 8) & 255, tempo & 255,
      0, 0xFF, 0x58, 4, parseInt(num, 10), den === '4' ? 2 : 3, 24, 8, 0, 0xFF, 0x2F, 0];
    const chunks = [head];
    for (const tr of song.tracks) {
      const ch = tr.channel, name = Array.from(tr.name, c => c.charCodeAt(0));
      const data = [0, 0xFF, 0x03, ...vlq(name.length), ...name];
      if (ch !== 9) data.push(0, 0xC0 | ch, PROGRAMS[tr.name]);
      const ev = [];
      for (const [s, d, n, v] of tr.notes) { ev.push([s + d, 0, n, 0x80 | ch, 0]); ev.push([s, 1, n, 0x90 | ch, v]); }
      ev.sort(cmp);
      let last = 0;
      for (const [t, , n, st, v] of ev) { data.push(...vlq(t - last), st, n, v); last = t; }
      data.push(0, 0xFF, 0x2F, 0);
      chunks.push(data);
    }
    const out = [0x4D, 0x54, 0x68, 0x64, 0, 0, 0, 6, 0, 1, (chunks.length >> 8) & 255, chunks.length & 255, 0, 24];
    for (const c of chunks) { out.push(0x4D, 0x54, 0x72, 0x6B, ...u32be(c.length)); for (const b of c) out.push(b); }
    return new Uint8Array(out);
  }

  // ------------------------------------------------------------------ Web Audio synthesis
  const hz = n => 440 * Math.pow(2, (n - 69) / 12);
  function distCurve(k) {
    const n = 2048, c = new Float32Array(n);
    for (let i = 0; i < n; i++) { const x = i * 2 / n - 1; c[i] = Math.tanh(k * x) / Math.tanh(k); }
    return c;
  }
  function noiseBuffer(ctx) {
    const len = Math.floor(ctx.sampleRate * 1.0), b = ctx.createBuffer(1, len, ctx.sampleRate), d = b.getChannelData(0);
    const rng = new Rng(12345);
    for (let i = 0; i < len; i++) d[i] = rng.u32() / 2147483648 - 1;
    return b;
  }
  // ADSR on a GainNode: attack a, decay d to sustain level s, release r after the note ends
  function adsr(g, t0, dur, peak, a, d, s, r) {
    const p = g.gain;
    p.setValueAtTime(0, t0);
    p.linearRampToValueAtTime(peak, t0 + a);
    p.setTargetAtTime(peak * s, t0 + a, d / 3);
    const end = t0 + Math.max(dur, a + 0.005);
    p.setValueAtTime(peak * s, end);
    p.setTargetAtTime(0, end, r / 3);
    return end + r * 1.5;
  }

  function Synth(ctx, dest) {
    this.ctx = ctx;
    this.noise = noiseBuffer(ctx);
    this.dist = distCurve(30);
    this.busses = {};
    const comp = ctx.createDynamicsCompressor();
    comp.threshold.value = -14; comp.knee.value = 8; comp.ratio.value = 4; comp.attack.value = 0.005; comp.release.value = 0.15;
    const master = ctx.createGain(); master.gain.value = 0.6;
    comp.connect(master); master.connect(dest || ctx.destination);
    this.input = comp; this.master = master;
  }
  Synth.prototype.bus = function (name) {
    if (this.busses[name]) return this.busses[name];
    const ctx = this.ctx;
    let first, last;
    if (name === 'lead_rock' || name === 'power_rock') {
      const pre = ctx.createGain(); pre.gain.value = name === 'lead_rock' ? 2.5 : 2.0;
      const ws = ctx.createWaveShaper(); ws.curve = this.dist; ws.oversample = '4x';
      const lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = name === 'lead_rock' ? 3800 : 2400; lp.Q.value = 0.8;
      const hp = ctx.createBiquadFilter(); hp.type = 'highpass'; hp.frequency.value = 90;
      const out = ctx.createGain(); out.gain.value = name === 'lead_rock' ? 0.16 : 0.08;
      pre.connect(ws); ws.connect(hp); hp.connect(lp); lp.connect(out);
      first = pre; last = out;
    } else {
      first = last = ctx.createGain();
      first.gain.value = { lead_folk: 1.8, chords_folk: 1.0, bass_folk: 1.6, bass_rock: 0.9, drums: 1.0 }[name] || 0.8;
    }
    last.connect(this.input);
    this.busses[name] = first;
    return first;
  };
  Synth.prototype.osc = function (type, f, t0, stop, dest, detune) {
    const o = this.ctx.createOscillator(); o.type = type; o.frequency.setValueAtTime(f, t0);
    if (detune) o.detune.value = detune;
    o.connect(dest); o.start(t0); o.stop(stop);
    return o;
  };
  Synth.prototype.note = function (name, t0, dur, n, v) {
    const ctx = this.ctx, bus = this.bus(name), vel = v / 127;
    if (name === 'drums') return this.drum(t0, n, vel, bus);
    const g = ctx.createGain(); g.connect(bus);
    if (name === 'lead_folk') {          // fiddle-like: two detuned saws, lowpass, delayed vibrato
      const lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 2600; lp.Q.value = 1.2; lp.connect(g);
      const stop = adsr(g, t0, dur * 0.95, 0.11 * vel, 0.03, 0.12, 0.75, 0.09);
      const o1 = this.osc('sawtooth', hz(n), t0, stop, lp, -4), o2 = this.osc('sawtooth', hz(n), t0, stop, lp, 5);
      const lfo = ctx.createOscillator(), lg = ctx.createGain(); lfo.frequency.value = 5.6;
      lg.gain.setValueAtTime(0, t0); lg.gain.linearRampToValueAtTime(hz(n) * 0.006, t0 + Math.min(0.25, dur));
      lfo.connect(lg); lg.connect(o1.frequency); lg.connect(o2.frequency); lfo.start(t0); lfo.stop(stop);
    } else if (name === 'chords_folk') { // plucked guitar-ish: triangle + square through a closing lowpass
      const lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.setValueAtTime(3000, t0); lp.frequency.exponentialRampToValueAtTime(700, t0 + 0.25); lp.connect(g);
      const stop = adsr(g, t0, dur, 0.06 * vel, 0.004, 0.18, 0.3, 0.12);
      this.osc('triangle', hz(n), t0, stop, lp); this.osc('square', hz(n), t0, stop, lp, 3);
    } else if (name === 'bass_folk') {
      const stop = adsr(g, t0, dur, 0.22 * vel, 0.006, 0.2, 0.5, 0.08);
      this.osc('triangle', hz(n), t0, stop, g);
    } else if (name === 'lead_rock') {   // distortion guitar: two saws into the WaveShaper bus
      const stop = adsr(g, t0, dur * 0.97, 0.5 * vel, 0.008, 0.25, 0.8, 0.12);
      this.osc('sawtooth', hz(n), t0, stop, g, -7); this.osc('square', hz(n), t0, stop, g, 7);
    } else if (name === 'power_rock') {  // palm-muted power chord eighths
      const stop = adsr(g, t0, dur * 0.85, 0.35 * vel, 0.003, 0.08, 0.45, 0.04);
      this.osc('sawtooth', hz(n), t0, stop, g, -5); this.osc('sawtooth', hz(n), t0, stop, g, 5);
    } else if (name === 'bass_rock') {
      const lp = ctx.createBiquadFilter(); lp.type = 'lowpass'; lp.frequency.value = 700; lp.Q.value = 2; lp.connect(g);
      const stop = adsr(g, t0, dur * 0.9, 0.3 * vel, 0.004, 0.1, 0.7, 0.05);
      this.osc('square', hz(n), t0, stop, lp); this.osc('sine', hz(n), t0, stop, g);
    }
  };
  Synth.prototype.noiseHit = function (t0, len, type, f, q, peak, dest) {
    const ctx = this.ctx, src = ctx.createBufferSource(); src.buffer = this.noise;
    const flt = ctx.createBiquadFilter(); flt.type = type; flt.frequency.value = f; flt.Q.value = q;
    const g = ctx.createGain(); g.gain.setValueAtTime(peak, t0); g.gain.exponentialRampToValueAtTime(0.0008, t0 + len);
    src.connect(flt); flt.connect(g); g.connect(dest);
    src.start(t0, (t0 * 7.3) % 0.5); src.stop(t0 + len + 0.02);
  };
  Synth.prototype.drum = function (t0, n, vel, bus) {
    const ctx = this.ctx;
    if (n === 36) {                      // kick: sine with a fast pitch drop
      const g = ctx.createGain(), o = ctx.createOscillator(); o.type = 'sine';
      o.frequency.setValueAtTime(150, t0); o.frequency.exponentialRampToValueAtTime(45, t0 + 0.12);
      g.gain.setValueAtTime(0.9 * vel, t0); g.gain.exponentialRampToValueAtTime(0.001, t0 + 0.35);
      o.connect(g); g.connect(bus); o.start(t0); o.stop(t0 + 0.4);
    } else if (n === 38) {               // snare: band of noise + short tone
      this.noiseHit(t0, 0.2, 'highpass', 1200, 0.7, 0.45 * vel, bus);
      const g = ctx.createGain(), o = ctx.createOscillator(); o.type = 'triangle'; o.frequency.setValueAtTime(190, t0);
      g.gain.setValueAtTime(0.3 * vel, t0); g.gain.exponentialRampToValueAtTime(0.001, t0 + 0.1);
      o.connect(g); g.connect(bus); o.start(t0); o.stop(t0 + 0.12);
    } else if (n === 42) {               // closed hi-hat
      this.noiseHit(t0, 0.05, 'highpass', 7500, 0.8, 0.16 * vel, bus);
    } else if (n === 49) {               // crash
      this.noiseHit(t0, 1.4, 'highpass', 5000, 0.5, 0.22 * vel, bus);
    }
  };

  function secondsPerTick(song) { return 60 / (song.prompt.bpm * METERS[song.prompt.meter].beat); }
  function songSeconds(song) { return song.total_ticks * secondsPerTick(song) + 1.6; }
  function schedule(ctx, song, t0, dest) {
    const synth = new Synth(ctx, dest), spt = secondsPerTick(song);
    let count = 0;
    for (const tr of song.tracks) for (const [s, d, n, v] of tr.notes) { synth.note(tr.name, t0 + s * spt, d * spt, n, v); count++; }
    return { synth, notes: count, seconds: songSeconds(song) };
  }

  let live = null;
  function play(song) {
    stop();
    const AC = root.AudioContext || root.webkitAudioContext;
    const ctx = new AC();
    const r = schedule(ctx, song, ctx.currentTime + 0.12);
    live = { ctx, timer: setTimeout(stop, r.seconds * 1000 + 300) };
    return r;
  }
  function stop() {
    if (!live) return;
    clearTimeout(live.timer);
    try { live.ctx.close(); } catch (e) { /* already closed */ }
    live = null;
  }
  function isPlaying() { return !!live; }

  async function renderBuffer(song, sampleRate) {
    const sr = sampleRate || 44100, secs = songSeconds(song);
    const ctx = new (root.OfflineAudioContext || root.webkitOfflineAudioContext)(2, Math.ceil(sr * secs), sr);
    schedule(ctx, song, 0.05);
    return ctx.startRendering();
  }
  function wavBytes(buf) {
    const ch = buf.numberOfChannels, len = buf.length, sr = buf.sampleRate;
    const out = new DataView(new ArrayBuffer(44 + len * ch * 2));
    const w = (o, s) => { for (let i = 0; i < s.length; i++) out.setUint8(o + i, s.charCodeAt(i)); };
    w(0, 'RIFF'); out.setUint32(4, 36 + len * ch * 2, true); w(8, 'WAVE'); w(12, 'fmt ');
    out.setUint32(16, 16, true); out.setUint16(20, 1, true); out.setUint16(22, ch, true); out.setUint32(24, sr, true);
    out.setUint32(28, sr * ch * 2, true); out.setUint16(32, ch * 2, true); out.setUint16(34, 16, true); w(36, 'data'); out.setUint32(40, len * ch * 2, true);
    const data = []; for (let c = 0; c < ch; c++) data.push(buf.getChannelData(c));
    let o = 44;
    for (let i = 0; i < len; i++) for (let c = 0; c < ch; c++) { const s = Math.max(-1, Math.min(1, data[c][i])); out.setInt16(o, s < 0 ? s * 32768 : s * 32767, true); o += 2; }
    return new Uint8Array(out.buffer);
  }
  async function renderWav(song, sampleRate) { return wavBytes(await renderBuffer(song, sampleRate)); }

  const api = { VERSION, NOTE_WRITER, METERS, arrange, setTable, Rng, parsePrompt, generate, toMidi, play, stop, isPlaying, renderBuffer, renderWav, wavBytes, songSeconds, schedule };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.MUMLWA = api;
})(typeof window !== 'undefined' ? window : globalThis);
