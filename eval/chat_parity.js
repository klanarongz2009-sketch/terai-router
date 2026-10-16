// Runs the JS Chat (docs/chat.js) over chat eval files and prints the replies as JSON.
// usage: node eval/chat_parity.js <eval.json> [<eval.json> ...]
// Each conversation starts from an empty session with the file's fixed clock and seed, like eval/chat_eval.py.
'use strict';
const fs = require('fs');
const path = require('path');
const ROOT = path.resolve(__dirname, '..');
const DATA = path.join(ROOT, 'src', 'terai_router', 'data');
const TERAI = require(path.join(ROOT, 'docs', 'terai.js'));
const { Chat, Knowledge } = require(path.join(ROOT, 'docs', 'chat.js'));
const load = f => JSON.parse(fs.readFileSync(path.join(DATA, f), 'utf8'));
const router = TERAI.create(load('model.json'), load('typo_pairs.json'));
const chitchat = load('chitchat_th.json').pairs;
const kb = new Knowledge(load('knowledge_th.json'));
const out = {};
for (const file of process.argv.slice(2)) {
  const spec = JSON.parse(fs.readFileSync(file, 'utf8'));
  const res = [];
  for (const conv of spec.conversations) {
    const now = conv.now || spec.now;
    const seed = conv.seed != null ? conv.seed : spec.seed;
    let saved = null;
    const mk = state => new Chat({ router, chitchat, knowledge: kb, now, seed, state, onSave: s => { saved = JSON.stringify(s); } });
    let chat = mk(null);
    const replies = [];
    for (const t of conv.turns) {
      if (t.restart) chat = mk(saved ? JSON.parse(saved) : null);
      replies.push(chat.reply(t.user));
    }
    res.push(replies);
  }
  out[file] = res;
}
process.stdout.write(JSON.stringify(out));
