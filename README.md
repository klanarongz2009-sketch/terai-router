# TER-AI

[Thai version](README.th.md)

> **Limited-time trial: TERM AI, the original Terminal AI, is back until 2027-01-01 00:00:00 Asia/Bangkok (UTC+7).** Try it with `terai term` ([v0.14.0](https://github.com/klanarongz2009-sketch/terai-router/releases/tag/v0.14.0), [announcement](https://github.com/klanarongz2009-sketch/terai-router/issues/6)). At that moment it stops running and is removed from the repository. [Details](#term-ai-the-original-terminal-ai-limited-time-trial-v0140)

TER-AI is a free set of Thai AI tools that runs offline on an ordinary CPU, with no GPU and no cloud API. Made with Sesame.

What is released today (v0.16.0):

| Part | What it does | Since |
|---|---|---|
| Intent router | Reads one Thai or Thai-English message, fixes common typos and returns one of 15 intents with a confidence score. 1.1 MB model, no dependencies. | v0.7.0 |
| Chat | Offline Thai chat. Since v0.16.0 the replies are written by the local model **TERAI1BETA** (Gemma 4 E2B on CPU); the old rules (calculator, date and time, unit conversion, memory, the bundled Thai Wikipedia pack) are its tools, every fact names its source, and it says "I don't know" when no source has the answer. It can also read images (`terai chat --image`). Without the model it falls back to the rule chat. Optional Wikipedia web search since v0.9.0. | v0.8.0 (model v0.16.0) |
| TTH | Reads Thai aloud with a local open-weight voice model (Wayu-Paxa-TTS-Edge), with edge-tts as an online fallback. Both optional. | v0.10.0 |
| SANKPUP | Makes pictures by writing SVG code (local Gemma 4 or a built-in offline generator), sanitizes it and renders PNG or JPG. Not an image model. | v0.11.0 |
| MuML 1.0 WA | Writes and plays music in the browser from a Thai or English prompt. Since v0.15.0 the notes come from the trained MuML 1.0 network (3.3M-parameter transformer, int8 weights 3.4 MB, run in JavaScript); Markov v1 is the fallback. Every sound is made by the Web Audio API. | v0.12.0, network v0.15.0 |
| MUML 1.0 HIQ | Text-to-music audio (.mp3/.wav) on CPU from a Thai or English prompt, with optional lyrics. ACE-Step 1.5 for instrumentals and English songs, YuE2-3B for Thai lyrics; weights download once with `--setup`. Slow on CPU, Thai lyrics only partly intelligible. | v0.13.0 |
| TERM AI (limited-time trial) | The original Terminal AI that TER-AI grew from: a Thai terminal chatbot made of rules plus the first own model, TER-AI-0.5. Offline, no dependencies. **Trial: stops working at 2027-01-01 00:00:00 Asia/Bangkok (UTC+7) and will be removed from the repository then.** | v0.14.0 |

Live demo: https://klanarongz2009-sketch.github.io/terai-router/ · Repository: https://github.com/klanarongz2009-sketch/terai-router · Wiki: https://github.com/klanarongz2009-sketch/terai-router/wiki

Licenses differ by part: the code is MIT, but some data and optional models are not. Check the [license table](#license) before commercial use.

> **Project notice:** TER-AI is an indie project and may pause or close with little warning. Read the [project notice](PROJECT_NOTICE.md).

```
$ terai "เส็ดหรือยัง"
status  1.00  เสร็จหรือยัง
```

## Versions: repository and models

The repository version and the model versions are separate. MuML 1.0 was the first model with its own id (v0.15.0); v0.16.0 writes the scheme down for every model.

- **Repository (package) version:** `0.X.Y`; this release is v0.16.0. It moves with every release. The criteria for the repository's own 1.0 are unchanged (see Roadmap).
- **Model id:** each model has its own name and version, written exactly as below. A package release never changes a model id, and the "1.0" in a model id is not the repository's 1.0.

| Model id | What it is | Since |
|---|---|---|
| TERAI1BETA | Chat model: local Gemma 4 E2B writes the replies, TER-AI's rules are its tools, reads images | v0.16.0 |
| MuML 1.0 | Note writer behind MuML 1.0 WA (trained network `muml-1.0-net` since v0.15.0) | v0.12.0 |
| MUML 1.0 HIQ | Text-to-music audio | v0.13.0 |
| Temmo 1.0 | Small indie game maker (prototype, not released) | - |
| TER-AI-0.5 | Intent model inside TERM AI (limited-time trial) | v0.14.0 |

`terai --version` prints both, for example `terai-router 0.16.0 / model TERAI1BETA`, and `terai models` lists every model id. The rule lives in `src/terai_router/versions.py`; a new version of one model changes only its own row there.

## Why the name

TER comes from the Thai word "เธอ" (you), and it works both ways: TER-AI calls the user เธอ, and the user calls TER-AI เธอ.

## Results (v0.16.0, measured 2026-10-22)

Run on the v0.16.0 code with the scripts in this repo. Machine: AMD EPYC, 8 cores, no GPU, Python 3.13.7.

| Check | Command | Result |
|---|---|---|
| Intent accuracy, frozen test set (124 sentences) | `python training/evaluate.py` | 97.6% (121/124), 0.169 ms per message (1 thread) |
| Intent accuracy, held-out set (112 sentences) | `python training/evaluate.py` | 99.1% (111/112), 0.26 ms per message (1 thread) |
| Chat eval, frozen (written before the Chat code) | `python eval/chat_eval.py eval/chat_eval_v08.json` | 81/81 turns, 18/18 conversations |
| Chat eval, held out | `python eval/chat_eval.py eval/chat_heldout_v08.json` | 37/37 turns, 14/14 conversations |
| Chat regressions (bugs fixed later) | `python eval/chat_eval.py eval/chat_regress_v08.json` | 16/16 turns, 3/3 conversations |
| Browser vs Python, intent router | `python eval/parity.py` | 607/607 sentences same intent and text, max confidence difference 6.66e-16 |
| Browser vs Python, chat | `python eval/parity.py` | 790/790 turns identical; 24/24 with mocked web search |
| Browser vs Python, TTH text frontend | `python eval/parity.py` | 1,700/1,700 checks identical |
| Browser vs Python, SANKPUP offline generator | `python eval/parity.py` | 688/688 checks identical (byte-identical SVG) |
| Browser vs Python, MuML 1.0 WA | `python eval/parity.py` | Markov v1 330/330 and MuML 1.0 network 30/30 songs identical (tokens, notes and `.mid` bytes); web note table matches `markov.json` byte for byte |
| Browser vs Python, Temmo remix rules | `python eval/parity.py` | 42/42 cases identical |
| TERM AI intent model (trial), leave-one-out on its 149 training sentences | `python -m terai_router.term_ai.intent_model eval` | 67.8% (101/149) |
| Chat model TERAI1BETA vs the rule chat, fixed set of 52 cases | `python eval/brain_eval.py --engine both` | correct 30/30 vs 22/30, hallucination 1/52 vs 1/52; details in [TERAI1BETA](#terai1beta-the-model-writes-the-replies-v0160) |
| Unit tests | `pytest` | 367 passed, 6 skipped (real speech and real model runs, opt-in) |

MUML 1.0 HIQ end to end (measured 2026-10-21 for v0.13.0, unchanged since; same machine, 8 vCPU, 8 GB RAM, `/usr/bin/time -v`). Thai test song: 4 lyric lines, seed 42, YuE2-3B Q5_K_M, 32 steps. CER is measured with the Thai ASR `airesearch/wav2vec2-large-xlsr-53-th` on the mixed song (music not separated), so it is a rough intelligibility signal, not a lyrics score:

| Run | Wall time | Peak RSS | CER | Lyric words heard |
|---|---|---|---|---|
| Thai lyrics, yue2, no `--duration` (90 s planned, song ended on its own at 50.6 s, 2.5 s fade-out) | 24:53 | 2.93 GB | 0.8598 | 14/30, from all 4 lines |
| Thai lyrics, yue2, `--duration 30` (before the fix: cut mid-phrase) | 14:03 | 2.93 GB | 0.9065 | 4/30 |
| Thai lyrics, split (ACE-Step instrumental + TTH Wayu speech, snap style; speech on a beat, not singing) | 5:44 | 3.33 GB | 0.2430 | 20/30 |
| English song on ACE-Step (reference floor: no Thai in it) | - | - | 0.8131 | 3/30 |

The fade-out took the last 0.25 s of the 90 s run from -23.8 dB to -73.1 dB. `--setup` on a clean machine (no binaries, no weights): about 3 GB of YuE2 GGUF downloaded, yue-synth built in 36 s; the downloaded files matched the reference SHA-256. More numbers and the ACE-Step variants: [docs/MUML-HIQ.md](docs/MUML-HIQ.md).

Test set by subset: clean 33/36 and 20/20, real user messages 13/13, profile typos 11/11, pattern typos 44/44. The test set is frozen (SHA-256 in `eval/SHA256SUMS`) and never used for training; `training/leak_check.py` reports the closest training sentence for each test sentence. Latency depends on the machine and its load.

Earlier results, not rerun for v0.12.0 (they need large downloads):

- **Against a 1B general model (v0.7.0 result).** The intent model has not changed since v0.7.0. Sources: `eval/results_v07.json` and `bench/typhoon_results.json`.

| | TER-AI v0.7.0 | Typhoon2 1B instruct (zero-shot) |
|---|---|---|
| Accuracy, frozen test set (124 sentences) | 97.6% (121/124) | 44.4% (55/124, 14 unparsed) |
| Mean latency per message, CPU | 0.24 ms (1 thread) | 2,325 ms (8 threads) |
| Model size | 1.1 MB | 2.49 GB download (1.24B params, float32) |

  Typhoon model: `typhoon-ai/llama3.2-typhoon2-1b-instruct`, revision `7513a054`, greedy decoding, max 6 new tokens, system prompt listing the 15 intents. Hardware: AMD EPYC, 8 threads, torch 2.14.1+cpu, transformers 5.19.0, Python 3.13.7. Reproduce with `python bench/bench_typhoon.py` (downloads about 2.5 GB).

- **SANKPUP with Gemma 4 E2B (v0.11.0 result).** 11 of 12 prompts gave a valid picture (Thai 5/6, English 6/6); time per picture p50 24.2 s, p95 49.1 s; model load 38 to 125 s, on an 8-core CPU with 8 GB RAM and no GPU. Details in [SANKPUP](#sankpup-pictures-from-code-v0110). Reproduce with `python eval/sankpup_gemma_bench.py --model e2b` (needs the `sankpup-gemma` extra and the Gemma 4 E2B weights).

## Install

```
pip install git+https://github.com/klanarongz2009-sketch/terai-router.git
```

From a local clone: `pip install .`

Python 3.9+, no runtime dependencies for the intent router and the rule Chat. TERAI1BETA (extra `llm`), TTH and SANKPUP have optional extras, described in their sections. MUML 1.0 HIQ needs no Python extra, but `terai muml --hiq --setup` needs git, cmake and a C++17 compiler to build its engines, and ffmpeg for .mp3 output and the fade-out.

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

### TERAI1BETA: the model writes the replies (v0.16.0)

Before v0.16.0 every chat reply came from a fixed template, so replies sounded scripted (the same words for the same kind of message). TERAI1BETA keeps the rules but moves them behind a local language model:

1. The rules pick a tool and run it: calculator, date and time, unit conversion, memory, the bundled Thai Wikipedia pack (and Wikipedia web search with `--web`).
2. Gemma 4 E2B (official QAT Q4_0 GGUF, CPU only, through llama-cpp-python) writes the reply from the tool result in natural Thai, or English when you write in English.
3. A grounding check reads the reply: every number must come from a tool result, your message or the memory; the calculator's result must be in it; a knowledge reply must overlap its source and names the source ("ที่มา: Wikipedia ..."). With no source the model must say it does not know. A reply that fails gets one retry, then the rule answer is used.

```
pip install "terai-router[llm] @ git+https://github.com/klanarongz2009-sketch/terai-router.git@v0.16.0"
terai chat --setup                       # once: about 4.3 GB (3.35 GB model + 0.99 GB vision projector), SHA-256 checked
terai chat                               # TERAI1BETA when installed, else the rule chat
terai chat --image menu.png              # ask about an image first, then keep chatting
terai vision sign.jpg                    # describe the image and read its Thai/English text
terai vision receipt.png "ยอดรวมเท่าไร"   # answer a question about the image
terai chat --brain rules                 # the rule chat only (v0.8.0 to v0.14.0 behaviour)
terai chat --trace                       # show which tool answered and the grounding check
```

Weights go to `~/.cache/terai/models` (or `TERAI_MODELS_DIR`); `TERAI_THREADS` or `--threads` sets CPU threads. `--model e4b` uses Gemma 4 E4B (4.9 GB, slower). Without llama-cpp-python or the weights, `terai chat` is the rule chat and says so in its first line. The web demo keeps the rule chat: TERAI1BETA and image reading are CLI only.

Measured on the fixed set `eval/terai1beta_cases_v15.json` (52 cases: 8 calculator, 4 date and time, 4 units, 4 memory, 10 knowledge with an answer in the pack, 10 questions with no source, 12 small-talk messages in 4 groups of 3 similar messages). Same machine as above, Gemma 4 E2B Q4_0, 4 threads. Other jobs were using the CPU at the same time (load average about 15 on 8 cores), so the latency below is pessimistic; the first test run of an earlier build measured p50 2.4 s, p95 9.6 s.

| | Rule chat (before) | TERAI1BETA |
|---|---|---|
| Answer correct (30 cases with a known answer) | 22/30 (calculator 4/8, knowledge 6/10) | 30/30 |
| Hallucination (a fact or number no source gave), all 52 cases | 1/52 | 1/52 |
| Says "I don't know" when no source has the answer | 9/10 | 9/10 |
| Small talk: different replies inside each group of 3 similar messages | 6/12 | 12/12 |
| Word overlap between replies in the same group (lower = less scripted) | 0.598 | 0.371 |
| Replies that fell back to the rule answer | - | 1/52 |
| Latency per reply, p50 / p95 | under 1 ms | 15.9 s / 46.2 s |
| Peak RAM (RSS) | 84 MB | 4.7 GB |
| Model load | - | 2.9 s (weights already in the page cache) |

Run it yourself: `python eval/brain_eval.py --engine both`.

Image reading, measured with `python eval/vision_eval.py` on 14 checks over 12 generated test images in `eval/vision/` (Gemma 4 E2B + vision projector, 4 threads, same busy machine):

| Image | Check | Result |
|---|---|---|
| Thai shop sign | read the text | exact (CER 0) |
| Thai menu | read the text | CER 0.04 ("ต้มยำ" read as "ตำยำ") |
| Thai notice | read the text | exact |
| Small Thai text | read the text | CER 0.39 |
| Thai text on a dark background | read the text | CER 0.56 |
| English sign | read the text | exact |
| English receipt | read the text | CER 0.21 |
| Thai and English mixed | read the text | exact |
| Shapes | how many shapes | correct |
| Shapes | colour of the square | correct |
| Bar chart | which month is highest | wrong |
| Scene | day or night | correct |
| Menu | which dish costs 120 baht | correct |
| Receipt | total | correct |

Text reading: mean CER 0.150 (Thai 0.165), 4 of 8 images exact. Questions: 5/6 correct. 35.8 s per image (p50, max 58.0 s), peak RAM 4.9 GB. Small or low-contrast Thai text and charts are the weak spots.

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
terai> [ค้นเว็บ] นายกรัฐมนตรีญี่ปุ่น (อังกฤษ: Prime Minister of Japan) นายกรัฐมนตรีคนปัจจุบัน คือ ซานาเอะ ทากาอิจิ ดำรงตำแหน่งตั้งแต่ 21 ตุลาคม พ.ศ. 2568 (ที่มา: Wikipedia ภาษาไทย "นายกรัฐมนตรีญี่ปุ่น", https://th.wikipedia.org/wiki/นายกรัฐมนตรีญี่ปุ่น, CC BY-SA 4.0)
```

The answer is only as current as the Wikipedia article at the time of the search. Passages are cut only where a new clause can start (never at ๆ, ฯ, an open bracket or a linking word such as และ, หรือ, คือ, ซึ่ง), but Thai has no sentence marks, so a cut can still split a name or a list now and then.

**Privacy:** without `--web` TER-AI never opens a network connection. With `--web` on, the question (minus question words) is sent to th.wikipedia.org and en.wikipedia.org, and to your SearXNG instance if you set one. Nothing else is sent: no session, no name, no history.

### In the browser demo

The chat in the [live demo](https://klanarongz2009-sketch.github.io/terai-router/) has a **Web search (Wikipedia)** switch under the message box. It is **off by default**, and the choice is saved in your browser (localStorage key `terai.chat.web.v1`).

- `docs/chat.js` has its own port of the web search: the same MediaWiki API requests (with `origin=*` for CORS), Thai Wikipedia then English Wikipedia, the same trigram-coverage ranking (threshold 0.6), the same "current/latest/now" rule, a 5-second timeout, the same citation, and the same fallback to the knowledge pack when offline. SearXNG is CLI only (most instances do not allow browser requests from other sites).
- Responses are kept in memory for the open page only (at most 200); errors are retried on the next message.
- `python eval/parity.py` feeds the same frozen API responses (`eval/web_fixtures_v09.json`, recorded with `eval/make_web_fixtures.py`) to the JavaScript and the Python chat over `eval/chat_web_v09.json`, including an offline conversation, and requires identical replies.

**Privacy (browser):** with the switch off, the page makes no request except loading itself and the knowledge pack from GitHub Pages. With it on, only the question text (minus question words) goes to th.wikipedia.org and en.wikipedia.org, directly from your browser. Your name, memory and chat history stay in your browser and are never sent.


## TTH: Thai speech (v0.10.0)

TTH is the text-to-speech part of TER-AI. The name comes from "TTS", with H for Thai. It reads a Thai or
Thai-English message aloud. The core install stays dependency-free; the speech engines are optional extras.

```bash
# local engine Wayu + edge-tts fallback (Python 3.10+, pulls torch; weights download once, about 315 MB)
pip install "terai-router[tth] @ git+https://github.com/klanarongz2009-sketch/terai-router.git"
# or only the small online fallback
pip install "terai-router[tth-edge] @ git+https://github.com/klanarongz2009-sketch/terai-router.git"

terai tth "สวัสดีครับ/ค่ะ นี่คือ TTH ของ TER-AI" -o hello.wav
terai tth -f note.txt -o note.mp3 --voice m_young_clear --speed 1.1
terai tth --dry-run "TER-AI v0.10.0 ได้ 97.6% เวลา 14:05 น."   # show what would be said, no audio
terai tth --list-voices          # 12 Wayu voices + 3 edge-tts voices
terai tth --engines              # which engines are installed
terai chat --speak               # speak every chat reply (saved in ~/.terai/tth, played if a player exists)
```

```python
from terai_router.tth import TTH, prepare
TTH(voice='f_young_clear').synthesize('12 × 7 = 84 ครับ/ค่ะ', 'out.wav')   # returns engine, voice, seconds, ...
prepare('12 × 7 = 84 ครับ/ค่ะ', polite='ค่ะ')   # 'สิบสอง คูณ เจ็ด เท่ากับ แปดสิบสี่ ค่ะ'
```

| | `wayu` (default) | `edge` (fallback) |
|---|---|---|
| Model | Wayu-Paxa-TTS-Edge, 82M open weights by Paxa Labs / Wayu Research (Kokoro-based) | Microsoft Edge read-aloud voices (th-TH-PremwadeeNeural, NiwatNeural, AcharaNeural) |
| Runs | locally on CPU, no internet after the first download | online: the text is sent to Microsoft |
| License | weights **CC-BY-NC-4.0**: non-commercial only, attribution to Paxa Labs; inference code Apache-2.0 | edge-tts LGPL-3.0; the service follows Microsoft's terms |

- **Engine choice:** `--engine auto` uses Wayu when it is installed and edge-tts when Wayu is missing or fails
  (`--no-fallback` turns that off). A voice the engine does not have is swapped for its voice of the same gender.
- **Text frontend:** before speaking, TTH rewrites the message: numbers in Thai words (8,192, 97.6, ๑๒๓), times
  (14:05 น.), versions (v0.10.0), maths (× ÷ = + − √ ^ %), units and abbreviations (กม., พ.ศ., ม.4), acronyms
  spelled with Thai letter names (GPU, API), fixed readings (TER-AI = เธอเอไอ, TTH, Wikipedia), the ครับ/ค่ะ slash
  (from the voice gender or `--polite`). Links and emoji are dropped; a web citation keeps only its source name.
  Then it cuts the text into chunks of at most 90 characters, at line breaks and Thai phrase spaces.
- **Web demo:** the Chat tab has a "Speak replies (TTH)" switch (off by default). It reads replies with a Thai
  voice already on your device through the browser's Web Speech API (th-TH): nothing is downloaded or sent.
  `docs/tth.js` is a line-by-line port of the frontend; `eval/parity.py` checks it gives the same spoken text and
  chunks as Python on 850 texts × 2 politeness settings (1,700 of 1,700 identical).
- **Not used:** the Paxa Labs cloud API (Paxa TTS Flash). TTH is local first.
- **Synthetic voice:** audio from TTH is machine-made. Do not present it as a real person's voice. Audio made with
  the Wayu engine is for non-commercial use (CC-BY-NC-4.0). Details and attribution: [NOTICE](NOTICE).

## SANKPUP: pictures from code (v0.11.0)

SANKPUP (from Thai "สร้างภาพ", "make a picture") turns a Thai or English prompt into a picture made purely from
code. It is a workflow, not a native image model: a language model (or the offline generator) writes SVG code,
SANKPUP sanitizes that code, then renders it to PNG and converts it to JPG. Nothing is drawn by a pixel or
diffusion model, and everything runs locally: no cloud API, no account, no key.

```bash
# rendering only (offline generator + PNG/JPG): resvg-py and Pillow
pip install "terai-router[sankpup] @ git+https://github.com/klanarongz2009-sketch/terai-router.git"
# plus local Gemma 4 through llama-cpp-python (CPU is fine)
pip install "terai-router[sankpup-gemma] @ git+https://github.com/klanarongz2009-sketch/terai-router.git"

terai sankpup "แมวสีส้มนั่งบนดวงจันทร์" -o cat.png              # auto: Gemma if downloaded, else offline
terai sankpup "a red sailboat on the sea" --engine offline -o boat.jpg
terai sankpup --pull                    # download Gemma 4 E2B (QAT Q4_0 GGUF, 3.35 GB, SHA-256 checked)
terai sankpup "หุ่นยนต์ถือดอกไม้" --engine gemma -o robot.png --save-code --json
terai sankpup "ภูเขากับพระอาทิตย์ตก" --server http://127.0.0.1:11434/v1 --server-model gemma4:e2b   # Ollama / llama-server
terai sankpup --list-models             # Gemma 4 variants, what is downloaded, which renderer is installed
```

```python
from terai_router.sankpup import generate, save
art = generate("บ้านหลังเล็กกับต้นไม้สองต้น ตอนกลางคืน", engine="offline", seed=1)
save(art, "house.png", save_code=True)   # house.png + house.svg
```

- **Engines:** `gemma` (local Gemma 4 writes the SVG; retries once with the error message if the code is unusable,
  then falls back to offline unless `--no-fallback`), `offline` (deterministic rules and vector templates, instant,
  no download) and `auto` (Gemma only if llama-cpp-python is installed and the weights are already on disk).
- **Models:** default `e2b` (Gemma 4 E2B, runs in 8 GB RAM on CPU). `e4b`, `12b`, `26b-a4b` and `31b` can be picked
  with `--model` on machines with more memory or a GPU; a path to any `.gguf` also works. Weights are Google's
  official QAT Q4_0 GGUF builds from Hugging Face, downloaded on first use into `~/.cache/terai/models`
  (`$TERAI_MODELS_DIR`), never stored in this repository.
- **Safety:** model output is treated as untrusted. Only drawing elements and attributes survive (no `script`,
  `foreignObject`, `image`, `use`, event handlers, external `url(...)`, `javascript:` or `data:` values, DOCTYPE or
  entities); size, element count and depth are capped. An unclosed local paint reference such as `url(#g` is closed.
- **Measured (Gemma 4 E2B, 8-core CPU, 8 GB RAM, no GPU, 12 prompts: 6 Thai, 6 English):** 11 of 12 valid (valid =
  parses as XML, passes the sanitizer, renders, and the image is not one flat colour). Thai 5/6, English 6/6. The
  one failure drew a full-canvas rectangle over everything (blank render). Time per picture p50 24.2 s, p95 49.1 s;
  model load 38 to 125 s. Reproduce with `python eval/sankpup_gemma_bench.py --model e2b`.
- **Browser:** the demo's SANKPUP tab runs `docs/sankpup.js`, a port of the offline generator that gives
  byte-identical SVG (checked by `eval/parity.py`), and can download PNG, JPG or the SVG code. Gemma is not used in
  the browser.

## MuML 1.0 WA: music in the browser (v0.12.0; MuML 1.0 network since v0.15.0)

MuML 1.0 WA (MuML 1.0 Web Audio API) is the browser member of the MuML music family. Type a prompt in Thai or
English, for example `เพลงร็อกมันส์ๆ 140 bpm คีย์ E minor 30 วินาที` or `rock reel key of D 120 bpm 30 seconds`,
pick a style (Auto, Folk or Rock) and a seed, then play it or download `.wav` and `.mid`. Open the MuML tab of the
[live demo](https://klanarongz2009-sketch.github.io/terai-router/).

```python
from terai_router import muml_wa
song = muml_wa.generate("เพลงเศร้า วอลทซ์ คีย์ A minor 30 วินาที", seed=3, style="auto")
print(song["prompt"]["meter"], song["note_writer"])   # 3/4 muml-1.0-net (markov-v1 if the weights are missing)
open("waltz.mid", "wb").write(muml_wa.to_midi(song))     # Standard MIDI File, format 1, 24 ticks per quarter
```

```bash
pip install numpy                    # the network runs on numpy in Python; the browser needs nothing
terai muml-wa --setup                # downloads muml-1.0-int8.bin (3,421,372 bytes) and checks its SHA-256
terai muml-wa "rock E minor 120 bpm 30 วินาที" --seed 1 -o rock.mid
terai muml-wa "folk jig D major" --writer markov    # the old Markov v1 writer
```

- **Note writer (since v0.15.0): the trained MuML 1.0 network.** A decoder-only transformer (4 layers, d_model 256,
  4 heads, context 512 tokens, 163 MuML tokens, 3,332,352 parameters) trained from scratch on the Nottingham folk
  tunes for 30 epochs (val loss 1.3780). It writes melody, chords and rhythm token by token, conditioned on meter,
  tune type, mode and key from the prompt. The forward pass is our own code (`docs/muml_wa_net.js`,
  `src/terai_router/muml_wa/net.py`), float64 with a key/value cache; no onnxruntime, no server. Weights are int8 with
  one scale per row (`docs/muml-1.0-int8.bin`, 3.4 MB, fetched once when you first press Write; val loss of the int8
  file 1.3779, same as fp32). Decoding: temperature 0.9, top-p 0.95, a grammar mask (a duration after every note) and
  a key guard (logit -2 for pitches outside the scale). Longer songs chain several tunes of up to 512 tokens.
- **Before/after** (`python eval/muml_wa_writers.py`, 10 fixed prompts x 3 seeds, same prompts for both):

  | Note writer | distinct 3-grams | distinct 4-grams | bars repeated | notes in key | ends on tonic | length / asked | time per song |
  |---|---|---|---|---|---|---|---|
  | Markov v1 (v0.12.0) | 0.648 | 0.757 | 22.3% | 97.6% | 100% | 1.04 | 0.002 s (Python) |
  | MuML 1.0 network | 0.762 | 0.927 | 1.2% | 98.3% | 26.7% | 1.02 | 1.7 s (Python, numpy) |
  | network, key guard off | 0.840 | 0.965 | 0% | 88.2% | 13.3% | 1.02 | 3.1 s |

  Browser (headless Chromium on the 8-core VM while other jobs ran): weights downloaded and parsed in about 0.5 s
  from a local server, a 30-second waltz (154 tokens) written in 1.8 s.
- **Markov v1 (v0.12.0) stays as the fallback**: used when the weights cannot load (browser) or numpy or the weights
  are missing (Python), or when you pick it. Key-relative pitch order-2 with order-1 back-off, a chord per bar,
  whole-bar rhythm patterns. The tab says which note writer wrote the song.

- **Sound:** everything is synthesized by the Web Audio API: fiddle-like lead, strummed chords and oom-pah bass for
  Folk; distorted lead, palm-muted power chords, bass and a synthesized drum kit for Rock; a compressor on the
  master. No soundfont, no samples, no server, no cloud API. `.wav` is rendered with OfflineAudioContext.
- **Same in Python and JavaScript:** `terai_router.muml_wa` is the reference; `docs/muml_wa.js` gives the same
  prompt reading, tokens, notes and `.mid` bytes for the same prompt, seed and style (`eval/parity.py`: Markov v1
  330 of 330, MuML 1.0 network 30 of 30). The network draws from integer weights (parts per million) with the same
  seeded generator, so float rounding between numpy and JavaScript does not change the song.
- **Limits:** the network almost never repeats a bar (1.2% against about 22% for Markov v1), so tunes wander instead
  of having clear AABB parts, and only 27% end on the tonic (a long song is cut at the bar where the asked length is
  reached); repeat signs it writes are not expanded; Python needs numpy; writing takes seconds, not milliseconds
  (Markov v1 is instant); the network is folk-trained, so Rock changes the arrangement, not the melody style.
  Markov v1 length is rounded to whole 8-bar parts (30 s asked as a jig gives 36.5 s); Folk is quieter than Rock.
- **License: code MIT, data GPL-3.0.** The network weights and the note table are built from the Nottingham Music Database as cleaned by
  [jukedeck/nottingham-dataset](https://github.com/jukedeck/nottingham-dataset), which is GPL-3.0, so the table
  and the weights are GPL-3.0 too. They are kept in their own files, `docs/muml-1.0-int8.bin` (license entry in its
  header; not in the Python package), `src/terai_router/muml_wa/data/markov.json` and `docs/muml_wa_table.js` (license header), each next to the full GPL-3.0 text (`LICENSE-GPL-3.0.txt`). The code
  that reads it stays MIT. Details: [DATA_LICENSE](DATA_LICENSE), [NOTICE](NOTICE).

## MUML 1.0 HIQ: text-to-music audio (v0.13.0)

MUML 1.0 HIQ is the high-quality member of the MuML music family: a Thai or English prompt (and optional lyrics) in, a real audio file out, on a CPU with 8 GB RAM, free and offline after the first download. It is built on other open models; the weights are not fine-tuned. HIQ tunes the conditioning: a prompt adapter turns Thai prompts into English music tags (genre, Thai instruments such as phin and khaen, mood) and moves BPM, length, key and meter into their own fields.

```
pip install git+https://github.com/klanarongz2009-sketch/terai-router.git@v0.13.0
terai muml --hiq --setup        # once: downloads the GGUF weights, builds acestep.cpp and yue2.cpp (git, cmake, C++17)
terai muml --hiq --status       # binaries and weights found?
terai muml --hiq "เพลงลูกทุ่งสนุกๆ มีพิณกับแคน จังหวะ 130" -o song.mp3          # instrumental, ACE-Step
terai muml --hiq "Lo-fi hip hop, 85 BPM, 30 seconds" -o lofi.mp3
terai muml --hiq "เพลงป๊อปช้าๆ ตอนกลางคืน" --lyrics lyrics_th.txt -o night.mp3   # Thai lyrics, YuE2-3B
terai muml --hiq --dry-run "เปียโนเศร้าๆ ตอนฝนตก"   # show the request, generate nothing
terai muml --hiq --credits      # credit line to keep with shared songs
```

Engines (`--vocal-engine yue2|ace|split`):

| Song | Default engine | Time per 30 s on 8 vCPU | Songs may be used commercially? |
|---|---|---|---|
| Instrumental | ace: ACE-Step 1.5 turbo (8 steps, acestep.cpp) | about 4 min | Yes (MIT parts only) |
| English lyrics | ace: ACE-Step 1.5 lyric LM, then synthesis | about 6 to 7 min | Yes (MIT parts only) |
| Thai lyrics | yue2: YuE2-3B Q5_K_M sings the Thai script (32 steps, yue2.cpp) | about 15 min | **No.** YuE2 is CC-BY-NC-4.0 |
| Thai lyrics, `--vocal-engine split` | ACE-Step instrumental + the local TTH Wayu voice per line, pitch-snapped, with ducking | about 6 min | **No.** Wayu is CC-BY-NC-4.0 |

- **`--fade-out SECONDS`** (default 2.5, 0 = off): both engines stop at the requested length whether the song has ended or not. When the last 0.25 s is louder than -40 dB, the CLI fades the end out (quadratic curve, ffmpeg), for every engine.
- **Song length for yue2:** without `--duration`, the length is sized from the lyrics (9 intro bars + 5 bars per lyric line + 4 outro bars, at the BPM or 90, in 5 s steps, at most 240 s); a 4-line song gets 90 s. A shorter `--duration` gives a warning with the length to use. After a yue2 render the CLI keeps the replay request in `<out>.yue2.json`.
- **`--setup`** checks for git, cmake and a C++ compiler before downloading anything, and finds a cmake installed by pip next to the venv's Python. Weights go to `~/.cache/terai/muml-hiq/models` (or `$TERAI_MUML_HIQ_MODELS`); `TERAI_ACESTEP_BIN` and `TERAI_YUE2_BIN` point to binaries you built yourself. yue2.cpp is pinned at commit `8af0174`, acestep.cpp at `de858d8`.
- **Limits:** CPU only and slow (a 90 s Thai song took about 25 minutes). Thai lyrics are only partly intelligible: the best yue2 run had CER 0.8598 with 14 of 30 lyric words heard, close to the 0.8131 floor of a song with no Thai at all. The split mode is far easier to understand (CER 0.2430) but it is speech on a beat, not singing. The yue2 score does not always plan every lyric section; the CLI reports which planned sections fit.
- **License:** this repository holds only TER-AI code (MIT). No weights are stored here; they are downloaded by `--setup`. Instrumentals and English songs use ACE-Step 1.5 (MIT) and can be used commercially. Songs made with yue2 (the default for Thai lyrics) or split are **non-commercial only** and must credit m-a-p (YuE2) or Paxa Labs / Wayu Research (Wayu); the CLI prints this warning before every such render. See the [license table](#license) and [NOTICE](NOTICE) items 8 to 13.

Full details, ASR tables and why there is no LoRA yet: [docs/MUML-HIQ.md](docs/MUML-HIQ.md).

## TERM AI: the original Terminal AI (limited-time trial, v0.14.0)

> **Limited-time trial.** TERM AI works until **2027-01-01 00:00:00 Asia/Bangkok (UTC+7)** (2026-12-31 17:00:00 UTC). At or after that moment `terai term` refuses to run, and TERM AI will be removed from this repository.

TERM AI is the program TER-AI grew from, written on 2026-10-10 before this repository existed: a Thai chatbot for the terminal. Regex rules answer first. When no rule matches, the first model the project trained, TER-AI-0.5 (character 1-3-gram Naive Bayes, 11 intents, 149 training sentences, a 34 KB JSON file), picks an intent; TERM AI answers from it only when the model is at least 90% sure and more than half of the message's 3+ character n-grams were seen in training, otherwise it says it does not understand. It is shipped as it was: same rules, same replies (in Thai), and the same model file, byte for byte, which the tests rebuild exactly from its training data. It is not the current intent router; it is here so you can try where TER-AI started.

```
terai term                              # interactive; type ออก, exit or quit to end
terai term "คำนวณ (12+8)*3"
TERM AI is a limited-time trial: it stops working at 2027-01-01 00:00:00 Asia/Bangkok (UTC+7) and will be removed from terai-router then (70 days left).
TERM AI> (12+8)*3 = 60
terai term --debug "ช่วยคิดเลข 3 คูณ 4"
TERM AI> 3 * 4 = 12 [model: calc p=1.00 cov=0.72]
terai term --trial-info                 # print the end time and exit
```

The notice line goes to stderr, replies to stdout. It understands greetings, remembering your name (`ผมชื่อ ...`, `ผมชื่ออะไร`), a safe calculator (also with the Thai words บวก ลบ คูณ หาร), the time and date in Thai time, a random number (`สุ่ม 1-100`), reversing and counting text, stats, forget all, "who are you" and "thank you". Memory (only the name you give and a message count) is saved in `~/.terai/term_ai.json`; `--memory PATH` and `--reset` change that. `--config FILE` takes the original JSON config keys. From Python: `from terai_router.term_ai import TermAI; TermAI().reply('สวัสดี')`.

- **Exact cutoff behaviour:** before 2027-01-01 00:00:00 UTC+7 every run prints that one-line notice with the end date and time, then runs (exit code 0). At that moment and after, `terai term` with any arguments, `--help` included, prints ``TERM AI trial ended at 2027-01-01 00:00:00 Asia/Bangkok (UTC+7). It no longer runs and is being removed from terai-router. Use `terai chat` instead.`` to stderr, prints nothing to stdout, does not touch the memory file, and exits with **code 3**. An interactive session still open at midnight stops at the next message the same way. In Python, `TermAI(...)` and `TermAI.reply()` raise `TrialEnded`. Thailand has no daylight saving time, so the limit is a fixed UTC+7 offset. It reads the machine clock: a trial notice, not copy protection.
- **Accuracy:** 101/149 (67.8%) leave-one-out on its training sentences. There is no held-out test set for this model.
- **Not in the browser demo:** TERM AI replies only in Thai and the demo UI is English only, so it is CLI and Python only.
- **License:** code and data MIT, written for this project; no third-party parts.

Details, the full cutoff table and the list of files the removal deletes: [docs/TERM-AI.md](docs/TERM-AI.md).

## How it works

1. A normalizer fixes common Thai typos and speech-to-text errors (context rules, a guarded typo table, repeated-character collapse).
2. Character n-gram features are read from the raw text, the normalized text and a phonetic skeleton.
3. A small linear model with 8-bit weights scores the 15 intents and a softmax gives the confidence.

## Browser demo

`docs/index.html` is a single self-contained page: the model and `docs/terai.js` are inlined, so it works offline and can be hosted on GitHub Pages. Rebuild it with `python docs/build_demo.py`. `python eval/parity.py` checks that the JavaScript and Python versions agree; on the current model they give the same intent and normalized text on all 607 eval sentences (max confidence difference 6.7e-16).

The demo has four tabs: chat, the intent router, SANKPUP (v0.11.0, pictures from code with the offline generator) and MuML (v0.12.0, music with the Web Audio API). The MuML note table is loaded from its own GPL-3.0 file, `docs/muml_wa_table.js`; everything else the page needs is inlined. The chat mode runs `docs/chat.js`, a JavaScript port of `Chat`: tools, follow-ups, memory saved in the browser (localStorage, with a reset button) and knowledge answers. The knowledge pack (`docs/knowledge_th.json`, about 2.8 MB over the network with gzip) is downloaded only the first time a knowledge question is asked. `python eval/parity.py` also runs the JavaScript chat against the Python chat with a fixed clock and seed: 790 of 790 turns give identical replies (chat eval, held-out, regression and probe sets), and 24 of 24 with web search on and mocked Wikipedia responses.

Since v0.10.0 the chat mode can speak its replies ("Speak replies (TTH)", off by default) with the browser's Web Speech API and a Thai voice already on the device. `docs/tth.js` prepares the text the same way as the Python TTH; `python eval/parity.py` checks 1,700 of 1,700 frontend outputs are identical.

## Development

```
pip install -e ".[dev,train]"
pytest                          # 353 pass, 4 skipped (real speech and real model runs, opt-in)
python eval/parity.py           # JS vs Python: router, chat, mocked web search, TTH text frontend, SANKPUP offline, MuML WA
python training/muml_wa/build_table.py             # rebuild the MuML WA note table (needs MuML 1.0 tunes.json)
python eval/sankpup_gemma_bench.py --model e2b     # SANKPUP + Gemma 4: valid-SVG rate and latency
python eval/muml_hiq_bench.py                      # MUML 1.0 HIQ: render the test prompts (needs --setup first)
python eval/chat_eval.py eval/chat_eval_v08.json   # chat eval
python -m terai_router.term_ai.intent_model eval   # TERM AI trial model: leave-one-out 101/149
python training/build_knowledge.py                 # rebuild the Thai Wikipedia pack
python training/gen_data.py     # rebuild training rows
python training/train.py        # train
python training/evaluate.py     # accuracy and latency
python bench/bench_typhoon.py   # Typhoon comparison (downloads about 2.5 GB)
```

## Roadmap

Planned:

- The repository's 1.0 criteria are unchanged by the model ids (TERAI1BETA, MuML 1.0, MUML 1.0 HIQ, Temmo 1.0); the repository stays 0.X.Y until they are met.
- v1.0 will add more languages, starting with English, each with its own training data, frozen test set and a 90% accuracy bar.

In progress (not released):

- MuML 1.0 training code and a CLI that writes from the network outside MuML 1.0 WA: the training scripts are not in
  this repository yet (only the export script `training/muml_wa/export_net.py` is).
- TTH-MTL: more voices and languages for TTH. A prototype engine is in this repository (`terai tth --engine mtl`, local OmniVoice, weights CC-BY-NC, about 3.3 GB, opt-in, extra `tth-mtl`); not released.
- Temmo 1.0: an AI that makes small indie games. A prototype is in this repository and in the Temmo tab of the live demo, with one sample game made by local Gemma 4 E2B.

Ending:

- TERM AI (limited-time trial since v0.14.0): stops working at 2027-01-01 00:00:00 Asia/Bangkok (UTC+7) and will be removed from the repository then.

## FAQ

### Does the model have a context window?
Not in the LLM sense. The intent classifier reads one message at a time and keeps no history inside the model. `Chat` (v0.8.0) is what keeps the conversation: it stores the history (last 200 turns), the facts the user told it and the context for follow-ups such as "แล้ว 5 ล่ะ", and saves them to a JSON session file, so the memory survives a restart. There is no token limit, because there is no language model. With TERAI1BETA (v0.16.0) the Gemma 4 model sees only the current message, the tool result, the user memory and the last 3 turns, inside a 4,096-token window; the history itself still lives in `Chat`.

### Can I download the model?
Yes. Install with `pip install git+https://github.com/klanarongz2009-sketch/terai-router.git` or download this repository. The intent model is one 1.1 MB JSON file (`src/terai_router/data/model.json`) that runs offline on CPU, with no GPU and no internet connection. The optional TTH, SANKPUP, MUML 1.0 HIQ and TERAI1BETA models are downloaded separately (on first use, or with `terai muml --hiq --setup` / `terai chat --setup`) and keep their own licenses (see below).

### Why choose TER-AI?
- Built for Thai, including typos and speech-to-text errors
- 97.6% accuracy on its frozen test set, against 44.4% for a 1B general model asked zero-shot (v0.7.0 comparison)
- About 0.17 ms per message on one CPU thread (measured 2026-10-21) and 1.1 MB in size, so it runs on small devices
- The intent model is our own, trained from scratch, not a wrapper around another company's model
- Everything released runs offline on CPU; the browser demo and its parity checks keep the JavaScript and Python versions identical

### Where can I contact the team?
Email: klanarongz2009@gmail.com

## License

Copyright (c) 2026 Clanarong Tammaketuek (klanarongz2009). Each part keeps its own license. The full texts and attributions are in [LICENSE](LICENSE), [DATA_LICENSE](DATA_LICENSE) and [NOTICE](NOTICE); if this table and those files ever differ, those files win.

| Part | Files | License | In this repository? | Commercial use? |
|---|---|---|---|---|
| Code (Python, JavaScript, web demo, scripts) | everything not listed below | MIT ([LICENSE](LICENSE)) | Yes | Yes |
| Intent model and other project data | `src/terai_router/data/model.json`, `typo_pairs.json`, `chitchat_th.json`; TERM AI trial: `src/terai_router/term_ai/data/model.json`, `train_data.json` | MIT (written or trained for this project, [DATA_LICENSE](DATA_LICENSE)) | Yes | Yes |
| Thai knowledge pack (from Thai Wikipedia) | `src/terai_router/data/knowledge_th.json` and its web copy `docs/knowledge_th.json` | CC BY-SA 4.0 ([DATA_LICENSE](DATA_LICENSE)) | Yes | Yes, with attribution to Wikipedia contributors and the same license on shared copies |
| MuML 1.0 WA note table and MuML 1.0 network weights (from the Nottingham Music Database via [jukedeck/nottingham-dataset](https://github.com/jukedeck/nottingham-dataset)) | `src/terai_router/muml_wa/data/markov.json`, its web copy `docs/muml_wa_table.js`, and `docs/muml-1.0-int8.bin` | GPL-3.0 (full text in `LICENSE-GPL-3.0.txt` next to each file; [DATA_LICENSE](DATA_LICENSE), [NOTICE](NOTICE) item 7) | Yes | Yes, under GPL-3.0: shared copies of these files must stay GPL-3.0 with their source named |
| Wayu-Paxa-TTS-Edge weights (TTH engine "wayu", by Paxa Labs / Wayu Research) | downloaded from Hugging Face on first use | CC-BY-NC-4.0 plus the Wayu Research Acceptable Use terms ([NOTICE](NOTICE) item 1) | No | **No.** Non-commercial only; credit Paxa Labs / Wayu Research. Audio made with this engine is non-commercial too |
| wayu-tts inference code | installed by the `tth` extra | Apache-2.0 ([NOTICE](NOTICE) item 1) | No | Yes |
| edge-tts (TTH engine "edge", online fallback) | installed by the `tth` or `tth-edge` extra | library LGPL-3.0; it sends text to Microsoft's online read-aloud service, whose voices follow Microsoft's terms ([NOTICE](NOTICE) item 2) | No | Library: yes. The Microsoft service and voices: only as Microsoft's terms allow; TER-AI grants nothing for them |
| Gemma 4 weights and vision projector (SANKPUP engine "gemma" and model TERAI1BETA, by Google DeepMind) | downloaded from Hugging Face on first use into `~/.cache/terai/models` | Apache License 2.0, as stated on Google's Gemma 4 license page ([NOTICE](NOTICE) item 4) | No | Yes |
| llama-cpp-python, resvg-py (wrapping resvg), Pillow | installed by the `sankpup` / `sankpup-gemma` / `llm` extras | MIT; MIT (resvg Apache-2.0); MIT-CMU ([NOTICE](NOTICE) items 5 and 6) | No | Yes |
| ACE-Step 1.5 weights and GGUF conversions (MUML 1.0 HIQ engine "ace", by ACE Studio and StepFun) | downloaded by `terai muml --hiq --setup` | MIT ([NOTICE](NOTICE) item 8) | No | Yes |
| Qwen3-Embedding-0.6B (ACE-Step text encoder) | downloaded by `--setup` | Apache License 2.0 ([NOTICE](NOTICE) item 9) | No | Yes |
| YuE2-3B and YuE2-Vae weights and GGUF conversions (MUML 1.0 HIQ engine "yue2", default for Thai lyrics, by m-a-p) | downloaded by `--setup` | CC-BY-NC-4.0 ([NOTICE](NOTICE) item 12) | No | **No.** Non-commercial only; credit m-a-p. Songs made with this engine are non-commercial too |
| Songs from MUML 1.0 HIQ split mode (TTH Wayu voice) | made on your machine | CC-BY-NC-4.0 through the Wayu weights ([NOTICE](NOTICE) item 11) | No | **No.** Non-commercial only; credit Paxa Labs / Wayu Research |
| acestep.cpp, yue2.cpp (ggml) | cloned and built by `--setup` at pinned commits | MIT ([NOTICE](NOTICE) items 10 and 12) | No | Yes |
| PyThaiNLP, pyworld (optional, MUML 1.0 HIQ) | installed by you if wanted | Apache-2.0; MIT (WORLD vocoder modified BSD) ([NOTICE](NOTICE) items 11 and 13) | No | Yes |
| Browser speech in the web demo | the device's own Thai voice (Web Speech API) | the device or browser maker's terms ([NOTICE](NOTICE) item 3) | No | Depends on the device maker |

TTH does not use the Paxa Labs cloud API, SANKPUP does not call any cloud API, MuML 1.0 WA uses no soundfont, samples or server, and MUML 1.0 HIQ runs locally after `--setup` with no cloud API.
