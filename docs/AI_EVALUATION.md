# TER-AI evaluation and safe-comparison guide

This guide turns the v0.18.0-alpha evaluation work into a repeatable practice. The first executable scorecard covers the intent router only; it does not imply that every TER-AI component has been benchmarked or that an external model is a suitable replacement.

## What this release changes

- `python eval/router_report.py` scores the production router on the checked-in frozen test and held-out sets. It prints dataset SHA-256 values, overall and macro intent accuracy, per-category/per-intent results, and average confidence/feature coverage.
- `--threshold 0.80` optionally reports the fraction of cases above a confidence threshold and their accuracy. This is a diagnostic, not a safety guarantee or calibrated confidence estimate.
- The scorer is local and makes no network calls. Frozen sets remain evaluation data: do not train on them or tune a threshold against the held-out set and then describe that same result as independent validation.

## Benchmark claims need scope

Gemini 4 Carbon's published cybersecurity scores are claims about that model in specified benchmark setups, not estimates of real-world exploit success and not transferable scores for TER-AI. Google reported 88.2% on SEC-bench Pro, 54.8% on ExploitGym, and 71.0% on CWE-bench; it said its external cyber tests were run without guardrails. The public announcement does not fully specify model snapshot, prompts, agent scaffolding, repetitions, uncertainty, or contamination controls needed for a complete reproduction.

Artificial Analysis independently ranked Carbon first with 59 on Intelligence Index v5, a broad general-capability index, not a cyber benchmark. CWE-bench's v1 page lists Carbon's 71% programmatic pass@1 and 81% pass@4 under Antigravity/high reasoning, four rollouts per task and up to one hour per rollout; the private test set limits independent reproduction. SEC-bench Pro uses already reported vulnerabilities and supplies task clues, so prior exposure to public reports/patches is a possible contamination risk. ExploitGym is a controlled challenge, not a measure of the likelihood of exploiting an arbitrary live system. See the linked benchmark/methodology pages and their versioned protocols before comparing numbers:

- [Google's Carbon announcement](https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-gemini-4-carbon/)
- [Artificial Analysis Intelligence Index](https://artificialanalysis.ai/evaluations/artificial-analysis-intelligence-index) and [methodology](https://artificialanalysis.ai/methodology/intelligence-benchmarking/)
- [SEC-bench Pro](https://github.com/SEC-bench/SEC-bench-Pro)
- [ExploitGym paper](https://arxiv.org/html/2605.11086)
- [CWE-bench v1](https://cwe-bench.com/)

Do not infer from those results that TER-AI's local Gemma 4 E2B has equivalent coding/cyber capabilities, that a broad index predicts Thai quality, or that the largest model should replace TER-AI's local-first design. Compare only results made with the same task set, version, prompt, tools, time/compute limits, number of attempts and scoring rules. Keep vendor-reported, benchmark-maintainer, and independently reproduced results clearly attributed.

## A reproducible evaluation loop

1. Record the code revision, package/model versions, hardware, OS/Python, dependency versions, model artifact/revision and hashes, configuration, prompt, tools, network mode, seeds, timeouts and number of attempts.
2. Keep train, development and held-out cases separate. Freeze the test data and publish its SHA-256; do not use held-out examples for tuning. Report failures and the denominator, not only a rounded success rate.
3. Use the current behavior as a baseline. Change one thing at a time (router, prompt, model, retrieval, verifier, or tool) and rerun the same frozen suite. Add genuinely new cases to a later versioned set rather than silently editing old results.
4. Report quality together with operating cost: latency (p50/p95), peak RAM, model/download size, CPU/GPU, offline behavior, and whether a first-run download was needed. For small datasets, show raw `correct/total` and avoid claims of statistical certainty.
5. A model comparison must use identical task wording and permitted context. If a hosted model is evaluated, use only public or synthetic/non-sensitive inputs, record endpoint/model version and cost, and make the cloud run opt-in. Do not send private user data just to compare scores.

### Component-specific measures

- **Intent router:** exact intent accuracy, macro-average across intents, category breakdown (including typo and Thai-English cases), confidence/coverage diagnostics, and latency. Keep unknown/out-of-scope requests separate so they do not inflate ordinary intent accuracy.
- **Chat / TERAI1:** expected-answer correctness, source attribution, unsupported claims, appropriate abstention, regression behavior, Thai fluency reviewed separately, plus latency/RAM. Mocked outputs validate guard logic but do not substitute for a real-model run.
- **Vision / OCR:** exact text and character error rate by script and image condition (small text, low contrast, dark background, charts); assess image-question correctness separately from transcription.
- **TTH speech:** preserve reference text/audio and report Thai word/character error rate with a named recognizer as a rough signal; include listening review because ASR scores alone do not establish naturalness or intelligibility.
- **SANKPUP SVG:** parse/sanitize/render success, empty or malformed output, output constraints and human-rated relevance. A syntactically valid SVG is not necessarily a good picture.
- **Music/audio:** duration and file validity, clipping/silence and repeatability where relevant; blind human review for musical fit and intelligible lyrics. Keep ASR-on-music results labelled as rough proxies.
- **Coding assistance:** use small, versioned repository tasks with tests and expected behavior. Measure tests passed, regressions, accepted patches and runtime; inspect diffs. Run only in a disposable, least-privilege workspace with no credentials or production data.

## Cybersecurity and code-execution boundary

Start with defensive code review and safe bug-fix tasks in TER-AI-owned code, not exploit generation or testing live third-party systems. A test runner may execute arbitrary code. TER-AI's Tagentic workspace checks path boundaries and asks for approval on sensitive tools, but the project documentation notes that shell/Python tools are not a hard security jail. Do not treat a working directory or approval prompt alone as isolation. For any agentic code task, use a separate disposable OS/container sandbox with no secrets, restricted network, resource limits and an explicit diff/test review before applying changes. Keep the adversarial set synthetic or intentionally vulnerable and local.

## Current limits and next measurements

The router report uses existing frozen internal sets and is an operationally reproducible baseline, not an independent external benchmark or a new held-out test. This release does not run a live Gemma model, TTS engine, vision model, music model, external cloud model, or cybersecurity benchmark. Those require their model assets, optional dependencies, hardware and explicitly documented runs. The project's existing component-specific scripts remain the source for those opt-in runs; mark missing runs as not run rather than as failures or successes.
