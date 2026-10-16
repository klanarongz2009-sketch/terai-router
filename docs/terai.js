/* TER-AI v0.7 inference in JavaScript. Same steps and integer arithmetic as src/terai_router/*.py.
   Browser: TERAI.create(modelJson, typoJson) ; Node: require('./terai.js').create(...) */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.TERAI = factory();
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  function startsAt(s, sub, i) { return i >= 0 && s.startsWith(sub, i); }

  function replaceGuarded(text, typed, intended) {
    const offs = [];
    for (let k = 0; k <= intended.length - typed.length; k++) if (intended.startsWith(typed, k)) offs.push(k);
    let out = '', i = 0, n = 0;
    for (;;) {
      const j = text.indexOf(typed, i);
      if (j < 0) { out += text.slice(i); break; }
      if (offs.some(k => startsAt(text, intended, j - k))) out += text.slice(i, j + typed.length);
      else { out += text.slice(i, j) + intended; n++; }
      i = j + typed.length;
    }
    return [out, n];
  }

  const DROP = new Set(['\u0E48', '\u0E49', '\u0E4A', '\u0E4B', '\u0E4C', '\u0E47', '\u0E3A', '\u0E4D']);
  const FOLD = { 'ภ': 'พ', 'ผ': 'พ', 'ฝ': 'ฟ', 'ฐ': 'ท', 'ถ': 'ท', 'ฑ': 'ท', 'ฒ': 'ท', 'ธ': 'ท', 'ณ': 'น', 'ญ': 'ย', 'ข': 'ค', 'ฆ': 'ค', 'ศ': 'ส',
    'ษ': 'ส', 'ซ': 'ส', 'ฎ': 'ด', 'ฏ': 'ต', 'ฬ': 'ล', 'ฮ': 'ห', 'ใ': 'ไ', 'ฌ': 'ช', 'ฉ': 'ช', 'ี': 'ิ', 'ู': 'ุ', 'ื': 'ึ' };

  function skeleton(text) {
    let t = '';
    for (const ch of text.toLowerCase()) { if (!DROP.has(ch)) t += (FOLD[ch] || ch); }
    t = t.replace(/ห(?=[งญนมยรลว])/g, '');
    return t.split('ทร').join('ส');
  }

  function fold(text) {
    return text.toLowerCase().replace(/[0-9\u0E50-\u0E59]+/g, '0').replace(/\s+/g, ' ').trim();
  }

  function create(model, typo) {
    let pairs = (typo.safe_pairs || []).map(p => [p[0], p[1]]).concat((typo.candidate_pairs || []).map(p => [p[0], p[1]]));
    pairs = pairs.map((p, i) => [p, i]).sort((a, b) => (b[0][0].length - a[0][0].length) || (a[1] - b[1])).map(x => x[0]);
    const ctx = (typo.ctx_rules || []).map(r => [new RegExp(r[0], 'g'), r[1].replace(/\\(\d)/g, '$$$1'), r[2]]);

    function normalize(text) {
      let out = text; const changes = [];
      for (const [re, rep, label] of ctx) { re.lastIndex = 0; const nw = out.replace(re, rep); if (nw !== out) { changes.push(label); out = nw; } }
      for (const [typed, intended] of pairs) {
        if (out.includes(typed)) { const [nw, n] = replaceGuarded(out, typed, intended); if (n) { changes.push(typed + '->' + intended); out = nw; } }
      }
      const nw = out.replace(/(.)\1{3,}/g, '$1');
      if (nw !== out) { changes.push('repeat-collapse'); out = nw; }
      return { text: out, changes };
    }

    const cfg = model.features;
    function features(text) {
      const t = fold(normalize(text).text);
      const out = [], seen = new Set();
      for (const [prefix, src] of [['c', t], ['k', skeleton(t)]]) {
        const [lo, hi] = cfg[prefix];
        const s = Array.from(' ' + src + ' ');
        for (let n = lo; n <= hi; n++) {
          for (let i = 0; i + n <= s.length; i++) {
            const g = s.slice(i, i + n).join('');
            if (!g.trim()) continue;
            const f = prefix + ':' + g;
            if (!seen.has(f)) { seen.add(f); out.push(f); }
          }
        }
      }
      return out;
    }

    const k = model.classes.length;
    const bin = (typeof atob === 'function') ? atob(model.weights_b64) : Buffer.from(model.weights_b64, 'base64').toString('binary');
    const w8 = new Int8Array(bin.length);
    for (let i = 0; i < bin.length; i++) { const b = bin.charCodeAt(i); w8[i] = b > 127 ? b - 256 : b; }
    const index = new Map();
    model.vocab.forEach((f, i) => index.set(f, i * k));

    function predict(text, top) {
      top = top || 3;
      const feats = features(text);
      const acc = new Array(k).fill(0);
      let known = 0;
      for (const f of feats) {
        const off = index.get(f);
        if (off === undefined) continue;
        known++;
        for (let j = 0; j < k; j++) acc[j] += w8[off + j];
      }
      const logits = acc.map((a, j) => model.bias[j] + model.scale * a);
      const m = Math.max.apply(null, logits);
      const ex = logits.map(x => Math.exp(x - m));
      const z = ex.reduce((a, b) => a + b, 0);
      const ranked = model.classes.map((c, j) => [c, ex[j] / z]).sort((a, b) => b[1] - a[1]);
      const nz = normalize(text);
      return { intent: ranked[0][0], confidence: ranked[0][1], coverage: known / Math.max(1, feats.length),
               normalized: nz.text, changes: nz.changes, ranking: ranked.slice(0, top) };
    }
    return { predict, normalize, features, skeleton, fold, meta: model.meta, classes: model.classes };
  }
  return { create };
}));
