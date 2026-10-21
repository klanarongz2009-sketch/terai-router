# Changelog

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
