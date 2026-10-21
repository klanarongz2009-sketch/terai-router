# TER-AI

[Thai version](README.th.md)

TER-AI is a free set of Thai AI tools that runs offline on an ordinary CPU, with no GPU and no cloud API. Made with Sesame.

What is released today (v0.12.0):

| Part | What it does | Since |
|---|---|---|
| Intent router | Reads one Thai or Thai-English message, fixes common typos and returns one of 15 intents with a confidence score. 1.1 MB model, no dependencies. | v0.7.0 |
| Chat | Offline Thai chat with real tools (calculator, date and time, unit conversion), answers from a bundled Thai Wikipedia pack with the source named, memory across restarts, says "I don't know" instead of guessing. No language model inside. Optional Wikipedia web search since v0.9.0. | v0.8.0 |
| TTH | Reads Thai aloud with a local open-weight voice model (Wayu-Paxa-TTS-Edge), with edge-tts as an online fallback. Both optional. | v0.10.0 |
| SANKPUP | Makes pictures by writing SVG code (local Gemma 4 or a built-in offline generator), sanitizes it and renders PNG or JPG. Not an image model. | v0.11.0 |
| MuML 1.0 WA | Writes and plays music in the browser from a Thai or English prompt. Notes come from a seeded Markov note writer (Markov v1, not the trained MuML 1.0 model); every sound is made by the Web Audio API. | v0.12.0 |

Live demo: https://klanarongz2009-sketch.github.io/terai-router/ · Repository: https://github.com/klanarongz2009-sketch/terai-router · Wiki: https://github.com/klanarongz2009-sketch/terai-router/wiki

Licenses differ by part: the code is MIT, but some data and optional models are not. Check the [license table](#license) before commercial use.

```
$ terai "เส็ดหรือยัง"
status  1.00  เสร็จหรือยัง
```

## Why the name

TER comes from the Thai word "เธอ" (you), and it works both ways: TER-AI calls the user เธอ, and the user calls TER-AI เธอ.

## Results (v0.12.0, measured 2026-10-21)

Run on commit `4867fa4` (v0.12.0) with the scripts in this repo. Machine: AMD EPYC, 8 cores, no GPU, Python 3.13.7.

| Check | Command | Result |
|---|---|---|
| Intent accuracy, frozen test set (124 sentences) | `python training/evaluate.py` | 97.6% (121/124), 0.169 ms per message (1 thread) |
| Intent accuracy, held-out set (112 sentences) | `python training/evaluate.py` | 99.1% (111/112), 0.209 ms per message (1 thread) |
| Chat eval, frozen (written before the Chat code) | `python eval/chat_eval.py eval/chat_eval_v08.json` | 81/81 turns, 18/18 conversations |
| Chat eval, held out | `python eval/chat_eval.py eval/chat_heldout_v08.json` | 37/37 turns, 14/14 conversations |
| Chat regressions (bugs fixed later) | `python eval/chat_eval.py eval/chat_regress_v08.json` | 16/16 turns, 3/3 conversations |
| Browser vs Python, intent router | `python eval/parity.py` | 607/607 sentences same intent and text, max confidence difference 6.66e-16 |
| Browser vs Python, chat | `python eval/parity.py` | 790/790 turns identical; 24/24 with mocked web search |
| Browser vs Python, TTH text frontend | `python eval/parity.py` | 1,700/1,700 checks identical |
| Browser vs Python, SANKPUP offline generator | `python eval/parity.py` | 688/688 checks identical (byte-identical SVG) |
| Browser vs Python, MuML 1.0 WA | `python eval/parity.py` | 330/330 checks identical; web note table matches `markov.json` byte for byte |
| Unit tests | `pytest` | 169 passed, 1 skipped (real speech, runs with `TERAI_TTH_REAL=1`) |

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

Python 3.9+, no runtime dependencies for the intent router and Chat. TTH and SANKPUP have optional extras, described in their sections.

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

## MuML 1.0 WA: music in the browser (v0.12.0)

MuML 1.0 WA (MuML 1.0 Web Audio API) is the browser member of the MuML music family. Type a prompt in Thai or
English, for example `เพลงร็อกมันส์ๆ 140 bpm คีย์ E minor 30 วินาที` or `rock reel key of D 120 bpm 30 seconds`,
pick a style (Auto, Folk or Rock) and a seed, then play it or download `.wav` and `.mid`. Open the MuML tab of the
[live demo](https://klanarongz2009-sketch.github.io/terai-router/).

```python
from terai_router import muml_wa
song = muml_wa.generate("เพลงเศร้า วอลทซ์ คีย์ A minor 30 วินาที", seed=3, style="auto")
print(song["prompt"]["meter"], song["form"], song["note_writer"])   # 3/4 AB markov-v1
open("waltz.mid", "wb").write(muml_wa.to_midi(song))     # Standard MIDI File, format 1, 24 ticks per quarter
```

- **Note writer: Markov v1, not the MuML 1.0 model.** A seeded Markov chain built from the MuML 1.0 training data
  (Nottingham folk tunes): key-relative pitch order-2 with order-1 back-off, a chord per bar, whole-bar rhythm
  patterns. It uses the MuML 1.0 token language and the same interface (prompt + seed in, MuML tokens out), so the
  trained MuML 1.0 network can replace it later. The tab says which note writer is in use.
- **Sound:** everything is synthesized by the Web Audio API: fiddle-like lead, strummed chords and oom-pah bass for
  Folk; distorted lead, palm-muted power chords, bass and a synthesized drum kit for Rock; a compressor on the
  master. No soundfont, no samples, no server, no cloud API. `.wav` is rendered with OfflineAudioContext.
- **Same in Python and JavaScript:** `terai_router.muml_wa` is the reference; `docs/muml_wa.js` gives the same
  prompt reading, tokens, notes and `.mid` bytes for the same prompt, seed and style (`eval/parity.py`: 330 of 330).
- **Limits:** length is rounded to whole 8-bar parts (30 s asked as a jig gives 36.5 s); Folk is quieter than Rock
  (no loudness normalization); the notes come from a Markov chain, so long-range structure is simple (AABB or AB).
- **License: code MIT, data GPL-3.0.** The note table is built from the Nottingham Music Database as cleaned by
  [jukedeck/nottingham-dataset](https://github.com/jukedeck/nottingham-dataset), which is GPL-3.0, so the table
  is GPL-3.0 too. It is kept in its own files, `src/terai_router/muml_wa/data/markov.json` and
  `docs/muml_wa_table.js` (license header), each next to the full GPL-3.0 text (`LICENSE-GPL-3.0.txt`). The code
  that reads it stays MIT. Details: [DATA_LICENSE](DATA_LICENSE), [NOTICE](NOTICE).

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
pytest                          # 169 pass, 1 skipped (real speech, runs with TERAI_TTH_REAL=1)
python eval/parity.py           # JS vs Python: router, chat, mocked web search, TTH text frontend, SANKPUP offline, MuML WA
python training/muml_wa/build_table.py             # rebuild the MuML WA note table (needs MuML 1.0 tunes.json)
python eval/sankpup_gemma_bench.py --model e2b     # SANKPUP + Gemma 4: valid-SVG rate and latency
python eval/chat_eval.py eval/chat_eval_v08.json   # chat eval
python training/build_knowledge.py                 # rebuild the Thai Wikipedia pack
python training/gen_data.py     # rebuild training rows
python training/train.py        # train
python training/evaluate.py     # accuracy and latency
python bench/bench_typhoon.py   # Typhoon comparison (downloads about 2.5 GB)
```

## Roadmap

Planned:

- v1.0 will add more languages, starting with English, each with its own training data, frozen test set and a 90% accuracy bar.

In progress (not released):

- MuML 1.0: the trained MuML 1.0 note model, to replace Markov v1 in MuML 1.0 WA. Not in this repository yet.
- MuML HIQ: higher-quality music, tuned from another model. Not in this repository yet.
- TTH-MTL: more and better Thai voices for TTH. Not in this repository yet.
- Temmo 1.0: an AI that makes small indie games. A prototype is in this repository and in the Temmo tab of the live demo, with one sample game made by local Gemma 4 E2B.

## FAQ

### Does the model have a context window?
Not in the LLM sense. The intent classifier reads one message at a time and keeps no history inside the model. `Chat` (v0.8.0) is what keeps the conversation: it stores the history (last 200 turns), the facts the user told it and the context for follow-ups such as "แล้ว 5 ล่ะ", and saves them to a JSON session file, so the memory survives a restart. There is no token limit, because there is no language model.

### Can I download the model?
Yes. Install with `pip install git+https://github.com/klanarongz2009-sketch/terai-router.git` or download this repository. The intent model is one 1.1 MB JSON file (`src/terai_router/data/model.json`) that runs offline on CPU, with no GPU and no internet connection. The optional TTH and SANKPUP models are downloaded separately on first use and keep their own licenses (see below).

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
| Intent model and other project data | `src/terai_router/data/model.json`, `typo_pairs.json`, `chitchat_th.json` | MIT (written or trained for this project, [DATA_LICENSE](DATA_LICENSE)) | Yes | Yes |
| Thai knowledge pack (from Thai Wikipedia) | `src/terai_router/data/knowledge_th.json` and its web copy `docs/knowledge_th.json` | CC BY-SA 4.0 ([DATA_LICENSE](DATA_LICENSE)) | Yes | Yes, with attribution to Wikipedia contributors and the same license on shared copies |
| MuML 1.0 WA note table (from the Nottingham Music Database via [jukedeck/nottingham-dataset](https://github.com/jukedeck/nottingham-dataset)) | `src/terai_router/muml_wa/data/markov.json` and its web copy `docs/muml_wa_table.js` | GPL-3.0 (full text in `LICENSE-GPL-3.0.txt` next to each file; [DATA_LICENSE](DATA_LICENSE), [NOTICE](NOTICE) item 7) | Yes | Yes, under GPL-3.0: shared copies of these files must stay GPL-3.0 with their source named |
| Wayu-Paxa-TTS-Edge weights (TTH engine "wayu", by Paxa Labs / Wayu Research) | downloaded from Hugging Face on first use | CC-BY-NC-4.0 plus the Wayu Research Acceptable Use terms ([NOTICE](NOTICE) item 1) | No | **No.** Non-commercial only; credit Paxa Labs / Wayu Research. Audio made with this engine is non-commercial too |
| wayu-tts inference code | installed by the `tth` extra | Apache-2.0 ([NOTICE](NOTICE) item 1) | No | Yes |
| edge-tts (TTH engine "edge", online fallback) | installed by the `tth` or `tth-edge` extra | library LGPL-3.0; it sends text to Microsoft's online read-aloud service, whose voices follow Microsoft's terms ([NOTICE](NOTICE) item 2) | No | Library: yes. The Microsoft service and voices: only as Microsoft's terms allow; TER-AI grants nothing for them |
| Gemma 4 weights (SANKPUP engine "gemma", by Google DeepMind) | downloaded from Hugging Face on first use into `~/.cache/terai/models` | Apache License 2.0, as stated on Google's Gemma 4 license page ([NOTICE](NOTICE) item 4) | No | Yes |
| llama-cpp-python, resvg-py (wrapping resvg), Pillow | installed by the `sankpup` / `sankpup-gemma` extras | MIT; MIT (resvg Apache-2.0); MIT-CMU ([NOTICE](NOTICE) items 5 and 6) | No | Yes |
| Browser speech in the web demo | the device's own Thai voice (Web Speech API) | the device or browser maker's terms ([NOTICE](NOTICE) item 3) | No | Depends on the device maker |

TTH does not use the Paxa Labs cloud API, SANKPUP does not call any cloud API, and MuML 1.0 WA uses no soundfont, samples or server.
