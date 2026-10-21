# MUML 1.0 HIQ (prototype, not released)

High-quality text-to-music for TER-AI. Thai or English prompt in, real audio
(.mp3/.wav) out, on a CPU with 8 GB RAM, free, offline after the first download.
MuML 1.0 (trained from scratch, MIDI + synth) is the small model; HIQ is the
high-quality one, built on someone else's open model.

```
terai muml --hiq --setup                     # once: download GGUF weights and build acestep.cpp + yue2.cpp
terai muml --hiq "เพลงลูกทุ่งสนุกๆ มีพิณกับแคน จังหวะ 130" -o song.mp3
terai muml --model hiq "Lo-fi hip hop, 85 BPM, 30 seconds" -o lofi.mp3
terai muml --hiq --dry-run "เปียโนเศร้าๆ ตอนฝนตก"   # show the request, generate nothing
```

Options: `--duration` (10-240 s, default from the prompt or 30), `--bpm`, `--key "A minor"`,
`--lyrics TEXT|FILE` (default instrumental), `--seed`, `--steps` (default 8),
`--quant Q4_K_M|Q8_0`, `--lm-model 0.6B|1.7B` (lyric LM, default 0.6B; Thai lyrics 1.7B),
`--thai-lyrics roman|native` (ACE-Step only, default roman), `--vocal-engine yue2|ace|split`
(default: yue2 for Thai lyrics, ace otherwise), `--yue2-quant Q5_K_M|Q6_K|Q8_0`,
`--thai-vocal sing|split` (older alias of ace|split), `--raw` (skip the adapter), `--status`, `--credits`, `--json`.

## Choosing the engine

| song | default engine | override | time per 30 s (8 vCPU, 8 GB) | licence of the output |
|---|---|---|---|---|
| instrumental | ace (ACE-Step 1.5 turbo) | - | ~4 min | MIT parts only |
| English lyrics | ace (ace-lm + ace-synth) | `--vocal-engine yue2` | ~6-7 min | MIT parts only |
| Thai lyrics | **yue2** (YuE2-3B Q5_K_M, Thai script, 32 steps) | `--vocal-engine ace` / `split` | ~15 min | **CC-BY-NC-4.0: non-commercial** |

yue2 was picked by ear (Bogus, 2026-10-21): it sings the Thai lyrics in order and
more clearly than ACE-Step, although the music-mixed CER below does not separate them.
`split` (ACE-Step instrumental + TTH Wayu voice) scores far better on CER but is
TTS speech on a beat, not singing. yue2.cpp picks one thread per physical core
(logical / 2) by itself; the CLI prints the time estimate and the licence warning
before every yue2 render.

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

Same lyrics, seed 42, 30 s, same ASR, other engines (2026-10-21):

| engine | CER | words | wall / peak RSS |
|---|---|---|---|
| **yue2 (default for Thai)**: YuE2-3B Q5_K_M, Thai script, 32 steps, 4 threads, via this CLI | 0.9065 | 4/30 (คืนนี้, ฟ้า, แค่, จอ, in lyric order) | 14:02.84 / 2.93 GB |
| YuE2-3B Q5_K_M, romanised lyrics | 0.9346 | 1/30 | 13:40 / 3.21 GB |
| ACE-Step LM 4B Q5_K_M + romanised | 0.8131 | 3/30 | LM 1:01 / 5.59 GB, synth 3:31 / 5.49 GB |
| split, snap style via this CLI (TTH Wayu speech, not singing) | 0.2430 | 20/30 | 5:43.94 / 3.33 GB |

The yue2 CLI run (`/usr/bin/time -v`, nothing else heavy running) produced a file
byte-identical to the earlier direct yue-synth run with the same request, so the
engine is deterministic for a given seed. The CER of yue2 and ACE-Step are both near
the floor with music mixed in; yue2 is the default because it sounded clearer.

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
| YuE2-3B + YuE2-Vae (m-a-p), Thai-lyrics engine | CC-BY-NC-4.0 | https://huggingface.co/m-a-p/YuE2-3B |
| YuE2 GGUF conversions | CC-BY-NC-4.0 | https://huggingface.co/Serveurperso/YuE2-GGUF |
| yue2.cpp (ggml), pinned 8af01740686824ffd4a1839a457954f42e2a8ce7 | MIT | https://github.com/ServeurpersoCom/yue2.cpp |
| Wayu-Paxa-TTS-Edge (split mode only) | CC-BY-NC-4.0 | NOTICE item 1 |

Commercial use is allowed for instrumentals and English songs on ACE-Step; songs
made with the yue2 (default for Thai lyrics) or split engine are non-commercial only.
Keep the credit line from `terai muml --hiq --credits`. No weights are stored in this repository.
