/* SANKPUP offline generator, JavaScript port of src/terai_router/sankpup/offline.py.
 * Prompt (Thai or English) -> SVG code, no model, no network.
 * Must stay byte-identical with the Python version (tests/test_sankpup_js_parity.py).
 * Browser: needs window.SANKPUP_LEXICON (docs/sankpup-lexicon.js).
 * Node: SANKPUP.setLexicon(require(".../lexicon.json")).
 */
(function (root) {
  "use strict";
  var W = 512, GROUND_Y = 400, WATER_Y = 260, SAND_Y = 470, MAX_PROMPT = 500;
  var WS_RE = /[\t\n\v\f\r \u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+/g;
  var DEFAULT_COLORS = {
    cat: "#f76b15", dog: "#c08552", bird: "#3e63dd", fish: "#f76b15",
    butterfly: "#8e4ec6", tree: "#30a46c", flower: "#e93d82",
    house: "#f5d0a9", car: "#e5484d", boat: "#e5484d", rocket: "#e8e8ec",
    robot: "#8b8d98", sun: "#ffc53d", moon: "#f1e7c5", star: "#ffc53d",
    cloud: "#f4f4f4", mountain: "#6b7a8f", heart: "#e5484d"
  };
  var SKY = ["sun", "moon", "star", "cloud", "bird", "butterfly", "heart"];
  var GROUND_SIZE = { cat: 150, dog: 150, tree: 230, flower: 130, house: 220, car: 200, boat: 200, robot: 180, rocket: 220, fish: 100 };
  var FOOT = { car: 0.42, boat: 0.32, bird: 0.2, fish: 0.2, cloud: 0.23, heart: 0.4 };
  var SURFACE = {
    moon: -0.39, sun: -0.24, cloud: -0.2, star: -0.12, house: -0.36,
    car: -0.16, boat: 0.1, tree: -0.42, mountain: -0.4, robot: -0.36,
    dog: -0.1, cat: -0.05, rocket: -0.3, fish: -0.12, bird: -0.1,
    heart: -0.25, flower: -0.2, butterfly: -0.1
  };
  var PALETTE = ["#e5484d", "#f76b15", "#ffc53d", "#30a46c", "#5eb1ef", "#3e63dd", "#8e4ec6", "#e93d82"];
  var ABSTRACT_BG = [["#1b1145", "#3e63dd"], ["#fff1e6", "#ffd6a0"], ["#e6f6ff", "#8fd3ff"], ["#0b1d3a", "#8e4ec6"]];
  var OPACITY = ["0.5", "0.8", "1"];
  var COS6 = [1.0, 0.5, -0.5, -1.0, -0.5, 0.5];
  var SIN6 = [0.0, 0.866, 0.866, 0.0, -0.866, -0.866];
  var COS12 = [1.0, 0.866, 0.5, 0.0, -0.5, -0.866, -1.0, -0.866, -0.5, 0.0, 0.5, 0.866];
  var SIN12 = [0.0, 0.5, 0.866, 1.0, 0.866, 0.5, 0.0, -0.5, -0.866, -1.0, -0.866, -0.5];
  var COS10 = [0.0, 0.588, 0.951, 0.951, 0.588, 0.0, -0.588, -0.951, -0.951, -0.588];
  var SIN10 = [-1.0, -0.809, -0.309, 0.309, 0.809, 1.0, 0.809, 0.309, -0.309, -0.809];
  var INK = "#1d1d1f";
  var fl = Math.floor;

  var LEX = root.SANKPUP_LEXICON || null;
  var ENTRIES = null;
  function setLexicon(lex) { LEX = lex; ENTRIES = null; }
  function inSky(c) { return SKY.indexOf(c) >= 0; }

  function normalizePrompt(text) {
    text = String(text).normalize("NFC");
    var out = "";
    for (var i = 0; i < text.length; i++) {
      var code = text.charCodeAt(i);
      if (code >= 0xd800 && code <= 0xdfff) continue; // astral (surrogates) dropped
      out += text[i];
    }
    out = out.replace(WS_RE, " ").replace(/^ +| +$/g, "").toLowerCase();
    return out.slice(0, MAX_PROMPT);
  }

  function utf8(text) {
    if (typeof TextEncoder !== "undefined") return new TextEncoder().encode(text);
    return Buffer.from(text, "utf8");
  }

  function fnv1a(text) {
    var h = 0x811c9dc5, bytes = utf8(text);
    for (var i = 0; i < bytes.length; i++) {
      h ^= bytes[i];
      h = Math.imul(h, 0x01000193) >>> 0;
    }
    return h >>> 0;
  }

  function Rng(seed) { this.a = seed >>> 0; }
  Rng.prototype.next = function () {
    this.a = (this.a + 0x6d2b79f5) >>> 0;
    var t = this.a;
    t = Math.imul(t ^ (t >>> 15), t | 1) >>> 0;
    t = (t ^ ((t + (Math.imul(t ^ (t >>> 7), t | 61) >>> 0)) >>> 0)) >>> 0;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  Rng.prototype.int = function (lo, hi) { return lo + fl(this.next() * (hi - lo + 1)); };

  function hex2(v) { var s = v.toString(16); return s.length < 2 ? "0" + s : s; }
  function shade(color, amt) {
    var out = "#";
    for (var i = 1; i < 7; i += 2) {
      var v = Math.max(0, Math.min(255, parseInt(color.slice(i, i + 2), 16) + amt));
      out += hex2(v);
    }
    return out;
  }
  function luminance(color) {
    var r = parseInt(color.slice(1, 3), 16), g = parseInt(color.slice(3, 5), 16), b = parseInt(color.slice(5, 7), 16);
    return fl((r * 299 + g * 587 + b * 114) / 1000);
  }
  function esc(t) { return t.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }

  // ------------------------------------------------------------ parsing
  function entries() {
    if (ENTRIES) return ENTRIES;
    var rows = [];
    ["subjects", "colors", "relations", "sizes", "numbers"].forEach(function (kind) {
      Object.keys(LEX[kind]).forEach(function (value) {
        ["th", "en"].forEach(function (lang) {
          (LEX[kind][value][lang] || []).forEach(function (w) { rows.push([w, kind, value, lang]); });
        });
      });
    });
    ["th", "en"].forEach(function (lang) {
      (LEX.stop[lang] || []).forEach(function (w) { rows.push([w, "stop", "", lang]); });
    });
    rows.sort(function (a, b) {
      if (a[0].length !== b[0].length) return b[0].length - a[0].length;
      if (a[0] !== b[0]) return a[0] < b[0] ? -1 : 1;
      if (a[1] !== b[1]) return a[1] < b[1] ? -1 : 1;
      return 0;
    });
    ENTRIES = rows;
    return rows;
  }
  function isWord(ch) { return /^[a-z0-9]$/.test(ch); }
  function enEnd(text, start, end) {
    var n = text.length;
    if (start > 0 && isWord(text[start - 1])) return -1;
    if (end < n && text[end] === "s" && (end + 1 >= n || !isWord(text[end + 1]))) end += 1;
    else if (end + 1 < n && text.slice(end, end + 2) === "es" && (end + 2 >= n || !isWord(text[end + 2]))) end += 2;
    if (end < n && isWord(text[end])) return -1;
    return end;
  }
  function scan(text) {
    var tokens = [], n = text.length, i = 0, rows = entries();
    while (i < n) {
      var ch = text[i];
      if (ch >= "0" && ch <= "9") {
        var j = i;
        while (j < n && text[j] >= "0" && text[j] <= "9") j++;
        var v = parseInt(text.slice(i, j), 10);
        if (v >= 1 && v <= 9) {
          var k = i - 1;
          while (k >= 0 && text[k] === " ") k--;
          var lang = (k >= 0 && text[k] >= "\u0e00" && text[k] <= "\u0e7f") ? "th" : "en";
          tokens.push({ kind: "numbers", value: String(v), lang: lang, start: i, end: j });
        }
        i = j;
        continue;
      }
      var hit = null;
      for (var r = 0; r < rows.length; r++) {
        var w = rows[r][0];
        if (text.startsWith(w, i)) {
          var end = i + w.length;
          if (rows[r][3] === "en") {
            end = enEnd(text, i, end);
            if (end < 0) continue;
          }
          hit = { kind: rows[r][1], value: rows[r][2], lang: rows[r][3], start: i, end: end };
          break;
        }
      }
      if (hit) {
        if (hit.kind !== "stop") tokens.push(hit);
        i = hit.end;
      } else {
        i += 1;
      }
    }
    return tokens;
  }
  function findScenes(text) {
    var found = [];
    Object.keys(LEX.scenes).forEach(function (name) {
      var hit = false;
      ["th", "en"].forEach(function (lang) {
        (LEX.scenes[name][lang] || []).forEach(function (word) {
          var pos = text.indexOf(word);
          while (pos >= 0 && !hit) {
            if (lang === "th" || enEnd(text, pos, pos + word.length) >= 0) hit = true;
            pos = text.indexOf(word, pos + 1);
          }
        });
      });
      if (hit) found.push(name);
    });
    return found;
  }
  function parse(text) {
    var tokens = scan(text);
    var subj = [];
    tokens.forEach(function (t, p) { if (t.kind === "subjects") subj.push(p); });
    var mentions = {};
    subj.forEach(function (p) { mentions[p] = { concept: tokens[p].value, color: null, count: null, size: null }; });
    function before(p) { var c = null; subj.forEach(function (q) { if (q < p) c = q; }); return c; }
    function after(p) { for (var i = 0; i < subj.length; i++) if (subj[i] > p) return subj[i]; return null; }
    var relations = [], used = {};
    var keyOf = { colors: "color", numbers: "count", sizes: "size" };
    tokens.forEach(function (t, p) {
      var kind = t.kind;
      if (kind === "colors" || kind === "numbers" || kind === "sizes") {
        var target;
        if (t.lang === "th") { target = before(p); if (target === null) target = after(p); }
        else { target = after(p); if (target === null) target = before(p); }
        if (target === null) return;
        var key = keyOf[kind];
        if (mentions[target][key] === null) mentions[target][key] = key === "count" ? parseInt(t.value, 10) : t.value;
      } else if (kind === "relations") {
        var a = before(p), b = after(p);
        if (a === null || b === null || used[a] || used[b] || relations.length >= 2) return;
        relations.push({ kind: t.value, a: a, b: b });
        used[a] = true; used[b] = true;
      }
    });
    return {
      mentions: subj.map(function (p) { var m = mentions[p]; return { concept: m.concept, color: m.color, count: m.count, size: m.size, pos: p }; }),
      relations: relations,
      scenes: findScenes(text)
    };
  }

  // ------------------------------------------------------------ drawing
  function Pen(cx, cy, s) { this.cx = cx; this.cy = cy; this.s = s; }
  Pen.prototype.x = function (f) { return fl(this.cx + this.s * f); };
  Pen.prototype.y = function (f) { return fl(this.cy + this.s * f); };
  Pen.prototype.l = function (f) { return Math.max(1, fl(this.s * f)); };
  Pen.prototype.pts = function () {
    var out = [];
    for (var i = 0; i < arguments.length; i += 2) out.push(this.x(arguments[i]) + "," + this.y(arguments[i + 1]));
    return out.join(" ");
  };
  function eye(c) { return luminance(c) < 80 ? "#ffc53d" : INK; }

  var DRAW = {
    cat: function (p, c) {
      var o = shade(c, -60), sw = p.l(0.012), e = eye(c);
      return '<path d="M' + p.x(0.2) + ',' + p.y(0.4) + ' Q' + p.x(0.5) + ',' + p.y(0.35) + ' ' + p.x(0.42) + ',' + p.y(0.05) + '" fill="none" stroke="' + c + '" stroke-width="' + p.l(0.06) + '" stroke-linecap="round"/>' +
        '<ellipse cx="' + p.x(0) + '" cy="' + p.y(0.25) + '" rx="' + p.l(0.28) + '" ry="' + p.l(0.24) + '" fill="' + c + '" stroke="' + o + '" stroke-width="' + sw + '"/>' +
        '<ellipse cx="' + p.x(0) + '" cy="' + p.y(0.3) + '" rx="' + p.l(0.14) + '" ry="' + p.l(0.14) + '" fill="' + shade(c, 40) + '"/>' +
        '<polygon points="' + p.pts(-0.18, -0.24, -0.13, -0.45, -0.03, -0.32) + '" fill="' + c + '" stroke="' + o + '" stroke-width="' + sw + '"/>' +
        '<polygon points="' + p.pts(0.18, -0.24, 0.13, -0.45, 0.03, -0.32) + '" fill="' + c + '" stroke="' + o + '" stroke-width="' + sw + '"/>' +
        '<circle cx="' + p.x(0) + '" cy="' + p.y(-0.15) + '" r="' + p.l(0.2) + '" fill="' + c + '" stroke="' + o + '" stroke-width="' + sw + '"/>' +
        '<circle cx="' + p.x(-0.07) + '" cy="' + p.y(-0.17) + '" r="' + p.l(0.03) + '" fill="' + e + '"/>' +
        '<circle cx="' + p.x(0.07) + '" cy="' + p.y(-0.17) + '" r="' + p.l(0.03) + '" fill="' + e + '"/>' +
        '<polygon points="' + p.pts(-0.02, -0.1, 0.02, -0.1, 0, -0.08) + '" fill="#e93d82"/>' +
        '<path d="M' + p.x(-0.06) + ',' + p.y(-0.08) + ' L' + p.x(-0.25) + ',' + p.y(-0.11) + ' M' + p.x(-0.06) + ',' + p.y(-0.07) + ' L' + p.x(-0.25) + ',' + p.y(-0.04) + ' ' +
        'M' + p.x(0.06) + ',' + p.y(-0.08) + ' L' + p.x(0.25) + ',' + p.y(-0.11) + ' M' + p.x(0.06) + ',' + p.y(-0.07) + ' L' + p.x(0.25) + ',' + p.y(-0.04) + '" stroke="' + o + '" stroke-width="' + sw + '"/>';
    },
    dog: function (p, c) {
      var d = shade(c, -50), e = eye(c);
      return '<path d="M' + p.x(0.28) + ',' + p.y(0.2) + ' Q' + p.x(0.45) + ',' + p.y(0.05) + ' ' + p.x(0.4) + ',' + p.y(-0.05) + '" fill="none" stroke="' + c + '" stroke-width="' + p.l(0.05) + '" stroke-linecap="round"/>' +
        '<rect x="' + p.x(-0.22) + '" y="' + p.y(0.32) + '" width="' + p.l(0.08) + '" height="' + p.l(0.18) + '" fill="' + d + '"/>' +
        '<rect x="' + p.x(0.14) + '" y="' + p.y(0.32) + '" width="' + p.l(0.08) + '" height="' + p.l(0.18) + '" fill="' + d + '"/>' +
        '<ellipse cx="' + p.x(0.02) + '" cy="' + p.y(0.25) + '" rx="' + p.l(0.3) + '" ry="' + p.l(0.17) + '" fill="' + c + '"/>' +
        '<ellipse cx="' + p.x(-0.31) + '" cy="' + p.y(-0.06) + '" rx="' + p.l(0.06) + '" ry="' + p.l(0.13) + '" fill="' + d + '"/>' +
        '<ellipse cx="' + p.x(0.01) + '" cy="' + p.y(-0.06) + '" rx="' + p.l(0.06) + '" ry="' + p.l(0.13) + '" fill="' + d + '"/>' +
        '<circle cx="' + p.x(-0.15) + '" cy="' + p.y(-0.1) + '" r="' + p.l(0.18) + '" fill="' + c + '"/>' +
        '<ellipse cx="' + p.x(-0.15) + '" cy="' + p.y(-0.01) + '" rx="' + p.l(0.09) + '" ry="' + p.l(0.06) + '" fill="' + shade(c, 50) + '"/>' +
        '<circle cx="' + p.x(-0.15) + '" cy="' + p.y(-0.05) + '" r="' + p.l(0.03) + '" fill="' + INK + '"/>' +
        '<circle cx="' + p.x(-0.21) + '" cy="' + p.y(-0.15) + '" r="' + p.l(0.025) + '" fill="' + e + '"/>' +
        '<circle cx="' + p.x(-0.09) + '" cy="' + p.y(-0.15) + '" r="' + p.l(0.025) + '" fill="' + e + '"/>';
    },
    bird: function (p, c) {
      return '<polygon points="' + p.pts(-0.25, 0, -0.5, -0.12, -0.48, 0.12) + '" fill="' + shade(c, -40) + '"/>' +
        '<ellipse cx="' + p.x(0) + '" cy="' + p.y(0.03) + '" rx="' + p.l(0.3) + '" ry="' + p.l(0.18) + '" fill="' + c + '"/>' +
        '<circle cx="' + p.x(0.22) + '" cy="' + p.y(-0.12) + '" r="' + p.l(0.14) + '" fill="' + c + '"/>' +
        '<path d="M' + p.x(-0.14) + ',' + p.y(0) + ' Q' + p.x(0.0) + ',' + p.y(-0.32) + ' ' + p.x(0.14) + ',' + p.y(0) + ' Z" fill="' + shade(c, -40) + '"/>' +
        '<polygon points="' + p.pts(0.34, -0.16, 0.47, -0.1, 0.34, -0.06) + '" fill="#ffc53d"/>' +
        '<circle cx="' + p.x(0.25) + '" cy="' + p.y(-0.15) + '" r="' + p.l(0.025) + '" fill="' + INK + '"/>';
    },
    fish: function (p, c) {
      return '<polygon points="' + p.pts(-0.2, 0, -0.48, -0.2, -0.48, 0.2) + '" fill="' + shade(c, -40) + '"/>' +
        '<polygon points="' + p.pts(0, -0.17, 0.12, -0.3, 0.18, -0.15) + '" fill="' + shade(c, -40) + '"/>' +
        '<ellipse cx="' + p.x(0.05) + '" cy="' + p.y(0) + '" rx="' + p.l(0.35) + '" ry="' + p.l(0.2) + '" fill="' + c + '"/>' +
        '<path d="M' + p.x(0) + ',' + p.y(-0.17) + ' Q' + p.x(-0.07) + ',' + p.y(0) + ' ' + p.x(0) + ',' + p.y(0.17) + '" fill="none" stroke="' + shade(c, 70) + '" stroke-width="' + p.l(0.04) + '"/>' +
        '<circle cx="' + p.x(0.25) + '" cy="' + p.y(-0.04) + '" r="' + p.l(0.045) + '" fill="#ffffff"/>' +
        '<circle cx="' + p.x(0.26) + '" cy="' + p.y(-0.04) + '" r="' + p.l(0.022) + '" fill="' + INK + '"/>';
    },
    butterfly: function (p, c) {
      var lt = shade(c, 50);
      return '<ellipse cx="' + p.x(-0.2) + '" cy="' + p.y(-0.14) + '" rx="' + p.l(0.2) + '" ry="' + p.l(0.24) + '" fill="' + c + '"/>' +
        '<ellipse cx="' + p.x(0.2) + '" cy="' + p.y(-0.14) + '" rx="' + p.l(0.2) + '" ry="' + p.l(0.24) + '" fill="' + c + '"/>' +
        '<ellipse cx="' + p.x(-0.15) + '" cy="' + p.y(0.17) + '" rx="' + p.l(0.14) + '" ry="' + p.l(0.17) + '" fill="' + lt + '"/>' +
        '<ellipse cx="' + p.x(0.15) + '" cy="' + p.y(0.17) + '" rx="' + p.l(0.14) + '" ry="' + p.l(0.17) + '" fill="' + lt + '"/>' +
        '<circle cx="' + p.x(-0.2) + '" cy="' + p.y(-0.17) + '" r="' + p.l(0.06) + '" fill="#ffffff" fill-opacity="0.8"/>' +
        '<circle cx="' + p.x(0.2) + '" cy="' + p.y(-0.17) + '" r="' + p.l(0.06) + '" fill="#ffffff" fill-opacity="0.8"/>' +
        '<rect x="' + p.x(-0.03) + '" y="' + p.y(-0.3) + '" width="' + p.l(0.06) + '" height="' + p.l(0.6) + '" rx="' + p.l(0.03) + '" fill="' + INK + '"/>' +
        '<path d="M' + p.x(0) + ',' + p.y(-0.28) + ' Q' + p.x(-0.05) + ',' + p.y(-0.45) + ' ' + p.x(-0.15) + ',' + p.y(-0.48) + ' M' + p.x(0) + ',' + p.y(-0.28) + ' Q' + p.x(0.05) + ',' + p.y(-0.45) + ' ' + p.x(0.15) + ',' + p.y(-0.48) + '" fill="none" stroke="' + INK + '" stroke-width="' + p.l(0.015) + '"/>';
    },
    tree: function (p, c) {
      return '<rect x="' + p.x(-0.07) + '" y="' + p.y(0) + '" width="' + p.l(0.14) + '" height="' + p.l(0.5) + '" fill="#8d5a3b"/>' +
        '<circle cx="' + p.x(-0.2) + '" cy="' + p.y(-0.02) + '" r="' + p.l(0.2) + '" fill="' + shade(c, -20) + '"/>' +
        '<circle cx="' + p.x(0.2) + '" cy="' + p.y(-0.02) + '" r="' + p.l(0.2) + '" fill="' + shade(c, -20) + '"/>' +
        '<circle cx="' + p.x(0) + '" cy="' + p.y(-0.2) + '" r="' + p.l(0.3) + '" fill="' + c + '"/>' +
        '<circle cx="' + p.x(-0.08) + '" cy="' + p.y(-0.28) + '" r="' + p.l(0.1) + '" fill="' + shade(c, 40) + '" fill-opacity="0.6"/>';
    },
    flower: function (p, c) {
      var out = '<path d="M' + p.x(0) + ',' + p.y(0.5) + ' Q' + p.x(0.06) + ',' + p.y(0.2) + ' ' + p.x(0) + ',' + p.y(-0.1) + '" fill="none" stroke="#30a46c" stroke-width="' + p.l(0.04) + '"/>' +
        '<path d="M' + p.x(0.01) + ',' + p.y(0.27) + ' Q' + p.x(0.2) + ',' + p.y(0.1) + ' ' + p.x(0.27) + ',' + p.y(0.2) + ' Q' + p.x(0.16) + ',' + p.y(0.31) + ' ' + p.x(0.01) + ',' + p.y(0.27) + ' Z" fill="#30a46c"/>';
      for (var i = 0; i < 6; i++) {
        out += '<circle cx="' + p.x(0.15 * COS6[i]) + '" cy="' + p.y(-0.15 + 0.15 * SIN6[i]) + '" r="' + p.l(0.1) + '" fill="' + c + '"/>';
      }
      return out + '<circle cx="' + p.x(0) + '" cy="' + p.y(-0.15) + '" r="' + p.l(0.09) + '" fill="#ffc53d"/>';
    },
    house: function (p, c) {
      return '<rect x="' + p.x(0.18) + '" y="' + p.y(-0.4) + '" width="' + p.l(0.08) + '" height="' + p.l(0.2) + '" fill="#8b5e3c"/>' +
        '<rect x="' + p.x(-0.35) + '" y="' + p.y(-0.06) + '" width="' + p.l(0.7) + '" height="' + p.l(0.56) + '" fill="' + c + '" stroke="' + shade(c, -60) + '" stroke-width="' + p.l(0.01) + '"/>' +
        '<polygon points="' + p.pts(-0.45, -0.05, 0, -0.45, 0.45, -0.05) + '" fill="#b4442e"/>' +
        '<rect x="' + p.x(-0.08) + '" y="' + p.y(0.2) + '" width="' + p.l(0.16) + '" height="' + p.l(0.3) + '" fill="#8d5a3b"/>' +
        '<rect x="' + p.x(-0.28) + '" y="' + p.y(0.05) + '" width="' + p.l(0.14) + '" height="' + p.l(0.12) + '" fill="#bfe3ff" stroke="#ffffff" stroke-width="' + p.l(0.012) + '"/>' +
        '<rect x="' + p.x(0.14) + '" y="' + p.y(0.05) + '" width="' + p.l(0.14) + '" height="' + p.l(0.12) + '" fill="#bfe3ff" stroke="#ffffff" stroke-width="' + p.l(0.012) + '"/>';
    },
    car: function (p, c) {
      return '<polygon points="' + p.pts(-0.3, 0.06, -0.18, -0.18, 0.18, -0.18, 0.32, 0.06) + '" fill="' + shade(c, -30) + '"/>' +
        '<polygon points="' + p.pts(-0.24, 0.04, -0.15, -0.13, -0.02, -0.13, -0.02, 0.04) + '" fill="#bfe3ff"/>' +
        '<polygon points="' + p.pts(0.03, 0.04, 0.03, -0.13, 0.15, -0.13, 0.25, 0.04) + '" fill="#bfe3ff"/>' +
        '<rect x="' + p.x(-0.48) + '" y="' + p.y(0.04) + '" width="' + p.l(0.96) + '" height="' + p.l(0.25) + '" rx="' + p.l(0.06) + '" fill="' + c + '"/>' +
        '<circle cx="' + p.x(0.44) + '" cy="' + p.y(0.12) + '" r="' + p.l(0.03) + '" fill="#ffc53d"/>' +
        '<circle cx="' + p.x(-0.27) + '" cy="' + p.y(0.3) + '" r="' + p.l(0.12) + '" fill="' + INK + '"/>' +
        '<circle cx="' + p.x(-0.27) + '" cy="' + p.y(0.3) + '" r="' + p.l(0.05) + '" fill="#8b8d98"/>' +
        '<circle cx="' + p.x(0.27) + '" cy="' + p.y(0.3) + '" r="' + p.l(0.12) + '" fill="' + INK + '"/>' +
        '<circle cx="' + p.x(0.27) + '" cy="' + p.y(0.3) + '" r="' + p.l(0.05) + '" fill="#8b8d98"/>';
    },
    boat: function (p, c) {
      return '<rect x="' + p.x(-0.015) + '" y="' + p.y(-0.45) + '" width="' + p.l(0.03) + '" height="' + p.l(0.56) + '" fill="#8d5a3b"/>' +
        '<polygon points="' + p.pts(0.03, -0.42, 0.03, 0.05, 0.36, 0.05) + '" fill="#f4f4f4"/>' +
        '<polygon points="' + p.pts(-0.03, -0.32, -0.03, 0.05, -0.28, 0.05) + '" fill="#e8e8ec"/>' +
        '<polygon points="' + p.pts(-0.45, 0.1, 0.45, 0.1, 0.32, 0.32, -0.32, 0.32) + '" fill="' + c + '" stroke="' + shade(c, -60) + '" stroke-width="' + p.l(0.01) + '"/>';
    },
    rocket: function (p, c) {
      return '<polygon points="' + p.pts(-0.1, 0.3, 0, 0.5, 0.1, 0.3) + '" fill="#f76b15"/>' +
        '<polygon points="' + p.pts(-0.05, 0.3, 0, 0.42, 0.05, 0.3) + '" fill="#ffc53d"/>' +
        '<polygon points="' + p.pts(-0.12, 0.08, -0.26, 0.32, -0.12, 0.28) + '" fill="#e5484d"/>' +
        '<polygon points="' + p.pts(0.12, 0.08, 0.26, 0.32, 0.12, 0.28) + '" fill="#e5484d"/>' +
        '<path d="M' + p.x(0) + ',' + p.y(-0.48) + ' Q' + p.x(0.19) + ',' + p.y(-0.25) + ' ' + p.x(0.13) + ',' + p.y(0.3) + ' L' + p.x(-0.13) + ',' + p.y(0.3) + ' Q' + p.x(-0.19) + ',' + p.y(-0.25) + ' ' + p.x(0) + ',' + p.y(-0.48) + ' Z" fill="' + c + '" stroke="' + shade(c, -70) + '" stroke-width="' + p.l(0.01) + '"/>' +
        '<circle cx="' + p.x(0) + '" cy="' + p.y(-0.1) + '" r="' + p.l(0.07) + '" fill="#5eb1ef" stroke="#8b8d98" stroke-width="' + p.l(0.02) + '"/>';
    },
    robot: function (p, c) {
      var d = shade(c, -40);
      return '<rect x="' + p.x(-0.01) + '" y="' + p.y(-0.47) + '" width="' + p.l(0.02) + '" height="' + p.l(0.1) + '" fill="' + d + '"/>' +
        '<circle cx="' + p.x(0) + '" cy="' + p.y(-0.47) + '" r="' + p.l(0.03) + '" fill="#e5484d"/>' +
        '<rect x="' + p.x(-0.36) + '" y="' + p.y(-0.08) + '" width="' + p.l(0.1) + '" height="' + p.l(0.28) + '" rx="' + p.l(0.03) + '" fill="' + d + '"/>' +
        '<rect x="' + p.x(0.26) + '" y="' + p.y(-0.08) + '" width="' + p.l(0.1) + '" height="' + p.l(0.28) + '" rx="' + p.l(0.03) + '" fill="' + d + '"/>' +
        '<rect x="' + p.x(-0.17) + '" y="' + p.y(0.27) + '" width="' + p.l(0.12) + '" height="' + p.l(0.23) + '" fill="' + d + '"/>' +
        '<rect x="' + p.x(0.05) + '" y="' + p.y(0.27) + '" width="' + p.l(0.12) + '" height="' + p.l(0.23) + '" fill="' + d + '"/>' +
        '<rect x="' + p.x(-0.24) + '" y="' + p.y(-0.1) + '" width="' + p.l(0.48) + '" height="' + p.l(0.38) + '" rx="' + p.l(0.05) + '" fill="' + c + '"/>' +
        '<rect x="' + p.x(-0.1) + '" y="' + p.y(0) + '" width="' + p.l(0.2) + '" height="' + p.l(0.12) + '" fill="#ffc53d"/>' +
        '<rect x="' + p.x(-0.18) + '" y="' + p.y(-0.38) + '" width="' + p.l(0.36) + '" height="' + p.l(0.26) + '" rx="' + p.l(0.04) + '" fill="' + c + '"/>' +
        '<circle cx="' + p.x(-0.08) + '" cy="' + p.y(-0.27) + '" r="' + p.l(0.04) + '" fill="#5eb1ef"/>' +
        '<circle cx="' + p.x(0.08) + '" cy="' + p.y(-0.27) + '" r="' + p.l(0.04) + '" fill="#5eb1ef"/>' +
        '<rect x="' + p.x(-0.08) + '" y="' + p.y(-0.19) + '" width="' + p.l(0.16) + '" height="' + p.l(0.03) + '" fill="' + INK + '"/>';
    },
    sun: function (p, c) {
      var out = "";
      for (var i = 0; i < 12; i++) {
        out += '<line x1="' + p.x(0.32 * COS12[i]) + '" y1="' + p.y(0.32 * SIN12[i]) + '" x2="' + p.x(0.47 * COS12[i]) + '" y2="' + p.y(0.47 * SIN12[i]) + '" ' +
          'stroke="' + c + '" stroke-width="' + p.l(0.04) + '" stroke-linecap="round"/>';
      }
      return out + '<circle cx="' + p.x(0) + '" cy="' + p.y(0) + '" r="' + p.l(0.27) + '" fill="' + c + '" stroke="' + shade(c, -30) + '" stroke-width="' + p.l(0.015) + '"/>';
    },
    moon: function (p, c) {
      var d = shade(c, -25);
      return '<circle cx="' + p.x(0) + '" cy="' + p.y(0) + '" r="' + p.l(0.45) + '" fill="' + c + '"/>' +
        '<circle cx="' + p.x(-0.15) + '" cy="' + p.y(-0.08) + '" r="' + p.l(0.08) + '" fill="' + d + '"/>' +
        '<circle cx="' + p.x(0.13) + '" cy="' + p.y(0.14) + '" r="' + p.l(0.11) + '" fill="' + d + '"/>' +
        '<circle cx="' + p.x(0.17) + '" cy="' + p.y(-0.2) + '" r="' + p.l(0.05) + '" fill="' + d + '"/>' +
        '<circle cx="' + p.x(-0.2) + '" cy="' + p.y(0.22) + '" r="' + p.l(0.04) + '" fill="' + d + '"/>';
    },
    star: function (p, c) {
      var fs = [];
      for (var i = 0; i < 10; i++) {
        var r = i % 2 === 0 ? 0.5 : 0.2;
        fs.push(r * COS10[i], r * SIN10[i]);
      }
      return '<polygon points="' + Pen.prototype.pts.apply(p, fs) + '" fill="' + c + '" stroke="' + shade(c, -40) + '" stroke-width="' + p.l(0.02) + '" stroke-linejoin="round"/>';
    },
    cloud: function (p, c) {
      return '<g fill="' + c + '" fill-opacity="0.95">' +
        '<circle cx="' + p.x(-0.22) + '" cy="' + p.y(0.05) + '" r="' + p.l(0.18) + '"/>' +
        '<circle cx="' + p.x(0) + '" cy="' + p.y(-0.07) + '" r="' + p.l(0.25) + '"/>' +
        '<circle cx="' + p.x(0.22) + '" cy="' + p.y(0.05) + '" r="' + p.l(0.18) + '"/>' +
        '<rect x="' + p.x(-0.22) + '" y="' + p.y(0.04) + '" width="' + p.l(0.44) + '" height="' + p.l(0.19) + '"/></g>';
    },
    mountain: function (p, c) {
      return '<polygon points="' + p.pts(-0.5, 0.5, 0, -0.45, 0.5, 0.5) + '" fill="' + c + '"/>' +
        '<polygon points="' + p.pts(0, -0.45, 0.5, 0.5, 0.15, 0.5) + '" fill="' + shade(c, -25) + '"/>' +
        '<polygon points="' + p.pts(-0.13, -0.2, 0, -0.45, 0.13, -0.2, 0.05, -0.15, 0, -0.22, -0.05, -0.15) + '" fill="#f4f4f4"/>';
    },
    heart: function (p, c) {
      return '<path d="M' + p.x(0) + ',' + p.y(0.4) + ' C' + p.x(-0.5) + ',' + p.y(0.05) + ' ' + p.x(-0.35) + ',' + p.y(-0.42) + ' ' + p.x(0) + ',' + p.y(-0.15) + ' ' +
        'C' + p.x(0.35) + ',' + p.y(-0.42) + ' ' + p.x(0.5) + ',' + p.y(0.05) + ' ' + p.x(0) + ',' + p.y(0.4) + ' Z" fill="' + c + '" stroke="' + shade(c, -50) + '" stroke-width="' + p.l(0.015) + '"/>';
    }
  };

  function draw(concept, cx, cy, s, color) { return DRAW[concept](new Pen(cx, cy, s), color || DEFAULT_COLORS[concept]); }
  function scaled(base, size) {
    if (size === "big") return fl(base * 1.25);
    if (size === "small") return fl(base * 0.7);
    return base;
  }
  function foot(c) { return Object.prototype.hasOwnProperty.call(FOOT, c) ? FOOT[c] : 0.5; }

  // ------------------------------------------------------------ scene
  function gradient(gid, stops) {
    var out = '<linearGradient id="' + gid + '" x1="0" y1="0" x2="0" y2="1">';
    stops.forEach(function (s) { out += '<stop offset="' + s[0] + '" stop-color="' + s[1] + '"/>'; });
    return out + "</linearGradient>";
  }
  var SKY_STOPS = {
    day: [["0", "#8fd3ff"], ["1", "#e6f6ff"]],
    night: [["0", "#0b1d3a"], ["1", "#27407a"]],
    space: [["0", "#050816"], ["1", "#1b1145"]],
    sunset: [["0", "#6e4aa8"], ["0.6", "#ff8a4c"], ["1", "#ffd27a"]],
    rain: [["0", "#9aa5b1"], ["1", "#d5dbe1"]],
    snow: [["0", "#c9d6e3"], ["1", "#eef3f8"]]
  };
  var GROUND_COLOR = { day: "#7cc36b", night: "#2f4f3a", sunset: "#3b3b5c", rain: "#6f9a62", snow: "#f4f7fb", space: "#7cc36b" };

  function stars(r, n, ymax) {
    var out = "";
    for (var i = 0; i < n; i++) {
      var x = r.int(0, W - 1), y = r.int(0, ymax), rad = r.int(1, 2), op = OPACITY[r.int(0, 2)];
      out += '<circle cx="' + x + '" cy="' + y + '" r="' + rad + '" fill="#ffffff" fill-opacity="' + op + '"/>';
    }
    return out;
  }
  function abstract(r) {
    var bg = ABSTRACT_BG[r.int(0, ABSTRACT_BG.length - 1)];
    var out = "<defs>" + gradient("bg", [["0", bg[0]], ["1", bg[1]]]) + '</defs><rect width="' + W + '" height="' + W + '" fill="url(#bg)"/>';
    var n = r.int(6, 9);
    for (var i = 0; i < n; i++) {
      var kind = r.int(0, 2), col = PALETTE[r.int(0, PALETTE.length - 1)];
      var x = r.int(40, 470), y = r.int(40, 470), s = r.int(30, 110), h = fl(s / 2);
      if (kind === 0) out += '<circle cx="' + x + '" cy="' + y + '" r="' + h + '" fill="' + col + '" fill-opacity="0.85"/>';
      else if (kind === 1) out += '<rect x="' + (x - h) + '" y="' + (y - h) + '" width="' + s + '" height="' + s + '" rx="' + fl(s / 8) + '" fill="' + col + '" fill-opacity="0.85"/>';
      else out += '<polygon points="' + x + ',' + (y - h) + ' ' + (x + h) + ',' + (y + h) + ' ' + (x - h) + ',' + (y + h) + '" fill="' + col + '" fill-opacity="0.85"/>';
    }
    return out;
  }

  function stack(g, cx, cy, s) {
    var base = g.base, top = g.top;
    var out = draw(base.concept, cx, cy, s, base.color);
    var ts = scaled(fl(s * 0.45), top.size);
    var surf = Object.prototype.hasOwnProperty.call(SURFACE, base.concept) ? SURFACE[base.concept] : -0.3;
    var rest = cy + fl(s * surf);
    return out + draw(top.concept, cx, rest - fl(ts * foot(top.concept)), ts, top.color);
  }

  function compose(text, seed) {
    seed = seed || 0;
    if (!LEX) throw new Error("SANKPUP lexicon not loaded");
    var norm = normalizePrompt(text);
    var r = new Rng(fnv1a(seed ? norm + "#" + seed : norm));
    var info = parse(norm);
    var mentions = info.mentions, scenes = info.scenes;
    var concepts = mentions.map(function (m) { return m.concept; });
    var has = function (arr, v) { return arr.indexOf(v) >= 0; };
    var head = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + W + ' ' + W + '" width="' + W + '" height="' + W + '"><title>' + esc(norm) + "</title>";
    if (!mentions.length && !scenes.length) return { svg: head + abstract(r) + "</svg>", subjects: [], scenes: [], layout: "abstract" };

    var byPos = {}; mentions.forEach(function (m) { byPos[m.pos] = m; });
    var groups = [], used = {};
    info.relations.forEach(function (rel) {
      var a = byPos[rel.a], b = byPos[rel.b];
      if (rel.kind === "on") groups.push({ type: "on", top: a, base: b, concept: b.concept });
      else if (!inSky(b.concept)) groups.push({ type: "under", item: a, base: b, concept: b.concept });
      else return;
      used[rel.a] = true; used[rel.b] = true;
    });
    var multi = mentions.length > 1;
    mentions.forEach(function (m) {
      if (used[m.pos]) return;
      var n = m.count;
      if (n === null) n = (m.concept === "star" && multi) ? 4 : 1;
      for (var k = 0; k < Math.min(5, n); k++) groups.push({ type: "single", m: m, concept: m.concept });
    });

    var sky;
    if (has(scenes, "space")) sky = "space";
    else if (has(scenes, "night")) sky = "night";
    else if (has(scenes, "sunset")) sky = "sunset";
    else if (has(scenes, "rain")) sky = "rain";
    else if (has(scenes, "snow")) sky = "snow";
    else {
      sky = "day";
      var uniq = concepts.filter(function (c, i) { return concepts.indexOf(c) === i; });
      if (has(concepts, "moon") && !has(concepts, "sun")) sky = "night";
      else if (has(concepts, "rocket") && uniq.length === 1) sky = "space";
    }
    var floor;
    if (sky === "space") floor = "none";
    else if (has(scenes, "sea") || has(concepts, "fish") || (has(concepts, "boat") && !has(concepts, "car"))) floor = "sea";
    else floor = "ground";
    var hero = groups.length === 1;
    if (hero && inSky(groups[0].concept) && floor === "ground" && !scenes.length) floor = "none";

    var defs = gradient("sky", SKY_STOPS[sky]);
    if (floor === "sea") defs += gradient("water", [["0", "#4fb3e8"], ["1", "#0d4f8b"]]);
    var bg = "<defs>" + defs + '</defs><rect width="' + W + '" height="' + W + '" fill="url(#sky)"/>';
    if (sky === "night" || sky === "space") bg += stars(r, sky === "space" ? 60 : 35, floor === "none" ? W - 1 : GROUND_Y - 60);
    if (sky === "sunset") bg += '<circle cx="256" cy="' + (floor === "ground" ? GROUND_Y : WATER_Y) + '" r="70" fill="#ffb347"/>';

    var decor = "";
    if (!hero || !inSky(groups[0].concept)) {
      var hasLight = has(concepts, "sun") || has(concepts, "moon");
      if (sky === "day" && !hasLight) {
        decor += draw("sun", r.int(400, 440), r.int(70, 100), 100, null);
        decor += draw("cloud", r.int(90, 160), r.int(70, 110), r.int(100, 130), null);
      } else if (sky === "night" && !hasLight) {
        decor += draw("moon", r.int(410, 440), r.int(70, 95), 80, null);
      } else if (sky === "rain") {
        decor += draw("cloud", r.int(110, 170), r.int(60, 90), 150, "#8b8d98");
        decor += draw("cloud", r.int(330, 400), r.int(70, 100), 130, "#a0a4ad");
      }
    }

    var back = "", floorSvg = "";
    if (floor === "ground") {
      var bump = r.int(8, 20);
      floorSvg = '<path d="M0,' + GROUND_Y + ' Q128,' + (GROUND_Y - bump) + ' 256,' + GROUND_Y + ' T512,' + GROUND_Y + ' L512,512 L0,512 Z" fill="' + GROUND_COLOR[sky] + '"/>';
    } else if (floor === "sea") {
      floorSvg = '<rect x="0" y="' + WATER_Y + '" width="' + W + '" height="' + (W - WATER_Y) + '" fill="url(#water)"/>';
      for (var k = 0; k < 3; k++) {
        var wy = WATER_Y + 30 + k * 60 + r.int(0, 10);
        floorSvg += '<path d="M0,' + wy + ' Q64,' + (wy - 8) + ' 128,' + wy + ' T256,' + wy + ' T384,' + wy + ' T512,' + wy + '" fill="none" stroke="#ffffff" stroke-opacity="0.35" stroke-width="3"/>';
      }
    }

    var skySvg = "", mid = "", front = "", groundLine = GROUND_Y + 8, groundGroups = [], lights = 0;
    if (floor === "sea") {
      var hasLand = groups.some(function (g) { return !inSky(g.concept) && ["fish", "boat", "mountain"].indexOf(g.concept) < 0; });
      if (hasLand) floorSvg += '<path d="M0,' + SAND_Y + ' Q256,' + (SAND_Y - 40) + ' 512,' + SAND_Y + ' L512,512 L0,512 Z" fill="#f2d49b"/>';
      groundLine = SAND_Y + 14;
    }

    groups.forEach(function (g) {
      var c = g.concept, s, m;
      if (g.type === "single") {
        m = g.m;
        if (hero) {
          if (inSky(c) || (c === "rocket" && floor === "none")) {
            s = scaled(300, m.size);
            skySvg += draw(c, 256, 250, s, m.color);
          } else if (c === "fish" && floor === "sea") {
            mid += draw(c, 256, 390, scaled(220, m.size), m.color);
          } else if (c === "boat" && floor === "sea") {
            s = scaled(260, m.size);
            mid += draw(c, 256, WATER_Y + 30 - fl(s * 0.32), s, m.color);
          } else if (c === "mountain") {
            s = scaled(340, m.size);
            back += draw(c, 256, groundLine - fl(s * 0.5), s, m.color);
          } else {
            s = scaled(280, m.size);
            if (floor === "sea") s = fl(s * 0.7);
            front += draw(c, 256, groundLine - fl(s * foot(c)), s, m.color);
          }
          return;
        }
        if (c === "sun" || c === "moon") {
          var x = lights === 0 ? r.int(380, 430) : r.int(80, 130);
          lights += 1;
          skySvg += draw(c, x, r.int(80, 110), scaled(r.int(90, 110), m.size), m.color);
        } else if (c === "star") {
          skySvg += draw(c, r.int(30, 480), r.int(30, 200), scaled(r.int(28, 44), m.size), m.color);
        } else if (c === "cloud") {
          skySvg += draw(c, r.int(70, 440), r.int(60, 150), scaled(r.int(90, 130), m.size), m.color);
        } else if (c === "bird") {
          skySvg += draw(c, r.int(60, 450), r.int(90, 200), scaled(r.int(40, 60), m.size), m.color);
        } else if (c === "butterfly") {
          skySvg += draw(c, r.int(60, 450), r.int(230, 320), scaled(r.int(50, 70), m.size), m.color);
        } else if (c === "heart") {
          skySvg += draw(c, r.int(80, 430), r.int(80, 180), scaled(r.int(60, 90), m.size), m.color);
        } else if (c === "rocket" && floor === "none") {
          skySvg += draw(c, r.int(100, 410), r.int(120, 380), scaled(r.int(110, 150), m.size), m.color);
        } else if (c === "mountain") {
          s = scaled(r.int(220, 300), m.size);
          back += draw(c, r.int(100, 410), groundLine - fl(s * 0.5), s, m.color);
        } else if (c === "fish" && floor === "sea") {
          mid += draw(c, r.int(60, 450), r.int(WATER_Y + 60, 470), scaled(r.int(60, 90), m.size), m.color);
        } else if (c === "boat" && floor === "sea") {
          s = scaled(r.int(130, 170), m.size);
          mid += draw(c, r.int(90, 420), WATER_Y + 20 - fl(s * 0.32), s, m.color);
        } else {
          groundGroups.push(g);
        }
      } else {
        if (inSky(g.concept)) {
          var bs = hero ? 290 : 170;
          var bx = hero ? 256 : r.int(150, 360), by = hero ? 285 : 170;
          skySvg += stack(g, bx, by, bs);
        } else {
          groundGroups.push(g);
        }
      }
    });

    var n = groundGroups.length;
    if (n) {
      var scale = n <= 2 ? 1.0 : (n === 3 ? 0.8 : 0.65);
      if (floor === "sea") scale = scale * 0.7;
      var placed = [];
      groundGroups.forEach(function (g, i) {
        var base = Object.prototype.hasOwnProperty.call(GROUND_SIZE, g.concept) ? GROUND_SIZE[g.concept] : 150;
        if (hero) base = 260;
        var m = g.type === "single" ? g.m : g.base;
        var s = fl(scaled(base, m.size) * scale);
        var x = hero ? 256 : fl(W * (i + 1) / (n + 1)) + r.int(-12, 12);
        var bottom = groundLine + (hero ? 0 : r.int(0, 14));
        placed.push([s, i, g, x, bottom]);
      });
      placed.sort(function (a, b) { return a[0] !== b[0] ? b[0] - a[0] : a[1] - b[1]; });
      placed.forEach(function (t) {
        var s = t[0], g = t[2], x = t[3], bottom = t[4];
        var cy = bottom - fl(s * foot(g.concept));
        if (g.type === "single") front += draw(g.concept, x, cy, s, g.m.color);
        else if (g.type === "on") front += stack(g, x, cy, s);
        else {
          var item = g.item, isz = fl(s * 0.5);
          front += draw(g.concept, x, cy, s, g.base.color);
          front += draw(item.concept, x + fl(s * 0.22), bottom - fl(isz * foot(item.concept)), isz, item.color);
        }
      });
    }

    var weather = "";
    if (has(scenes, "rain")) {
      for (var q = 0; q < 45; q++) {
        var rx = r.int(0, W - 1), ry = r.int(0, W - 1);
        weather += '<line x1="' + rx + '" y1="' + ry + '" x2="' + (rx - 6) + '" y2="' + (ry + 18) + '" stroke="#5eb1ef" stroke-opacity="0.6" stroke-width="2"/>';
      }
    }
    if (has(scenes, "snow")) {
      for (var z = 0; z < 50; z++) {
        var sx = r.int(0, W - 1), sy = r.int(0, W - 1), sr = r.int(2, 4);
        weather += '<circle cx="' + sx + '" cy="' + sy + '" r="' + sr + '" fill="#ffffff" fill-opacity="0.9"/>';
      }
    }
    var body = bg + decor + skySvg + back + floorSvg + mid + front + weather;
    return { svg: head + body + "</svg>", subjects: concepts, scenes: scenes, layout: hero ? "hero" : "scene" };
  }

  var api = { compose: compose, generateSvg: function (p, seed) { return compose(p, seed).svg; }, normalizePrompt: normalizePrompt, fnv1a: fnv1a, setLexicon: setLexicon, parse: function (t) { return parse(normalizePrompt(t)); } };
  root.SANKPUP = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : (typeof globalThis !== "undefined" ? globalThis : this));
