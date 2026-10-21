# MUML 1.0 HIQ (prototype, not released)

High-quality text-to-music for TER-AI. Thai or English prompt in, real audio
(.mp3/.wav) out, on a CPU with 8 GB RAM, free, offline after the first download.
MuML 1.0 (trained from scratch, MIDI + synth) is the small model; HIQ is the
high-quality one, built on someone else's open model.

```
terai muml --hiq --setup                     # once: download GGUF weights (~2.6 GB) and build acestep.cpp
terai muml --hiq "เพลงลูกทุ่งสนุกๆ มีพิณกับแคน จังหวะ 130" -o song.mp3
terai muml --model hiq "Lo-fi hip hop, 85 BPM, 30 seconds" -o lofi.mp3
terai muml --hiq --dry-run "เปียโนเศร้าๆ ตอนฝนตก"   # show the request, generate nothing
```

Options: `--duration` (10-240 s, default from the prompt or 30), `--bpm`, `--key "A minor"`,
`--lyrics TEXT|FILE` (default instrumental), `--seed`, `--steps` (default 8),
`--quant Q4_K_M|Q8_0`, `--lm-model 0.6B|1.7B` (lyric LM, default 0.6B; Thai lyrics 1.7B),
`--thai-lyrics roman|native` (default roman), `--raw` (skip the adapter), `--status`, `--credits`, `--json`.

## How it works

1. **Prompt adapter** (`terai_router/muml_hiq/adapter.py`, pure Python, deterministic).
   ACE-Step 1.5 was trained on English-style captions plus explicit metadata.
   The adapter turns a Thai prompt into English music tags (genre, Thai instruments
   such as phin, khaen, ranat, khlui, mood, scene) and pulls BPM, duration, key and
   time signature into their own fields; Thai digits, tempo words (ช้า/เร็ว) and
   genre default tempos included. English prompts keep the user's wording and only
   have the metadata moved out. Unknown Thai is passed through verbatim.
2. **ACE-Step 1.5 turbo** (2.39 B-parameter DiT, 8 steps) renders the audio through
   **acestep.cpp** with GGUF Q4_K_M weights, text encoder Qwen3-Embedding-0.6B Q8_0 and
   the BF16 VAE. Instrumentals skip the 5 Hz LM planner.
3. **Songs with `--lyrics`** run `ace-lm` first (writes the audio codes the vocals
   follow), then `ace-synth`. Without the LM step there are no vocals. `vocal_language`
   comes from the lyrics script, not the prompt (Thai prompt + English lyrics = `en`).

### Thai lyrics (test 2026-10-21, seed 42, 30 s, turbo Q8, 8 steps)

CER with Thai ASR `airesearch/wav2vec2-large-xlsr-53-th`, music mixed in (no source
separation), against the Thai lyrics; "words" = lyric words found in the transcript:

| variant | CER | words | LM time / peak RSS |
|---|---|---|---|
| old: LM 0.6B + Thai script, `th` | 0.8411 | 3/30 | 2:02 / 2.68 GB |
| A: LM 1.7B + Thai script, `th` | 0.8692 | 0/30 | 1:35 / 4.05 GB |
| B: LM 0.6B + romanised, `unknown` | 0.8972 | 3/30 | 2:04 / 2.68 GB |
| C: LM 1.7B + romanised, `unknown` | 0.8411 | 5/30 | 1:24 / 4.06 GB |
| floor: English song (no Thai) | 0.8131 | 3/30 | - |

No variant is clearly intelligible to the ASR (all near the English-song floor).
C is the default for Thai lyrics because it scored best on lyric words; romanisation
uses PyThaiNLP `royin` (optional dependency; without it Thai script is sent as `th`).

## What "จูน" means here

The weights are **not** fine-tuned. HIQ is tuned at the conditioning level: the
adapter above, which is what turned out to be doable on this machine. A LoRA on the
DiT was not run:

- The turbo DiT has 2,394 M parameters (read from the safetensors header). In fp32 that
  is 9.58 GB of weights alone, more than the 8 GB VM. In bf16 it is 4.79 GB, but this CPU
  has AVX2 only (no AVX512-BF16 or AMX), so bf16 training would run emulated, and the
  other TER-AI jobs already hold about 3 GB of RAM.
- acestep.cpp can load PEFT LoRA adapters at inference time, so a LoRA trained elsewhere
  (a free GPU) can be dropped in later without changing this code.
- No training data was used, so there is no dataset licence to clear yet.

## Licences and credits

| Part | Licence | Source |
|---|---|---|
| TER-AI code (adapter, wrapper) | MIT | this repo |
| ACE-Step 1.5 weights + code | MIT, not gated | https://huggingface.co/ACE-Step/Ace-Step1.5 |
| GGUF conversions | MIT | https://huggingface.co/Serveurperso/ACE-Step-1.5-GGUF |
| Qwen3-Embedding-0.6B | Apache-2.0 | https://huggingface.co/Qwen/Qwen3-Embedding-0.6B |
| acestep.cpp (ggml) | MIT | https://github.com/ServeurpersoCom/acestep.cpp |

Commercial use is allowed by these licences; keep the credit line from
`terai muml --hiq --credits`. No weights are stored in this repository.
