# TER-AI

Offline Thai intent router that tolerates typos. Small, CPU-only, no dependencies. Made with Sesame.

Live demo: https://klanarongz2009-sketch.github.io/terai-router/ · Repository: https://github.com/klanarongz2009-sketch/terai-router

TER-AI reads one Thai (or Thai-English) message and tells you what the user wants: one of 15 intents, a confidence score, and the message with common typos fixed. It runs fully offline on CPU, so it fits phones, Raspberry Pi, IoT devices and chat bots that should not send every message to a large model.

Since v0.8.0 it also ships `Chat`: an offline Thai chat that answers with real tools (calculator, date and time, unit conversion), answers knowledge questions from a bundled Thai Wikipedia pack with the source named, remembers what the user tells it across restarts, and says it does not know instead of guessing. There is no language model inside.

```
$ terai "เส็ดหรือยัง"
status  1.00  เสร็จหรือยัง
```

## Why the name

TER comes from the Thai word "เธอ" (you), and it works both ways: TER-AI calls the user เธอ, and the user calls TER-AI เธอ.

## Results (v0.8.0)

The intent model is unchanged since v0.7.0; its numbers come from `eval/results_v07.json` and `bench/typhoon_results.json` in this repo (rechecked on v0.8.0 with `python training/evaluate.py`: 121/124 and 111/112).

| | TER-AI v0.7.0 | Typhoon2 1B instruct (zero-shot) |
|---|---|---|
| Accuracy, frozen test set (124 sentences) | 97.6% (121/124) | 44.4% (55/124, 14 unparsed) |
| Mean latency per message, CPU | 0.24 ms (1 thread) | 2,325 ms (8 threads) |
| Model size | 1.1 MB | 2.49 GB download (1.24B params, float32) |

- Held-out set built before training (112 sentences): 99.1% (111/112).
- Test set by subset: clean 33/36 and 20/20, real user messages 13/13, profile typos 11/11, pattern typos 44/44.
- Typhoon model: `typhoon-ai/llama3.2-typhoon2-1b-instruct`, revision `7513a054`, greedy decoding, max 6 new tokens, system prompt listing the 15 intents. Hardware: AMD EPYC, 8 threads, torch 2.14.1+cpu, transformers 5.19.0, Python 3.13.7.
- The test set is frozen (SHA-256 in `eval/SHA256SUMS`) and never used for training. `training/leak_check.py` reports the closest training sentence for each test sentence.

Chat (v0.8.0), scored with `python eval/chat_eval.py <file>`:

| Chat eval | Turns passed | Conversations passed |
|---|---|---|
| `eval/chat_eval_v08.json` (frozen, written before the Chat code) | 81/81 | 18/18 |
| `eval/chat_heldout_v08.json` (held out) | 37/37 | 14/14 |
| `eval/chat_regress_v08.json` (regressions for bugs fixed later) | 16/16 | 3/3 |

## Install

```
pip install git+https://github.com/klanarongz2009-sketch/terai-router.git
```

From a local clone: `pip install .`

Python 3.9+, no runtime dependencies.

## Use

Command line:

```
# intent, confidence, normalized text
terai "เส็ดหรือยัง"

# JSON with the top 3 intents
terai --json "ช้วยบวก 2+3"

# one result per input line
echo "ทำต่อ" | terai -

# interactive prompt (Ctrl-D to quit)
terai

# print 'unknown' below this confidence
terai --threshold 0.5 "..."
```

Python:

```python
from terai_router import route

r = route("ช้วยบวก 2+3")
print(r["intent"], r["confidence"], r["normalized"])
# calc 0.9999 ช่วยบวก 2+3
```

`route()` returns `intent`, `confidence`, `normalized`, `coverage` (share of known features) and `ranking` (top intents with scores). More in `examples/`: `basic.py`, `bot_router.py`, `iot_switch.py`.

## Intents

`calc`, `fix`, `forget`, `get_name`, `go_on`, `greet`, `help`, `random`, `refuse`, `set_name`, `stats`, `status`, `thanks`, `time`, `who`

## Chat

`Chat` keeps one conversation: facts about the user, the history, and the context for follow-ups. Every reply comes from a rule-based step, tried in order: forget, memory questions, new facts, greeting / thanks / help, date and time, random, text tools, calculator, unit conversion, small talk, the Thai Wikipedia pack, and the intent router. When none can answer, the reply says ไม่รู้ or ไม่มีข้อมูล.

Python:

```
from terai_router import Chat

c = Chat(path='session.json')      # memory is saved to this file after every turn
c.reply('ผมชื่อบอส')               # 'ยินดีที่ได้รู้จักครับ/ค่ะ คุณบอส ผมจำชื่อไว้แล้ว'
c.reply('12*7')                    # '12 × 7 = 84'
c.reply('แล้ว 5 ล่ะ')               # '12 × 5 = 60'
c.facts                            # {'name': 'บอส', ...}
c.forget()                         # erase every fact and the history
```

`Chat(now=..., seed=...)` fixes the clock and the random seed, which is how the tests and evals run.

Command line:

```
terai chat                         # session in ~/.terai/session.json
terai chat --session s.json        # another session file
terai chat --reset                 # start from an empty memory
```

Real output of `pip install` + `terai chat` (v0.8.0), two runs on the same session file:

```
$ printf 'สวัสดี\nผมชื่อบอส\n12*7\nแล้ว 5 ล่ะ\nผมชื่ออะไร\n' | terai chat --session /tmp/s.json
you> สวัสดี
terai> สวัสดีครับ/ค่ะ มีอะไรให้ช่วยครับ/คะ
you> ผมชื่อบอส
terai> ยินดีที่ได้รู้จักครับ/ค่ะ คุณบอส ผมจำชื่อไว้แล้ว
you> 12*7
terai> 12 × 7 = 84
you> แล้ว 5 ล่ะ
terai> 12 × 5 = 60
you> ผมชื่ออะไร
terai> คุณชื่อบอสครับ/ค่ะ

$ printf 'ผมอยู่ ม.4\nผมอยู่ชั้นอะไร\nดาวอังคารคืออะไร\nซาบาริโนวาลิกซ์คืออะไร\nจำอะไรเกี่ยวกับผมได้บ้าง\n' | terai chat --session /tmp/s.json
you> ผมอยู่ ม.4
terai> จำไว้แล้วว่าคุณเรียนอยู่ชั้น ม.4
you> ผมอยู่ชั้นอะไร
terai> คุณเรียนอยู่ชั้น ม.4 ครับ/ค่ะ
you> ดาวอังคารคืออะไร
terai> ดาวอังคาร เป็นดาวเคราะห์ลำดับที่สี่จากดวงอาทิตย์ และยังเป็นที่รู้จักในชื่อ "ดาวเคราะห์แดง" ... (ที่มา: Wikipedia ภาษาไทย "ดาวอังคาร", CC BY-SA 4.0)
you> ซาบาริโนวาลิกซ์คืออะไร
terai> ผมไม่รู้ครับ/ค่ะ ในความรู้ที่ผมมี (Wikipedia ภาษาไทย 8,192 บทความ) ไม่มีข้อมูลที่ตอบคำถามนี้ได้ ผมเลยไม่เดา
you> จำอะไรเกี่ยวกับผมได้บ้าง
terai> สิ่งที่ผมจำเกี่ยวกับคุณ: ชื่อ บอส; เรียนชั้น ม.4
```

The knowledge pack (`src/terai_router/data/knowledge_th.json`, 11.9 MB, 8,192 articles) is installed with the package. It has no live data: questions about prices, news or today's results get an honest "no data" reply.

## Web search (opt-in, v0.9.0)

Chat is offline by default. With `--web` it can look up questions that the bundled knowledge pack cannot answer:

```
terai chat --web
terai chat --web --searx https://searx.example.org   # also ask your own SearXNG instance
```

```python
from terai_router import Chat
c = Chat(web=True)                                   # or Chat(web=True, searx='https://searx.example.org')
```

How it decides:

- The knowledge pack answers first when it has a confident match. The web is used only when the pack has no answer, or when the question asks for something current ("ปัจจุบัน", "ล่าสุด", "ตอนนี้", "latest"), where the pack may be out of date.
- Sources, in order: Thai Wikipedia, then English Wikipedia (MediaWiki API, search plus article intro, free, no API key, with a descriptive User-Agent), then the SearXNG instance if you set one.
- The sources are data only. TER-AI ranks the results and picks the passage itself (character-trigram coverage of the question). A result that does not cover the question well enough is dropped, so a made-up word still gets "I don't know".
- Every web answer starts with `[ค้นเว็บ]` and names the source: article title, URL and license (Wikipedia text is CC BY-SA 4.0).
- Timeout 5 seconds. Responses are cached on disk in `~/.terai/webcache` for 24 hours (at most 200 files).
- Offline or an error: Chat falls back to the knowledge pack and says that the web search failed. It never guesses.

Real output (v0.9.0, 2026-10-16):

```
$ printf 'ซาบาริโนวาลิกซ์คืออะไร\nใครคือนายกรัฐมนตรีคนปัจจุบันของญี่ปุ่น\n' | terai chat --web --session /tmp/w.json
you> ซาบาริโนวาลิกซ์คืออะไร
terai> ผมไม่รู้ครับ/ค่ะ ในความรู้ที่ผมมี (Wikipedia ภาษาไทย 8,192 บทความ) ไม่มีข้อมูลที่ตอบคำถามนี้ได้ ค้น Wikipedia ไทยและอังกฤษแล้วก็ไม่พบบทความที่ตรงพอ ผมเลยไม่เดา
you> ใครคือนายกรัฐมนตรีคนปัจจุบันของญี่ปุ่น
terai> [ค้นเว็บ] นายกรัฐมนตรีญี่ปุ่น (อังกฤษ: Prime Minister of Japan) ๆ จะดำรงตำแหน่งตามอัธยาศัยของนายกรัฐมนตรี นายกรัฐมนตรีคนปัจจุบัน คือ ซานาเอะ ทากาอิจิ ดำรงตำแหน่งตั้งแต่ 21 ตุลาคม พ.ศ. 2568 (ที่มา: Wikipedia ภาษาไทย "นายกรัฐมนตรีญี่ปุ่น", https://th.wikipedia.org/wiki/นายกรัฐมนตรีญี่ปุ่น, CC BY-SA 4.0)
```

The answer is only as current as the Wikipedia article at the time of the search, and the passage cut is not always clean (the second answer starts mid-sentence).

**Privacy:** without `--web` TER-AI never opens a network connection. With `--web` on, the question (minus question words) is sent to th.wikipedia.org and en.wikipedia.org, and to your SearXNG instance if you set one. Nothing else is sent: no session, no name, no history.

The browser demo does not have web search yet; it comes in the next part of v0.9.

## How it works

1. A normalizer fixes common Thai typos and speech-to-text errors (context rules, a guarded typo table, repeated-character collapse).
2. Character n-gram features are read from the raw text, the normalized text and a phonetic skeleton.
3. A small linear model with 8-bit weights scores the 15 intents and a softmax gives the confidence.

## Browser demo

`docs/index.html` is a single self-contained page: the model and `docs/terai.js` are inlined, so it works offline and can be hosted on GitHub Pages. Rebuild it with `python docs/build_demo.py`. `python eval/parity.py` checks that the JavaScript and Python versions agree; on the current model they give the same intent and normalized text on all 607 eval sentences (max confidence difference 6.7e-16).

The demo has two modes: the intent router and a chat mode. The chat mode runs `docs/chat.js`, a JavaScript port of `Chat`: tools, follow-ups, memory saved in the browser (localStorage, with a reset button) and knowledge answers. The knowledge pack (`docs/knowledge_th.json`, about 2.8 MB over the network with gzip) is downloaded only the first time a knowledge question is asked. `python eval/parity.py` also runs the JavaScript chat against the Python chat with a fixed clock and seed: 790 of 790 turns give identical replies (chat eval, held-out, regression and probe sets).

## Development

```
pip install -e ".[dev,train]"
pytest                          # 42 tests
python eval/chat_eval.py eval/chat_eval_v08.json   # chat eval
python training/build_knowledge.py                 # rebuild the Thai Wikipedia pack
python training/gen_data.py     # rebuild training rows
python training/train.py        # train
python training/evaluate.py     # accuracy and latency
python bench/bench_typhoon.py   # Typhoon comparison (downloads about 2.5 GB)
```

## Roadmap

v1.0 will add more languages, starting with English, each with its own training data, frozen test set and a 90% accuracy bar.

## FAQ

### Does the model have a context window?
Not in the LLM sense. The intent classifier reads one message at a time and keeps no history inside the model. `Chat` (v0.8.0) is what keeps the conversation: it stores the history (last 200 turns), the facts the user told it and the context for follow-ups such as "แล้ว 5 ล่ะ", and saves them to a JSON session file, so the memory survives a restart. There is no token limit, because there is no language model.

### Can I download the model?
Yes. Install with `pip install git+https://github.com/klanarongz2009-sketch/terai-router.git` or download this repository. The model is one 1.1 MB JSON file (`src/terai_router/data/model.json`) that runs offline on CPU, with no GPU and no internet connection.

### Why choose TER-AI?
- Built for Thai, including typos and speech-to-text errors
- 97.6% accuracy on its test set, against 44.4% for a 1B general model asked zero-shot
- About 0.24 ms per message on one CPU thread and 1.1 MB in size, so it runs on small devices
- Our own model, trained from scratch, not a wrapper around another company's model

### Where can I contact the team?
Email: klanarongz2009@gmail.com

## License

Code: MIT. Copyright (c) 2026 Clanarong Tammaketuek (Bogus).

Data: `src/terai_router/data/knowledge_th.json` is adapted from Thai Wikipedia (text by Wikipedia contributors) and is licensed under CC BY-SA 4.0. Details and the list of changes are in `DATA_LICENSE`.
