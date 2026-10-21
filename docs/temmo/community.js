/* Temmo community (MIT): play, remix and share single-file Temmo games.
   Remix rules mirror src/terai_router/temmo/remix.py (tests/test_temmo_server.py checks parity with node).
   With a Temmo server URL the remix goes through its queue (free local Gemma, per-day quota);
   without one it runs the same free rule engine right here in the page. No key is ever needed. */
(function (root) {
  'use strict';
  const TEXT_FIELDS = ['title', 'title_th', 'tagline', 'win_title', 'win_text', 'gem_name', 'enemy_name'];
  const PALETTE_KEYS = ['bg', 'wall', 'floor', 'player', 'gem', 'enemy', 'exit'];
  const HEX = /^#[0-9a-fA-F]{6}$/;
  const COLORS = {
    'แดง': '#e53935', red: '#e53935', 'ส้ม': '#fb8c00', orange: '#fb8c00', 'เหลือง': '#fdd835',
    yellow: '#fdd835', 'เขียว': '#43a047', green: '#43a047', 'ฟ้า': '#4fc3f7', sky: '#4fc3f7',
    'น้ำเงิน': '#1e3a8a', blue: '#1e88e5', 'ม่วง': '#8e24aa', purple: '#8e24aa', 'ชมพู': '#f06292',
    pink: '#f06292', 'ดำ': '#0b0d10', black: '#0b0d10', 'ขาว': '#f5f5f5', white: '#f5f5f5',
    'น้ำตาล': '#6d4c41', brown: '#6d4c41', 'เทา': '#607d8b', grey: '#607d8b', gray: '#607d8b'
  };
  const PARTS = {
    'พื้นหลัง': 'bg', background: 'bg', bg: 'bg', 'กำแพง': 'wall', wall: 'wall', 'พื้น': 'floor',
    floor: 'floor', 'ผู้เล่น': 'player', 'ตัวละคร': 'player', player: 'player', 'ไอเทม': 'gem',
    'ของ': 'gem', gem: 'gem', 'ศัตรู': 'enemy', enemy: 'enemy', 'ประตู': 'exit', exit: 'exit',
    // v0.13: "enemies" and "door" ("walls", "gems"... already start with a part word)
    enemies: 'enemy', door: 'exit'
  };
  const byLen = (o) => Object.keys(o).sort((a, b) => b.length - a.length);
  const PART_WORDS = byLen(PARTS), COLOR_WORDS = byLen(COLORS);
  // a clause break between two words: "pink background, blue walls" pairs inside each clause
  const SEP = /[,;.!?\n&+]|(?:^|[^a-z])(?:and|then)(?:[^a-z]|$)|และ|แล้ว/;
  const MAX_LEVELS = 10;
  const isAscii = (w) => /^[\x00-\x7f]*$/.test(w);

  function cleanText(v, limit) {
    const s = String(v).replace(/[<>{}`\\]/g, '').trim().replace(/\s+/g, ' ');
    return Array.from(s).slice(0, limit || 80).join('');
  }

  function tokens(low) { // part and colour words, left to right (longest word first at each position)
    const toks = [];
    for (let i = 0; i < low.length;) {
      let w = PART_WORDS.find((x) => low.startsWith(x, i)), kind = 'part', table = PARTS;
      if (!w) { w = COLOR_WORDS.find((x) => low.startsWith(x, i)); kind = 'color'; table = COLORS; }
      if (w) { toks.push({ kind, val: table[w], en: isAscii(w), start: i, end: i + w.length, used: false }); i += w.length; continue; }
      i += 1;
    }
    return toks;
  }

  // Thai order and "background pink" (part, then colour) work as before v0.13: each part word takes the
  // first colour word after it. English order ("pink background", "blue walls") is read only for English
  // words: a colour right before a part word in the same clause, when that part has no colour yet.
  function palette(low) {
    const t = tokens(low);
    const sep = (a, b) => SEP.test(low.slice(a.end, b.start));
    const enPart = (j, after) => j < t.length && t[j].kind === 'part' && t[j].en && !t[j].used && !sep(after, t[j]);
    const pal = {};
    let part = null, pi = -1;
    for (let j = 0; j < t.length; j++) {
      const tok = t[j];
      if (tok.kind === 'part') { if (!tok.used) { part = tok; pi = j; } continue; }
      if (part === null) continue;
      if (tok.en && part.en) {
        const prev = pi > 0 ? t[pi - 1] : null;
        const claimed = !!(prev && prev.kind === 'color' && prev.en && !prev.used && !sep(prev, part));
        if ((sep(part, tok) || claimed) && enPart(j + 1, tok)) {
          const nxt = t[j + 1]; // "pink background, blue walls": blue goes to walls, not background
          pal[nxt.val] = tok.val; tok.used = nxt.used = true; part = null; continue;
        }
      }
      pal[part.val] = tok.val; tok.used = part.used = true; part = null;
    }
    for (let j = 0; j < t.length; j++) { // English order: colour, then its part
      const tok = t[j];
      if (tok.kind === 'color' && tok.en && !tok.used && enPart(j + 1, tok) && !(t[j + 1].val in pal)) {
        pal[t[j + 1].val] = tok.val; tok.used = t[j + 1].used = true;
      }
    }
    return pal;
  }

  function addLevels(low) {
    const m = low.match(/(?:add|plus)\s+(\d+)\s+(?:more\s+|extra\s+|new\s+)?levels?|(\d+)\s+(?:more|extra|new)\s+levels?/);
    if (m) return parseInt(m[1] || m[2], 10);
    if (/(?:more|extra|add|new)\s+levels/.test(low)) return 2;
    if (/(?:one more|another|an extra|add an?|extra|new)\s+level/.test(low)) return 1;
    return 0;
  }

  function rulePatch(instruction) {
    const s = String(instruction || '').trim(), low = s.toLowerCase(), patch = {};
    let m = s.match(/(?:ชื่อ(?:เกม)?|title)\s*[:=]?\s*["“']?([^"”'\n]{1,60})/i);
    if (m && m[1].trim()) {
      const name = cleanText(m[1], 60);
      patch[/[\u0e00-\u0e7f]/.test(name) ? 'title_th' : 'title'] = name;
    }
    m = s.match(/(?:คำโปรย|tagline)\s*[:=]?\s*["“']?([^"”'\n]{1,100})/i);
    if (m) patch.tagline = cleanText(m[1], 100);
    const pal = palette(low);
    if (Object.keys(pal).length) patch.palette = pal;
    if (/ง่ายขึ้น|ง่ายลง|easier|เวลาเพิ่ม|more time/.test(low)) { patch.time_delta = 20; patch.enemy_speed = 'slower'; }
    else if (/ยากขึ้น|harder|เวลาน้อยลง|less time/.test(low)) { patch.time_delta = -15; patch.enemy_speed = 'faster'; }
    if (/faster enem|enem[a-z]* (?:move |are |go )?faster|speed up (?:the )?enem|quicker enem/.test(low)) patch.enemy_speed = 'faster';
    else if (/slower enem|enem[a-z]* (?:move |are |go )?slower|slow down (?:the )?enem/.test(low)) patch.enemy_speed = 'slower';
    const n = addLevels(low);
    if (n) patch.add_levels = n;
    return patch;
  }

  function validatePatch(p) {
    const out = {};
    if (!p || typeof p !== 'object') return out;
    for (const k of TEXT_FIELDS) {
      if (typeof p[k] === 'string' && cleanText(p[k])) out[k] = cleanText(p[k], (k === 'tagline' || k === 'win_text') ? 100 : 60);
    }
    if (p.palette && typeof p.palette === 'object') {
      const pal = {};
      for (const [k, v] of Object.entries(p.palette)) if (PALETTE_KEYS.includes(k) && typeof v === 'string' && HEX.test(v)) pal[k] = v.toLowerCase();
      if (Object.keys(pal).length) out.palette = pal;
    }
    if ('time_delta' in p && isFinite(parseFloat(p.time_delta))) out.time_delta = Math.max(-30, Math.min(30, Math.trunc(parseFloat(p.time_delta))));
    if (p.enemy_speed === 'faster' || p.enemy_speed === 'slower') out.enemy_speed = p.enemy_speed;
    if ('add_levels' in p && Math.trunc(parseFloat(p.add_levels)) >= 1) out.add_levels = Math.min(3, Math.trunc(parseFloat(p.add_levels)));
    return out;
  }

  function applyPatch(game, patch) {
    const g = JSON.parse(JSON.stringify(game));
    patch = validatePatch(patch);
    for (const k of TEXT_FIELDS) if (k in patch) g[k] = patch[k];
    if (patch.palette) g.palette = Object.assign({}, g.palette || {}, patch.palette);
    const levels = g.levels;
    if (patch.add_levels && Array.isArray(levels) && levels.length) {
      const orig = levels.length;
      for (let k = 0; k < patch.add_levels; k++) { // a new level = an earlier one, mirrored left to right
        if (levels.length >= MAX_LEVELS) break;
        const lv = JSON.parse(JSON.stringify(levels[k % orig]));
        lv.grid = (lv.grid || []).map((row) => Array.from(String(row)).reverse().join(''));
        lv.name = String(lv.name || 'Level') + ' (mirror)';
        levels.push(lv);
      }
    }
    for (const lv of g.levels || []) {
      if ('time_delta' in patch) lv.time = Math.max(40, Math.min(180, parseInt(lv.time == null ? 90 : lv.time, 10) + patch.time_delta));
      if (patch.enemy_speed) lv.enemy_every = Math.max(1, Math.min(4, parseInt(lv.enemy_every == null ? 2 : lv.enemy_every, 10) + (patch.enemy_speed === 'slower' ? 1 : -1)));
    }
    g.remix_of = game.remix_of || game.id;
    return g;
  }

  function remix(game, instruction) {
    const patch = validatePatch(rulePatch(instruction));
    return { game: applyPatch(game, patch), patch: patch, source: 'rules' };
  }

  const GAME_LINE = /^window\.TEMMO_GAME = (.*);$/m;
  function readGame(html) {
    const m = String(html).match(GAME_LINE);
    if (!m) throw new Error('not a Temmo single-file game');
    return JSON.parse(m[1]);
  }
  function writeGame(html, game) {
    readGame(html);
    const body = JSON.stringify(game).replace(/<\/script/g, '<\\/script');
    const t = cleanText(game.title || 'Temmo', 60);
    return html.replace(GAME_LINE, () => 'window.TEMMO_GAME = ' + body + ';').replace(/<title>[\s\S]*?<\/title>/, () => '<title>' + t + '</title>');
  }

  const api = { rulePatch, validatePatch, applyPatch, remix, readGame, writeGame, cleanText };
  if (typeof module !== 'undefined' && module.exports) { module.exports = api; return; }
  root.TemmoCommunity = api;

  // ---------- page UI ----------
  const doc = root.document;
  const $ = (id) => doc.getElementById(id);
  if (!doc || !$('temmo-community')) return;
  const BASE = 'temmo/games/';
  const MINE = 'temmo.community.mine.v1';
  let current = null; // {html, game, name}
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const user = (() => { let u = localStorage.getItem('temmo.user'); if (!u) { u = 'web-' + Math.random().toString(36).slice(2, 12); localStorage.setItem('temmo.user', u); } return u; })();
  const log = (t) => { $('temmo-c-log').textContent = t; };

  function play(entry) {
    current = entry;
    $('temmo-frame').srcdoc = entry.html;
    $('temmo-now').textContent = (entry.game.title || entry.game.title_th) + (entry.game.remix_of ? '  (remix)' : '');
    $('temmo-remix-box').hidden = false;
  }

  function card(entry, mine) {
    const g = entry.game, el = doc.createElement('div');
    el.className = 'temmo-card';
    el.style.cssText = 'border:1px solid #2b3445;border-radius:8px;padding:10px;margin:6px 0;background:#121722';
    const sw = PALETTE_KEYS.map((k) => '<span title="' + k + '" style="display:inline-block;width:12px;height:12px;border-radius:3px;background:' + esc((g.palette || {})[k] || '#333') + '"></span>').join(' ');
    // The card is English: the English title and the English tagline (tagline_en in games/index.json).
    // A tagline typed in a remix is the player's own text and is shown as typed.
    const n = (g.levels || []).length;
    el.innerHTML = '<b>' + esc(g.title || g.title_th) + '</b><br><small>' + esc(entry.tagline_en || '') + '</small><br>' + sw +
      '<br><small>' + esc(entry.by || (mine ? 'my remix' : '')) + ' · ' + n + (n === 1 ? ' level' : ' levels') + '</small><br>' +
      '<button data-a="play">Play</button> <button data-a="remix">Remix</button> <button data-a="share">Share (.html)</button>';
    el.querySelector('[data-a=play]').onclick = () => play(entry);
    el.querySelector('[data-a=remix]').onclick = () => { play(entry); $('temmo-remix-text').focus(); };
    el.querySelector('[data-a=share]').onclick = () => share(entry);
    return el;
  }

  function share(entry) {
    const name = (entry.game.title || 'temmo').replace(/[^A-Za-z0-9\u0e00-\u0e7f]+/g, '-').slice(0, 40) + '.html';
    const a = doc.createElement('a');
    a.href = URL.createObjectURL(new Blob([entry.html], { type: 'text/html' }));
    a.download = name; doc.body.appendChild(a); a.click(); a.remove();
    log('Saved ' + name + ': one file that plays in any browser, offline.');
  }

  function renderMine() {
    const box = $('temmo-mine'); box.innerHTML = '';
    const mine = JSON.parse(localStorage.getItem(MINE) || '[]');
    if (!mine.length) { box.innerHTML = '<small>No remixes yet</small>'; return; }
    for (const e of mine) box.appendChild(card(e, true));
  }

  async function serverRemix(url, game, text) {
    const r = await fetch(url.replace(/\/$/, '') + '/api/remix', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user: user, game: game, instruction: text }) });
    let st = await r.json();
    if (!r.ok) throw new Error(st.message || st.error);
    for (let i = 0; i < 120 && st.state !== 'done' && st.state !== 'failed'; i++) {
      log('Queue position ' + (st.position || '-') + ' · remixes left today: ' + (st.left == null ? '?' : st.left));
      await new Promise((ok) => setTimeout(ok, 1500));
      st = await (await fetch(url.replace(/\/$/, '') + '/api/job?id=' + st.id)).json();
    }
    if (st.state !== 'done') throw new Error(st.error || 'timeout');
    return st.result;
  }

  $('temmo-remix-go').onclick = async () => {
    if (!current) return;
    const text = $('temmo-remix-text').value.trim();
    if (!text) { log('Type what you want to change first.'); return; }
    const url = $('temmo-server').value.trim();
    let res;
    try { res = url ? await serverRemix(url, current.game, text) : remix(current.game, text); }
    catch (e) { log('The server did not answer (' + e.message + '); using the remix rules in this page instead.'); res = remix(current.game, text); }
    if (!Object.keys(res.patch).length) { log('Found nothing to change. Try e.g. "pink background, harder" or title "..."'); return; }
    const entry = { html: writeGame(current.html, res.game), game: res.game, by: 'remix (' + res.source + ')',
      tagline_en: res.patch.tagline || current.tagline_en || '' };
    const mine = JSON.parse(localStorage.getItem(MINE) || '[]');
    mine.unshift(entry); localStorage.setItem(MINE, JSON.stringify(mine.slice(0, 5)));
    renderMine(); play(entry);
    log('Remixed (' + res.source + '): ' + JSON.stringify(res.patch));
  };
  $('temmo-share-now').onclick = () => current && share(current);

  fetch(BASE + 'index.json').then((r) => r.json()).then(async (list) => {
    const box = $('temmo-community'); box.innerHTML = '';
    for (const it of list.games) {
      const html = await (await fetch(BASE + it.file)).text();
      const entry = { html: html, game: readGame(html), by: it.by, tagline_en: it.tagline_en || '' };
      box.appendChild(card(entry, false));
      if (!current) play(entry);
    }
    renderMine();
  }).catch((e) => log('Could not load the game list: ' + e.message));
})(typeof window !== 'undefined' ? window : globalThis);
