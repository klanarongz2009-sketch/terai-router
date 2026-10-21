/* TER-AI v0.8 Chat in JavaScript: a line-by-line port of src/terai_router/chat.py, tools.py and knowledge.py.
   Same rules, same order, same strings, so for the same input, clock and seed it gives the same reply.
   Browser: new TERAI_CHAT.Chat({router, chitchat, knowledge, now, seed, state, onSave})
   Node:    const { Chat, Knowledge } = require('./chat.js')
   router = TERAI.create(model, typo) from terai.js. The knowledge pack can be attached later
   (Knowledge.setPack); replyAsync() loads it on demand through knowledge.loader. */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.TERAI_CHAT = factory();
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  const VERSION = '0.11.0';
  const STATE_VERSION = 1;
  const HISTORY_MAX = 200;

  // ------------------------------------------------------------ Python helpers
  const CACHE = new Map();
  function R(p, f) { f = f || ''; const k = f + '\u0000' + p; let r = CACHE.get(k); if (!r) { r = new RegExp(p, f); CACHE.set(k, r); } return r; }
  const search = (p, s, f) => R(p, f).exec(s);
  const sub = (p, rep, s) => s.replace(R(p, 'g'), rep);
  const findall = (p, s) => Array.from(s.matchAll(R(p, 'g')), m => m[0]);
  const finditer = (p, s) => Array.from(s.matchAll(R(p, 'g')));
  const rall = (s, a, b) => s.split(a).join(b);
  const cpLen = s => { let n = 0; for (const _ of s) n++; return n; };  // len() counts code points
  const cps = s => Array.from(s);
  function strip(s, chars) {
    if (chars === undefined) return s.trim();
    let a = 0, b = s.length;
    while (a < b && chars.includes(s[a])) a++;
    while (b > a && chars.includes(s[b - 1])) b--;
    return s.slice(a, b);
  }
  const pad2 = x => String(x).padStart(2, '0');
  const mod = (a, b) => ((a % b) + b) % b;
  const fdiv = (a, b) => Math.floor(a / b);
  const commas = n => String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ',');

  function pyRepr(x) {  // Python repr(float)
    if (x !== x) return 'nan';
    if (x === Infinity) return 'inf';
    if (x === -Infinity) return '-inf';
    if (x === 0) return Object.is(x, -0) ? '-0.0' : '0.0';
    let [mant, ex] = x.toExponential().split('e');
    const exp = parseInt(ex, 10);
    const neg = mant[0] === '-';
    if (neg) mant = mant.slice(1);
    const digits = mant.replace('.', '');
    let out;
    if (exp >= -4 && exp < 16) {
      if (exp >= 0) {
        const ip = digits.length > exp + 1 ? digits.slice(0, exp + 1) : digits + '0'.repeat(exp + 1 - digits.length);
        const fp = digits.length > exp + 1 ? digits.slice(exp + 1) : '0';
        out = ip + '.' + fp;
      } else out = '0.' + '0'.repeat(-exp - 1) + digits;
    } else {
      out = digits[0] + (digits.length > 1 ? '.' + digits.slice(1) : '') + 'e' + (exp < 0 ? '-' : '+') + String(Math.abs(exp)).padStart(2, '0');
    }
    return (neg ? '-' : '') + out;
  }

  // ------------------------------------------------------------ tools.py
  function fmtNum(x, places) {
    if (places === undefined) places = 6;
    if (x !== x || x === Infinity || x === -Infinity) return pyRepr(x);
    const p = Math.pow(10, places);
    let r = Math.floor(x * p + 0.5) / p;
    if (r === 0) r = 0;
    if (Number.isInteger(r) && Math.abs(r) < 1e15) return String(r);
    return pyRepr(r);
  }

  class CalcError extends Error {}
  const WORD_OPS = [['ยกกำลัง', '^'], ['คูณด้วย', '*'], ['หารด้วย', '/'], ['บวก', '+'], ['ลบ', '-'], ['คูณ', '*'], ['หาร', '/'],
    ['×', '*'], ['÷', '/'], ['plus', '+'], ['minus', '-'], ['times', '*'], ['divided by', '/']];
  const SQRT = /(?:รากที่สอง(?:ของ)?|สแควร์รูท|sqrt|√) ?\(?([0-9.]+)\)?/g;
  const PCT_OF = /([0-9.]+) ?(?:%|เปอร์เซ็นต์) ?(?:ของ|of) ?([0-9.]+)/g;

  function calcPrepare(text) {
    let t = rall(text.toLowerCase(), ',', '');
    t = t.replace(PCT_OF, (m0, a, b) => '(' + a + '/100*' + b + ')');
    t = t.replace(SQRT, (m0, a) => 's' + a);
    for (const [w, s] of WORD_OPS) t = rall(t, w, ' ' + s + ' ');
    t = t.replace(/ +/g, ' ');
    t = t.replace(/(?<=[0-9)]) ?x ?(?=[0-9(])/g, '*');
    let best = null;
    for (const m of t.matchAll(/[0-9.()+\-*/^ s]+/g)) {
      const span = m[0].trim();
      if (!/[0-9]/.test(span)) continue;
      if (!(/[0-9)] ?[+\-*/^] ?[-(s0-9]/.test(span) || span.includes('s'))) continue;
      if (best === null || span.length > best.length) best = span;
    }
    return best;
  }

  function tokens(expr) {
    const out = []; let i = 0;
    while (i < expr.length) {
      const c = expr[i];
      if (c === ' ') i++;
      else if ('0123456789.'.includes(c)) {
        let j = i;
        while (j < expr.length && '0123456789.'.includes(expr[j])) j++;
        const num = expr.slice(i, j);
        if (num.split('.').length - 1 > 1 || num === '.') throw new CalcError('bad number');
        out.push(Number(num));
        i = j;
      } else if ('+-*/^()s'.includes(c)) { out.push(c); i++; }
      else throw new CalcError('bad char');
    }
    return out;
  }

  function calcEval(expr) {
    const toks = tokens(expr);
    let pos = 0;
    const peek = () => (pos < toks.length ? toks[pos] : null);
    const take = () => toks[pos++];
    function atom() {
      const t = peek();
      if (t === null) throw new CalcError('incomplete');
      if (t === '-') { take(); return -atom(); }
      if (t === '+') { take(); return atom(); }
      if (t === 's') { take(); const v = atom(); if (v < 0) throw new CalcError('sqrt of negative'); return Math.sqrt(v); }
      if (t === '(') { take(); const v = add(); if (peek() !== ')') throw new CalcError('missing )'); take(); return v; }
      if (typeof t === 'number') { take(); return t; }
      throw new CalcError('unexpected ' + t);
    }
    function power() {
      const b = atom();
      if (peek() === '^') {
        take();
        const e = power();
        if (Number.isInteger(e) && Math.abs(e) <= 1024) {
          let r = 1.0; const k = Math.abs(e);
          for (let i = 0; i < k; i++) r *= b;
          if (e < 0) { if (r === 0) throw new CalcError('div0'); r = 1.0 / r; }
          return r;
        }
        throw new CalcError('non-integer power');
      }
      return b;
    }
    function mul() {
      let v = power();
      while (peek() === '*' || peek() === '/') {
        const op = take(); const r = power();
        if (op === '*') v *= r;
        else { if (r === 0) throw new CalcError('div0'); v /= r; }
      }
      return v;
    }
    function add() {
      let v = mul();
      while (peek() === '+' || peek() === '-') { const op = take(); const r = mul(); v = op === '+' ? v + r : v - r; }
      return v;
    }
    const v = add();
    if (pos !== toks.length) throw new CalcError('trailing');
    if (Math.abs(v) > 1e300) throw new CalcError('overflow');
    return v;
  }

  function prettyExpr(expr) {
    let e = rall(rall(rall(rall(rall(expr, 's', '√'), '*', ' × '), '/', ' ÷ '), '+', ' + '), '^', ' ^ ');
    e = e.replace(/(?<=[0-9)]) ?- ?/g, ' - ');
    return e.replace(/ +/g, ' ').trim();
  }

  const TH_DAYS = ['จันทร์', 'อังคาร', 'พุธ', 'พฤหัสบดี', 'ศุกร์', 'เสาร์', 'อาทิตย์'];
  const TH_MONTHS = ['มกราคม', 'กุมภาพันธ์', 'มีนาคม', 'เมษายน', 'พฤษภาคม', 'มิถุนายน', 'กรกฎาคม', 'สิงหาคม', 'กันยายน', 'ตุลาคม', 'พฤศจิกายน', 'ธันวาคม'];

  function daysFromCivil(y, m, d) {
    y -= (m <= 2) ? 1 : 0;
    const era = fdiv(y >= 0 ? y : y - 399, 400);
    const yoe = y - era * 400;
    const doy = fdiv(153 * (m + (m > 2 ? -3 : 9)) + 2, 5) + d - 1;
    const doe = yoe * 365 + fdiv(yoe, 4) - fdiv(yoe, 100) + doy;
    return era * 146097 + doe - 719468;
  }
  function civilFromDays(z) {
    z += 719468;
    const era = fdiv(z >= 0 ? z : z - 146096, 146097);
    const doe = z - era * 146097;
    const yoe = fdiv(doe - fdiv(doe, 1460) + fdiv(doe, 36524) - fdiv(doe, 146096), 365);
    const y = yoe + era * 400;
    const doy = doe - (365 * yoe + fdiv(yoe, 4) - fdiv(yoe, 100));
    const mp = fdiv(5 * doy + 2, 153);
    const d = doy - fdiv(153 * mp + 2, 5) + 1;
    const m = mp + (mp < 10 ? 3 : -9);
    return [y + (m <= 2 ? 1 : 0), m, d];
  }
  const weekday = z => mod(z + 3, 7);
  function thDate(z, withDay) {
    if (withDay === undefined) withDay = true;
    const [y, m, d] = civilFromDays(z);
    const s = d + ' ' + TH_MONTHS[m - 1] + ' ' + (y + 543);
    return withDay ? ('วัน' + TH_DAYS[weekday(z)] + 'ที่ ' + s) : s;
  }

  const UNITS = [
    [['กิโลเมตร', 'กม.', 'กม', 'km', 'kilometers', 'kilometer'], 'len', 1000.0, 'กิโลเมตร'],
    [['เซนติเมตร', 'ซม.', 'ซม', 'cm'], 'len', 0.01, 'เซนติเมตร'],
    [['มิลลิเมตร', 'มม.', 'mm'], 'len', 0.001, 'มิลลิเมตร'],
    [['เมตร', 'meters', 'meter', 'm'], 'len', 1.0, 'เมตร'],
    [['ไมล์', 'miles', 'mile', 'mi'], 'len', 1609.344, 'ไมล์'],
    [['นิ้ว', 'inches', 'inch', 'in'], 'len', 0.0254, 'นิ้ว'],
    [['ฟุต', 'feet', 'foot', 'ft'], 'len', 0.3048, 'ฟุต'],
    [['หลา', 'yards', 'yard', 'yd'], 'len', 0.9144, 'หลา'],
    [['กิโลกรัม', 'กก.', 'กก', 'กิโล', 'kg', 'kilograms', 'kilogram'], 'mass', 1000.0, 'กิโลกรัม'],
    [['กรัม', 'grams', 'gram', 'g'], 'mass', 1.0, 'กรัม'],
    [['ปอนด์', 'pounds', 'pound', 'lb', 'lbs'], 'mass', 453.59237, 'ปอนด์'],
    [['ออนซ์', 'ounces', 'ounce', 'oz'], 'mass', 28.349523125, 'ออนซ์'],
    [['ตัน', 'tonnes', 'tonne', 'tons', 'ton'], 'mass', 1000000.0, 'ตัน'],
    [['มิลลิลิตร', 'มล.', 'ml'], 'vol', 0.001, 'มิลลิลิตร'],
    [['ลิตร', 'liters', 'liter', 'litres', 'litre', 'l'], 'vol', 1.0, 'ลิตร'],
    [['แกลลอน', 'gallons', 'gallon', 'gal'], 'vol', 3.785411784, 'แกลลอน'],
    [['วินาที', 'seconds', 'second', 'sec', 's'], 'time', 1.0, 'วินาที'],
    [['นาที', 'minutes', 'minute', 'min'], 'time', 60.0, 'นาที'],
    [['ชั่วโมง', 'ชม.', 'hours', 'hour', 'hr', 'h'], 'time', 3600.0, 'ชั่วโมง'],
    [['สัปดาห์', 'อาทิตย์', 'weeks', 'week'], 'time', 604800.0, 'สัปดาห์'],
    [['วัน', 'days', 'day'], 'time', 86400.0, 'วัน'],
    [['องศาเซลเซียส', 'เซลเซียส', 'องศาซี', 'celsius', '°c'], 'temp', 'C', 'องศาเซลเซียส'],
    [['องศาฟาเรนไฮต์', 'ฟาเรนไฮต์', 'fahrenheit', '°f'], 'temp', 'F', 'องศาฟาเรนไฮต์'],
    [['เคลวิน', 'kelvin'], 'temp', 'K', 'เคลวิน'],
  ];
  const ALIASES = [];
  UNITS.forEach((u, i) => u[0].forEach(a => ALIASES.push([a, i])));
  ALIASES.sort((p, q) => cpLen(q[0]) - cpLen(p[0]));
  const isAsciiAlpha = c => /^[A-Za-z]$/.test(c);

  function findUnits(t) {
    const taken = new Array(t.length).fill(false);
    const found = [];
    for (const [alias, idx] of ALIASES) {
      let start = 0;
      for (;;) {
        const j = t.indexOf(alias, start);
        if (j < 0) break;
        const end = j + alias.length;
        let ok = !taken.slice(j, end).some(Boolean);
        if (ok && /[a-z°]/.test(alias[0])) {
          const before = j > 0 ? t[j - 1] : ' ';
          const after = end < t.length ? t[end] : ' ';
          ok = !isAsciiAlpha(before) && !isAsciiAlpha(after);
        }
        if (ok) { for (let k = j; k < end; k++) taken[k] = true; found.push([j, end, idx]); }
        start = end;
      }
    }
    return found.sort((a, b) => (a[0] - b[0]) || (a[1] - b[1]) || (a[2] - b[2]));
  }
  function toBase(v, u) {
    const dim = UNITS[u][1], f = UNITS[u][2];
    if (dim !== 'temp') return v * f;
    if (f === 'C') return v;
    if (f === 'F') return (v - 32) * 5 / 9;
    return v - 273.15;
  }
  function fromBase(v, u) {
    const dim = UNITS[u][1], f = UNITS[u][2];
    if (dim !== 'temp') return v / f;
    if (f === 'C') return v;
    if (f === 'F') return v * 9 / 5 + 32;
    return v + 273.15;
  }
  function convert(v, a, b) { if (UNITS[a][1] !== UNITS[b][1]) return null; return fromBase(toBase(v, a), b); }

  function rngNext(state) {  // mulberry32, same as tools.rng_next
    state = (state + 0x6D2B79F5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1) >>> 0;
    t = (t ^ ((t + (Math.imul(t ^ (t >>> 7), t | 61) >>> 0)) >>> 0)) >>> 0;
    return [state, ((t ^ (t >>> 14)) >>> 0) / 4294967296];
  }

  // ------------------------------------------------------------ knowledge.py
  const PREFIXES = ['ประเทศ', 'จังหวัด', 'อำเภอ', 'เมือง', 'ภาษา', 'ศาสนา'];
  const PREFIX_KEEP = ['ภาษา', 'ศาสนา'];
  const Q_ANY = ['คืออะไร', 'คือใคร', 'เป็นใคร', 'เป็นอะไร', 'หมายถึงอะไร', 'หมายถึง', 'อะไร', 'ใคร', 'ที่ไหน', 'ไหน',
    'เมื่อไร', 'เมื่อไหร่', 'เท่าไร', 'เท่าไหร่', 'ยังไง', 'อย่างไร', 'ทำไม', 'หรือเปล่า', 'บอก', 'เกี่ยวกับ',
    'อยากรู้', 'รู้จัก', 'อธิบาย', 'เล่าเรื่อง', 'ขอข้อมูล', 'ช่วย', 'คือ', 'กี่',
    'what is', 'who is', 'who was', 'tell me about', 'what', 'who', 'where'].sort((a, b) => cpLen(b) - cpLen(a));
  const Q_EDGE = ['ครับ', 'คับ', 'ค่ะ', 'คะ', 'นะ', 'หรอ', 'เหรอ', 'ไหม', 'มั้ย', 'หน่อย', 'ได้', 'ให้ฟัง', 'ว่า', 'คุณ', 'เธอ',
    'ผม', 'ฉัน', 'ข้อมูล', 'the', 'a'];
  const WHERE = /ที่ไหน|อยู่ไหน|อยู่(?:ภาค|ทวีป|ประเทศ|จังหวัด)|ตั้งอยู่|where/;
  const WHEN = /เมื่อไร|เมื่อไหร่|ปีอะไร|ปีไหน|ปีไร|when/;
  const NUMBER = /เท่าไร|เท่าไหร่|กี่(?!ย)|how many|how much/;
  const CUES = {
    where: ['ตั้งอยู่', 'อยู่', 'ภาค', 'ทวีป', 'ประเทศ', 'ทิศ', 'เอเชีย', 'ยุโรป', 'แอฟริกา', 'อเมริกา', 'โอเชียเนีย'],
    when: ['พ.ศ.', 'ค.ศ.', 'ปี', 'เมื่อ', 'วันที่', 'ศตวรรษ'],
    number: ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'ล้าน', 'พัน'],
    what: [],
  };
  const squash = s => s.toLowerCase().replace(/[ \-_.,·()"'“”!?:;/]/g, '');
  function qtype(text) {
    const t = text.toLowerCase();
    if (WHERE.test(t)) return 'where';
    if (WHEN.test(t)) return 'when';
    if (NUMBER.test(t)) return 'number';
    return 'what';
  }
  function residual(text) {
    let t = text.toLowerCase();
    for (const p of Q_ANY) t = rall(t, p, ' ');
    const out = [];
    for (let part of t.split(' ')) {
      part = squash(part);
      let changed = true;
      while (changed && part) {
        changed = false;
        for (const e of Q_EDGE) {
          if (part.startsWith(e) && part.length > e.length) { part = part.slice(e.length); changed = true; }
          if (part.endsWith(e) && part.length >= e.length) { part = part.slice(0, part.length - e.length); changed = true; }
        }
      }
      out.push(part);
    }
    return out.join('');
  }
  function bigrams(s) { const a = cps(s), out = new Set(); for (let i = 0; i < a.length - 1; i++) out.add(a[i] + a[i + 1]); return out; }
  function chunks(text) {
    const out = []; let cur = '';
    for (const piece of text.split(' ')) {
      cur = cur ? (cur + ' ' + piece) : piece;
      if (cpLen(cur) >= 50) { out.push(cur); cur = ''; }
    }
    if (cur) {
      if (out.length && cpLen(cur) < 25) out[out.length - 1] += ' ' + cur;
      else out.push(cur);
    }
    return out;
  }
  const tupleLt = (a, b) => { for (let i = 0; i < a.length; i++) { if (a[i] < b[i]) return true; if (a[i] > b[i]) return false; } return false; };

  // ---------------------------------------------------------- opt-in web search (port of websearch.py)
  /* Off by default. When on: Thai Wikipedia, then English Wikipedia (MediaWiki API, origin=* for CORS, free, no key).
     Ranking and passage choice are TER-AI's own (trigram coverage, threshold 0.6), identical to the Python package.
     reply() stays synchronous: a URL that is not fetched yet throws NeedWeb, Chat.replyAsync() rolls the turn back,
     fetches it (timeout 5 s) and runs the turn again. Errors are kept for the current turn only. */
  const WIKIS = [['th', 'Wikipedia ภาษาไทย'], ['en', 'Wikipedia ภาษาอังกฤษ']];
  const WIKI_LICENSE = 'CC BY-SA 4.0';
  const WEB_MIN_COVER = 0.6;
  const WEB_CACHE_MAX = 200;
  const CURRENT = R('ปัจจุบัน|ตอนนี้|ล่าสุด|current|incumbent|now|latest');
  const CUR_CUES = ['ปัจจุบัน', 'คนปัจจุบัน', 'ดำรงตำแหน่ง', 'current', 'incumbent'];
  const WEB_TAIL = R('(?: *(?:ครับ|คับ|ค่ะ|คะ|ค่า|จ้า|นะ|หรอ|เหรอ|ไหม|มั้ย|หน่อย|\\?))+$');
  const CONT = ['ๆ', 'ฯ', '(', ')', ']', ',', '.', ';', ':', 'และ', 'หรือ', 'ซึ่ง', 'โดย', 'แต่', 'ของ', 'จะ', 'เป็น', 'คือ',
    'ได้', 'ก็', 'จึง', 'เพื่อ', 'ทำให้', 'ตั้งแต่', 'กับ', 'แห่ง'];
  const countCh = (s, c) => s.split(c).length - 1;
  function trigrams(s) {
    const a = cps(s), out = new Set();
    if (a.length < 3) { if (s) out.add(s); return out; }
    for (let i = 0; i < a.length - 2; i++) out.add(a[i] + a[i + 1] + a[i + 2]);
    return out;
  }
  function queryText(question) {
    let t = question.trim().toLowerCase().replace(WEB_TAIL, '');
    for (const p of Q_ANY) t = rall(t, p, ' ');
    t = t.replace(/ +/g, ' ').trim();
    return t || question.trim();
  }
  function cover(question, text) {
    const g = trigrams(residual(question));
    if (!g.size) return 0.0;
    const body = squash(text);
    let k = 0;
    for (const x of g) if (body.includes(x)) k++;
    return k / g.size;
  }
  function glue(prev, piece) {
    if (countCh(prev, '(') > countCh(prev, ')') || countCh(prev, '[') > countCh(prev, ']')) return true;
    if (CONT.some(w => piece.startsWith(w)) || (piece[0] >= '0' && piece[0] <= '9')) return true;
    const words = prev.split(' ');
    if (CONT.includes(words[words.length - 1])) return true;
    return /^[A-Za-z]/.test(piece) && !'.!?'.includes(prev[prev.length - 1]) && /[A-Za-z0-9,]$/.test(prev);
  }
  function units(text) {
    const out = [];
    for (const piece of text.split(' ')) {
      if (!piece) continue;
      if (out.length && glue(out[out.length - 1], piece)) out[out.length - 1] += ' ' + piece;
      else out.push(piece);
    }
    return out;
  }
  function passages(text) {
    const out = []; let cur = '';
    for (const u of units(text)) {
      cur = cur ? (cur + ' ' + u) : u;
      if (cpLen(cur) >= 50) { out.push(cur); cur = ''; }
    }
    if (cur) {
      if (out.length && cpLen(cur) < 25) out[out.length - 1] += ' ' + cur;
      else out.push(cur);
    }
    return out;
  }
  function webExtract(question, text, limit) {
    limit = limit || 300;
    const cs = passages(text);
    if (!cs.length) return '';
    const cues = CUES[qtype(question)].slice();
    if (CURRENT.test(question.toLowerCase())) for (const w of CUR_CUES) cues.push(w);
    let best = 0;
    if (cues.length) {
      const grams = trigrams(residual(question));
      let bestS = -1;
      cs.forEach((c, j) => {
        const sq = squash(c), low = c.toLowerCase();
        let s = 0;
        for (const g of grams) if (sq.includes(g)) s++;
        for (const w of cues) if (low.includes(w)) s += 3;
        if (s > bestS) { best = j; bestS = s; }
      });
    }
    let out = cs[best];
    if (best > 0 && cpLen(cs[0]) + 1 + cpLen(out) <= limit + 60) out = cs[0] + ' ' + out;
    let k = best + 1;
    while (k < cs.length && cpLen(out) + 1 + cpLen(cs[k]) <= limit) { out += ' ' + cs[k]; k++; }
    return out;
  }
  const unquote = s => { try { return decodeURIComponent(s); } catch (e) { return s; } };
  function webError(name, message) { const e = new Error(message); e.name = name; return e; }
  async function defaultFetch(url, timeout) {
    const ctl = typeof AbortController === 'function' ? new AbortController() : null;
    const timer = ctl ? setTimeout(() => ctl.abort(), timeout) : null;
    try {
      const r = await fetch(url, { signal: ctl ? ctl.signal : undefined, headers: { Accept: 'application/json' } });
      if (!r.ok) throw webError('HTTPError', 'HTTP ' + r.status);
      return await r.json();
    } catch (e) {
      if (e && e.name === 'AbortError') throw webError('TimeoutError', 'timed out after ' + timeout + ' ms');
      if (e && e.name === 'TypeError') throw webError('NetworkError', e.message);
      throw e;
    } finally { if (timer) clearTimeout(timer); }
  }
  class NeedWeb extends Error {
    constructor(url) { super('web fetch needed'); this.needWeb = true; this.url = url; }
  }
  class WebSearch {
    /* o.enabled: false = no network ever. o.fetch: async (url) => parsed JSON (tests inject a fake). o.timeout in ms. */
    constructor(o) {
      o = o || {};
      this.enabled = !!o.enabled; this.timeout = o.timeout || 5000; this._fetch = o.fetch || null;
      this.cache = new Map(); this.lastError = null; this.calls = 0;
    }
    static wikiUrl(lang, query, limit) {
      limit = limit || 5;
      const p = new URLSearchParams([['action', 'query'], ['format', 'json'], ['formatversion', '2'], ['generator', 'search'],
        ['gsrsearch', query], ['gsrlimit', String(limit)], ['prop', 'extracts|info'], ['exintro', '1'], ['explaintext', '1'],
        ['exlimit', String(limit)], ['inprop', 'url'], ['redirects', '1'], ['origin', '*']]);
      return 'https://' + lang + '.wikipedia.org/w/api.php?' + p.toString();
    }
    get(url) {
      if (!this.enabled) throw new Error('web search is disabled');
      const item = this.cache.get(url);
      if (!item) throw new NeedWeb(url);
      if (item.error) throw webError(item.error, item.message);
      return item.data;
    }
    async load(url) {
      this.calls += 1;
      try {
        const data = this._fetch ? await this._fetch(url) : await defaultFetch(url, this.timeout);
        this.cache.set(url, { data });
      } catch (e) {
        this.cache.set(url, { error: (e && e.name) || 'Error', message: String((e && e.message) || e).slice(0, 120) });
      }
      while (this.cache.size > WEB_CACHE_MAX) this.cache.delete(this.cache.keys().next().value);
    }
    dropErrors() { for (const [k, v] of Array.from(this.cache)) if (v.error) this.cache.delete(k); }
    _wiki(lang, name, query) {
      const data = this.get(WebSearch.wikiUrl(lang, query));
      const pages = (((data || {}).query || {}).pages || []).slice()
        .sort((a, b) => (a.index == null ? 99 : a.index) - (b.index == null ? 99 : b.index));
      const out = [];
      for (const p of pages) {
        const text = (p.extract || '').trim();
        if (!text || p.missing) continue;
        const url = p.fullurl || ('https://' + lang + '.wikipedia.org/wiki/' + encodeURIComponent(p.title.replace(/ /g, '_')));
        out.push({ title: p.title, url, text: text.replace(/\s+/g, ' '), source: name, license: WIKI_LICENSE });
      }
      return out;
    }
    static rank(question, results) {
      let best = null;
      results.forEach((r, i) => {
        const cAll = cover(question, r.title + ' ' + r.text);
        if (cAll < WEB_MIN_COVER) return;
        const score = cAll + 0.5 * cover(question, r.title) - 0.01 * i;
        if (best === null || score > best.score) best = Object.assign({}, r, { score });
      });
      if (best !== null) {
        best.score = Math.round(best.score * 1000) / 1000;
        best.answer = webExtract(question, best.text);
      }
      return best;
    }
    search(question) {
      this.lastError = null;
      if (!this.enabled) return null;
      const q = queryText(question);
      const steps = WIKIS.map(([lang, name]) => () => this._wiki(lang, name, q));
      let errors = 0;
      for (const step of steps) {
        let hit;
        try {
          hit = WebSearch.rank(question, step());
        } catch (e) {
          if (e && (e.needWeb || e.needKnowledge)) throw e;
          errors += 1;
          this.lastError = ((e && e.name) || 'Error') + ': ' + String((e && e.message) || e).slice(0, 120);
          continue;
        }
        if (hit !== null) { this.lastError = null; return hit; }
      }
      if (errors < steps.length) this.lastError = null;
      return null;
    }
    static cite(hit) {
      return '(ที่มา: ' + hit.source + ' "' + hit.title + '", ' + unquote(hit.url) + ', ' + hit.license + ')';
    }
  }

  class NeedKnowledge extends Error {
    constructor() { super('knowledge pack not loaded'); this.needKnowledge = true; }
  }

  class Knowledge {
    /* pack: the parsed knowledge_th.json, or null to attach later. meta: {count, retrieved} known before loading.
       loader: async () => pack, used by ensure() / Chat.replyAsync(). */
    constructor(pack, meta, loader) {
      this._docs = null; this.meta = Object.assign({}, meta || {}); this.loader = loader || null; this._pending = null;
      if (pack) this.setPack(pack);
    }
    get loaded() { return this._docs !== null; }
    setPack(pack) {
      for (const k of Object.keys(pack)) if (k !== 'docs') this.meta[k] = pack[k];
      const docs = pack.docs;
      this.meta.count = docs.length;
      const best = new Map();
      const put = (a, pri, i) => {
        if (cpLen(a) < 2) return;
        const cand = [pri, cpLen(docs[i][1]), i];
        const cur = best.get(a);
        if (!cur || tupleLt(cand, cur)) best.set(a, cand);
      };
      docs.forEach((d, i) => {
        const base = d[1].replace(/ \([^()]*\)$/, '');
        put(squash(base), 0, i);
        for (const p of PREFIXES) if (base.startsWith(p) && cpLen(base) - cpLen(p) >= 2) put(squash(base.slice(p.length)), PREFIX_KEEP.includes(p) ? 2 : 1, i);
        const words = base.split(' ');
        if (words.length >= 2 && cpLen(words[words.length - 1]) >= 4) put(squash(words[words.length - 1]), 3, i);
      });
      this.alias = new Map(); let maxlen = 0;
      for (const [a, v] of best) { this.alias.set(a, v[2]); maxlen = Math.max(maxlen, cpLen(a)); }
      this.maxlen = maxlen;
      this.fuzzy = new Map(); this._abg = new Map();
      for (const a of Array.from(this.alias.keys()).sort()) {
        if (cpLen(a) >= 3) {
          const g = bigrams(a);
          this._abg.set(a, g.size);
          for (const b of g) { let l = this.fuzzy.get(b); if (!l) { l = []; this.fuzzy.set(b, l); } l.push(a); }
        }
      }
      this._chunks = new Map();
      this._docs = docs;
      return this;
    }
    async ensure() {
      if (this._docs) return this;
      if (!this.loader) throw new Error('no knowledge loader');
      if (!this._pending) this._pending = Promise.resolve(this.loader()).then(p => this.setPack(p), e => { this._pending = null; throw e; });
      return this._pending;
    }
    load() { if (this._docs === null) throw new NeedKnowledge(); return this; }
    get docs() { return this.load()._docs; }
    count() { return this._docs ? this._docs.length : this.meta.count; }
    retrieved() { return this.meta.retrieved || ''; }
    chunksOf(doc) { let c = this._chunks.get(doc); if (!c) { c = chunks(this.docs[doc][2]); this._chunks.set(doc, c); } return c; }

    find(text) {
      const r = residual(text), ra = cps(r);
      if (ra.length < 2) return null;  // Python returns None here too; no pack needed to know it
      this.load();
      const hits = [];
      for (let i = 0; i < ra.length; i++) {
        for (let L = Math.min(this.maxlen, ra.length - i); L > 1; L--) {
          const a = ra.slice(i, i + L).join('');
          if (this.alias.has(a) && (L >= 3 || L === ra.length)) { hits.push([i, a, L]); break; }
        }
      }
      if (hits.length) {
        const ks = r.indexOf('ของ');
        const k = ks < 0 ? -1 : cpLen(r.slice(0, ks));
        const after = hits.filter(h => k >= 0 && h[0] > k);
        const pool = after.length ? after : hits;
        let b = pool[0];
        for (const h of pool) if (h[2] > b[2] || (h[2] === b[2] && h[0] < b[0])) b = h;
        const tail = after.length ? ra.length - k - 3 : ra.length;
        if (b[2] * 10 >= 4 * ra.length || (after.length && b[2] * 10 >= 8 * tail)) return { doc: this.alias.get(b[1]), alias: b[1], how: 'title', resid: r };
      }
      if (ra.length >= 3) {
        const rg = bigrams(r);
        const count = new Map();
        for (const g of rg) for (const a of (this.fuzzy.get(g) || [])) count.set(a, (count.get(a) || 0) + 1);
        let best = null, bn = 0, bd = 1;
        for (const a of Array.from(count.keys()).sort()) {
          const num = 2 * count.get(a), den = this._abg.get(a) + rg.size;
          if (num * bd > bn * den) { best = a; bn = num; bd = den; }
        }
        if (best !== null && bn * 10 >= 7 * bd) return { doc: this.alias.get(best), alias: best, how: 'fuzzy', resid: r };
      }
      return null;
    }
    passage(doc, text, start) {
      start = start || 0;
      const cs = this.chunksOf(doc);
      const qt = qtype(text);
      if (start >= cs.length) return [cs, null];
      if (qt === 'what' && start === 0) return [cs, 0];
      const titleSq = squash(this.docs[doc][1]);
      const extra = cps(rall(residual(text), titleSq, ''));
      const grams = new Set();
      for (let i = 0; i < extra.length - 2; i++) grams.add(extra[i] + extra[i + 1] + extra[i + 2]);
      let best = start, bestS = -1;
      for (let j = start; j < cs.length; j++) {
        const c = squash(cs[j]);
        let s = 0;
        for (const g of grams) if (c.includes(g)) s++;
        for (const w of CUES[qt]) if (cs[j].includes(w)) s += 3;
        if (s > bestS) { best = j; bestS = s; }
      }
      return [cs, best];
    }
    answer(doc, text, start, limit) {
      start = start || 0; if (limit === undefined) limit = 260;
      const [cs, j] = this.passage(doc, text, start);
      if (j === null) return [null, start];
      let out = cs[j], k = j + 1;
      if (j > start && j > 0 && start === 0 && cpLen(cs[0]) + 1 + cpLen(out) <= limit + 60) out = cs[0] + ' ' + out;
      while (k < cs.length && cpLen(out) + 1 + cpLen(cs[k]) <= limit) { out += ' ' + cs[k]; k++; }
      const title = this.docs[doc][1];
      if (j > 0 && !squash(out).includes(squash(title))) out = title + ': ' + out;
      return [out, k];
    }
    cite(doc) { return '(ที่มา: Wikipedia ภาษาไทย "' + this.docs[doc][1] + '", CC BY-SA 4.0)'; }
    numbersMissing(doc, text) {
      const body = rall(this.docs[doc][2], ',', '');
      return findall('[0-9]+', rall(text, ',', '')).filter(n => !body.includes(n));
    }
  }

  // ------------------------------------------------------------ chat.py
  const GREETINGS = ['มีอะไรให้ช่วยครับ/คะ', 'ให้ช่วยอะไรไหมครับ/คะ'];
  const ME = '(?:ผม|ฉัน|หนู|เรา|ดิฉัน|กู|เค้า|ข้า)';
  const Q = R('อะไร|ไหน|เท่าไร|เท่าไหร่|กี่|ไหม|มั้ย|หรือเปล่า|รึเปล่า|ยังไง|อย่างไร|ทำไม|ใคร|เมื่อไร|เมื่อไหร่|\\?|' +
    '(?:^| )(?:what|who|where|when|how|which)(?: |$)|^(?:is|are|do|does|can) ');
  const END = R('(?: *(?:ครับ|คับ|ค่ะ|คะ|ค่า|จ้า|จ้ะ|จ๊ะ|นะ|น่ะ|ล่ะ|หล่ะ|เลย|แหละ|ด้วย|มากๆ|มาก ๆ|มาก|ที่สุด))+$');
  const NAME_END = R('(?: *(?:ครับ|คับ|ค่ะ|คะ|ค่า|จ้า|จ้ะ|จ๊ะ|นะครับ|นะคะ|นะค่ะ| นะ))+$');
  const DAY_WORDS = [['มะรืนนี้', 2], ['มะรืน', 2], ['พรุ่งนี้', 1], ['วันนี้', 0], ['คืนนี้', 0], ['เย็นนี้', 0],
    ['เช้านี้', 0], ['บ่ายนี้', 0], ['เมื่อวานซืน', -2], ['เมื่อวาน', -1]];
  const WEEKDAY_RE = R('วัน(จันทร์|อังคาร|พุธ|พฤหัสบดี|พฤหัส|ศุกร์|เสาร์|อาทิตย์)');
  const LIVE = R('ราคา|ล่าสุด|ปัจจุบัน|ข่าว|หุ้น|ผลบอล|ผลฟุตบอล|ค่าเงิน|อัตราแลกเปลี่ยน|ตอนนี้|วันนี้|เมื่อวาน|พรุ่งนี้|today|latest|price');
  const PRONOUN = R('^(?:แล้ว)? *(?:มัน|เขา|เค้า|ที่นั่น|ที่นี่|อันนี้|อันนั้น|เมืองนี้|ประเทศนี้|เรื่องนี้|คนนี้|it |he |she |they )');
  const GRADE = R('(?:ชั้น *|ระดับชั้น *)?((?:ม|ป)\\. *[1-6]|(?:มัธยม|ประถม)(?:ศึกษา)?(?: *ปีที่)? *[1-6]|ปวช\\.? *[1-3]|ปวส\\.? *[1-2]|อนุบาล *[1-3]|มหาวิทยาลัย *ปี *[1-8]|grade *[0-9]{1,2})');
  const GRADE_Q = R(ME + ' *(?:กำลัง)?(?:เรียน *)?(?:อยู่ *)?(?:ชั้น|ระดับชั้น|ม\\.|ป\\.) *(?:อะไร|ไหน|ไร|เท่าไร|เท่าไหร่|ที่เท่าไร|ที่เท่าไหร่)|' + ME + ' *เรียน(?:อยู่)? *(?:ชั้น)?(?:อะไร|ไหน|ไร)|what grade am i');
  const NO_PENDING = 'ต่อเรื่องไหนดีครับ/คะ ตอนนี้ไม่มีเรื่องค้างอยู่ ลองถามความรู้ เช่น ดาวอังคารคืออะไร แล้วพิมพ์ เล่าต่อ';
  const CONTINUE = R('^(?:เล่าต่อ|ต่อเลย|ต่อสิ|ขยายความ|อีก|ต่อ|มีอีกไหม|มีอีกมั้ย|เพิ่มเติม|more|go on)$');
  const NUM = '[0-9]+(?:\\.[0-9]+)?';

  const call = name => 'คุณ' + (/^[\u0E00-\u0E7F]/.test(name) ? '' : ' ') + name;
  const clean = v => strip(v.trim().replace(END, '').trim(), ' "\'“”.,!');
  const cleanName = v => strip(v.trim().replace(NAME_END, '').trim(), ' "\'“”.,!');

  function parseNow(now) {
    if (now == null) {
      try {
        const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Bangkok', hourCycle: 'h23', year: 'numeric', month: '2-digit',
          day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }).formatToParts(new Date());
        const g = t => parseInt(parts.find(p => p.type === t).value, 10);
        return { y: g('year'), m: g('month'), d: g('day'), H: g('hour') % 24, M: g('minute'), S: g('second') };
      } catch (e) {
        const d = new Date();
        return { y: d.getFullYear(), m: d.getMonth() + 1, d: d.getDate(), H: d.getHours(), M: d.getMinutes(), S: d.getSeconds() };
      }
    }
    if (typeof now === 'function') return parseNow(now());
    if (typeof now === 'string') {
      const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/.exec(now);
      return { y: +m[1], m: +m[2], d: +m[3], H: +(m[4] || 0), M: +(m[5] || 0), S: +(m[6] || 0) };
    }
    return now;
  }
  const isoSeconds = n => String(n.y).padStart(4, '0') + '-' + pad2(n.m) + '-' + pad2(n.d) + 'T' + pad2(n.H) + ':' + pad2(n.M) + ':' + pad2(n.S);

  function emptyState(seed) {
    return { version: STATE_VERSION, name: null, likes: [], dislikes: [], plans: [], age: null, location: null, grade: null,
      kv: [], history: [], turns: 0, rng: mod(Math.floor(seed), 4294967296), last: null };
  }

  class Chat {
    constructor(o) {
      o = o || {};
      this.router = o.router;
      this.kb = o.knowledge;
      this.chitchatPairs = o.chitchat;
      this._now = o.now;
      this.onSave = o.onSave || null;
      this.web = o.web || null;  // a WebSearch, or null = offline (default)
      this._webTried = false;
      const seed = o.seed == null ? Date.now() : o.seed;
      this.state = emptyState(seed);
      if (o.state) Object.assign(this.state, o.state);
    }
    save() { if (this.onSave) this.onSave(this.state); }
    forget() { const rng = this.state.rng; this.state = emptyState(0); this.state.rng = rng; this.save(); }
    get facts() {
      const s = this.state;
      return { name: s.name, likes: s.likes.slice(), dislikes: s.dislikes.slice(), age: s.age, location: s.location, grade: s.grade == null ? null : s.grade,
        plans: s.plans.map(p => Object.assign({}, p)), kv: s.kv.map(p => p.slice()) };
    }
    get history() { return this.state.history.slice(); }
    now() { return parseNow(this._now); }
    today() { const n = this.now(); return daysFromCivil(n.y, n.m, n.d); }
    _rand() { const r = rngNext(this.state.rng); this.state.rng = r[0]; return r[1]; }
    _randint(lo, hi) { return lo + Math.floor(this._rand() * (hi - lo + 1)); }
    _nm() { return this.state.name ? (' ' + call(this.state.name)) : ''; }
    _factCount() {
      const s = this.state;
      return (s.name ? 1 : 0) + s.likes.length + s.dislikes.length + s.plans.length + (s.age ? 1 : 0) + (s.location ? 1 : 0) + s.kv.length;
    }
    _dayLabel(day) {
      const t = this.today();
      const rel = day === t - 1 ? 'เมื่อวาน' : day === t + 2 ? 'มะรืนนี้' : day === t + 1 ? 'พรุ่งนี้' : day === t ? 'วันนี้' : null;
      return rel ? (rel + ' (' + thDate(day) + ')') : thDate(day);
    }
    _planText(p) {
      if (p.day != null) return this._dayLabel(p.day) + ' คุณจะ' + p.what;
      return (p.when ? (p.when + ' ') : '') + 'คุณจะ' + p.what;
    }
    _resolveDay(text) {
      for (const [w, off] of DAY_WORDS) if (text.includes(w)) return [w, this.today() + off];
      const m = WEEKDAY_RE.exec(text);
      if (m) {
        const name = m[1] === 'พฤหัส' ? 'พฤหัสบดี' : m[1];
        const t = this.today();
        const k = TH_DAYS.indexOf(name);
        const ahead = mod(k - weekday(t), 7);
        return [m[0], t + (ahead ? ahead : 7)];
      }
      for (const w of ['สัปดาห์หน้า', 'อาทิตย์หน้า', 'เดือนหน้า', 'ปีหน้า']) if (text.includes(w)) return [w, null];
      return [null, null];
    }
    _route(n) { return this.router.predict(n); }

    // ---------------------------------------------------------- main entry
    reply(text) {
      text = (text || '').trim();
      if (!text) return 'พิมพ์ข้อความมาได้เลยครับ/ค่ะ';
      let n = this.router.normalize(text).text;
      n = n.replace(/ +/g, ' ').trim();
      this.state.turns += 1;
      this._webTried = false;
      let out = null;
      for (const step of [this._forget, this._recall, this._learn, this._social, this._datetime, this._random,
        this._textops, this._calc, this._units, this._continue, this._chitchatReply,
        this._knowledgeReply, this._router, this._unknown]) {
        out = step.call(this, text, n);
        if (out != null) break;
      }
      if (this.state.turns === 0) this.state.turns = 1;
      const h = this.state.history;
      h.push({ t: isoSeconds(this.now()), user: text, bot: out });
      if (h.length > HISTORY_MAX) h.splice(0, h.length - HISTORY_MAX);
      this.save();
      return out;
    }

    /* Browser entry: when a step needs the knowledge pack (not loaded yet) or a web page (web search on, not fetched
       yet), the turn is rolled back, the missing piece is loaded (onLoading(true/false) around the pack download,
       onWeb(true/false) around a web request) and the same turn runs again. */
    async replyAsync(text, onLoading, onWeb) {
      const snap = JSON.stringify(this.state);
      const saver = this.onSave;
      this.onSave = null;
      if (this.web) this.web.dropErrors();
      try {
        for (let round = 0; ; round++) {
          try {
            const out = this.reply(text);
            this.onSave = saver; this.save();
            return out;
          } catch (e) {
            this.state = JSON.parse(snap);
            if (round >= 12 || !(e && (e.needKnowledge || e.needWeb))) throw e;
            if (e.needKnowledge) {
              if (onLoading) onLoading(true);
              try { await this.kb.ensure(); } finally { if (onLoading) onLoading(false); }
            } else {
              if (onWeb) onWeb(true);
              try { await this.web.load(e.url); } finally { if (onWeb) onWeb(false); }
            }
          }
        }
      } finally { this.onSave = saver; }
    }

    // ---------------------------------------------------------- 1. forget
    _forget(text, n) {
      const low = n.toLowerCase();
      if (search('^(?:ช่วย)?(?:ลืม|ล้าง)(?:ความจำ|ทั้งหมด|ทุกอย่าง|หมดเลย|หมด|ทุกเรื่อง)|ล้างความจำ|^forget (?:everything|all)|^clear memory', low)) {
        this.forget();
        this.state.turns = 0;
        return 'ล้างความจำทั้งหมดแล้วครับ/ค่ะ ตอนนี้ผมไม่รู้อะไรเกี่ยวกับคุณเลย เริ่มใหม่ได้';
      }
      const m = search('^(?:ช่วย)?ลืม(ชื่อ|สิ่งที่ชอบ|ที่ชอบ|ที่ไม่ชอบ|แผน|อายุ|ที่อยู่|ชั้นเรียน|ชั้น)', low);
      if (m) {
        const k = m[1];
        if (k === 'ชื่อ') this.state.name = null;
        else if (k === 'สิ่งที่ชอบ' || k === 'ที่ชอบ') this.state.likes = [];
        else if (k === 'ที่ไม่ชอบ') this.state.dislikes = [];
        else if (k === 'แผน') this.state.plans = [];
        else if (k === 'อายุ') this.state.age = null;
        else if (k === 'ชั้นเรียน' || k === 'ชั้น') this.state.grade = null;
        else this.state.location = null;
        return 'ลืม' + k + 'ของคุณแล้วครับ/ค่ะ';
      }
      return null;
    }

    // ---------------------------------------------------------- 2. questions about the user
    _recall(text, n) {
      const s = this.state;
      const low = n.toLowerCase();
      if (search('(?:เมื่อกี้|เมื่อกี๊|เมื่อตะกี้|ก่อนหน้านี้|ล่าสุด).*(?:พูด|ถาม|พิมพ์|บอก|ส่ง).*(?:อะไร|ไร)|what did i (?:say|ask)', low)) {
        const users = s.history.map(h => h.user);
        if (!users.length) return 'ผมยังไม่มีข้อความก่อนหน้าของคุณในความจำครับ/ค่ะ (ไม่มีข้อมูล)';
        const verb = (low.includes('ถาม') || low.includes('ask')) ? 'ถาม' : 'พิมพ์';
        let out = 'เมื่อกี้คุณ' + verb + 'ว่า "' + users[users.length - 1] + '"';
        if (users.length >= 2) out += ' ก่อนหน้านั้น: "' + users[users.length - 2] + '"';
        return out;
      }
      if (search('จำอะไร.*(?:ผม|ฉัน|หนู|เรา).*ได้|รู้อะไรเกี่ยวกับ' + ME + '|จำอะไรได้บ้าง|what do you (?:know|remember)', low)) return this._allFacts();
      if (!search('ของ' + ME + ' *ชื่อ', low) && search(ME + ' *ชื่อ(?:อะไร|ไร)|ชื่อ(?:ของ)?' + ME + ' *(?:คือ)?(?:อะไร|ไร)|what(?: is|\'s) my name|do you know my name|ผมชื่ออะไร', low)) {
        if (s.name) return 'คุณชื่อ' + (/^[\u0E00-\u0E7F]/.test(s.name) ? '' : ' ') + s.name + 'ครับ/ค่ะ';
        return 'ผมยังไม่รู้ชื่อคุณครับ/ค่ะ บอกได้เลย เช่น ผมชื่อ... หรือ ฉันชื่อ...';
      }
      if (search(ME + ' *(?:ไม่ชอบ|เกลียด)(?:อะไร|ไร)', low)) {
        if (s.dislikes.length) return 'คุณไม่ชอบ' + s.dislikes.join(', ') + 'ครับ/ค่ะ';
        return 'ผมยังไม่รู้ว่าคุณไม่ชอบอะไร (ยังไม่มีข้อมูล) บอกได้ เช่น ผมไม่ชอบ...';
      }
      if (search(ME + ' *(?:ชอบ|รัก)(?:อะไร|ไร)|what do i like', low)) {
        if (s.likes.length) return 'คุณชอบ' + s.likes.join(', ') + 'ครับ/ค่ะ';
        return 'ผมยังไม่รู้ว่าคุณชอบอะไร (ยังไม่มีข้อมูล) บอกได้ เช่น ผมชอบ...';
      }
      let m = search('^(.*?)' + ME + '? *(?:จะ|ต้อง)? *(?:ทำ(?:อะไร|ไร)|ไปไหน|มีแผนอะไร|มีนัดอะไร|มีนัดไหม|มีแผนไหม)', low);
      if (m && (search(ME, low) || this._resolveDay(m[1])[0]) && !search('เธอ|คุณจะ|บอท', low)) {
        const [label, day] = this._resolveDay(low);
        const plans = s.plans;
        let hit;
        if (label && day != null) hit = plans.filter(p => (p.day == null ? null : p.day) === day);
        else if (label) hit = plans.filter(p => p.when === label);
        else hit = plans.slice();
        if (hit.length) return hit.map(p => this._planText(p)).join('; ');
        let out = 'ผมไม่มีข้อมูลว่า' + (label ? label + 'คุณ' : 'คุณ') + 'จะทำอะไรครับ/ค่ะ';
        if (plans.length) out += ' แผนที่ผมจำไว้: ' + plans.map(p => this._planText(p)).join('; ');
        return out;
      }
      if (search(ME + ' *อายุ *(?:เท่าไร|เท่าไหร่|กี่ปี|กี่ขวบ)|how old am i', low)) {
        if (s.age) return 'คุณอายุ ' + s.age + ' ปีครับ/ค่ะ';
        return 'ผมยังไม่รู้อายุคุณครับ/ค่ะ (ยังไม่มีข้อมูล)';
      }
      if (GRADE_Q.test(low)) {
        if (s.grade) return 'คุณเรียนอยู่ชั้น ' + s.grade + ' ครับ/ค่ะ';
        return 'ผมยังไม่รู้ว่าคุณเรียนอยู่ชั้นอะไรครับ/ค่ะ (ยังไม่มีข้อมูล) บอกได้ เช่น ผมอยู่ ม.4';
      }
      if (search(ME + ' *(?:อยู่|อาศัยอยู่|มาจาก) *(?:ที่)?(?:ไหน|จังหวัดอะไร|ที่ไหน)|บ้าน' + ME + 'อยู่(?:ที่)?ไหน|where do i live', low)) {
        if (s.location) return 'คุณอยู่' + s.location + 'ครับ/ค่ะ';
        return 'ผมยังไม่รู้ว่าคุณอยู่ที่ไหนครับ/ค่ะ (ยังไม่มีข้อมูล)';
      }
      m = search('^(.+?) *ของ' + ME + ' *(?:คือ|เป็น|ชื่อ)? *(?:อะไร|ไร|เท่าไร|เท่าไหร่|ที่ไหน|ไหน|ใคร)', n);
      if (m) {
        const key = squash(m[1]);
        for (const [k, v] of s.kv) {
          if (squash(k) === key || (cpLen(key) >= 3 && (squash(k).includes(key) || key.includes(squash(k))))) return k + 'ของคุณคือ ' + v + ' ครับ/ค่ะ';
        }
        return 'ผมไม่รู้' + m[1].trim() + 'ของคุณครับ/ค่ะ (ยังไม่มีข้อมูล) ถ้าบอกผม เช่น "' + m[1].trim() + 'ของผมคือ ..." ผมจะจำไว้';
      }
      if (Q.test(low) && search('(?:บ้าน|ของ|แม่|พ่อ|พี่|น้อง|เพื่อน|ครู|แฟน|ห้อง|โรงเรียน)' + ME + '|' + ME + ' *(?:มี|เคย|ได้|เป็น)', low)) {
        return 'ผมไม่รู้ครับ/ค่ะ เรื่องนี้ของคุณผมยังไม่มีข้อมูล ถ้าบอกผม ผมจะจำไว้';
      }
      return null;
    }

    _allFacts() {
      const s = this.state;
      const parts = [];
      if (s.name) parts.push('ชื่อ ' + s.name);
      if (s.age) parts.push('อายุ ' + s.age + ' ปี');
      if (s.location) parts.push('อยู่' + s.location);
      if (s.grade) parts.push('เรียนชั้น ' + s.grade);
      if (s.likes.length) parts.push('ชอบ ' + s.likes.join(', '));
      if (s.dislikes.length) parts.push('ไม่ชอบ ' + s.dislikes.join(', '));
      for (const p of s.plans) parts.push('แผน: ' + this._planText(p));
      for (const [k, v] of s.kv) parts.push(k + ' = ' + v);
      if (!parts.length) return 'ตอนนี้ผมยังไม่รู้อะไรเกี่ยวกับคุณเลยครับ/ค่ะ (ยังไม่มีข้อมูล) เล่าให้ฟังได้ เช่น ผมชื่อ... ผมชอบ...';
      return 'สิ่งที่ผมจำเกี่ยวกับคุณ: ' + parts.join('; ');
    }

    // ---------------------------------------------------------- 3. new facts
    _learn(text, n) {
      const s = this.state;
      if (Q.test(n.toLowerCase())) return null;
      let src = rall(text, ' ', '') === rall(n, ' ', '') ? text : n;
      src = src.replace(/ +/g, ' ').trim();
      let corr = false;
      let m = search('^(?:ไม่ใช่|ไม่ช่าย|ผิด|no)(?:ครับ|คับ|ค่ะ|คะ|นะ)?[ ,]*', src);
      if (m && src.length > m[0].length) { src = src.slice(m[0].length); corr = true; }
      const low = src.toLowerCase();
      const said = [];
      m = search('^(.+?) *ของ' + ME + ' *(?:คือ|เป็น|ชื่อ) *(.+)$', src);
      if (m) {
        const k = m[1].trim(), v = clean(m[2]);
        if (k && v) {
          const kv = s.kv.filter(p => squash(p[0]) !== squash(k));
          kv.push([k, v]);
          s.kv = kv;
          return 'จำไว้แล้วครับ/ค่ะ: ' + k + 'ของคุณคือ ' + v;
        }
      }
      m = search('(?:^|[ ,])' + ME + ' *ชื่อ(?:เล่น)? *(?:ว่า)? *([^ ,]+)', src, 'd')
        || search('^(?:ชื่อ|เรียก' + ME + 'ว่า) *([^ ,]+)', src, 'd')
        || search('เรียก' + ME + ' *ว่า *([^ ,]+)', src, 'd')
        || search('(?:my name is|call me|i am called|i\'m called) +([^ ,.!]+)', low, 'd');
      if (m) {
        const name = cleanName(src.slice(m.indices[1][0], m.indices[1][1]));
        if (name && name !== 'อะไร' && name !== 'ไร' && cpLen(name) <= 30) {
          const old = s.name;
          s.name = name;
          if (old === name) said.push('ใช่ครับ/ค่ะ ' + call(name) + ' ผมจำไว้อยู่แล้ว');
          else if (old && (corr || old !== name)) said.push('แก้ให้แล้วครับ/ค่ะ ต่อไปผมจะเรียกว่า' + call(name));
          else said.push('ยินดีที่ได้รู้จักครับ/ค่ะ ' + call(name) + ' ผมจำชื่อไว้แล้ว');
        }
      }
      const hasMe = search(ME, low) !== null || said.length > 0;
      m = search('(?:' + ME + ' *)?อายุ *([0-9]+) *(?:ปี|ขวบ)?', low);
      if (m && hasMe) { s.age = m[1]; said.push('จำไว้แล้วว่าคุณอายุ ' + m[1] + ' ปี'); }
      m = GRADE.exec(src);
      if (m && hasMe && search(ME + ' *(?:กำลัง)?(?:เรียน|อยู่|เป็นนักเรียน|เป็นนักศึกษา|ขึ้น)', src)) {
        let g = m[1].replace(/ +/g, ' ').trim();
        g = g.replace(/^(ม|ป)\. */, '$1.');
        s.grade = g;
        said.push('จำไว้แล้วว่าคุณเรียนอยู่ชั้น ' + g);
      }
      m = search('(?:' + ME + ' *)?(?:อาศัยอยู่|อยู่|มาจาก) *(?:ที่|จังหวัด)? *([^ ,]+)', src);
      if (m && hasMe && !search('อยู่ *(?:กับ|บ้าน|ม\\.|ป\\.|ชั้น|ห้อง|ว่าง|ดี|เฉย|คนเดียว)', src)) {
        const loc = clean(m[1]);
        if (loc && !/^(?:แล้ว|ตอนนี้|ใน|ที่นี่|นี่)$/.test(loc)) { s.location = loc; said.push('จำไว้แล้วว่าคุณอยู่' + loc); }
      }
      if (!said.length) {
        m = search('(?:^|[ ,])' + ME + ' *(?:ไม่ชอบ|เกลียด|ไม่ถูกกับ) *(.+)$', src);
        if (m) {
          const v = clean(m[1]);
          if (v) {
            if (!s.dislikes.includes(v)) s.dislikes.push(v);
            s.likes = s.likes.filter(x => x !== v);
            return 'จำไว้แล้วครับ/ค่ะ ว่าคุณไม่ชอบ' + v;
          }
        }
        m = search('(?:^|[ ,])' + ME + ' *(?:ชอบ|รัก|ชื่นชอบ|ติด) *(.+)$', src);
        if (m) {
          const v = clean(m[1]);
          if (v && !['เธอ', 'คุณ', 'นาย', 'บอท'].includes(v)) {
            if (!s.likes.includes(v)) s.likes.push(v);
            s.dislikes = s.dislikes.filter(x => x !== v);
            return 'จำไว้แล้วครับ/ค่ะ ว่าคุณชอบ' + v;
          }
        }
        m = search('^(.*?)' + ME + ' *(?:จะ|ต้อง|มีนัด|มีแผน(?:จะ)?|กำลังจะ) *(.+)$', src);
        if (m) {
          let what = clean(m[2]);
          const rest = m[1] + ' ' + what;
          const [label, day] = this._resolveDay(rest);
          if (label) what = what.includes(label) ? clean(rall(what, label, '')) : what;
          if (what) {
            const p = { what: what, when: label, day: day };
            s.plans = s.plans.filter(x => !(x.what === what && (x.day == null ? null : x.day) === day)).concat([p]);
            return 'จำไว้แล้วครับ/ค่ะ: ' + this._planText(p);
          }
        }
      }
      if (said.length) return said.join(' ');
      return null;
    }

    // ---------------------------------------------------------- 4. greeting, thanks, who, help, stats
    _social(text, n) {
      const low = n.toLowerCase();
      const short = cpLen(squash(low)) <= 20;
      if (search('^(?:สวัสดี|หวัดดี|ดีจ้า|ดีครับ|ดีค่ะ|ดีคับ|hello|hi|hey|สวัสดีตอน)', low) || (short && this._intent(n, 'greet'))) {
        const v = GREETINGS[Math.floor(this._rand() * GREETINGS.length)];
        return 'สวัสดีครับ/ค่ะ' + this._nm() + ' ' + v;
      }
      if (search('ขอบคุณ|ขอบใจ|thank|แต๊งกิ้ว|thx', low)) return 'ยินดีครับ/ค่ะ' + this._nm() + ' มีอะไรให้ช่วยต่อบอกได้เลย';
      if (search('^(?:เธอ|คุณ|นาย|แก|บอท|ตัวเอง)? *(?:เป็น|คือ)(?:ใคร|อะไร)|^(?:เธอ|คุณ|นาย|บอท) *ชื่อ(?:อะไร|ไร)|who are you|what are you|your name', low)) {
        return 'ผมคือ TER-AI (เธอ) v' + VERSION + ' แชทบอทภาษาไทยขนาดเล็กที่รัน offline บน CPU สร้างโดย Bogus (made with Sesame) ' +
          'ไม่มี LLM ข้างใน ตอบจากเครื่องมือ (คิดเลข วันที่ แปลงหน่วย สุ่ม) ความจำของบทสนทนา และ Wikipedia ภาษาไทย';
      }
      if (search('(?:ช่วย|ทำ)อะไรได้บ้าง|ใช้ยังไง|ใช้งานยังไง|วิธีใช้|มีคำสั่งอะไร|^help$|^คำสั่ง$|^ช่วยด้วย$', low)) {
        return 'ผมทำได้: คิดเลข (เช่น (3+4)*2, 15% ของ 200, รากที่สองของ 144), บอกเวลาและวันที่ (อีก 10 วันเป็นวันที่เท่าไร), ' +
          'แปลงหน่วย (100 กิโลเมตรเป็นกี่ไมล์), สุ่มเลข ทอยลูกเต๋า โยนเหรียญ, นับตัวอักษร กลับคำ ตัวพิมพ์ใหญ่, ' +
          'ตอบความรู้จาก Wikipedia ภาษาไทย ' + commas(this.kb.count()) + ' บทความ (ถามต่อด้วย มัน... หรือ เล่าต่อ), ' +
          'จำชื่อ อายุ ที่อยู่ สิ่งที่ชอบ/ไม่ชอบ แผน และข้อมูลที่บอก (ถาม จำอะไรเกี่ยวกับผมได้บ้าง, ลืมทั้งหมด = ล้างความจำ)';
      }
      if (search('คุย(?:กัน)?ไป(?:แล้ว)?กี่|คุยกันกี่|กี่ครั้งแล้ว|สถิติ|^stats$', low)) {
        return 'เราคุยกันไปแล้ว ' + this.state.turns + ' ครั้ง (นับข้อความของคุณ รวมครั้งนี้) ' +
          'ผมจำเรื่องของคุณไว้ ' + this._factCount() + ' เรื่อง';
      }
      return null;
    }
    _intent(n, want, conf, cov) {
      if (conf === undefined) conf = 0.9;
      if (cov === undefined) cov = 0.9;
      const r = this._route(n);
      return r.intent === want && r.confidence >= conf && r.coverage >= cov;
    }

    // ---------------------------------------------------------- 5. date and time
    _datetime(text, n) {
      const low = n.toLowerCase();
      const now = this.now();
      if (search('กี่โมง|เวลาเท่าไร|เวลาเท่าไหร่|ตอนนี้เวลา|เวลาอะไร|what time', low)) {
        return 'ตอนนี้เวลา ' + pad2(now.H) + ':' + pad2(now.M) + ' น. ' + thDate(this.today()) + ' (เวลาเครื่อง)';
      }
      if (!search('วันอะไร|วันไหน|วันที่เท่า|วันที่อะไร|วันที่ไหน|เป็นวันที่|ตรงกับวัน|เดือนอะไร|ปีอะไร|ปีนี้ปี|ปี พ\\.ศ\\.|what day|what date|date today', low)) return null;
      const t = this.today();
      let label = 'วันนี้', off = 0;
      const m = search('อีก *([0-9]+) *(วัน|สัปดาห์|อาทิตย์)', low);
      const m2 = search('([0-9]+) *(วัน|สัปดาห์|อาทิตย์)(?:ที่แล้ว|ก่อน)', low);
      if (m) {
        const k = parseInt(m[1], 10) * (m[2] !== 'วัน' ? 7 : 1);
        label = 'อีก ' + m[1] + ' ' + m[2]; off = k;
      } else if (m2) {
        const k = parseInt(m2[1], 10) * (m2[2] !== 'วัน' ? 7 : 1);
        label = m2[1] + ' ' + m2[2] + 'ที่แล้ว'; off = -k;
      } else {
        for (const [w, o] of DAY_WORDS) {
          if (low.includes(w) && !['คืนนี้', 'เย็นนี้', 'เช้านี้', 'บ่ายนี้'].includes(w)) { label = w; off = o; break; }
        }
      }
      const day = t + off;
      if (search('ปีอะไร|ปีนี้ปี|ปี พ\\.ศ\\.', low) && !search('วัน', low)) {
        const y = civilFromDays(day)[0];
        return 'ปีนี้คือ พ.ศ. ' + (y + 543) + ' (ค.ศ. ' + y + ')';
      }
      if (low.includes('เดือนอะไร') && !search('วัน', low)) {
        const [y, mth] = civilFromDays(day);
        return 'เดือนนี้คือเดือน' + TH_MONTHS[mth - 1] + ' ' + (y + 543);
      }
      const verb = off === 0 ? 'คือ' : (off > 0 ? 'ตรงกับ' : 'คือ');
      return label + verb + thDate(day);
    }

    // ---------------------------------------------------------- 6. random
    _random(text, n) {
      const low = n.toLowerCase();
      if (search('ลูกเต๋า|ทอยเต๋า|dice|roll a die', low)) {
        const m = search('([0-9]+) *(?:ลูก|ครั้ง)', low);
        const k = m ? Math.max(1, Math.min(10, parseInt(m[1], 10))) : 1;
        const rolls = [];
        for (let i = 0; i < k; i++) rolls.push(this._randint(1, 6));
        this.state.last = { kind: 'random' };
        if (k === 1) return 'ทอยลูกเต๋าได้ ' + rolls[0];
        return 'ทอยลูกเต๋า ' + k + ' ลูกได้ ' + rolls.join(', ') + ' รวม ' + rolls.reduce((a, b) => a + b, 0);
      }
      if (search('โยนเหรียญ|หัวหรือก้อย|หัวก้อย|flip a coin|coin', low)) {
        this.state.last = { kind: 'random' };
        return 'โยนเหรียญได้ ' + (this._rand() < 0.5 ? 'หัว' : 'ก้อย');
      }
      if (search('สุ่ม|random', low)) {
        const m = search('(-?[0-9]+) *(?:ถึง|-|to|จนถึง|และ|กับ) *(-?[0-9]+)', low);
        let lo = 1, hi = 100;
        if (m) { lo = parseInt(m[1], 10); hi = parseInt(m[2], 10); }
        if (lo > hi) { const x = lo; lo = hi; hi = x; }
        const v = this._randint(lo, hi);
        this.state.last = { kind: 'random' };
        return 'สุ่มได้ ' + v + ' (จาก ' + lo + ' ถึง ' + hi + ')';
      }
      return null;
    }

    // ---------------------------------------------------------- 7. text tools
    _textops(text, n) {
      const ops = [['(?:นับ(?:จำนวน)?(?:ตัวอักษร|ตัวอักขระ|ตัวหนังสือ)|count (?:letters|characters|chars)(?: in)?)', 'count'],
        ['(?:กลับคำ|กลับด้าน|กลับหลัง|reverse)', 'rev'],
        ['(?:ตัวพิมพ์ใหญ่|เป็นพิมพ์ใหญ่|uppercase|upper case|upper)', 'up'],
        ['(?:ตัวพิมพ์เล็ก|เป็นพิมพ์เล็ก|lowercase|lower case|lower)', 'down']];
      for (const [pat, op] of ops) {
        let m = null;
        for (const src of [text, n]) {
          m = search('^(?:ช่วย|ขอ|ทำ|แปลง)? *(?:ให้)? *' + pat + ' *(?:ของ|คำว่า|ข้อความ)? *[:"“]? *(.+?)["”]?$', src, 'i');
          if (m) break;
        }
        if (!m) continue;
        const arg = m[1].trim();
        this.state.last = { kind: 'text' };
        if (op === 'count') {
          const k = cpLen(rall(arg, ' ', ''));
          return '"' + arg + '" มี ' + k + ' ตัวอักษร (นับสระและวรรณยุกต์เป็น 1 ตัว ไม่นับช่องว่าง)';
        }
        if (op === 'rev') return cps(arg).reverse().join('');
        if (op === 'up') return arg.toUpperCase();
        return arg.toLowerCase();
      }
      return null;
    }

    // ---------------------------------------------------------- 8. calculator
    _calc(text, n) {
      const low = n.toLowerCase();
      const last = this.state.last || {};
      let expr = null;
      let follow = sub('^(?:แล้ว|เอา|ถ้า|ต่อ) *', '', low);
      follow = sub('อีก|เข้าไป|ไป ', '', follow).trim();
      const nums = findall(NUM, follow);
      if (last.kind === 'calc' && nums.length === 1 && search('^(?:บวก|ลบ|คูณ|หาร|ยกกำลัง|plus|minus|times|divided|[+\\-*/^x×÷])', follow)) {
        expr = calcPrepare(fmtNum(last.value) + ' ' + follow);
      }
      if (expr === null && last.kind === 'calc' && last.expr) {
        let bare = sub('^(?:แล้ว|ถ้า|เอา) *(?:ถ้า)? *(?:เป็น|เปลี่ยนเป็น)? *', '', low);
        bare = bare.replace(END, '').trim();
        bare = sub(' *(?:ล่ะ|ละ|หล่ะ)$', '', bare).trim();
        if (search('^-?' + NUM + '$', bare) && bare !== low.trim()) {
          const numsIn = finditer(NUM, last.expr);
          if (numsIn.length) {
            const k = numsIn[numsIn.length - 1];
            expr = last.expr.slice(0, k.index) + bare + last.expr.slice(k.index + k[0].length);
          }
        }
      }
      if (expr === null) expr = calcPrepare(low);
      if (expr === null) return null;
      let v;
      try {
        v = calcEval(expr);
      } catch (e) {
        if (!(e instanceof CalcError)) throw e;
        const msg = e.message;
        if (msg === 'div0') return prettyExpr(expr) + ': หารด้วยศูนย์ไม่ได้ครับ/ค่ะ (หารด้วย 0 ไม่ได้ ไม่มีคำตอบ)';
        if (msg === 'sqrt of negative') return 'รากที่สองของจำนวนลบไม่มีคำตอบในจำนวนจริงครับ/ค่ะ';
        if (msg === 'non-integer power') return 'ผมยกกำลังได้เฉพาะเลขชี้กำลังที่เป็นจำนวนเต็มครับ/ค่ะ';
        return 'โจทย์ "' + expr.trim() + '" ไม่ครบหรือรูปแบบไม่ถูก ผมคำนวณไม่ได้ครับ/ค่ะ';
      }
      this.state.last = { kind: 'calc', value: v, expr: expr };
      return prettyExpr(expr) + ' = ' + fmtNum(v);
    }

    // ---------------------------------------------------------- 9. units
    _units(text, n) {
      const low = n.toLowerCase();
      const last = this.state.last || {};
      const found = findUnits(low);
      const uniq = [];
      for (const f of found) if (!uniq.some(u => u[2] === f[2])) uniq.push(f);
      let num = null, ua, ub;
      if (uniq.length >= 2) {
        const a = uniq[0], b = uniq[1];
        const before = finditer('-?' + NUM, low).filter(m => m.index + m[0].length <= a[0]);
        const anyn = search('-?' + NUM, low);
        num = before.length ? before[before.length - 1][0] : (anyn ? anyn[0] : '1');
        ua = a[2]; ub = b[2];
      } else if (last.kind === 'unit') {
        let stripped = sub('^(?:แล้ว|ถ้า|เอา) *', '', low);
        stripped = stripped.replace(END, '').trim();
        stripped = sub(' *(?:ล่ะ|ละ|หล่ะ)$', '', stripped).trim();
        const m = search('^(-?' + NUM + ')$', stripped);
        if (!m) return null;
        num = m[1]; ua = last.from; ub = last.to;
      } else return null;
      const v = Number(num);
      const r = convert(v, ua, ub);
      if (r === null) return UNITS[ua][3] + ' กับ ' + UNITS[ub][3] + ' เป็นหน่วยคนละชนิด แปลงกันไม่ได้ครับ/ค่ะ';
      this.state.last = { kind: 'unit', from: ua, to: ub };
      const places = Math.abs(r) >= 1 ? 2 : 6;
      return fmtNum(v) + ' ' + UNITS[ua][3] + ' = ' + fmtNum(r, places) + ' ' + UNITS[ub][3];
    }

    // ---------------------------------------------------------- 10. continue the last article
    _continue(text, n) {
      const last = this.state.last || {};
      const t = n.toLowerCase().replace(END, '').trim();
      if (!CONTINUE.test(t)) return null;
      if (last.kind !== 'kb') return NO_PENDING;
      const [ans, nxt] = this.kb.answer(last.doc, last.q, last.next);
      if (ans === null) return 'เรื่อง "' + this.kb.docs[last.doc][1] + '" ผมมีข้อมูลเท่านี้ครับ/ค่ะ ไม่มีข้อมูลเพิ่มแล้ว';
      last.next = nxt;
      return ans + ' ' + this.kb.cite(last.doc);
    }

    // ---------------------------------------------------------- 11. small talk
    _chitchatReply(text, n) {
      const s = squash(n.toLowerCase().replace(END, ''));
      if (!s) return null;
      const sl = cpLen(s);
      let best = null, bestLen = 0;
      for (const pair of this.chitchatPairs) {
        for (const p of pair.p) {
          const ps = squash(p.toLowerCase()), pl = cpLen(ps);
          if (ps && s.includes(ps) && pl * 10 >= 5 * sl && pl > bestLen) { best = pair; bestLen = pl; }
        }
      }
      if (best === null) return null;
      let r = best.r[this.state.turns % best.r.length];
      const like = this.state.likes.length ? this.state.likes[0] : 'อะไรสักอย่าง';
      const name = this.state.name ? (' ' + call(this.state.name)) : '';
      r = rall(r, 'คุณ{name}', this.state.name ? call(this.state.name) : 'คุณ');
      return rall(rall(r, '{name}', name), '{like}', like);
    }

    // ---------------------------------------------------------- 12. knowledge
    _knowledgeReply(text, n) {
      const last = this.state.last || {};
      let q = sub('^(?:แล้ว|และ|ส่วน) *', '', n);
      q = sub(' *(?:ล่ะ|หล่ะ|ละ)(?:ครับ|คับ|ค่ะ|คะ)?$', '', q).trim();
      if (PRONOUN.test(n.toLowerCase() + ' ') && last.kind === 'kb') {
        const doc = last.doc;
        const [ans, nxt] = this.kb.answer(doc, n);
        if (ans !== null) {
          this.state.last = { kind: 'kb', doc: doc, q: n, next: nxt };
          return ans + ' ' + this.kb.cite(doc);
        }
      }
      const live = Q.test(n.toLowerCase()) && LIVE.test(n.toLowerCase());
      if (live && this.web !== null) {  // "current/latest" questions: the pack may be stale, ask the web first
        const out = this._webReply(text, q);
        if (out !== null) return out;
      }
      const hit = q ? this.kb.find(q) : null;
      if (hit === null) {
        if (this.web !== null && Q.test(n.toLowerCase()) && !this._webTried) {
          const out = this._webReply(text, q);
          if (out !== null) return out;
        }
        if (live) {
          return 'ผมไม่มีข้อมูลแบบ real-time (ราคา ข่าว ผลการแข่งขัน หรือเรื่องที่เปลี่ยนทุกวัน) ครับ/ค่ะ ' +
            'เพราะผมรัน offline และความรู้หยุดที่ Wikipedia ภาษาไทยวันที่ ' + this.kb.retrieved() + ' เลยตอบไม่ได้';
        }
        return null;
      }
      const doc = hit.doc;
      const miss = this.kb.numbersMissing(doc, n);
      const title = this.kb.docs[doc][1];
      if (miss.length) {
        return 'ผมไม่มีข้อมูลเรื่อง ' + miss.join(', ') + ' ใน "' + title + '" ครับ/ค่ะ ผมไม่รู้คำตอบ เลยไม่เดา ' +
          '(ความรู้ของผมมาจาก Wikipedia ภาษาไทยวันที่ ' + this.kb.retrieved() + ')';
      }
      const [ans, nxt] = this.kb.answer(doc, q);
      if (ans === null) return null;
      this.state.last = { kind: 'kb', doc: doc, q: q, next: nxt };
      const pre = hit.how === 'fuzzy' ? ('(คิดว่าหมายถึง "' + title + '") ') : '';
      return pre + ans + ' ' + this.kb.cite(doc);
    }

    _webReply(text, q) {
      this._webTried = true;
      const hit = this.web.search(q || text);
      if (hit === null || !hit.answer) return null;
      this.state.last = { kind: 'web', title: hit.title, url: hit.url };
      return '[ค้นเว็บ] ' + hit.answer + ' ' + WebSearch.cite(hit);
    }

    // ---------------------------------------------------------- 13. router for short commands
    _router(text, n) {
      if (cpLen(squash(n)) > 25) return null;
      const r = this._route(n);
      if (r.confidence < 0.9 || r.coverage < 0.9) return null;
      const i = r.intent;
      const last = this.state.last || {};
      if (i === 'go_on') {
        if (last.kind === 'kb') return this._continue(text, 'ต่อ');
        return NO_PENDING;
      }
      const replies = {
        refuse: 'ได้ครับ/ค่ะ ไม่ทำต่อแล้ว มีอะไรอื่นบอกได้เลย',
        fix: 'ตรงไหนผิดบอกได้เลยครับ/ค่ะ ถ้าเป็นข้อมูลของคุณ พิมพ์แก้ได้ เช่น ไม่ใช่ ผมชื่อ...',
        status: 'ตอนนี้ไม่มีงานค้างครับ/ค่ะ ผมตอบทันทีทุกข้อความ ไม่มีงานเบื้องหลัง',
        calc: 'พิมพ์โจทย์เป็นตัวเลขมาได้เลยครับ/ค่ะ เช่น 12*8 หรือ 15% ของ 200',
        forget: 'ถ้าต้องการล้างความจำทั้งหมด พิมพ์ ลืมทั้งหมด ครับ/ค่ะ',
        set_name: 'บอกชื่อมาได้เลยครับ/ค่ะ เช่น ผมชื่อ... หรือ ฉันชื่อ...',
      };
      if (Object.prototype.hasOwnProperty.call(replies, i)) return replies[i];
      if (i === 'time') return this._datetime(text, 'กี่โมง');
      if (i === 'random') return this._random(text, 'สุ่ม');
      if (i === 'get_name') return this._recall(text, 'ผมชื่ออะไร');
      const probes = { greet: 'สวัสดี', thanks: 'ขอบคุณ', who: 'เป็นใคร', help: 'ช่วยอะไรได้บ้าง', stats: 'สถิติ' };
      if (Object.prototype.hasOwnProperty.call(probes, i)) return this._social(text, probes[i]);
      return null;
    }

    // ---------------------------------------------------------- 14. honest fallback
    _unknown(text, n) {
      if (Q.test(n.toLowerCase())) {
        const base = 'ผมไม่รู้ครับ/ค่ะ ในความรู้ที่ผมมี (Wikipedia ภาษาไทย ' + commas(this.kb.count()) + ' บทความ) ' +
          'ไม่มีข้อมูลที่ตอบคำถามนี้ได้';
        if (this._webTried && this.web !== null) {
          if (this.web.lastError) return base + ' และค้นเว็บไม่สำเร็จ (' + this.web.lastError.split(':')[0] + ') ผมเลยไม่เดา';
          return base + ' ค้น Wikipedia ไทยและอังกฤษแล้วก็ไม่พบบทความที่ตรงพอ ผมเลยไม่เดา';
        }
        return base + ' ผมเลยไม่เดา';
      }
      return 'ผมยังไม่เข้าใจข้อความนี้ครับ/ค่ะ (ไม่รู้ว่าจะตอบยังไง) ลองถามความรู้ คิดเลข ถามวันเวลา ' +
        'หรือเล่าเรื่องของคุณให้ผมจำ เช่น ผมชื่อ... ผมชอบ... พิมพ์ ช่วยอะไรได้บ้าง เพื่อดูทั้งหมด';
    }
  }

  return { VERSION, Chat, Knowledge, NeedKnowledge, WebSearch, NeedWeb, emptyState,
    tools: { fmtNum, pyRepr, calcPrepare, calcEval, prettyExpr, daysFromCivil, civilFromDays, thDate, findUnits, convert, rngNext },
    knowledge: { squash, residual, qtype, chunks },
    web: { trigrams, queryText, cover, units, passages, extract: webExtract } };
}));
