// Runs the JS Chat (docs/chat.js) over chat eval files and prints the replies as JSON.
// usage: node eval/chat_parity.js <eval.json> [<eval.json> ...]
//        node eval/chat_parity.js --web <web_fixtures.json> <web_eval.json>
//   --web: web search on, every request answered from the frozen fixtures (offline=true conversations get a
//   network error), through the browser path Chat.replyAsync (roll back, fetch, run the turn again).
// Each conversation starts from an empty session with the file's fixed clock and seed, like eval/chat_eval.py.
'use strict';
const fs = require('fs');
const path = require('path');
const ROOT = path.resolve(__dirname, '..');
const DATA = path.join(ROOT, 'src', 'terai_router', 'data');
const TERAI = require(path.join(ROOT, 'docs', 'terai.js'));
const { Chat, Knowledge, WebSearch } = require(path.join(ROOT, 'docs', 'chat.js'));
const load = f => JSON.parse(fs.readFileSync(path.join(DATA, f), 'utf8'));
const router = TERAI.create(load('model.json'), load('typo_pairs.json'));
const chitchat = load('chitchat_th.json').pairs;
const kb = new Knowledge(load('knowledge_th.json'));
function webKey(url) { const u = new URL(url); return u.host + '|' + (u.searchParams.get('gsrsearch') || ''); }

async function runWeb(fixFile, file) {
  const fix = JSON.parse(fs.readFileSync(fixFile, 'utf8')).responses;
  const spec = JSON.parse(fs.readFileSync(file, 'utf8'));
  const res = [];
  for (const conv of spec.conversations) {
    const now = conv.now || spec.now;
    const seed = conv.seed != null ? conv.seed : spec.seed;
    const fetch = async url => {
      if (conv.offline) { const e = new Error('network is unreachable'); e.name = 'OfflineError'; throw e; }
      return Object.prototype.hasOwnProperty.call(fix, webKey(url)) ? fix[webKey(url)] : { batchcomplete: true };
    };
    let saved = null;
    const mk = state => new Chat({ router, chitchat, knowledge: kb, now, seed, state, onSave: s => { saved = JSON.stringify(s); },
      web: new WebSearch({ enabled: true, fetch }) });
    let chat = mk(null);
    const replies = [];
    for (const t of conv.turns) {
      if (t.restart) chat = mk(saved ? JSON.parse(saved) : null);
      replies.push(await chat.replyAsync(t.user));
    }
    res.push(replies);
  }
  return { [file]: res };
}

if (process.argv[2] === '--web') {
  runWeb(process.argv[3], process.argv[4]).then(o => process.stdout.write(JSON.stringify(o)), e => { console.error(e); process.exit(1); });
} else {
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
}
