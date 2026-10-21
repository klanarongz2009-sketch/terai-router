# Changelog

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
