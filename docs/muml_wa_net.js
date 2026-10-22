/* MuML 1.0 WA network note writer (MIT). Port of src/terai_router/muml_wa/net.py: same operations, same order.
 * The trained MuML 1.0 network (4-layer transformer, d_model 256, 4 heads, context 512, 163 tokens, 3,332,352
 * parameters, trained from scratch on the Nottingham Music Database) writes melody, chords and rhythm; muml_wa.js
 * arranges and plays them. Weights: muml-1.0-int8.bin (3,421,372 bytes, int8 per row, GPL-3.0 data, see
 * DATA_LICENSE), fetched once on first use. Needs muml_wa.js (MUMLWA) first.
 */
(function (root) {
  'use strict';
  const NOTE_WRITER = 'muml-1.0-net', MODEL_ID = 'MuML 1.0', WEIGHTS_NAME = 'muml-1.0-int8.bin';
  const TEMPERATURE = 0.9, TOP_P_PCT = 95, KEY_GUARD = 2.0, PPM = 1000000, MAX_SEGMENTS = 12;
  const SCALE = { major: [0, 2, 4, 5, 7, 9, 11], minor: [0, 2, 3, 5, 7, 8, 10] };
  const TYPE_OF = { '4/4': 'reel', '6/8': 'jig', '3/4': 'waltz' };
  let NET = null;

  function parse(buf) {
    const u8 = new Uint8Array(buf), dv = new DataView(buf);
    const magic = String.fromCharCode.apply(null, u8.subarray(0, 7));
    if (magic !== 'MUMLWA1') throw new Error('not a MuML WA weight file');
    const hl = dv.getUint32(8, true);
    const h = JSON.parse(new TextDecoder('utf-8').decode(u8.subarray(12, 12 + hl)));
    const base = 12 + hl, w = {};
    for (const t of h.tensors) {
      const n = t.shape.reduce((a, b) => a * b, 1), out = new Float64Array(n);
      if (t.q) {
        const q = new Int8Array(buf, base + t.q.offset, n), cols = t.shape[1];
        for (let r = 0; r < t.shape[0]; r++) {
          const s = dv.getFloat32(base + t.scale.offset + 4 * r, true);
          for (let c = 0; c < cols; c++) out[r * cols + c] = q[r * cols + c] * s;
        }
      } else {
        for (let i = 0; i < n; i++) out[i] = dv.getFloat32(base + t.data.offset + 4 * i, true);
      }
      w[t.name] = { a: out, shape: t.shape };
    }
    return { h, w, cfg: h.config, vocab: h.vocab, bytes: buf.byteLength };
  }

  function load(buf) { NET = parse(buf); return NET; }
  async function fetchWeights(url) {
    const r = await fetch(url || WEIGHTS_NAME);
    if (!r.ok) throw new Error('MuML 1.0 weights: HTTP ' + r.status);
    return load(await r.arrayBuffer());
  }
  function ready() { return !!NET; }

  function matvec(W, x, b) {
    const rows = W.shape[0], cols = W.shape[1], a = W.a, out = new Float64Array(rows);
    for (let r = 0; r < rows; r++) {
      let s = 0; const o = r * cols;
      for (let c = 0; c < cols; c++) s += a[o + c] * x[c];
      out[r] = b ? s + b.a[r] : s;
    }
    return out;
  }
  function erf(x) {
    const s = x >= 0 ? 1 : -1; x = Math.abs(x);
    const t = 1 / (1 + 0.3275911 * x);
    const y = 1 - (((((1.061405429 * t - 1.453152027) * t) + 1.421413741) * t - 0.284496736) * t + 0.254829592) * t * Math.exp(-x * x);
    return s * y;
  }

  function Runner(net) { this.net = net; this.w = net.w; this.cfg = net.cfg; this.reset(); }
  Runner.prototype.reset = function () {
    this.k = []; this.v = [];
    for (let i = 0; i < this.cfg.n_layer; i++) { this.k.push([]); this.v.push([]); }
    this.pos = 0;
  };
  Runner.prototype.ln = function (x, name) {
    const n = x.length, wt = this.w[name + '.weight'].a, bs = this.w[name + '.bias'].a, out = new Float64Array(n);
    let s = 0; for (let i = 0; i < n; i++) s += x[i];
    const mean = s / n; let v = 0;
    for (let i = 0; i < n; i++) { const d = x[i] - mean; v += d * d; }
    const sd = Math.sqrt(v / n + 1e-5);
    for (let i = 0; i < n; i++) out[i] = (x[i] - mean) / sd * wt[i] + bs[i];
    return out;
  };
  Runner.prototype.step = function (tid) {
    const w = this.w, cfg = this.cfg, d = cfg.d_model, nh = cfg.n_head, hd = d / nh, sq = Math.sqrt(hd);
    const tok = w['tok.weight'].a, pos = w['pos.weight'].a;
    let x = new Float64Array(d);
    for (let i = 0; i < d; i++) x[i] = tok[tid * d + i] + pos[this.pos * d + i];
    for (let li = 0; li < cfg.n_layer; li++) {
      const p = 'blocks.' + li + '.';
      const qkv = matvec(w[p + 'qkv.weight'], this.ln(x, p + 'ln1'), w[p + 'qkv.bias']);
      const q = qkv.subarray(0, d), K = this.k[li], V = this.v[li];
      K.push(qkv.slice(d, 2 * d)); V.push(qkv.slice(2 * d));
      const T = K.length, y = new Float64Array(d), sc = new Float64Array(T);
      for (let hh = 0; hh < nh; hh++) {
        const o = hh * hd; let m = -Infinity;
        for (let j = 0; j < T; j++) { let s = 0; const kj = K[j]; for (let c = 0; c < hd; c++) s += kj[o + c] * q[o + c]; sc[j] = s / sq; if (sc[j] > m) m = sc[j]; }
        let tot = 0;
        for (let j = 0; j < T; j++) { sc[j] = Math.exp(sc[j] - m); tot += sc[j]; }
        for (let j = 0; j < T; j++) { const pj = sc[j] / tot, vj = V[j]; for (let c = 0; c < hd; c++) y[o + c] += pj * vj[o + c]; }
      }
      const pr = matvec(w[p + 'proj.weight'], y, w[p + 'proj.bias']);
      for (let i = 0; i < d; i++) x[i] += pr[i];
      const a = matvec(w[p + 'mlp.0.weight'], this.ln(x, p + 'ln2'), w[p + 'mlp.0.bias']);
      for (let i = 0; i < a.length; i++) a[i] = 0.5 * a[i] * (1 + erf(a[i] / Math.SQRT2));
      const m2 = matvec(w[p + 'mlp.2.weight'], a, w[p + 'mlp.2.bias']);
      for (let i = 0; i < d; i++) x[i] += m2[i];
    }
    this.pos++;
    return matvec(w['tok.weight'], this.ln(x, 'ln'), null);
  };

  function Sampler(vocab, tonic, mode) {
    this.dur = []; this.body = []; this.note = new Set(); this.offKey = new Set();
    const cond = { M: 1, T: 1, MODE: 1, KEY: 1 }, sc = SCALE[mode];
    vocab.forEach((t, i) => {
      if (t.startsWith('D:')) this.dur.push(i);
      else if (t !== 'PAD' && t !== 'BOS' && !cond[t.split(':')[0]]) this.body.push(i);
      if (t.startsWith('P:') || t === 'R') this.note.add(i);
      if (t.startsWith('P:') && sc.indexOf((((parseInt(t.slice(2), 10) - tonic) % 12) + 12) % 12) < 0) this.offKey.add(i);
    });
  }
  Sampler.prototype.weights = function (logits, prev) {
    const allowed = this.note.has(prev) ? this.dur : this.body, z = [];
    for (const i of allowed) { let v = logits[i]; if (this.offKey.has(i)) v -= KEY_GUARD; z.push(v / TEMPERATURE); }
    let m = -Infinity; for (const v of z) if (v > m) m = v;
    const e = z.map(v => Math.exp(v - m));
    let s = 0; for (const v of e) s += v;
    const opts = [];
    allowed.forEach((id, k) => { const wt = Math.floor(e[k] / s * PPM + 0.5); if (wt > 0) opts.push([id, wt]); });
    opts.sort((a, b) => (b[1] - a[1]) || (a[0] - b[0]));
    let total = 0; for (const o of opts) total += o[1];
    const keep = []; let cum = 0;
    for (const o of opts) { if (100 * cum >= TOP_P_PCT * total) break; keep.push(o); cum += o[1]; }
    return keep;
  };

  function write(p, rng, net) {
    const M = root.MUMLWA, met = M.METERS[p.meter], vocab = net.vocab, stoi = {}, ctx = net.cfg.ctx;
    vocab.forEach((t, i) => { stoi[t] = i; });
    const bpb = met.bar / met.beat, target = Math.ceil((p.seconds * p.bpm) / (60 * bpb)) * met.bar;
    const tonic = p.tonic, mode = p.mode;
    const header = ['BOS', 'M:' + p.meter, 'T:' + TYPE_OF[p.meter], 'MODE:' + mode, 'KEY:' + tonic];
    const sampler = new Sampler(vocab, tonic, mode), runner = new Runner(net);
    const BARS = { '|': 1, '|:': 1, ':|': 1, '[1': 1, '[2': 1 };
    const toks = header.slice(), melody = [], harmony = [];
    let tick = 0, chord = [0, tonic, mode === 'major' ? 'maj' : 'min'], segments = 0, done = false;
    while (!done && segments < MAX_SEGMENTS) {
      segments++;
      runner.reset();
      let logits = null;
      for (const t of header) logits = runner.step(stoi[t]);
      let body = [], prev = stoi[header[header.length - 1]];
      while (runner.pos < ctx) {
        const nxt = rng.pick(sampler.weights(logits, prev));
        if (vocab[nxt] === 'EOS') break;
        body.push(vocab[nxt]); prev = nxt;
        logits = runner.step(nxt);
      }
      if (runner.pos >= ctx) {
        let last = -1; body.forEach((t, i) => { if (BARS[t]) last = i; });
        body = body.slice(0, last + 1);
      }
      let added = 0;
      for (let i = 0; i < body.length; i++) {
        const t = body[i];
        if (BARS[t]) { toks.push(t); if (tick >= target) { done = true; break; } }
        else if (t.startsWith('CH:')) {
          const sp = t.split(':');
          if (tick > chord[0]) harmony.push([chord[0], tick - chord[0], chord[1], chord[2]]);
          chord = [tick, parseInt(sp[1], 10), sp[2]];
          toks.push(t);
        } else if ((t.startsWith('P:') || t === 'R') && i + 1 < body.length && body[i + 1].startsWith('D:')) {
          const d = parseInt(body[i + 1].slice(2), 10);
          if (t !== 'R') { melody.push([tick, d, parseInt(t.slice(2), 10)]); added++; }
          toks.push(t, body[i + 1]); tick += d; i++;
        }
      }
      if (!added) break;
      if (!done && tick >= target) done = true;
      if (!done && !BARS[toks[toks.length - 1]]) toks.push('|');
    }
    if (tick > chord[0]) harmony.push([chord[0], tick - chord[0], chord[1], chord[2]]);
    toks.push('EOS');
    return { toks, melody, harmony, tick, segments };
  }

  function generate(prompt, seed, style, net) {
    net = net || NET;
    if (!net) throw new Error('MuML 1.0 weights not loaded: call MUMLWA_NET.fetchWeights() first');
    const M = root.MUMLWA;
    seed = (seed || 0) >>> 0;
    const p = M.parsePrompt(prompt, style || 'auto'), rng = new M.Rng(seed);
    const r = write(p, rng, net);
    return { version: M.VERSION, note_writer: NOTE_WRITER, model: MODEL_ID, seed, prompt: p, form: 'net x' + r.segments,
      tokens: r.toks, total_ticks: r.tick, tracks: M.arrange(p, r.melody, r.harmony, r.tick) };
  }

  const api = { NOTE_WRITER, MODEL_ID, WEIGHTS_NAME, load, fetchWeights, ready, generate, parse };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.MUMLWA_NET = api;
})(typeof window !== 'undefined' ? window : globalThis);
