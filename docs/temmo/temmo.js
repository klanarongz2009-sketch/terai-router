/* Temmo 1.0 demo tab: BYOK game design in the browser, played by the Temmo runtime in an iframe. MIT. */
(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  if (!$('temmo-go')) return;
  const MODELS = { gemini: 'gemini-3.6-flash', openai: 'gpt-5-mini', anthropic: 'claude-sonnet-4-5', deepseek: 'deepseek-chat' };
  const SYSTEM = 'You are Temmo, a game designer for a fixed top-down maze runtime. Reply with ONE JSON object and nothing else.';
  const PROMPT = idea => 'Design a complete game for this idea: ' + idea + '\nJSON keys: title, title_th, tagline (Thai), story (Thai), gem_name, enemy_name, win_title, win_text, ' +
    'palette {bg,wall,floor,player,gem,enemy,exit as #hex}, music {menu, level as short music prompts}, ' +
    'levels: 3-5 objects {name, time 40-120, enemy_every 1-3, grid: 9 strings of 13 chars using # . P G E X H (one P, one X)}. Levels get harder.';
  const log = t => { $('temmo-log').textContent += t + '\n'; };

  async function call(provider, key, idea) {
    const model = MODELS[provider];
    if (provider === 'gemini') {
      const r = await fetch('https://generativelanguage.googleapis.com/v1beta/models/' + model + ':generateContent', { method: 'POST',
        headers: { 'x-goog-api-key': key, 'Content-Type': 'application/json' },
        body: JSON.stringify({ systemInstruction: { parts: [{ text: SYSTEM }] }, contents: [{ role: 'user', parts: [{ text: PROMPT(idea) }] }] }) });
      const d = await r.json(); if (d.error) throw new Error(d.error.message);
      return d.candidates[0].content.parts.map(p => p.text || '').join('');
    }
    if (provider === 'anthropic') {
      const r = await fetch('https://api.anthropic.com/v1/messages', { method: 'POST',
        headers: { 'x-api-key': key, 'anthropic-version': '2023-06-01', 'anthropic-dangerous-direct-browser-access': 'true', 'content-type': 'application/json' },
        body: JSON.stringify({ model, max_tokens: 3000, system: SYSTEM, messages: [{ role: 'user', content: PROMPT(idea) }] }) });
      const d = await r.json(); if (d.type === 'error') throw new Error(d.error.message);
      return d.content.filter(b => b.type === 'text').map(b => b.text).join('');
    }
    const base = provider === 'deepseek' ? 'https://api.deepseek.com' : 'https://api.openai.com/v1';
    const r = await fetch(base + '/chat/completions', { method: 'POST', headers: { Authorization: 'Bearer ' + key, 'Content-Type': 'application/json' },
      body: JSON.stringify({ model, messages: [{ role: 'system', content: SYSTEM }, { role: 'user', content: PROMPT(idea) }] }) });
    const d = await r.json(); if (d.error) throw new Error(d.error.message || JSON.stringify(d.error));
    return d.choices[0].message.content;
  }

  function firstJson(t) {
    t = String(t).replace(/```(json)?/g, '');
    for (let s = t.indexOf('{'); s !== -1; s = t.indexOf('{', s + 1)) {
      for (let e = t.lastIndexOf('}'); e > s; e = t.lastIndexOf('}', e - 1)) {
        try { return JSON.parse(t.slice(s, e + 1).replace(/,\s*([}\]])/g, '$1')); } catch (err) { /* keep looking */ }
      }
    }
    return null;
  }
  function levelOk(lv) {
    const g = lv && Array.isArray(lv.grid) ? lv.grid : null;
    if (!g || g.length < 5 || new Set(g.map(r => r.length)).size !== 1 || g.some(r => /[^#.PGEXH]/.test(r))) return false;
    const flat = g.join(''), w = g[0].length;
    if ((flat.match(/P/g) || []).length !== 1 || (flat.match(/X/g) || []).length !== 1 || !/G/.test(flat)) return false;
    const p = flat.indexOf('P'), seen = new Set([p]), q = [p];
    while (q.length) { const i = q.shift(); [1, -1, w, -w].forEach(d => { const j = i + d; if (j >= 0 && j < flat.length && !seen.has(j) && flat[j] !== '#' && !(Math.abs(d) === 1 && Math.floor(j / w) !== Math.floor(i / w))) { seen.add(j); q.push(j); } }); }
    return [...flat].every((c, i) => !'GX'.includes(c) || seen.has(i));
  }

  async function build(design) {
    const frame = $('temmo-frame');
    const sample = frame.contentWindow.TEMMO_GAME;
    const g = JSON.parse(JSON.stringify(sample));
    ['title', 'title_th', 'tagline', 'story', 'gem_name', 'enemy_name', 'win_title', 'win_text'].forEach(k => { if (typeof design[k] === 'string' && design[k].trim()) g[k] = design[k].slice(0, 160); });
    if (design.palette) Object.entries(design.palette).forEach(([k, v]) => { if (/^#[0-9a-f]{6}$/i.test(v)) g.palette[k] = v; });
    if (design.music) g.music = Object.assign({}, g.music, design.music);
    const levels = (design.levels || []).slice(0, 6), used = [];
    g.levels = sample.levels.map((s, i) => { const ok = levelOk(levels[i]); used.push(ok ? 'model' : 'sample'); return ok ? { name: String(levels[i].name || s.name), time: Math.max(40, Math.min(180, +levels[i].time || 90)), enemy_every: Math.max(1, Math.min(4, +levels[i].enemy_every || 2)), grid: levels[i].grid } : s; });
    g.id = 'byok-' + Date.now(); g.assets = { sprites: {}, voice: {} };
    log('levels: ' + used.join(', ') + ' (sample = the model grid failed the checks)');
    const files = await Promise.all(['../muml_wa_table.js', '../muml_wa.js', 'engine.js'].map(f => fetch('temmo/' + f).then(r => r.text())));
    const esc = s => s.replace(/<\/script/gi, '<\\/script');
    frame.srcdoc = '<!doctype html><meta charset="utf-8"><style>html,body{margin:0;background:' + (g.palette.bg || '#0b0d10') + '}canvas{width:100%}</style>' +
      '<canvas id="temmo" width="720" height="540"></canvas><script>' + esc(files[0]) + '<\/script><script>' + esc(files[1]) + '<\/script>' +
      '<script>if(window.MUML_WA_TABLE)MUMLWA.setTable(MUML_WA_TABLE);window.TEMMO_GAME=' + esc(JSON.stringify(g)) + ';<\/script><script>' + esc(files[2]) + '<\/script>';
  }

  $('temmo-go').addEventListener('click', async () => {
    $('temmo-log').textContent = '';
    const key = $('temmo-key').value.trim(), provider = $('temmo-provider').value, idea = $('temmo-idea').value.trim();
    if (!key) { log('Enter your API key first.'); return; }
    try {
      log('Asking ' + provider + ' (' + MODELS[provider] + ') for a GDD ...');
      const design = firstJson(await call(provider, key, idea));
      if (!design) throw new Error('reply was not JSON');
      log('Got the GDD: ' + (design.title || '?'));
      await build(design);
    } catch (e) { log('Error: ' + e.message); }
  });
})();
