/* TTH v0.10 text frontend in JavaScript: a line-by-line port of prepare() and chunk() in src/terai_router/tth.py.
   Same rules, same order, so the same message gives the same spoken text and the same chunks
   (checked by eval/parity.py). In the browser, speak() reads the chunks with the Web Speech API (lang th-TH),
   which uses a voice already on the device: nothing is downloaded and nothing is sent by TER-AI.
   Browser: TERAI_TTH.speak(text, {polite, rate})
   Node:    const { prepare, chunk } = require('./tth.js') */
(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.TERAI_TTH = factory();
}(typeof self !== 'undefined' ? self : this, function () {
  'use strict';
  const VERSION = '0.11.0';
  const MAX_CHARS = 90;
  const MAX_DIGITS = 15;

  const DIGITS = ['ศูนย์', 'หนึ่ง', 'สอง', 'สาม', 'สี่', 'ห้า', 'หก', 'เจ็ด', 'แปด', 'เก้า'];
  const PLACES = ['', 'สิบ', 'ร้อย', 'พัน', 'หมื่น', 'แสน'];

  function lstrip0(s) { let i = 0; while (i < s.length && s[i] === '0') i++; return s.slice(i); }

  function group(s) {
    s = lstrip0(s);
    let out = '';
    const n = s.length;
    for (let i = 0; i < n; i++) {
      const d = s.charCodeAt(i) - 48;
      const p = n - 1 - i;
      if (d === 0) continue;
      if (p === 1 && d === 1) out += 'สิบ';
      else if (p === 1 && d === 2) out += 'ยี่สิบ';
      else if (p === 0 && d === 1 && n > 1) out += 'เอ็ด';
      else out += DIGITS[d] + PLACES[p];
    }
    return out;
  }

  function readDigits(s) { let o = ''; for (const c of s) o += DIGITS[c.charCodeAt(0) - 48]; return o; }

  function readInt(s) {
    s = s.split(',').join('');
    if (s.length > MAX_DIGITS) return readDigits(s);
    let s2 = lstrip0(s);
    if (!s2) return DIGITS[0];
    if (s.length - s2.length > 0 && s.length > 1) return readDigits(s);
    let out = '';
    while (s2.length > 6) {
      const head = s2.slice(0, -6);
      s2 = s2.slice(-6);
      out += readInt(head) + 'ล้าน';
      s2 = lstrip0(s2);
      if (!s2) return out;
      if (s2.length <= 6) break;
    }
    return out + group(s2);
  }

  function readNumber(s) {
    const i = s.indexOf('.');
    if (i >= 0) return readInt(s.slice(0, i)) + 'จุด' + readDigits(s.slice(i + 1));
    return readInt(s);
  }

  const LETTERS = { A: 'เอ', B: 'บี', C: 'ซี', D: 'ดี', E: 'อี', F: 'เอฟ', G: 'จี', H: 'เอช', I: 'ไอ', J: 'เจ', K: 'เค',
    L: 'แอล', M: 'เอ็ม', N: 'เอ็น', O: 'โอ', P: 'พี', Q: 'คิว', R: 'อาร์', S: 'เอส', T: 'ที', U: 'ยู', V: 'วี',
    W: 'ดับเบิลยู', X: 'เอ็กซ์', Y: 'วาย', Z: 'แซด' };

  const LEXICON = [
    ['TER-AI', 'เธอเอไอ'], ['TER AI', 'เธอเอไอ'], ['TER', 'เธอ'], ['TTH', 'ทีทีเอช'], ['TTS', 'ทีทีเอส'],
    ['CC BY-SA', 'ซีซี บายเอสเอ'], ['Wikipedia', 'วิกิพีเดีย'], ['GitHub', 'กิตฮับ'], ['Sesame', 'เซซามี'],
    ['SearXNG', 'เซิร์ชเอ็นจี'], ['Python', 'ไพทอน'], ['JavaScript', 'จาวาสคริปต์'], ['CPU', 'ซีพียู'],
    ['GPU', 'จีพียู'], ['AI', 'เอไอ'],
  ];
  const ABBREVIATIONS = [['พ.ศ.', 'พุทธศักราช'], ['ค.ศ.', 'คริสต์ศักราช'], ['กม.', 'กิโลเมตร'], ['ซม.', 'เซนติเมตร'],
    ['มม.', 'มิลลิเมตร'], ['กก.', 'กิโลกรัม'], ['ชม.', 'ชั่วโมง'], ['ตร.', 'ตาราง'], ['ฯลฯ', 'และอื่น ๆ']];
  const SYMBOLS = [['×', ' คูณ '], ['÷', ' หาร '], ['=', ' เท่ากับ '], ['+', ' บวก '], ['−', ' ลบ '], ['√', ' รากที่สองของ '],
    ['^', ' ยกกำลัง '], ['°C', ' องศาเซลเซียส '], ['°F', ' องศาฟาเรนไฮต์ '], ['°', ' องศา '],
    ['&', ' และ '], ['%', 'เปอร์เซ็นต์ '], ['→', ' '], ['•', ' ']];

  const esc = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const LEX = LEXICON.map(([a, b]) => [new RegExp('(?<![A-Za-z0-9])' + esc(a) + '(?![A-Za-z0-9])', 'g'), b]);
  const NON_BMP = /[\uD800-\uDFFF\uFE0F\u200B-\u200D]/g;
  const CITE = /\(ที่มา: ?([^,)]*)[^)]*\)/g;
  const URL_RE = /(?:https?:\/\/|www\.)[^\s)]+/g;
  const THAI_DIGIT = /[\u0E50-\u0E59]/g;
  const MO = /(?<![\u0E00-\u0E7F])([มป])\. ?(?=[0-9])/g;
  const TIME = /(?<![0-9.:])([01]?[0-9]|2[0-3]):([0-5][0-9])(?![0-9])(?: ?น\.)?/g;
  const VERSION_RE = /(?<![0-9A-Za-z.])(v?)([0-9]+(?:\.[0-9]+){2,})(?![0-9])/g;
  const TIMES = /([0-9]) ?\* ?(?=[0-9])/g;
  const SLASH = /([0-9]) ?\/ ?(?=[0-9])/g;
  const MINUS = /([0-9]) - (?=[0-9])/g;
  const NEG = /(?<![0-9A-Za-z\u0E00-\u0E7F])-(?=[0-9])/g;
  const NUMBER = /[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?|[0-9]+(?:\.[0-9]+)?/g;
  const ACRONYM = /(?<![A-Za-z])[A-Z]{2,6}(?![A-Za-z])/g;
  const DROP = /["“”‘’'«»()\[\]{}<>*_#|\\`~]/g;
  const SPACES = /[ \t\u00A0]+/g;
  const rep = (s, a, b) => s.split(a).join(b);

  function prepare(text, polite) {
    polite = polite === undefined ? 'ครับ' : polite;
    if (polite !== 'ครับ' && polite !== 'ค่ะ') throw new Error("polite must be 'ครับ' or 'ค่ะ'");
    let t = (text || '').replace(NON_BMP, '');
    t = t.replace(CITE, (m, a) => ' ที่มา ' + a + ' ');
    t = t.replace(URL_RE, ' ');
    t = rep(t, '[ค้นเว็บ]', 'จากการค้นเว็บ');
    const [p1, p2] = polite === 'ครับ' ? ['ครับ', 'ครับ'] : ['ค่ะ', 'คะ'];
    t = rep(rep(rep(rep(t, 'ครับ/ค่ะ', p1), 'ค่ะ/ครับ', p1), 'ครับ/คะ', p2), 'คะ/ครับ', p2);
    t = t.replace(THAI_DIGIT, c => String.fromCharCode(c.charCodeAt(0) - 0x0E50 + 48));
    for (const [rx, b] of LEX) t = t.replace(rx, () => b);
    for (const [a, b] of ABBREVIATIONS) t = rep(t, a, b);
    t = t.replace(MO, (m, a) => (a === 'ม' ? 'มอ' : 'ปอ'));
    t = t.replace(TIME, (m, h, mi) => {
      let o = ' ' + readInt(String(parseInt(h, 10))) + ' นาฬิกา';
      const m2 = parseInt(mi, 10);
      if (m2) o += ' ' + readInt(String(m2)) + ' นาที';
      return o + ' ';
    });
    t = t.replace(VERSION_RE, (m, v, num) => (v ? ' เวอร์ชัน ' : ' ') + num.split('.').map(readInt).join('จุด') + ' ');
    t = t.replace(TIMES, '$1 คูณ ');
    t = t.replace(SLASH, '$1 ทับ ');
    t = t.replace(MINUS, '$1 ลบ ');
    for (const [a, b] of SYMBOLS) t = rep(t, a, b);
    t = t.replace(NEG, 'ลบ');
    t = t.replace(NUMBER, m => readNumber(m));
    t = t.replace(ACRONYM, m => { let o = ''; for (const c of m) o += LETTERS[c]; return o; });
    t = t.replace(DROP, ' ');
    t = rep(rep(t, ':', ' '), ';', ',');
    const lines = [];
    for (let line of t.split('\n')) {
      line = line.replace(SPACES, ' ').trim();
      if (line) lines.push(line);
    }
    return lines.join('\n');
  }

  const COMBINING = new Set([0x0E31, 0x0E34, 0x0E35, 0x0E36, 0x0E37, 0x0E38, 0x0E39, 0x0E3A,
    0x0E47, 0x0E48, 0x0E49, 0x0E4A, 0x0E4B, 0x0E4C, 0x0E4D, 0x0E4E].map(c => String.fromCharCode(c)));
  const LEADING = new Set([0x0E40, 0x0E41, 0x0E42, 0x0E43, 0x0E44].map(c => String.fromCharCode(c)));

  function hardSplit(piece, maxChars) {
    const out = [];
    let s = piece;
    while (s.length > maxChars) {
      let cut = maxChars;
      while (cut > 1 && (COMBINING.has(s[cut]) || LEADING.has(s[cut - 1]))) cut--;
      out.push(s.slice(0, cut));
      s = s.slice(cut);
    }
    if (s) out.push(s);
    return out;
  }

  function chunk(text, maxChars) {
    maxChars = maxChars === undefined ? MAX_CHARS : maxChars;
    if (maxChars < 8) throw new Error('max_chars must be at least 8');
    const out = [];
    for (const line of text.split('\n')) {
      let cur = '';
      for (const piece of line.split(' ')) {
        if (!piece) continue;
        const parts = piece.length > maxChars ? hardSplit(piece, maxChars) : [piece];
        for (const p of parts) {
          if (cur && cur.length + 1 + p.length > maxChars) { out.push(cur); cur = p; }
          else cur = cur ? cur + ' ' + p : p;
        }
      }
      if (cur) out.push(cur);
    }
    return out;
  }

  // ------------------------------------------------------------ browser speech (Web Speech API, th-TH)
  function available() { return typeof window !== 'undefined' && 'speechSynthesis' in window; }

  function thaiVoice() {
    if (!available()) return null;
    const vs = window.speechSynthesis.getVoices().filter(v => /^th(\b|[-_])/i.test(v.lang));
    return vs.find(v => v.localService) || vs[0] || null;
  }

  function stop() { if (available()) window.speechSynthesis.cancel(); }

  function speak(text, opts) {
    opts = opts || {};
    if (!available()) return false;
    const pieces = chunk(prepare(text, opts.polite || 'ค่ะ'), opts.maxChars);
    if (!pieces.length) return false;
    const synth = window.speechSynthesis;
    synth.cancel();
    const voice = thaiVoice();
    for (const p of pieces) {
      const u = new SpeechSynthesisUtterance(p);
      u.lang = 'th-TH';
      if (voice) u.voice = voice;
      u.rate = opts.rate || 1;
      synth.speak(u);
    }
    return true;
  }

  return { VERSION, MAX_CHARS, prepare, chunk, readInt, readNumber, available, thaiVoice, speak, stop };
}));
