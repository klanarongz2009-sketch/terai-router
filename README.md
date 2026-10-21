# TER-AI

Offline Thai intent router that tolerates typos. Small, CPU-only, no dependencies. Made with Sesame.

Live demo: https://klanarongz2009-sketch.github.io/terai-router/ · Repository: https://github.com/klanarongz2009-sketch/terai-router · Wiki: https://github.com/klanarongz2009-sketch/terai-router/wiki

TER-AI reads one Thai (or Thai-English) message and tells you what the user wants: one of 15 intents, a confidence score, and the message with common typos fixed. It runs fully offline on CPU, so it fits phones, Raspberry Pi, IoT devices and chat bots that should not send every message to a large model.

Since v0.8.0 it also ships `Chat`: an offline Thai chat that answers with real tools (calculator, date and time, unit conversion), answers knowledge questions from a bundled Thai Wikipedia pack with the source named, remembers what the user tells it across restarts, and says it does not know instead of guessing. There is no language model inside.

Since v0.10.0 it can also speak: TTH reads Thai aloud with a local open-weight voice model (Wayu-Paxa-TTS-Edge) and falls back to edge-tts, both optional. See [TTH: Thai speech](#tth-thai-speech-v0100).

Since v0.11.0 it can also make pictures: SANKPUP writes a picture as SVG code, either with a local Gemma 4 model or with a built-in offline generator, then renders it to PNG or JPG. It is not an image model and no cloud API is used. See [SANKPUP: pictures from code](#sankpup-pictures-from-code-v0110).

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

## How it works

1. A normalizer fixes common Thai typos and speech-to-text errors (context rules, a guarded typo table, repeated-character collapse).
2. Character n-gram features are read from the raw text, the normalized text and a phonetic skeleton.
3. A small linear model with 8-bit weights scores the 15 intents and a softmax gives the confidence.

## Browser demo

`docs/index.html` is a single self-contained page: the model and `docs/terai.js` are inlined, so it works offline and can be hosted on GitHub Pages. Rebuild it with `python docs/build_demo.py`. `python eval/parity.py` checks that the JavaScript and Python versions agree; on the current model they give the same intent and normalized text on all 607 eval sentences (max confidence difference 6.7e-16).

The demo has three tabs: chat, the intent router and SANKPUP (v0.11.0, pictures from code with the offline generator). The chat mode runs `docs/chat.js`, a JavaScript port of `Chat`: tools, follow-ups, memory saved in the browser (localStorage, with a reset button) and knowledge answers. The knowledge pack (`docs/knowledge_th.json`, about 2.8 MB over the network with gzip) is downloaded only the first time a knowledge question is asked. `python eval/parity.py` also runs the JavaScript chat against the Python chat with a fixed clock and seed: 790 of 790 turns give identical replies (chat eval, held-out, regression and probe sets), and 24 of 24 with web search on and mocked Wikipedia responses.

Since v0.10.0 the chat mode can speak its replies ("Speak replies (TTH)", off by default) with the browser's Web Speech API and a Thai voice already on the device. `docs/tth.js` prepares the text the same way as the Python TTH; `python eval/parity.py` checks 1,700 of 1,700 frontend outputs are identical.

## Development

```
pip install -e ".[dev,train]"
pytest                          # 138 tests (1 more, real speech, with TERAI_TTH_REAL=1)
python eval/parity.py           # JS vs Python: router, chat, mocked web search, TTH text frontend, SANKPUP offline
python eval/sankpup_gemma_bench.py --model e2b     # SANKPUP + Gemma 4: valid-SVG rate and latency
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

Speech (TTH, optional, not included in this repository): the Wayu-Paxa-TTS-Edge weights by Paxa Labs / Wayu Research are CC-BY-NC-4.0 (non-commercial, attribution required) and are downloaded from Hugging Face on first use; edge-tts (LGPL-3.0) uses an online Microsoft service. Attribution and details are in `NOTICE`.

Pictures (SANKPUP, optional, not included in this repository): Gemma 4 weights by Google are released under the Apache License 2.0 (https://ai.google.dev/gemma/docs/gemma_4_license) and are downloaded from Hugging Face on first use. Rendering uses resvg-py (MIT, wrapping resvg, Apache-2.0) and Pillow (MIT-CMU); llama-cpp-python is MIT. Details: [NOTICE](NOTICE).
