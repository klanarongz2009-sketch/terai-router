/*
 * Temmo 1.0 runtime (TER-AI): a complete top-down maze game driven by a Game Design Doc (GDD).
 * The GDD and assets come from window.TEMMO_GAME (written by terai_router.temmo). MIT.
 * Screens: menu -> playing -> level clear -> (next level | victory) / game over -> high score.
 * Test hooks: window.TEMMO (state, startGame, step), URL ?bot=1 lets a BFS bot play, ?fast=1 speeds time.
 */
(function () {
  'use strict';
  const G = window.TEMMO_GAME;
  const Q = new URLSearchParams(location.search);
  const BOT = Q.get('bot') === '1', FAST = Q.get('fast') === '1';
  const KEY = 'temmo:' + (G.id || G.title);
  const errors = (window.__temmoErrors = window.__temmoErrors || []);
  window.addEventListener('error', e => errors.push(String(e.message || e)));

  // ---------- storage (save + high scores) ----------
  const store = {
    get() { try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch (e) { return {}; } },
    set(v) { try { localStorage.setItem(KEY, JSON.stringify(v)); } catch (e) { /* private mode */ } },
  };
  function saveProgress(level) { const s = store.get(); s.unlocked = Math.max(s.unlocked || 0, level); store.set(s); }
  function addHighScore(name, score, cleared) {
    const s = store.get(); s.scores = (s.scores || []).concat([{ name, score, cleared, at: Date.now() }]);
    s.scores.sort((a, b) => b.score - a.score); s.scores = s.scores.slice(0, 5); store.set(s); return s.scores;
  }

  // ---------- audio: SFX (Web Audio), music (MuML WA), voice (TTH clips) ----------
  let actx = null, muted = !!store.get().muted, songKey = '';
  function ctx() { if (!actx) { try { actx = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) { actx = null; } } return actx; }
  function sfx(kind) {
    if (muted) return; const c = ctx(); if (!c) return;
    const spec = { gem: [880, 1320, 0.09, 'square'], hit: [220, 80, 0.25, 'sawtooth'], clear: [523, 1046, 0.35, 'triangle'],
      lose: [330, 110, 0.6, 'sawtooth'], step: [140, 120, 0.03, 'triangle'], heart: [660, 990, 0.15, 'sine'], click: [600, 600, 0.05, 'square'] }[kind];
    if (!spec) return;
    const t = c.currentTime, o = c.createOscillator(), g = c.createGain();
    o.type = spec[3]; o.frequency.setValueAtTime(spec[0], t); o.frequency.exponentialRampToValueAtTime(spec[1], t + spec[2]);
    g.gain.setValueAtTime(kind === 'step' ? 0.03 : 0.12, t); g.gain.exponentialRampToValueAtTime(0.0001, t + spec[2]);
    o.connect(g).connect(c.destination); o.start(t); o.stop(t + spec[2] + 0.02);
  }
  const songs = {};
  function music(which) {
    if (songKey === which) return; songKey = which;
    const M = window.MUMLWA; if (!M) return;
    try { M.stop(); } catch (e) { /* not playing */ }
    if (muted || !which) return;
    const m = G.music || {};
    const prompt = which === 'menu' ? (m.menu || 'calm folk waltz 30 seconds') : (m.level || 'rock 140 bpm 30 seconds');
    try {
      if (!songs[which]) songs[which] = M.generate(prompt, (m.seed || 1) + (which === 'menu' ? 0 : 7), 'auto');
      M.play(songs[which]);
      musicLoop = setTimeout(() => { if (songKey === which) { songKey = ''; music(which); } }, M.songSeconds(songs[which]) * 1000);
    } catch (e) { errors.push('music: ' + e.message); }
  }
  let musicLoop = null;
  const voices = {};
  function say(line) {
    const src = (G.assets && G.assets.voice || {})[line]; if (muted || !src) return;
    try { const a = voices[line] || (voices[line] = new Audio(src)); a.currentTime = 0; const p = a.play(); if (p && p.catch) p.catch(() => {}); } catch (e) { /* autoplay */ }
  }
  function setMuted(v) { muted = v; const s = store.get(); s.muted = v; store.set(s); if (v) { clearTimeout(musicLoop); try { window.MUMLWA && MUMLWA.stop(); } catch (e) {} songKey = ''; } else music(state.screen === 'playing' ? 'level' : 'menu'); }

  // ---------- sprites ----------
  const img = {};
  Object.entries((G.assets && G.assets.sprites) || {}).forEach(([k, src]) => { const i = new Image(); i.src = src; img[k] = i; });

  // ---------- game state ----------
  const DIRS = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] };
  const state = { screen: 'menu', level: 0, score: 0, lives: 3, time: 0, steps: 0, totalSteps: 0, cleared: 0, result: null, events: [] };
  let L = null; // current level runtime
  let seed = 1;
  const rnd = () => { seed = (seed * 1664525 + 1013904223) >>> 0; return seed / 4294967296; };

  function loadLevel(i) {
    const spec = G.levels[i];
    const grid = spec.grid.map(r => r.split(''));
    const lv = { spec, grid, w: grid[0].length, h: grid.length, gems: 0, enemies: [], start: null, exit: null, inv: 0, tick: 0 };
    grid.forEach((row, y) => row.forEach((ch, x) => {
      if (ch === 'P') { lv.start = [x, y]; row[x] = '.'; }
      else if (ch === 'E') { lv.enemies.push({ x, y, d: [[1, 0], [0, 1], [-1, 0], [0, -1]][(x + y) % 4] }); row[x] = '.'; }
      else if (ch === 'G') lv.gems++;
      else if (ch === 'X') lv.exit = [x, y];
    }));
    lv.px = lv.start[0]; lv.py = lv.start[1];
    seed = (G.seed || 1) * 31 + i;
    state.time = spec.time || 90; state.steps = 0;
    L = lv;
  }
  const STEP_SEC = 0.15;
  const open = (x, y) => L && y >= 0 && y < L.h && x >= 0 && x < L.w && L.grid[y][x] !== '#' && !(L.grid[y][x] === 'X' && L.gems > 0);
  function moveEnemies() {
    const every = Math.max(1, Math.round(L.spec.enemy_every || 2));
    if (L.tick % every) return;
    L.enemies.forEach(e => {
      const turns = [e.d, [-e.d[1], e.d[0]], [e.d[1], -e.d[0]], [-e.d[0], -e.d[1]]];
      if (rnd() < 0.2) turns.splice(0, 0, turns.splice(1 + Math.floor(rnd() * 2), 1)[0]);
      for (const d of turns) { const nx = e.x + d[0], ny = e.y + d[1]; if (open(nx, ny) && L.grid[ny][nx] !== 'X') { e.x = nx; e.y = ny; e.d = d; break; } }
    });
  }
  function hitCheck() {
    if (L.inv > 0) return;
    if (L.enemies.some(e => e.x === L.px && e.y === L.py)) {
      state.lives--; sfx('hit'); state.events.push('hit'); L.inv = 12; L.px = L.start[0]; L.py = L.start[1];
      api.emit('hit');
      if (state.lives <= 0) gameOver('caught');
    }
  }
  function step(dir) {
    if (state.screen !== 'playing') return;
    L.tick++; state.steps++; state.totalSteps++;
    if (L.inv > 0) L.inv--;
    const d = DIRS[dir];
    if (d && open(L.px + d[0], L.py + d[1])) {
      L.px += d[0]; L.py += d[1];
      const c = L.grid[L.py][L.px];
      if (c === 'G') { L.grid[L.py][L.px] = '.'; L.gems--; state.score += 100; sfx('gem'); api.emit('gem'); if (!L.gems) say('exit_open'); }
      else if (c === 'H') { L.grid[L.py][L.px] = '.'; state.lives = Math.min(5, state.lives + 1); sfx('heart'); }
      else if (c === 'X' && !L.gems) return levelClear();
    }
    hitCheck(); if (state.screen !== 'playing') return;
    moveEnemies(); hitCheck(); if (state.screen !== 'playing') return;
    state.time = Math.max(0, state.time - STEP_SEC);
    api.emit('step');
    if (state.time <= 0) gameOver('time');
  }
  function startGame(level) {
    ctx(); if (actx && actx.state === 'suspended') actx.resume();
    state.level = level || 0; state.score = 0; state.lives = (G.player && G.player.lives) || 3; state.cleared = 0; state.result = null; state.totalSteps = 0;
    beginLevel();
  }
  function beginLevel() { loadLevel(state.level); state.screen = 'playing'; music('level'); say('start'); api.emit('levelStart'); }
  function levelClear() {
    state.score += Math.round(state.time) * 10 + state.lives * 50; state.cleared = state.level + 1; sfx('clear');
    saveProgress(state.cleared); state.events.push('clear:' + state.level);
    if (state.level + 1 >= G.levels.length) { state.screen = 'victory'; state.result = 'win'; say('win'); finish(); }
    else { state.screen = 'levelclear'; say('level_clear'); if (BOT) setTimeout(next, FAST ? 30 : 600); }
  }
  function next() { if (state.screen !== 'levelclear') return; state.level++; beginLevel(); }
  function gameOver(why) { state.screen = 'gameover'; state.result = 'lose:' + why; sfx('lose'); say('lose'); finish(); }
  function finish() { music('menu'); state.highscores = addHighScore(BOT ? 'BOT' : 'YOU', state.score, state.cleared); }

  // ---------- mod hook (code written by a provider, optional) ----------
  const listeners = {};
  const api = {
    on(ev, cb) { (listeners[ev] = listeners[ev] || []).push(cb); },
    emit(ev) { (listeners[ev] || []).forEach(cb => { try { cb(api); } catch (e) { errors.push('mod: ' + e.message); } }); },
    addScore(n) { state.score += Math.max(-1000, Math.min(1000, n | 0)); },
    addTime(s) { state.time = Math.max(0, state.time + Math.max(-30, Math.min(30, +s || 0))); },
    get state() { return { screen: state.screen, level: state.level, score: state.score, lives: state.lives, gems: L ? L.gems : 0, steps: state.steps }; },
    toast(t) { toast = { text: String(t).slice(0, 60), until: performance.now() + 1500 }; },
  };
  let toast = null;
  if (typeof window.TemmoMod === 'function') { try { window.TemmoMod(api); } catch (e) { errors.push('mod init: ' + e.message); } }

  // ---------- bot (BFS, avoids cells next to enemies) ----------
  function botMove() {
    const danger = new Set();
    L.enemies.forEach(e => [[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1]].forEach(d => danger.add((e.x + d[0]) + ',' + (e.y + d[1]))));
    const goal = (x, y) => L.gems ? L.grid[y][x] === 'G' : (L.exit && x === L.exit[0] && y === L.exit[1]);
    const bfs = avoid => {
      const seen = new Map([[L.px + ',' + L.py, null]]), q = [[L.px, L.py]];
      while (q.length) {
        const [x, y] = q.shift();
        if (goal(x, y) && !(x === L.px && y === L.py)) { let k = x + ',' + y, first = null; while (seen.get(k)) { first = seen.get(k); k = first[1]; } return first ? first[0] : null; }
        for (const [name, d] of Object.entries(DIRS)) {
          const nx = x + d[0], ny = y + d[1], k = nx + ',' + ny;
          if (seen.has(k) || !open(nx, ny) || (avoid && danger.has(k) && L.inv <= 0)) continue;
          seen.set(k, [name, x + ',' + y]); q.push([nx, ny]);
        }
      }
      return null;
    };
    let dir = bfs(true);
    if (!dir) { // no safe path: step to the neighbour farthest from enemies, or wait
      let best = null, bestD = -1;
      for (const [name, d] of Object.entries(DIRS)) {
        const nx = L.px + d[0], ny = L.py + d[1]; if (!open(nx, ny)) continue;
        const m = Math.min(...L.enemies.map(e => Math.abs(e.x - nx) + Math.abs(e.y - ny)), 99);
        if (m > bestD) { bestD = m; best = name; }
      }
      const here = Math.min(...L.enemies.map(e => Math.abs(e.x - L.px) + Math.abs(e.y - L.py)), 99);
      dir = bestD > here ? best : (here > 2 ? bfs(false) : null);
    }
    return dir;
  }

  // ---------- input ----------
  let held = null;
  const keymap = { ArrowUp: 'up', KeyW: 'up', ArrowDown: 'down', KeyS: 'down', ArrowLeft: 'left', KeyA: 'left', ArrowRight: 'right', KeyD: 'right' };
  addEventListener('keydown', e => {
    if (keymap[e.code]) { held = keymap[e.code]; e.preventDefault(); }
    if (e.code === 'Enter' || e.code === 'Space') { if (state.screen === 'menu') startGame(0); else if (state.screen === 'levelclear') next(); else if (state.screen === 'victory' || state.screen === 'gameover') state.screen = 'menu'; }
    if (e.code === 'KeyM') setMuted(!muted);
  });
  addEventListener('keyup', e => { if (keymap[e.code] === held) held = null; });

  // ---------- canvas + UI ----------
  const cv = document.getElementById('temmo'), g = cv.getContext('2d');
  const P = Object.assign({ bg: '#0b0d10', wall: '#2b3445', floor: '#151a22', player: '#4fd1c5', gem: '#f6c945', enemy: '#f56565', exit: '#9f7aea', ui: '#e6edf3', heart: '#ff6b9a' }, G.palette || {});
  const buttons = [];
  function btn(label, x, y, w, h, fn) { buttons.push({ x, y, w, h, fn }); g.fillStyle = P.wall; g.fillRect(x, y, w, h); g.strokeStyle = P.player; g.strokeRect(x + .5, y + .5, w - 1, h - 1); g.fillStyle = P.ui; g.font = 'bold 18px system-ui, sans-serif'; g.textAlign = 'center'; g.fillText(label, x + w / 2, y + h / 2 + 6); }
  function onTap(px, py, dirFromTouch) {
    const b = buttons.find(b => px >= b.x && px <= b.x + b.w && py >= b.y && py <= b.y + b.h);
    if (b) { sfx('click'); b.fn(); return; }
    if (state.screen === 'playing' && dirFromTouch) held = dirFromTouch;
  }
  function canvasXY(e) { const r = cv.getBoundingClientRect(); return [(e.clientX - r.left) * cv.width / r.width, (e.clientY - r.top) * cv.height / r.height]; }
  cv.addEventListener('pointerdown', e => {
    const [x, y] = canvasXY(e); const cx = cv.width / 2, cy = cv.height / 2, dx = x - cx, dy = y - cy;
    onTap(x, y, Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 'right' : 'left') : (dy > 0 ? 'down' : 'up'));
  });
  cv.addEventListener('pointerup', () => { held = null; });

  function text(t, x, y, size, color, align) { g.fillStyle = color || P.ui; g.font = (size >= 24 ? 'bold ' : '') + size + 'px system-ui, sans-serif'; g.textAlign = align || 'center'; g.fillText(t, x, y); }
  function wrap(t, x, y, maxW, size) { const words = String(t).split(/(\s+)/); let line = '', yy = y; g.font = size + 'px system-ui, sans-serif'; for (const w of words) { if (g.measureText(line + w).width > maxW && line) { text(line.trim(), x, yy, size); line = ''; yy += size + 6; } line += w; } if (line.trim()) text(line.trim(), x, yy, size); }
  function drawMenu() {
    if (img.title && img.title.complete && img.title.naturalWidth) { g.globalAlpha = 0.45; g.drawImage(img.title, 0, 0, cv.width, cv.height); g.globalAlpha = 1; }
    text(G.title, cv.width / 2, 110, 42, P.gem); if (G.title_th) text(G.title_th, cv.width / 2, 148, 22);
    wrap(G.tagline || '', cv.width / 2, 186, cv.width - 80, 16);
    const s = store.get();
    btn('Start', cv.width / 2 - 120, 240, 240, 44, () => startGame(0));
    if (s.unlocked && s.unlocked < G.levels.length) btn('Continue: level ' + (s.unlocked + 1), cv.width / 2 - 120, 294, 240, 44, () => startGame(s.unlocked));
    btn(muted ? 'Sound: off (M)' : 'Sound: on (M)', cv.width / 2 - 120, 348, 240, 44, () => setMuted(!muted));
    text('High scores', cv.width / 2, 420, 18, P.gem);
    (s.scores || []).slice(0, 5).forEach((r, i) => text((i + 1) + '. ' + r.name + '  ' + r.score + '  (level ' + r.cleared + '/' + G.levels.length + ')', cv.width / 2, 446 + i * 22, 15));
    text('Arrows/WASD or tap: collect every ' + (G.gem_name || 'gem') + ', then reach the door. Avoid ' + (G.enemy_name || 'enemies'), cv.width / 2, cv.height - 18, 13);
  }
  function drawLevel() {
    const top = 40, cs = Math.floor(Math.min(cv.width / L.w, (cv.height - top) / L.h)), ox = Math.floor((cv.width - cs * L.w) / 2);
    const cell = (k, x, y, color, shape) => {
      const X = ox + x * cs, Y = top + y * cs, im = img[k];
      if (im && im.complete && im.naturalWidth) { g.drawImage(im, X + 1, Y + 1, cs - 2, cs - 2); return; }
      g.fillStyle = color; if (shape === 'circle') { g.beginPath(); g.arc(X + cs / 2, Y + cs / 2, cs * 0.33, 0, 7); g.fill(); } else g.fillRect(X + 3, Y + 3, cs - 6, cs - 6);
    };
    for (let y = 0; y < L.h; y++) for (let x = 0; x < L.w; x++) {
      const c = L.grid[y][x]; g.fillStyle = c === '#' ? P.wall : P.floor; g.fillRect(ox + x * cs, top + y * cs, cs, cs);
      if (c === 'G') cell('gem', x, y, P.gem, 'circle');
      if (c === 'H') cell('heart', x, y, P.heart, 'circle');
      if (c === 'X') { g.globalAlpha = L.gems ? 0.35 : 1; cell('exit', x, y, P.exit); g.globalAlpha = 1; }
    }
    L.enemies.forEach(e => cell('enemy', e.x, e.y, P.enemy));
    if (!(L.inv > 0 && (L.tick % 2))) cell('player', L.px, L.py, P.player, 'circle');
    text('Level ' + (state.level + 1) + '/' + G.levels.length + ': ' + (L.spec.name || ''), 12, 26, 16, P.ui, 'left');
    text('Score ' + state.score + '   Lives ' + '♥'.repeat(Math.max(0, state.lives)) + '   Time ' + Math.ceil(state.time) + '   Left ' + L.gems, cv.width - 12, 26, 16, P.ui, 'right');
  }
  function drawEnd(title, sub) {
    text(title, cv.width / 2, 150, 40, state.result === 'win' ? P.gem : P.enemy); wrap(sub, cv.width / 2, 200, cv.width - 80, 17);
    text('Score ' + state.score + ' | cleared ' + state.cleared + '/' + G.levels.length + ' levels', cv.width / 2, 270, 20);
    (state.highscores || []).forEach((r, i) => text((i + 1) + '. ' + r.name + '  ' + r.score, cv.width / 2, 310 + i * 22, 15));
    btn('Menu', cv.width / 2 - 120, 440, 240, 44, () => { state.screen = 'menu'; });
  }
  function draw() {
    buttons.length = 0; g.fillStyle = P.bg; g.fillRect(0, 0, cv.width, cv.height);
    if (state.screen === 'menu') drawMenu();
    else if (state.screen === 'playing') drawLevel();
    else if (state.screen === 'levelclear') { drawLevel(); g.fillStyle = 'rgba(0,0,0,.6)'; g.fillRect(0, 0, cv.width, cv.height); text('Level ' + (state.level + 1) + ' clear!', cv.width / 2, 200, 36, P.gem); btn('Next level', cv.width / 2 - 120, 260, 240, 44, next); }
    else if (state.screen === 'victory') drawEnd(G.win_title || 'You win!', G.win_text || '');
    else if (state.screen === 'gameover') drawEnd('Game Over', state.result === 'lose:time' ? 'Time is up' : 'Caught');
    if (toast && performance.now() < toast.until) text(toast.text, cv.width / 2, cv.height - 40, 18, P.gem);
  }

  // ---------- loop ----------
  let acc = 0, last = performance.now();
  function frame(now) {
    const dt = Math.min(0.25, (now - last) / 1000); last = now;
    if (state.screen === 'playing') {
      acc += FAST ? STEP_SEC * 25 : dt;
      while (acc >= STEP_SEC && state.screen === 'playing') { acc -= STEP_SEC; step(BOT ? botMove() : held); }
    } else acc = 0;
    draw(); requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
  if (!BOT) setTimeout(() => music('menu'), 0);

  window.TEMMO = { get state() { return JSON.parse(JSON.stringify(Object.assign({}, state, { gems: L ? L.gems : null }))); }, startGame, next, step, store, errors, version: '1.0' };
})();
