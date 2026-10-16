# TER-AI

Offline Thai intent router that tolerates typos. Small, CPU-only, no dependencies. Made with Sesame.

TER-AI reads one Thai (or Thai-English) message and tells you what the user wants: one of 15 intents, a confidence score, and the message with common typos fixed. It runs fully offline on CPU, so it fits phones, Raspberry Pi, IoT devices and chat bots that should not send every message to a large model.

```
$ terai "เส็ดหรือยัง"
status  1.00  เสร็จหรือยัง
```

## Why the name

TER comes from the Thai word "เธอ" (you), and it works both ways: TER-AI calls the user เธอ, and the user calls TER-AI เธอ.

## Results (v0.7.0)

All numbers come from `eval/results_v07.json` and `bench/typhoon_results.json` in this repo.

| | TER-AI v0.7.0 | Typhoon2 1B instruct (zero-shot) |
|---|---|---|
| Accuracy, frozen test set (124 sentences) | 97.6% (121/124) | 44.4% (55/124, 14 unparsed) |
| Mean latency per message, CPU | 0.24 ms (1 thread) | 2,325 ms (8 threads) |
| Model size | 1.1 MB | 2.49 GB download (1.24B params, float32) |

- Held-out set built before training (112 sentences): 99.1% (111/112).
- Test set by subset: clean 33/36 and 20/20, real user messages 13/13, profile typos 11/11, pattern typos 44/44.
- Typhoon model: `typhoon-ai/llama3.2-typhoon2-1b-instruct`, revision `7513a054`, greedy decoding, max 6 new tokens, system prompt listing the 15 intents. Hardware: AMD EPYC, 8 threads, torch 2.14.1+cpu, transformers 5.19.0, Python 3.13.7.
- The test set is frozen (SHA-256 in `eval/SHA256SUMS`) and never used for training. `training/leak_check.py` reports the closest training sentence for each test sentence.

## Install

```
pip install .
```

Python 3.9+, no runtime dependencies.

## Use

Command line:

```
terai "เส็ดหรือยัง"            # intent, confidence, normalized text
terai --json "ช้วยบวก 2+3"     # JSON with the top 3 intents
echo "ทำต่อ" | terai -          # one result per input line
terai                           # interactive prompt (Ctrl-D to quit)
terai --threshold 0.5 "..."     # print 'unknown' below this confidence
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

## How it works

1. A normalizer fixes common Thai typos and speech-to-text errors (context rules, a guarded typo table, repeated-character collapse).
2. Character n-gram features are read from the raw text, the normalized text and a phonetic skeleton.
3. A small linear model with 8-bit weights scores the 15 intents and a softmax gives the confidence.

## Browser demo

`docs/index.html` is a single self-contained page: the model and `docs/terai.js` are inlined, so it works offline and can be hosted on GitHub Pages. Rebuild it with `python docs/build_demo.py`. `python eval/parity.py` checks that the JavaScript and Python versions agree; on the current model they give the same intent and normalized text on all 607 eval sentences (max confidence difference 6.7e-16).

## Development

```
pip install -e ".[dev,train]"
pytest                          # 24 tests
python training/gen_data.py     # rebuild training rows
python training/train.py        # train
python training/evaluate.py     # accuracy and latency
python bench/bench_typhoon.py   # Typhoon comparison (downloads about 2.5 GB)
```

## Roadmap

v1.0 will add more languages, starting with English, each with its own training data, frozen test set and a 90% accuracy bar.

## FAQ

### Does the model have a context window?
No. TER-AI is a small intent classifier, not a chat LLM. It reads one message at a time and keeps no conversation history inside the model. Anything an app wants to remember, such as the user's name, is stored by the app outside the model.

### Can I download the model?
Yes. Install with `pip install .` or download this repository. The model is one 1.1 MB JSON file (`src/terai_router/data/model.json`) that runs offline on CPU, with no GPU and no internet connection.

### Why choose TER-AI?
- Built for Thai, including typos and speech-to-text errors
- 97.6% accuracy on its test set, against 44.4% for a 1B general model asked zero-shot
- About 0.24 ms per message on one CPU thread and 1.1 MB in size, so it runs on small devices
- Our own model, trained from scratch, not a wrapper around another company's model

### Where can I contact the team?
Email: klanarongz2009@gmail.com

## License

MIT. Copyright (c) 2026 Clanarong Tammaketuek (Bogus).
