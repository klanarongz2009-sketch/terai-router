# TERM AI: the original Terminal AI (limited-time trial)

> **Limited-time trial, added in v0.14.0 (2026-10-22).** TERM AI works until
> **2027-01-01 00:00:00 Asia/Bangkok (UTC+7)**, which is 2026-12-31 17:00:00 UTC.
> At or after that moment it refuses to run, and it will be removed from this repository.

## What it is

TERM AI is the program TER-AI grew from. It was written on 2026-10-10 on the development
machine, before this repository existed (Phase 0 on the wiki History page), as `term_ai.py`:
a Thai chatbot for the terminal.

1. **Rules first.** Regular expressions answer greetings, "remember my name" and "what is my
   name", a safe calculator (an AST walker, no `eval`; exponents above 100 refused), the time
   and date in Thai time, a random number, reverse text, count text, stats, forget all,
   "who are you" and "thank you".
2. **Then the first own model.** When no rule matches, the TER-AI-0.5 intent classifier picks
   one of 11 intents: character 1-3-gram binary Naive Bayes, smoothing 0.01, trained on 149
   sentences written for the project (`data/train_data.json`). The model file is 34 KB of JSON.
3. **Out-of-domain guard.** It answers from the model only when the top intent has
   probability >= 0.9 and more than half of the message's n-grams of 3+ characters were seen
   for that intent in training. Otherwise it says it does not understand and points to `ช่วย`.

It is shipped as it was. The rules, replies (in Thai), thresholds and fallbacks are the
original ones; the bundled `model.json` is byte-identical to the original file and is rebuilt
exactly from `train_data.json` by the tests. The changes for the package are only these: the
clock and the random generator can be injected (for tests), the memory file path is a
parameter, the display name is "TERM AI", and every reply checks the time limit.

TERM AI is not the current intent router (15 intents, 97.6% on the frozen test set). It is
here so people can try where TER-AI started.

## Run it

```
pip install git+https://github.com/klanarongz2009-sketch/terai-router.git@v0.14.0
terai term                         # interactive; type ออก, exit or quit to end
terai term "คำนวณ (12+8)*3"
terai term --debug "ช่วยคิดเลข 3 คูณ 4"   # shows [rule] or [model: intent p= cov=]
terai term --trial-info            # print the end time and exit
python -m terai_router.term_ai.intent_model eval      # leave-one-out accuracy
python -m terai_router.term_ai.intent_model predict "ขอบใจนะ"
```

Example (the first line goes to stderr):

```
$ terai term "คำนวณ (12+8)*3"
TERM AI is a limited-time trial: it stops working at 2027-01-01 00:00:00 Asia/Bangkok (UTC+7) and will be removed from terai-router then (70 days left).
TERM AI> (12+8)*3 = 60
```

Options: `--memory PATH` (default `~/.terai/term_ai.json`, holds only the name you told it
and a message count), `--reset` clears it, `--config FILE` takes the original JSON config keys
(`bot_name`, `tagline`, `user_prompt`, `model_threshold`, `min_coverage`, `greetings`,
`who_reply`, `thanks_reply`, `fallback`, `debug`), `--seed N` fixes the random replies,
`--debug` (or `TERM_AI_DEBUG=1`) shows which layer answered.

From Python:

```python
from terai_router.term_ai import TermAI
bot = TermAI()                 # memory in RAM only; TermAI(memory_path=...) to keep it
print(bot.reply('ผมชื่อต้น'))   # จำแล้ว: ชื่อ ต้น
```

No network, no GPU, no dependencies, Python 3.9+.

## The time limit, exactly

The end is `TRIAL_END = 2027-01-01 00:00:00` at a fixed UTC+7 offset (Thailand has no
daylight saving time, so no tz database is needed). It lives in
`src/terai_router/term_ai/trial.py`.

| When | `terai term` (any arguments, `--help` included) | Python API |
|---|---|---|
| Before 2027-01-01 00:00:00 UTC+7 | prints one line to stderr: `TERM AI is a limited-time trial: it stops working at 2027-01-01 00:00:00 Asia/Bangkok (UTC+7) and will be removed from terai-router then (N days left).`, then runs; exit code 0 | works |
| At 2027-01-01 00:00:00 UTC+7 or later | prints ``TERM AI trial ended at 2027-01-01 00:00:00 Asia/Bangkok (UTC+7). It no longer runs and is being removed from terai-router. Use `terai chat` instead.`` to stderr, prints nothing to stdout, does not read or write the memory file; **exit code 3** | `TermAI(...)` and `TermAI.reply()` raise `TrialEnded` |
| Interactive session still open at midnight | the next message gets no reply; the ended message is printed; exit code 3 | - |

`python -m terai_router.term_ai.intent_model` follows the same rule (exit code 3). The check
reads the machine clock; it is a trial notice, not copy protection (the code is MIT).

Tests (`tests/test_term_ai.py`) inject the clock and never depend on today's date: one
microsecond before the end, exactly at the end, after it, the same instants written in UTC and
in UTC-5, every argument form at and after the end, a session that crosses midnight, and the
library API.

## Accuracy

Leave-one-out on the 149 training sentences: 101/149 (67.8%). There is no held-out test set
for this model; the number is from the original Terminal AI and is reproduced by the tests.

## Not in the browser demo

TERM AI replies only in Thai and the demo UI is English only, so TERM AI is CLI and Python
only. There is no web limit to keep in sync.

## License

Code MIT. `data/model.json` and `data/train_data.json` were written or trained for this
project: MIT ([DATA_LICENSE](../DATA_LICENSE)). No third-party code, data or weights.

## Removal

On 2027-01-01 00:00:00 (UTC+7) TERM AI is removed in one commit. Delete:

- `src/terai_router/term_ai/` (the whole folder: code and `data/`)
- `tests/test_term_ai.py`
- `docs/TERM-AI.md` (this file)

and take TERM AI out of:

- `src/terai_router/cli.py`: the `if argv and argv[0] == 'term':` branch in `main()` and the
  `terai term` line in the module docstring
- `pyproject.toml`: `"term_ai/data/*.json"` in `[tool.setuptools.package-data]`
- `README.md` and `README.th.md`: the TERM AI row of the release table, the TERM AI section,
  the Development line, the Roadmap line and the license-table mention
- `CHANGELOG.md`: keep the v0.14.0 entry as history and add a removal entry
- the wiki: page `TERM-AI`, its `_Sidebar` link, the Home row; keep the History entry

The same lists are in `REMOVAL_PATHS` and `REMOVAL_EDITS` in `trial.py`, and a test checks
that they exist and that nothing outside `cli.py` imports `term_ai`, so the removal cannot
break another part. After removing, `pytest` and `python eval/parity.py` must still pass.
