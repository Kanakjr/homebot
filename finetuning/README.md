# Qwen3.5 HomeBot Fine-tune (Distillation Pipeline)

This folder contains the end-to-end pipeline to fine-tune **Qwen3.5** (2B or 4B)
into a drop-in replacement for the Gemini-backed `deepagent` runtime. It combines
a **teacher-student distillation loop** with **real Telegram chat history** to
produce a hybrid multi-turn ChatML dataset, then trains a bf16 LoRA on a free
Colab T4 and exports a Q4_K_M GGUF that plugs into Ollama.

The Colab notebook exposes `MODEL_SIZE` (`"2B"` or `"4B"`) as a single knob --
everything else (LoRA attach, chat template, SFT loop, GGUF export, Ollama
Modelfile) is identical across sizes because it follows Unsloth's official
Qwen3.5 recipe. Recommended flow: run 2B first for a fast sanity loop, then
switch to 4B for the final ship build.

A parallel **Gemma 4** notebook (`unsloth_gemma4_homebot.ipynb`) trains Google's
Gemma 4 E2B / E4B on the same dataset with the same LoRA + GGUF flow, so you
can A/B the two architectures without rebuilding any data. See
[Which model should I train?](#which-model-should-i-train) below.

After training, flipping `MODEL=ollama:homebot-<family>-<size>` in the deepagent
env is all it takes to swap from Gemini to the local model.

## Why Qwen3.5, bf16 LoRA?

| Candidate | Size | T4 VRAM (bf16 LoRA) | ~2 epoch wall-clock | Role |
|---|---|---|---|---|
| **Qwen3.5-2B** | 2B dense | ~5 GB  | ~8 min  | **fast first pass** -- sanity-check pipeline |
| **Qwen3.5-4B** | 4B dense | ~10 GB | ~20 min | **final ship build** |
| Qwen3.6-35B-A3B | 35B MoE | No fit | -- | rejected: MoE too large for free T4 |
| Qwen3-4B-Instruct-2507 | 4B dense | ~6 GB 4-bit | ~15 min | older family, Qwen3.5 preferred |

Unsloth explicitly warns that 4-bit QLoRA on Qwen3.5 produces *"higher than
normal quantization differences."* We therefore use **bf16 LoRA** (trades ~2x
VRAM for better accuracy -- still fits 16 GB T4). Thinking mode is disabled by
default on small Qwen3.5 models, which is exactly what we want for
deterministic tool calls.

## Which model should I train?

Three viable families work on the current dataset. All three reuse the exact
same `kanakjr/homebot-qwen3.5` hub dataset -- the conversations are model-
agnostic until `apply_chat_template` runs in step 5, so no re-curation is
required to try a different architecture.

| Family              | Params  | bf16 on T4? | Mac Ollama Q4_K_M (est) | Tool-call format           | When to pick |
|---------------------|---------|-------------|-------------------------|----------------------------|--------------|
| **Qwen3.5-2B**      | 2B      | yes (~5 GB) | **~30 tok/s** (fastest) | ChatML `<tool_call>` JSON  | Fast lane -- short commands, snappy Telegram loop |
| **Qwen3.5-4B**      | 4B      | yes (~10 GB)| ~18 tok/s               | ChatML `<tool_call>` JSON  | **Production default** -- proven tool loop, ship build |
| Gemma 4 E2B         | 5.1B    | yes (~10 GB)| ~15 tok/s               | Native OpenAI `tool_calls` | A/B candidate -- newer training, 128K ctx, 140 langs |
| Gemma 4 E4B         | 8B      | **no** (16 GB > T4; QLoRA only) | ~8-10 tok/s | Native OpenAI `tool_calls` | Quality ceiling on Ampere+ hardware; slow on Mac |

**Recommendation:**

1. **Production: Qwen3.5-4B.** The current pipeline, prompts, and Modelfile are
   tuned around Qwen's ChatML tool-call format. Keep shipping this.
2. **Fast lane: Qwen3.5-2B.** Meaningfully snappier on Mac for quick commands
   (`"turn off the light"`). Useful as a router / quick handler in front of 4B.
3. **Experiment: Gemma 4 E2B.** Very similar footprint to Qwen3.5-4B on disk
   but newer training data, native OpenAI-format tool calling (less escaping at
   inference), and 128K context. Worth A/B-ing if you suspect Qwen is
   bottlenecking on Indian-English / Hindi code-mixing.
4. **Skip for now: Gemma 4 E4B.** Doesn't fit bf16 on Colab T4; QLoRA on T4
   degrades accuracy; on Mac it's ~2x slower than Qwen3.5-4B at the same
   quantisation. Only worth training if you have an L4 / A100 / RTX 4090+.

## Architecture

```
Telegram threads        SKILL.md contexts
 in LangSmith              (~7 skill families)
       |                         |
       |                         v
       |                dataset_generator.py
       |                (clustered per skill,
       |                 300 queries total)
       |                         |
       |                         v
       |               run_deepagent_simulation.py
       |                (POST live deepagent,
       |                 tagged distillation_simulation)
       |                         |
       |                         v
       |                  LangSmith traces
       |                         |
       v                         v
extract_telegram_dataset.py  langsmith_client.py +
 (multi-turn ChatML,           dataset_formatter.py
  real conversations)         (multi-turn ChatML,
       |                       full tool loops)
       \                         /
        \                       /
         v                     v
               merge_datasets.py
            (dedup + 90/10 split)
                    |
                    v
     data/qwen3_5_training.jsonl
     data/qwen3_5_val.jsonl
                    |
                    v
               push_to_hub.py
          (kanakjr/homebot-qwen3.5)
                    |
                    v
   unsloth_qwen3_5_4b_homebot.ipynb
         (Colab T4, bf16 LoRA, MODEL_SIZE="2B"|"4B")
                    |
                    v
     homebot-qwen3_5-{2b|4b}.Q4_K_M.gguf
                    |
                    v
   ollama create homebot-qwen3_5-{2b|4b}
                    |
                    v
      MODEL=ollama:homebot-qwen3_5-{2b|4b}
```

## Training Example Shape

Every training row is one multi-turn conversation covering the full agent loop,
so the fine-tuned model learns to both emit tool calls AND synthesize the final
natural-language response from tool outputs:

```json
{"messages": [
  {"role": "system", "content": "You are HomeBotAI, ..."},
  {"role": "user", "content": "turn off the air purifier"},
  {"role": "assistant", "content": "", "tool_calls": [
    {"id": "c1", "type": "function",
     "function": {"name": "ha_call_service",
                  "arguments": "{\"domain\":\"fan\",\"service\":\"turn_off\",\"entity_id\":\"fan.air_purifier\"}"}}
  ]},
  {"role": "tool", "tool_call_id": "c1", "name": "ha_call_service",
   "content": "{\"success\": true}"},
  {"role": "assistant", "content": "Done -- air purifier is off."}
]}
```

## File Layout

| File | Role |
|---|---|
| `dataset_generator.py` | Clustered per-skill synthetic query generator (Gemini 2.5 Pro, 300 queries default) |
| `run_deepagent_simulation.py` | Fires queries at the live deepagent HTTP stream, auto-repairs missing tool calls |
| `langsmith_client.py` | Downloads `distillation_simulation`-tagged traces -> `data/langsmith_export.jsonl` |
| `dataset_formatter.py` | Multi-turn formatter: walks full LangSmith chain -> `data/qwen_training_dataset.jsonl` |
| `extract_telegram_dataset.py` | Pulls real `telegram-*` threads from LangSmith -> `data/real_telegram.jsonl` |
| `merge_datasets.py` | Dedup + 90/10 split -> `data/qwen3_5_training.jsonl` + `data/qwen3_5_val.jsonl` |
| `push_to_hub.py` | Push merged splits to `kanakjr/homebot-qwen3.5` on HF Hub |
| `run_pipeline.sh` | Orchestrator wrapping every step (see `Commands` below) |
| `unsloth_qwen3_5_4b_homebot.ipynb` | **Colab T4** notebook (Qwen): bf16-declared LoRA (runs as fp16 on T4), `FastVisionModel` loader, parquet fallback for Colab's older `datasets`, `train_on_responses_only`, GGUF Q4_K_M |
| `unsloth_qwen3_5_homebot_nvidia.ipynb` | **Native NVIDIA GPU** notebook (Qwen): real bf16 LoRA, `FastLanguageModel`, auto batch-size from free VRAM, Flash Attention 2; targets Ampere/Ada/Hopper/Blackwell (A100, L4, RTX 4090/6000 Ada, H100, B200, RTX Pro 6000) |
| `unsloth_gemma4_homebot.ipynb` | **Colab T4** notebook (Gemma 4): same LoRA + GGUF flow on Gemma 4 E2B (bf16) or E4B (auto-QLoRA on T4). Reuses `kanakjr/homebot-qwen3.5` dataset unchanged; swaps chat template, `train_on_responses_only` delimiters, and Modelfile. |
| `scripts/build_gemma4_notebook.py` | Generator that re-emits `unsloth_gemma4_homebot.ipynb` from the Qwen T4 notebook so the two stay in parity. Run `python scripts/build_gemma4_notebook.py` after editing the Qwen notebook to propagate shared changes (install pins, LoRA config, SFT args, etc.). |
| `homebot_qwen3_5.Modelfile` | Ollama Modelfile with Qwen3.5 sampling params + tool_call template |
| `requirements.txt` | Python deps for local pipeline (not Colab) |

## Execution Guide

### 1. Initial Setup

`run_pipeline.sh` automatically creates `finetuning/.venv` and installs from
`requirements.txt` on first run. Credentials are read from
`../deepagent/.env`:

- `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` -- required for both the synthetic
  extract (`extract`) and the real-telegram extract (`real`).
- `GEMINI_API_KEY` -- required for `generate`.
- `HF_TOKEN` -- required for `push` (optional for Colab load).
- `API_KEY` -- required for `simulate` (deepagent HTTP auth).

If you're behind a corporate proxy, remember to:

```bash
source ~/Workspace/set-proxy.sh
```

before running the scripts.

### 2. Build the dataset

```bash
cd Apps/homebot/finetuning

./run_pipeline.sh generate                    # 300 synthetic queries, clustered per skill
./run_pipeline.sh simulate --limit 50          # fire at live deepagent; WARNING: real side effects
./run_pipeline.sh extract                      # pull distillation_simulation traces from LangSmith
./run_pipeline.sh format                       # synthetic traces -> multi-turn ChatML JSONL
./run_pipeline.sh real --days 60               # real telegram history -> multi-turn ChatML JSONL
./run_pipeline.sh merge                        # dedup, 90/10 split
./run_pipeline.sh push                         # push to kanakjr/homebot-qwen3.5 on HF Hub
```

Each step is idempotent: re-running `format`/`real`/`merge`/`push` after adding
new traces is cheap (dedup keeps duplicates out). Use `./run_pipeline.sh all`
to run every step back-to-back.

Inspect the produced dataset locally:

```bash
head -n 1 data/qwen3_5_training.jsonl | python -m json.tool | head -60
wc -l data/qwen3_5_training.jsonl data/qwen3_5_val.jsonl
```

### 3. Train on Google Colab

1. Open `unsloth_qwen3_5_4b_homebot.ipynb` in Colab with a **T4 GPU** runtime.
2. In **Step 0** paste your HF write token, then pick a size:
   - `MODEL_SIZE = "2B"` (default) -- ~5 GB VRAM, ~8 min for 2 epochs on T4.
     Start here on the first end-to-end run.
   - `MODEL_SIZE = "4B"` -- ~10 GB VRAM, ~20 min for 2 epochs on T4. Use for
     the final ship build once the 2B run looks healthy.
3. `Runtime -> Run all`. No other stops. The notebook pulls the dataset from
   `kanakjr/homebot-qwen3.5` on HF Hub using the token from Step 0.
4. Step 16 writes `homebot-qwen3_5-<size>.Q4_K_M.gguf` + a matching
   `homebot-qwen3_5-<size>.Modelfile`. Download both via the Colab file
   browser -- the size-suffixed filenames mean 2B and 4B builds never
   overwrite each other in either Colab or Ollama.

**Tuning knobs** (in the notebook):

- `MODEL_SIZE` (step 0): `"2B"` or `"4B"` -- picks model, GGUF filename,
  Ollama tag, and HF GGUF repo automatically.
- `REAL_OVERSAMPLE` (step 5.5, default 4): how many times to duplicate each
  real Telegram row in the train set. With 16 real rows, 4x => 64 -- target
  a synthetic:real ratio of ~3:1 after oversampling.
- Under-fit after 2 epochs? bump `LORA_R` and `LORA_ALPHA` to 32 in step 0.
- OOM on T4? use `MODEL_SIZE = "2B"` instead of `"4B"`.
- Want longer context? increase `MAX_SEQ_LENGTH` to 8192 in step 0 (costs VRAM).

The merge step already prints a `[merge] WARNING: synthetic/real ratio is
N/M (>=5x)` line when the dataset is skewed; that's your cue to bump
`REAL_OVERSAMPLE` or run `./run_pipeline.sh real --days 365 --limit 5000`
to pull more authentic Telegram history before re-merging.

### 3b. Train on a native NVIDIA GPU (A100 / L4 / RTX 4090 / RTX 6000 Ada / H100 / B200 / RTX Pro 6000)

Prefer this path over the Colab notebook when you have access to an Ampere or
newer GPU -- it trains in **native bf16**, auto-sizes the batch to the detected
free VRAM, and skips every Colab-specific workaround (no `torchcodec` uninstall,
no `FastVisionModel` dtype-juggling, no raw-parquet fallback).

1. Upload `unsloth_qwen3_5_homebot_nvidia.ipynb` to your GPU box (Jupyter, VS
   Code remote, or a Kubernetes/Brev/Runpod-style notebook node).
2. **Step 0** -- paste your HF write token, pick `MODEL_SIZE = "2B"` or
   `"4B"`. `BUILD_TAG` is derived from the size so 2B and 4B artifacts never
   collide.
3. **Step 2** -- the notebook auto-detects the GPU, reports `bf16_supported`,
   and picks `BATCH_SIZE` based on free VRAM (e.g. 8 on 48 GB, 16 on 180 GB).
   Override by setting `BATCH_SIZE` explicitly in step 0.
4. `Run All`. The dataset is pulled from `kanakjr/homebot-qwen3.5` exactly
   like the Colab flow, but `load_dataset()` just works (modern `datasets`).
5. Step 15 emits the GGUF at `./{BUILD_TAG}/{BUILD_TAG}.Q4_K_M.gguf`. Step 17
   writes a matching `{BUILD_TAG}.Modelfile` (the canonical template from
   `homebot_qwen3_5.Modelfile`, with the `FROM` line rewritten to point at
   the new GGUF).
6. `scp` both files back to the Mac and follow the Ollama steps in 4. below.

Rough wall-clock (2 epochs, bf16 LoRA, `BATCH_SIZE=8`):

| GPU                 | VRAM    | Qwen3.5-2B | Qwen3.5-4B |
|---------------------|---------|------------|------------|
| RTX 4090            | 24 GB   | ~2 min     | ~5 min     |
| RTX 6000 Ada        | 48 GB   | ~3 min     | ~8 min     |
| H100                | 80 GB   | ~1 min     | ~3 min     |
| B200                | 180 GB  | ~45 s      | ~2 min     |

(Colab T4 is ~8 min / 2B, ~20 min / 4B for comparison.)

Step 16 has optional flags (`PUSH_GGUF_TO_HUB`, `PUSH_MERGED_TO_HUB`) if you
want the GGUF or full 16-bit merged weights backed up on
`kanakjr/homebot-qwen3.5-{2b|4b}-gguf`.

### 3c. Train Gemma 4 on Colab T4

Same dataset, same LoRA recipe, Google's Gemma 4 instead of Qwen3.5. Use this
when you want to A/B Gemma against the Qwen ship build (see
[Which model should I train?](#which-model-should-i-train)).

1. Open `unsloth_gemma4_homebot.ipynb` in Colab with a **T4 GPU** runtime.
2. In **Step 0** paste your HF write token, then pick a size:
   - `MODEL_SIZE = "E2B"` (default) -- ~10 GB VRAM in bf16 LoRA, ~12 min for
     2 epochs on T4. Comfortable fit. Start here.
   - `MODEL_SIZE = "E4B"` -- 8B params, 16 GB bf16 (doesn't fit T4). The
     registry auto-sets `load_in_4bit = True` so E4B runs as QLoRA on T4;
     flip it back to `False` if you are on L4 / A100 / RTX 4090+.
3. `Runtime -> Run all`. The install cell pins `transformers==5.5.0`,
   `datasets==4.3.0`, and `timm` (required for Gemma 4's vision/audio towers
   -- we freeze them and only train language layers).
4. Step 16 writes `homebot-gemma4-<e2b|e4b>.Q4_K_M.gguf` + a matching
   `homebot-gemma4-<e2b|e4b>.Modelfile`. Download both, `ollama create`, and
   the DeepAgent's existing `ollama:<name>` resolver picks it up.

**What's different from the Qwen notebook (at a glance):**

| | Qwen3.5 notebook | Gemma 4 notebook |
|---|---|---|
| Chat template | `"qwen3-instruct"` (`<\|im_start\|>role`) | `"gemma-4"` (`<start_of_turn>role`) |
| Assistant role name | `assistant` | `model` |
| `train_on_responses_only` delimiters | `<\|im_start\|>user\n` / `<\|im_start\|>assistant\n` | `<start_of_turn>user\n` / `<start_of_turn>model\n` |
| Tool-call serialisation in GGUF | `<tool_call>{...}</tool_call>` wrapper | Native OpenAI `tool_calls` array |
| Install pins | `transformers==5.2.0` | `transformers==5.5.0` + `timm` |
| Stop tokens (Modelfile) | `<\|im_end\|>`, `<\|im_start\|>`, `<\|endoftext\|>` | `<end_of_turn>`, `<start_of_turn>`, `<eos>` |
| Ollama TEMPLATE block | explicit Go template w/ tool_call branch | omitted -- relies on GGUF metadata auto-detect |

`unsloth_gemma4_homebot.ipynb` is **regenerated from the Qwen T4 notebook** via
`scripts/build_gemma4_notebook.py`. If you edit the Qwen notebook (dataset
loader, LoRA config, SFT args, etc.), re-run the generator to propagate the
change into the Gemma notebook. Model-specific cells (config, install, model
load, chat template, response-mask delimiters, Modelfile, troubleshooting)
are overridden inside the script and won't be clobbered.

```bash
cd Apps/homebot/finetuning
python scripts/build_gemma4_notebook.py
```

### 4. Deploy locally via Ollama

Pick the build you want to deploy, place its GGUF next to its Modelfile, then:

```bash
cd Apps/homebot/finetuning

# Qwen3.5-2B fast build
ollama create homebot-qwen3_5-2b -f homebot-qwen3_5-2b.Modelfile
ollama run homebot-qwen3_5-2b "turn off the air purifier"

# Qwen3.5-4B final build (can coexist with 2B -- different names)
ollama create homebot-qwen3_5-4b -f homebot-qwen3_5-4b.Modelfile
ollama run homebot-qwen3_5-4b "turn off the air purifier"

# Gemma 4 E2B experimental build (coexists with Qwen builds)
ollama create homebot-gemma4-e2b -f homebot-gemma4-e2b.Modelfile
ollama run homebot-gemma4-e2b "turn off the air purifier"
```

Flip the deepagent over by setting in `Apps/homebot/deepagent/.env`:

```
MODEL=ollama:homebot-qwen3_5-4b       # production
# MODEL=ollama:homebot-qwen3_5-2b     # fast lane
# MODEL=ollama:homebot-gemma4-e2b     # A/B candidate
```

`deepagent/agent.py::_resolve_model` already handles the `ollama:` prefix, so
you can A/B builds just by editing this one line and restarting the deepagent.

## Data Quality Gates

The `format` and `real` stages share a single cleanup pipeline
(`extract_telegram_dataset.py`) that enforces:

- **Entity rename + drop.** `ENTITY_RENAMES` rewrites renamed Home Assistant
  entity IDs (e.g. `fan.xiaomi_smart_air_purifier_4` -> `fan.air_purifier`).
  `DROP_ENTITY_TOKENS` (incl. `HA_HIDDEN_ENTITIES`) discards any chain that
  still references a removed/hidden entity so the model never learns dead IDs.
- **Repair-prompt splice.** The simulator's nudge ("You did not actually
  perform the action...") and the preceding hallucinated assistant turn are
  spliced out, so the model is NOT trained to wait for a nag before tool
  calling.
- **Reasoning-tag strip.** `<thinking>` / `<think>` / `<reasoning>` blocks
  (common in Gemini 2.5/3 output) are removed from assistant content.
- **Tool-call JSON validation.** Every `tool_call.function.arguments` string
  is `json.loads`'d; any malformed tool call drops the whole chain.
- **Min-length final response.** Final assistant text must be >=3 words;
  "Done." / "" -only completions are discarded.
- **Tool output truncation.** Tool results >4000 chars are clamped.
- **System-prompt re-injection.** The stored trace's system prompt is
  overwritten with the live `get_system_prompt()` at format time, so training
  always matches current production behavior.
- **Dedup.** Sha256 of (role, content, tool_call signature) excluding system;
  real-source rows win on collision with synthetic duplicates.
- **Spot-check.** `merge` prints 5 random sampled training examples and warns
  if synthetic >> real.

## Tips & Gotchas

- **`simulate` WILL cause real side effects** (lights toggle, torrents queue,
  movies added to Radarr). Use `--limit 1` first and keep an eye on LangSmith.
- The formatter picks the LangSmith trace with the **longest input history**
  per user query -- this is how we capture the full multi-turn chain instead
  of the first tool call only.
- `merge_datasets.py` prefers `telegram`-sourced conversations over synthetic
  duplicates, so your real voice dominates where they overlap.
- If the Colab `apply_chat_template` rendering looks wrong (missing tool
  delimiters), print `train_ds[0]["text"]` in step 6 to confirm; the shape
  should include `<|im_start|>tool` blocks.
- The Modelfile ships with a compact fallback SYSTEM prompt for direct
  `ollama run` debugging; at runtime the deepagent injects its authoritative
  system prompt via the LangChain chat interface, which takes precedence.

## Troubleshooting

### `Removed N out of M samples where all labels were -100`

This is Unsloth's way of saying `train_on_responses_only` could not find
any assistant response tokens in those rows. There are three distinct
causes we have hit; check them in this order:

**1. `FastVisionModel.from_pretrained` didn't receive `max_seq_length`.**

This is the one that bit us hardest. If you load the model like this:

```python
model, tokenizer = FastVisionModel.from_pretrained(
    MODEL_NAME,
    load_in_4bit = False,   # no max_seq_length passed
)
```

Unsloth silently defaults to `max_seq_length = 2048-4096`. That cap is
baked into the model and tokeniser and clips downstream tokenisation
even when `SFTConfig.max_length` is larger. Rows longer than the default
get right-truncated past the assistant turn, masking fails, and those
rows are dropped. The symptom is suspiciously specific: the number of
rows that survive equals the number of rows shorter than 4096 tokens.

Fix: pass it explicitly (already applied in the notebook).

```python
model, tokenizer = FastVisionModel.from_pretrained(
    MODEL_NAME,
    max_seq_length = MAX_SEQ_LENGTH,   # <-- REQUIRED
    load_in_4bit   = False,
    use_gradient_checkpointing = "unsloth",
)
```

**2. Defensive: use the inner text tokeniser, not the VLM processor.**

`FastVisionModel` returns a Qwen3.5-VL *processor*, not a plain text
tokeniser. Its `__call__` treats the first positional argument as image
input, so any code path that passes the chat-template string positionally
(e.g. the sanity-inference cell in step 12) crashes with `ValueError:
Incorrect image source`. It is not the primary cause of dropped rows in
training, but it is a sharp edge worth avoiding. Extract the inner text
tokeniser once and reuse it:

```python
_text_tok = getattr(tokenizer, "tokenizer", tokenizer)

trainer = SFTTrainer(model=model, tokenizer=_text_tok, ...)

trainer = train_on_responses_only(
    trainer,
    tokenizer        = _text_tok,
    instruction_part = "<|im_start|>user\n",
    response_part    = "<|im_start|>assistant\n",
)
```

On the NVIDIA notebook this is a no-op because `FastLanguageModel` already
exposes a plain tokeniser with no `.tokenizer` attribute.

**3. Legitimate truncation of rare, very long rows.**

After fixes 1 and 2 you should see the vast majority of rows survive
(e.g. 262/268 at `MAX_SEQ_LENGTH=12288`). The handful that still drop are
genuine outliers whose raw token length exceeds your budget. Either raise
`MAX_SEQ_LENGTH` further (16384 keeps ~264/268), or accept the loss.

### Debugging tip: measure token lengths safely

Don't call `tokenizer(text)` positionally on the Colab path -- the VLM
processor treats the first positional argument as images and crashes with
`ValueError: Incorrect image source. Got <|im_start|>system ...`. Always
use the inner text tokeniser for length diagnostics:

```python
_text_tok = getattr(tokenizer, "tokenizer", tokenizer)
lens = [len(_text_tok(r["text"])["input_ids"]) for r in train_ds]
print(f"max={max(lens)}  > 12288: {sum(1 for l in lens if l > 12288)}")
```

### Gemma-4-specific pitfalls

- **`TemplateError: Conversation roles must alternate user/assistant/user/
  assistant/...`** Gemma 4's stock Jinja chat template (shipped with
  `transformers==5.5.0`) does **not** support the OpenAI-style `system` /
  `tool` roles -- the tool-calling patch HF #45257 is not in that release.
  Step 6 of the notebook already works around this by flattening our
  multi-turn ChatML into strict `user/assistant/user/assistant` alternation
  via `_flatten_to_strict_alternation`:
    - `system` content is prepended to the next `user` turn.
    - `assistant.tool_calls` become inline `<tool_call>{...}</tool_call>`
      blocks in the assistant `content`. The model learns to emit these
      verbatim; Ollama's Gemma renderer re-wraps them as native tool calls
      at inference time.
    - `role=tool` outputs become `user` turns wrapped in
      `<tool_response>...</tool_response>`.
  If you still hit this error, you are calling
  `tokenizer.apply_chat_template(convo, ...)` on the raw messages somewhere
  (e.g. a custom eval cell). Route the input through
  `_flatten_to_strict_alternation(convo)` first.
- **`KeyError: 'gemma4'` during model load.** Install cell didn't pick up
  `transformers==5.5.0`. Re-run the install cell; if that doesn't fix it,
  `Runtime -> Restart`, then `Run all`.
- **`ImportError: cannot import name 'gemma4' from 'timm'`.** Same root cause
  as above -- `timm` didn't upgrade. Re-run `!pip install --no-deps --upgrade
  timm` then retry the model-load cell.
- **Response mask finds zero matches on Gemma data.** Make sure
  `train_on_responses_only` uses `<start_of_turn>user\n` /
  `<start_of_turn>model\n`, not the Qwen ChatML delimiters. Gemma uses
  `model` (not `assistant`) as the assistant-role name in its template.
- **`ollama run` emits raw `<start_of_turn>model` tokens in output.** Your
  Ollama build is older than the one that auto-detects Gemma 4's chat
  template from GGUF metadata (shipped with Ollama >= 0.12). Either upgrade
  Ollama or paste an explicit `TEMPLATE """..."""` block into the Modelfile
  (see `ollama show --modelfile gemma3` for a starting point and swap
  `assistant` -> `model`).
- **OOM on T4 with Gemma 4 E4B.** Expected -- E4B is 8B params (~16 GB bf16,
  > T4's 14.5 GB). The notebook's `_MODEL_REGISTRY` auto-enables `load_in_4bit
  = True` for E4B so weights fit; if you forced it off, either flip it back
  or pick `MODEL_SIZE = "E2B"`.
