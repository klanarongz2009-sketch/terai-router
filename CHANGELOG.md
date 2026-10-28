# Changelog

## v0.17.0 (2026-10-28)

Repository v0.17.0. TTH-MTL is released, and the chat model TERAI1BETA is renamed to **TERAI1** ("beta" is its status, not part of its name). The model itself is unchanged.

### Added
- TTH-MTL released: `terai tth --engine mtl` (opt-in, extra `tth-mtl`), OmniVoice by k2-fsa on CPU, more languages (`--lang`) and voice cloning (`--ref-audio`, `--ref-text`, `--mtl-steps`). First use downloads `k2-fsa/OmniVoice` (about 3.3 GB); `--ref-audio` without `--ref-text` also downloads Whisper large-v3-turbo (about 1.6 GB). No quality, speed or memory benchmarks are in the repository yet. License: OmniVoice weights CC-BY-NC and the Higgs Audio 2 tokenizer under the Boson Higgs Audio 2 Community License, so audio made with TTH-MTL is non-commercial only; NOTICE item 15 has the terms and the required attribution.
- TERAI1 identity guard: the system prompt (chat and image reading) gives the model fixed facts about itself (TERAI1 of the TER-AI project, runs locally on the open model Gemma 4 E2B as its base, not trained by TER-AI, still being improved). A reply that says it was developed by Google, that it is Gemma, or that TER-AI trained the model gets one retry, then the fixed identity answer. "TERAI1BETA" in any reply is rewritten to "TERAI1". `tests/test_brain_identity.py` (mock model output).
- `tests/test_terai1_rename.py`: new names, old aliases and the rule chat identity answer.

### Changed
- Model id TERAI1BETA renamed to TERAI1 in code, CLI and docs (`terai --version` prints `terai-router 0.17.0 / model TERAI1`). Docs say "TERAI1 (beta)" where the status matters. This is the one exception to the rule that model ids keep their spelling, written into `src/terai_router/versions.py`.
- New names: `terai chat --brain terai1`, `eval/brain_eval.py --engine terai1`, `make_brain(..., 'terai1', ...)`. The old names `terai1beta` still work and print a deprecation notice; `versions.MODEL_ID_ALIASES` maps TERAI1BETA to TERAI1.
- Rule chat: the answer to "ใครพัฒนาคุณ" (who made you) said TER-AI trained every model itself. It now says the rule chat and the intent router are written and trained in this project, and the TERAI1 chat runs on Gemma 4, which TER-AI did not train. The web demo (`docs/index.html`) was rebuilt with the same answer. No frozen chat fixture asserted the old wording.

### Unchanged
- The eval data: `eval/terai1beta_cases_v15.json` keeps its file name (the original name of the TERAI1 test set) and content. The model evals were not rerun; none of the 52 cases is an identity question.
- Chat eval 81/81 and browser parity 790/790 (rerun 2026-10-28). Older CHANGELOG entries keep the name TERAI1BETA.

## v0.16.0 (2026-10-22)

Repository v0.16.0, first release of the model **TERAI1BETA**. This release writes down the versioning scheme for every model: the repository stays 0.X.Y, each model has its own id (MuML 1.0 was the first, in v0.15.0). See "Versions: repository and models" in README.md.

### Added
- Model TERAI1BETA for `terai chat`: local Gemma 4 E2B (official QAT Q4_0 GGUF, CPU, llama-cpp-python) writes the replies instead of fixed templates. The existing rules are its tools: calculator, date and time, unit conversion, memory and the bundled Thai Wikipedia pack. Every fact in a reply names its source; with no source the reply says it does not know. A grounding check rejects replies with numbers no tool returned (or missing the tool's number); the model gets one retry, then the rule answer is used.
- Image input: `terai chat --image FILE` (ask about an image, then keep chatting) and `terai vision FILE` (describe, read Thai/English text, answer a question about the image), through the Gemma 4 vision projector (mmproj).
- `terai chat --setup` downloads the TERAI1BETA weights (about 4.3 GB: 3.35 GB model + 0.99 GB vision projector, SHA-256 checked) into `~/.cache/terai/models`. New flags: `--brain auto|terai1beta|rules`, `--model e2b|e4b`, `--threads`, `--image`, `--trace`. Environment: `TERAI_MODELS_DIR`, `TERAI_THREADS`.
- `terai models` lists every model id; `terai --version` prints `terai-router 0.16.0 / model TERAI1BETA`. Model ids and the rule for them live in `src/terai_router/versions.py`.
- Optional extra `llm` (llama-cpp-python).
- Evals: `eval/brain_eval.py` on the fixed set `eval/terai1beta_cases_v15.json` (52 cases), `eval/vision_eval.py` on 12 generated test images in `eval/vision/`; `tests/test_brain.py`.

### Unchanged
- Without the model (or with `--brain rules`) the chat is the rule chat of v0.8.0 to v0.14.0: chat eval 81/81, 37/37, 16/16 and browser parity 790/790.
- The web demo keeps the rule chat; TERAI1BETA and image reading are CLI only (a 4 GB model does not run in the demo page).
- The repository's own 1.0 criteria. The "1.0" in MuML 1.0, MUML 1.0 HIQ and Temmo 1.0 is a model id, not the repository version.

## v0.15.0 (2026-10-22)

MuML 1.0 WA now writes notes with the trained MuML 1.0 network instead of the Markov chain. Markov v1 stays only as
the fallback. Model id: MuML 1.0 (note writer `muml-1.0-net`); the repository version stays 0.x.

- Network: decoder-only transformer, 4 layers, d_model 256, 4 heads, context 512, 163 MuML tokens, 3,332,352
  parameters, trained from scratch on the Nottingham folk tunes, 30 epochs, best val loss 1.3780.
- Weights: `docs/muml-1.0-int8.bin`, int8 with one float32 scale per row, 3,421,372 bytes, SHA-256
  f8a6d103...144fef (`training/muml_wa/export_net.py`). Val loss of the int8 file 1.3779 (fp32: 1.3780). Not in the
  Python package; also attached to this release.
- Browser: `docs/muml_wa_net.js`, our own float64 forward pass with a key/value cache (no onnxruntime, no server).
  The MuML tab gets a Writer choice (MuML 1.0 network / Markov v1) and a Write button; weights download once on
  first use; if they fail, Markov v1 writes the song and the tab says so.
- Python and CLI: `terai_router.muml_wa.net` (numpy) and the new `terai muml-wa` command (`--setup` downloads and
  checks the weights, `--writer net|markov|auto`). `generate(..., writer='auto')` uses the network when numpy and the
  weights are there.
- Decoding: temperature 0.9, top-p 0.95, grammar mask, key guard (logit -2 outside the scale). Probabilities become
  integer weights (parts per million) drawn with the seeded mulberry32 generator, so Python and JavaScript write the
  same song.
- Before/after (`eval/muml_wa_writers.py`, 10 prompts x 3 seeds): distinct 4-grams 0.757 -> 0.927, bars repeated
  22.3% -> 1.2%, notes in key 97.6% -> 98.3%, ends on tonic 100% -> 26.7%, length/asked 1.04 -> 1.02, time per song
  0.002 s -> 1.7 s (Python). Browser: 30-second waltz written in 1.8 s, weights parsed in about 0.5 s.
- Tests: pytest 353 passed, 4 skipped (6 new in `tests/test_muml_wa_net.py`). Parity: MuML WA Markov v1 330/330,
  MuML 1.0 network 30/30 (tokens, notes, `.mid` bytes), all other suites unchanged.
- License: code MIT; the weights are learned from the GPL-3.0 Nottingham data, so they are GPL-3.0 like the Markov
  table (DATA_LICENSE, NOTICE item 12).
- Limits: almost no repeated bars, so no clear AABB parts; only about a quarter of songs end on the tonic; repeat
  signs are not expanded; Python needs numpy; folk-trained, so Rock changes only the arrangement.

## v0.14.0 (2026-10-22)

TERM AI, the original Terminal AI that TER-AI grew from, as a limited-time trial (`terai term`). It stops working at
2027-01-01 00:00:00 Asia/Bangkok (UTC+7) and will be removed from the repository then.

- What it is: the first program of the project (2026-10-10, before this repository): a Thai terminal chatbot with
  regex rules first, then the TER-AI-0.5 intent model (character 1-3-gram binary Naive Bayes, 11 intents, 149
  training sentences) behind a confidence (>= 0.9) and n-gram coverage (> 0.5) guard. Rules, replies and thresholds
  are the original ones; `term_ai/data/model.json` is byte-identical to the original and is rebuilt exactly from
  `train_data.json` by the tests. Offline, CPU, no dependencies.
- `terai term` (interactive), `terai term "text"`, `--memory`, `--reset`, `--config`, `--seed`, `--debug`,
  `--trial-info`; Python API `terai_router.term_ai.TermAI`.
- Time limit: before 2027-01-01 00:00:00 UTC+7 every run prints a one-line notice with the end date and time to
  stderr. At or after it, `terai term` with any arguments prints that the trial ended, writes nothing, and exits with
  code 3; a session open at midnight stops at the next message; the Python API raises `TrialEnded`. Not in the web
  demo (Thai-only replies, English-only demo UI).
- Removal list for 2027-01-01: `REMOVAL_PATHS` / `REMOVAL_EDITS` in `term_ai/trial.py` and docs/TERM-AI.md; a test
  checks the paths exist and that only `cli.py` imports `term_ai`.
- Results: TERM AI leave-one-out 101/149 (67.8%). pytest 347 passed, 4 skipped (54 new tests, clock injected for
  before, at and after the cutoff). Parity: router 607 with no diff, chat 790/790, web 24/24, TTH 1700/1700, SANKPUP
  688/688, MuML WA 330/330, Temmo remix 42/42. Router frozen 121/124, held-out 111/112.

## v0.13.0 (2026-10-21)

MUML 1.0 HIQ: text-to-music audio on CPU (`terai muml --hiq`), released. Built on other open models; no weights
are stored in this repository.

- Engines (`--vocal-engine yue2|ace|split`): ACE-Step 1.5 turbo through acestep.cpp for instrumentals and English
  songs (lyrics: ace-lm, then ace-synth); YuE2-3B Q5_K_M through yue2.cpp as the default for Thai lyrics (sings the
  Thai script); `split` = ACE-Step instrumental plus the local TTH Wayu voice per lyric line, pitch-snapped, with
  ducking. `--thai-vocal sing|split` stays as an older alias.
- Prompt adapter: Thai prompts become English music tags (genre, Thai instruments, mood); BPM, length, key and meter
  go to their own fields. Thai lyrics on ACE-Step are romanised with PyThaiNLP when installed (`--thai-lyrics`,
  `--lm-model`).
- `--fade-out SECONDS` (default 2.5): songs cut at the requested length get a quadratic fade (ffmpeg) when the last
  0.25 s is louder than -40 dB, for every engine.
- yue2 sizes the song length from the lyrics when `--duration` is not given (a 4-line song gets 90 s), scales the
  semantic stage, reports the planned score sections and keeps the replay request in `<out>.yue2.json`.
- `--setup` downloads the GGUF weights and builds acestep.cpp and yue2.cpp at pinned commits. It now checks for git,
  cmake and a C++ compiler before any download and finds a cmake installed by pip next to the venv's Python (before:
  about 3 GB downloaded, then `[Errno 2] No such file or directory: 'cmake'`).
- License: TER-AI code stays MIT. ACE-Step 1.5 (MIT) songs can be used commercially. YuE2-3B and YuE2-Vae are
  CC-BY-NC-4.0, so songs made with yue2 (default for Thai lyrics) or split (Wayu voice) are non-commercial only; the
  CLI warns before each such render and `--credits` prints the credit lines. README license table and NOTICE items 8
  to 13.
- Results (8 vCPU, 8 GB RAM, no GPU): Thai test song on yue2 without `--duration`: 24:53 wall time, peak RSS 2.93 GB,
  ended on its own at 50.6 s, CER 0.8598, 14 of 30 lyric words heard from all 4 lines (30 s run before the fix: CER
  0.9065, 4/30). split: CER 0.2430, 20/30 (speech, not singing). Clean-machine `--setup`: yue-synth built in 36 s,
  downloaded GGUF files match the reference SHA-256. pytest 293 passed, 4 skipped. Parity: router 607 with no diff,
  chat 790/790, web 24/24, TTH 1700/1700, SANKPUP 688/688, MuML WA 330/330, Temmo remix 42/42.
- Limits: CPU only and slow (about 15 minutes per 30 s of Thai song); Thai lyrics are only partly intelligible.
- Also in this release: Temmo 1.0 prototype (not released) and the English-only web demo UI, merged to main after
  v0.12.0.

## v0.12.0 (2026-10-21)

MuML 1.0 WA: music written and played in the browser with the Web Audio API.

- New `terai_router.muml_wa` (Python reference) and `docs/muml_wa.js` (browser): a Thai or English prompt (mood,
  BPM, key, meter, length) and a seed give a song as MuML 1.0 tokens, arranged notes and `.mid` bytes. Styles: Auto,
  Folk, Rock.
- Note writer: Markov v1 (seeded Markov chain built from the MuML 1.0 training data, Nottingham folk tunes).
  It is not the trained MuML 1.0 model yet; it uses the same interface so the model can replace it later.
- Web demo: new MuML tab with Play, Stop, Download .wav (OfflineAudioContext) and Download .mid. All sound is
  synthesized by the Web Audio API: no soundfont, no server, no cloud API.
- License: code stays MIT. The note table is GPL-3.0 data built from jukedeck/nottingham-dataset
  (https://github.com/jukedeck/nottingham-dataset, GPL-3.0). It lives in its own files,
  `src/terai_router/muml_wa/data/markov.json` (with a `license` entry) and `docs/muml_wa_table.js` (license header,
  loaded by the demo instead of being inlined), each next to the full GPL-3.0 text. See DATA_LICENSE and NOTICE.
- Tests: `tests/test_muml_wa.py` and `tests/test_muml_wa_js_parity.py` (JS vs Python 228 cases, table file and
  license checks). `eval/parity.py` adds MuML WA (330 of 330) and checks that the demo's table file equals
  markov.json. `eval/muml_wa_render.py` renders samples with the real Web Audio API in headless Chromium.
- Results: pytest 169 passed, 1 skipped. Parity: router 607 with no diff, chat 790/790, web 24/24, TTH 1700/1700,
  SANKPUP 688/688, MuML WA 330/330.

## v0.11.0 (2026-10-21)

SANKPUP, pictures from code: `terai sankpup` lets a local Gemma 4 model or the offline generator write SVG, which is
sanitized and rendered to PNG/JPG. Web demo SANKPUP tab.

## v0.10.0 (2026-10-21)

TTH, Thai text-to-speech: `terai tth`, `terai chat --speak` and Speak replies in the web demo.

Older releases are described in the README and on the GitHub releases page.
