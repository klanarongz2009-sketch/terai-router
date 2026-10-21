# `terai muml` CLI contract (MuML 1.0 and MUML 1.0 HIQ)

Two music models share one command. This file is how the two branches agree,
so neither overwrites the other's work.

| Command | Goes to | Package |
|---|---|---|
| `terai muml "<prompt>" ...` | MuML 1.0 (trained from scratch, symbolic MIDI + synth) | `terai_router.muml` |
| `terai muml --hiq "<prompt>" -o song.mp3` | MUML 1.0 HIQ (ACE-Step 1.5 audio) | `terai_router.muml_hiq` |
| `terai muml --model hiq "<prompt>"` | MUML 1.0 HIQ | `terai_router.muml_hiq` |
| `terai muml-hiq "<prompt>"` | MUML 1.0 HIQ (alias) | `terai_router.muml_hiq` |

Rules

1. The dispatcher lives in `src/terai_router/cli.py` `main()`. It checks
   `terai_router.muml_hiq.cli.is_hiq_request(argv)` first. Only when that is false
   does it import `terai_router.muml.cli.main`.
2. MuML 1.0 owns `terai_router/muml/` and every `terai muml` flag except `--hiq`
   and `--model hiq`. If MuML 1.0 adds its own `--model` flag, the value `hiq`
   stays reserved.
3. MUML 1.0 HIQ owns `terai_router/muml_hiq/`, `eval/muml_hiq_*` and
   `tests/test_muml_hiq*.py`. It never edits `terai_router/muml/`.
4. Whichever branch merges second keeps a single `if argv[0] in ('muml', 'muml-hiq')`
   block in `cli.py` with the HIQ check first. Both branches' tests must pass after
   the merge.
5. No weights in the repo for either model.
