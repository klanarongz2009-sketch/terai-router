# TERAI1CIBETA v0.1 prototype

TERAI1CIBETA is an early defensive-analysis mode for TER-AI. The name is the owner's wordplay `CIBER + BETA → CIBETA`; BETA describes an adapting early launch. It is a task profile using TERAI1's existing local Gemma 4 E2B base, not a separately trained foundation model.

## What it does

Two read-only workflows analyze only text explicitly provided by the user:

- `source_review`: review authorized source-code excerpts and return evidence-linked hypotheses, safe-fix suggestions, and regression-test ideas.
- `log_triage`: summarize potentially relevant patterns in provided logs/alerts without asserting an attack or attribution beyond the text.

Findings include source line numbers and an exact excerpt; the interface discards findings whose citations do not match the provided input. `confidence` is the model's uncalibrated self-report. A report can abstain or return no findings. Two narrow deterministic checks supplement the model: bare Python `eval()` calls and at least three explicit authentication-failure lines in the supplied excerpt. If model JSON is invalid, only these rule-based findings are returned; otherwise the result explicitly abstains. Comment-only code alerts and successful-login-only log alerts are filtered. These safeguards are limited and are not a substitute for human review.

The mode makes no network calls, does not execute or alter code, does not scan live targets, and does not take remediation actions. Input is capped at 12,000 characters. A narrow preflight guard rejects likely credential assignments/private-key headers before model invocation; redact secrets locally instead of submitting them. This guard is not a complete secret detector. Code and logs are still untrusted input; instruction-like text inside them is treated as data by the prompt, but prompt injection resistance is not guaranteed.

## Use

The local TERAI Gemma model and `llama-cpp-python` must already be installed; this command deliberately does not download weights:

```sh
terai cibeta code snippet.py
terai cibeta logs incident.log --json
cat snippet.py | terai cibeta code -
```

If the model is not present, use TER-AI's separately documented local model setup (`terai chat --setup`) when network download is acceptable, then run the review locally. Never paste credentials into the input.

## Synthetic smoke set

`eval/cibeta_fixtures.json` contains small intentionally safe/vulnerable code and log examples, Thai and English examples, and instruction-like content embedded in source/log strings. Run `python eval/cibeta_smoke.py` with the local model installed. It prints fixture matches and raw categories only; it has no pass threshold and is not a security benchmark. Unit tests in `tests/test_cibeta.py` use a fake client to verify the interface, evidence checks, safe/empty results, credential gate, and prompt-data separation. Those tests do not measure Gemma's detection or prompt-injection behavior.

Before making performance claims, review the fixtures, add held-out examples, test the real model/runtime, and manually inspect false positives, misses, evidence accuracy, fix quality, and abstentions. Do not infer cyber capability from TER-AI's intent-router scorecard.
