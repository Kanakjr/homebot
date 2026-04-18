"""Generate unsloth_gemma4_homebot.ipynb from the Qwen 3.5 Colab notebook.

We clone the Qwen notebook cell-for-cell and then swap model-specific pieces:
model names, chat-template id, SFT response-masking delimiters, install pins,
the Ollama Modelfile template, and the intro/troubleshooting prose.

Run from the repo root:
    python Apps/homebot/finetuning/scripts/build_gemma4_notebook.py
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

FINETUNE = Path(__file__).resolve().parents[1]
SRC = FINETUNE / "unsloth_qwen3_5_4b_homebot.ipynb"
DST = FINETUNE / "unsloth_gemma4_homebot.ipynb"


def src_lines(text: str) -> list[str]:
    """Split a multi-line string into a Jupyter-notebook ``source`` list.

    Each entry keeps its trailing newline except the final one.
    """
    lines = text.split("\n")
    return [line + "\n" for line in lines[:-1]] + [lines[-1]]


CELL_0_TITLE = """\
# HomeBot Gemma 4 Fine-tune (Unsloth, E2B / E4B, bf16 LoRA)

End-to-end notebook that takes the merged HomeBot multi-turn ChatML dataset,
fine-tunes **Gemma 4 E2B or E4B** with **bf16 LoRA** via Unsloth on a free
Colab T4, and exports a Q4_K_M GGUF that slots directly into the existing
Ollama-based DeepAgent runtime. It mirrors the `unsloth_qwen3_5_4b_homebot`
notebook so you can A/B the two architectures on the same dataset.

**Model size is a single knob** (`MODEL_SIZE` in step 0). Recommended flow:

1. First run: `MODEL_SIZE = "E2B"` (~12 min / 2 epochs on T4). Full bf16 LoRA,
   fits on T4 with ~4 GB free. Sanity-checks pipeline, chat template, prompts.
2. Final run: `MODEL_SIZE = "E4B"` on an **L4/A100/RTX 4090+** for bf16, OR on
   T4 with auto-QLoRA (4-bit base, bf16 adapters -- slight accuracy hit).

Everything else (LoRA attach, chat template, SFT loop, train-on-responses,
GGUF export, Modelfile emit) is identical across sizes.

**Why Gemma 4 vs Qwen 3.5?**

- Gemma 4 has native OpenAI-format tool calling built into the tokenizer,
  so the `tool_calls` / `tool_response` round-trip tokenises cleanly without
  the `<tool_call>` wrapper that Qwen ChatML needs.
- 128K native context (we only use ~12K), matters if you ever extend the
  training examples to include full multi-turn chat history.
- Multilingual (140 languages). For Indian-English + Hindi code-mixing on
  Telegram this is often a noticeable upgrade over Qwen.
- Same LoRA recipe -- drop-in replacement. Reuses the
  `kanakjr/homebot-qwen3.5` dataset unchanged because the ChatML conversations
  are model-agnostic until `apply_chat_template` runs in step 5.

**Training loop shape** (same as the Qwen notebook):

```
system -> user -> assistant+tool_calls -> tool -> ... -> assistant (final text)
```

We use `train_on_responses_only` with Gemma's `<start_of_turn>` delimiters so
loss only applies to `model` + tool-call spans; the model is NOT rewarded for
regurgitating the (long) HomeBot system prompt.

**Inputs required.**
1. A T4 (or better) Colab GPU runtime.
2. An HF **write** token pasted into step 0 below.
3. `MODEL_SIZE` set to `"E2B"` or `"E4B"` (step 0).

That's it -- `Runtime -> Run all` then go grab a coffee.
"""


CELL_1_CONFIG_HEADER = """\
## 0. Configuration -- set your HF token + pick a model size

Paste your Hugging Face **write** token in the cell below, then flip
`MODEL_SIZE` to `"E2B"` or `"E4B"`. Everything else (dataset pull, GGUF
export repo name) is derived automatically.

| `MODEL_SIZE` | bf16 VRAM (load) | On T4 (16 GB) | ~2-epoch wall-clock |
| --- | --- | --- | --- |
| `"E2B"` | ~10 GB | bf16 LoRA fits comfortably | ~12 min |
| `"E4B"` | ~16 GB | **auto-QLoRA** (load_in_4bit) required | ~25 min (T4) / ~12 min (L4) |

Token + config lives in the cell below so you don't need Colab Secrets or an
`.env` file. Just remember to clear it before sharing the notebook.
"""


CELL_2_CONFIG_CODE = """\
import os

# --- REQUIRED: paste your HF write token here -----------------------------
HF_TOKEN = ""  # e.g. "hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
# --------------------------------------------------------------------------

# --- Model size toggle ----------------------------------------------------
# "E2B" -> ~10 GB bf16 VRAM, ~12 min / 2 epochs on T4. Recommended first run.
# "E4B" -> ~16 GB bf16 VRAM. On T4 the registry forces load_in_4bit=True
#          (QLoRA) so weights still fit; on L4/A100/4090+ flip it to False.
MODEL_SIZE = "E2B"   # "E2B" or "E4B"

_MODEL_REGISTRY = {
    "E2B": {
        "name":    "unsloth/gemma-4-E2B-it",
        "gguf":    "kanakjr/homebot-gemma4-e2b-gguf",
        "max_seq": 12288,
        # bf16 LoRA on T4: comfortable fit for E2B (~10 GB base + adapters).
        "load_in_4bit": False,
    },
    "E4B": {
        "name":    "unsloth/gemma-4-E4B-it",
        "gguf":    "kanakjr/homebot-gemma4-e4b-gguf",
        "max_seq": 12288,
        # E4B bf16 is 16 GB, which doesn't fit on T4's 14.5 GB. QLoRA keeps
        # the base in 4-bit NF4 and only trains bf16 adapters. Flip this to
        # False if you are on L4 / A100 / RTX 4090 / 6000 Ada / H100 / B200.
        "load_in_4bit": True,
    },
}
assert MODEL_SIZE in _MODEL_REGISTRY, f"MODEL_SIZE must be one of {list(_MODEL_REGISTRY)}"
_m = _MODEL_REGISTRY[MODEL_SIZE]
MODEL_NAME     = _m["name"]
MAX_SEQ_LENGTH = _m["max_seq"]
LOAD_IN_4BIT   = _m["load_in_4bit"]

# BUILD_TAG is threaded through every artifact path (LoRA dir, GGUF dir,
# Modelfile filename, Ollama model name) so E2B and E4B runs don't overwrite
# each other. e.g. "homebot-gemma4-e2b", "homebot-gemma4-e4b".
BUILD_TAG = f"homebot-gemma4-{MODEL_SIZE.lower()}"

# --- Dataset + (optional) model repo names --------------------------------
# Reuses the Qwen-trained dataset verbatim -- the conversations are plain
# role/content records, the model-specific chat template is only applied in
# step 5 via `apply_chat_template`.
HUB_DATASET_REPO = "kanakjr/homebot-qwen3.5"
HUB_MODEL_REPO   = _m["gguf"]

# --- Knobs you rarely touch -----------------------------------------------
REAL_OVERSAMPLE = 4       # step 5.5: how many times each real Telegram row is repeated
LORA_R = 16; LORA_ALPHA = 16  # bump both to 32 if under-fitting

# --- Propagate to env so downstream libs (datasets, huggingface_hub) see it
if HF_TOKEN:
    os.environ["HF_TOKEN"] = HF_TOKEN
    os.environ["HUGGING_FACE_HUB_TOKEN"] = HF_TOKEN

# Best-effort Colab Secrets fallback (only used if you left HF_TOKEN blank).
if not HF_TOKEN:
    try:
        from google.colab import userdata
        _secret = userdata.get("HF_TOKEN") or ""
        if _secret:
            HF_TOKEN = _secret
            os.environ["HF_TOKEN"] = _secret
            os.environ["HUGGING_FACE_HUB_TOKEN"] = _secret
            print("[config] using HF_TOKEN from Colab Secrets")
    except Exception:
        pass

assert HF_TOKEN, (
    "HF_TOKEN is empty -- paste your token in the cell above, or add it as a "
    "Colab Secret named HF_TOKEN."
)
print(f"[config] HF_TOKEN set (len={len(HF_TOKEN)})")
print(f"[config] MODEL_SIZE    = {MODEL_SIZE}")
print(f"[config] base model    = {MODEL_NAME}")
print(f"[config] load_in_4bit  = {LOAD_IN_4BIT}")
print(f"[config] max seq len   = {MAX_SEQ_LENGTH}")
print(f"[config] build tag     = {BUILD_TAG}")
print(f"[config] dataset repo  = {HUB_DATASET_REPO}")
print(f"[config] gguf    repo  = {HUB_MODEL_REPO}")
"""


CELL_4_INSTALL_CODE = """\
%%capture
import os, importlib.util
!pip install --upgrade -qqq uv

# Colab ships torchcodec pre-built against its bundled torch; Gemma 4 pulls
# in timm which depends on torchcodec transitively, and the bundled .so
# fails to load against the unsloth-pinned torch with
# "undefined symbol: _ZN3c104cuda...". Uninstall first, then let the timm
# install pull a matching version below.
!pip uninstall -y -qqq torchcodec torchao || true

if importlib.util.find_spec("torch") is None or "COLAB_" in "".join(os.environ.keys()):
    try:
        import numpy, PIL
        _numpy = f"numpy=={numpy.__version__}"
        _pil = f"pillow=={PIL.__version__}"
    except Exception:
        _numpy = "numpy"; _pil = "pillow"
    !uv pip install -qqq \\
        "torch==2.8.0" "triton>=3.3.0" {_numpy} {_pil} torchvision bitsandbytes xformers==0.0.32.post2 \\
        "unsloth_zoo[base] @ git+https://github.com/unslothai/unsloth-zoo" \\
        "unsloth[base] @ git+https://github.com/unslothai/unsloth"
elif importlib.util.find_spec("unsloth") is None:
    !uv pip install -qqq unsloth

# Core deps locked to what Gemma 4 ships against in Unsloth's reference
# notebook (2026.4.x). Transformers 5.5.0 is required for Gemma 4 patching;
# timm is required for Gemma 4's vision/audio towers even though we only
# train the text path.
!uv pip install -qqq "datasets==4.3.0" "huggingface_hub>=0.34.0" hf_transfer sentencepiece protobuf
!uv pip install --upgrade --no-deps tokenizers trl==0.22.2 unsloth unsloth_zoo
!uv pip install --no-deps transformers==5.5.0
!uv pip install --no-deps --upgrade timm
!uv pip install --no-build-isolation flash-linear-attention causal_conv1d==1.6.0

# Defensive: re-uninstall any torchcodec that crept back in as a transitive
# dep. Safe to skip if not present.
!pip uninstall -y -qqq torchcodec || true
"""


CELL_7_MODEL_HEADER = """\
## 3. Load Gemma 4 ({MODEL_SIZE}) in bf16 LoRA mode

Gemma 4 is a unified VLM (text + image + audio). Our training data is text-only
so we load via `FastVisionModel` (the T4-safe path for VLMs), freeze the
vision + audio towers in step 4, and only attach LoRA on language layers.
`max_seq_length` **must** be passed here -- otherwise Unsloth silently caps
the sequence at 2048-4096 and most of our 12k-token rows get truncated past
the assistant turn, which `train_on_responses_only` then drops as all-labels
= -100.
"""


CELL_8_MODEL_CODE = """\
from unsloth import FastVisionModel
import torch

# Canonical loader from Unsloth's official Gemma 4 Colab notebook
# (https://colab.research.google.com/github/unslothai/notebooks/blob/main/nb/Gemma4_(E4B)-Vision.ipynb).
# Unsloth auto-detects T4 (no bf16) vs. Ampere+ (bf16) and picks the right
# 16-bit dtype for weights, LoRA adapters, and autocast. DO NOT pass `dtype=`
# manually -- the model registry drives the 4-bit / 16-bit choice via
# LOAD_IN_4BIT instead.
#
# IMPORTANT: we MUST pass `max_seq_length` here, not just on SFTConfig.
# Unsloth defaults this to 2048-4096 at load time and that cap silently
# clips downstream tokenisation even when SFTConfig.max_length is larger,
# causing `train_on_responses_only` to see truncated rows with no
# assistant response and drop them as all-labels=-100.
model, tokenizer = FastVisionModel.from_pretrained(
    MODEL_NAME,
    max_seq_length = MAX_SEQ_LENGTH,
    load_in_4bit   = LOAD_IN_4BIT,
    use_gradient_checkpointing = "unsloth",
)
"""


CELL_11_CHAT_HEADER = """\
## 5. Apply the gemma-4 chat template

The `gemma-4` template wraps turns as `<start_of_turn>role\\ncontent<end_of_turn>`. Note Gemma uses `model` (not `assistant`) as the assistant role, and the current Unsloth template supports `system` and `tool` roles via the OpenAI-style tool-calling patch (HF PR #45257). Our training JSONL already has `role=system/user/assistant/tool` with OpenAI-style `tool_calls`, so `apply_chat_template` handles everything -- the `assistant` -> `model` rename happens inside the template.
"""


CELL_12_CHAT_CODE = """\
from unsloth.chat_templates import get_chat_template

tokenizer = get_chat_template(
    tokenizer,
    chat_template = "gemma-4",
)
"""


CELL_19_RESP_HEADER = """\
## 8. `train_on_responses_only` -- loss ONLY on `model` + tool_calls

Without this, the model learns to regurgitate the long system prompt, which is wasted capacity. Gemma 4 ChatML delimiters are:

- `<start_of_turn>user\\n` ... `<end_of_turn>`
- `<start_of_turn>model\\n` ... `<end_of_turn>`
"""


CELL_20_RESP_CODE = """\
from unsloth.chat_templates import train_on_responses_only

# `train_on_responses_only` tokenises `instruction_part` and
# `response_part` to locate loss-masking boundaries. Pass the inner text
# tokenizer so it matches whatever SFTTrainer used to tokenise the rows
# (we also set `tokenizer=_text_tok` on the trainer above). Also keeps us
# clear of the processor's image-as-positional-arg quirk.
# No-op on FastLanguageModel (plain tokenizer has no `.tokenizer`).
_text_tok = getattr(tokenizer, "tokenizer", tokenizer)

trainer = train_on_responses_only(
    trainer,
    tokenizer        = _text_tok,
    instruction_part = "<start_of_turn>user\\n",
    response_part    = "<start_of_turn>model\\n",
)
"""


_TQ = '"' * 3  # sentinel for triple-double-quote inside the cell source
_TSQ = "'" * 3  # sentinel for triple-single-quote inside the cell source

CELL_36_MODELFILE_CODE = (
    "# Gemma 4 Ollama Modelfile. We rely on Ollama's built-in chat-template\n"
    "# auto-detection from the GGUF metadata (the tokenizer's chat template is\n"
    "# serialised inside the GGUF), so we don't ship a TEMPLATE block -- Gemma\n"
    "# 4's template is complex (tool-calling PR #45257) and manually re-rendering\n"
    "# it is a footgun. If your Ollama version ever ships without auto-detect,\n"
    "# paste the template from `ollama show --modelfile gemma3` as a starting\n"
    "# point and swap `assistant` -> `model`.\n"
    "# The SYSTEM block is only a FALLBACK -- at runtime the DeepAgent injects\n"
    "# the canonical get_system_prompt() which supersedes this.\n"
    f"MODELFILE_TEMPLATE = f{_TSQ}FROM ./{{BUILD_TAG}}.Q4_K_M.gguf{_TSQ} + r{_TSQ}\n"
    "\n"
    "# Gemma 4 sampling defaults (matches Google's model card).\n"
    "PARAMETER temperature 0.6\n"
    "PARAMETER top_p 0.9\n"
    "PARAMETER top_k 40\n"
    "PARAMETER repeat_penalty 1.05\n"
    "PARAMETER num_ctx 8192\n"
    'PARAMETER stop "<end_of_turn>"\n'
    'PARAMETER stop "<start_of_turn>"\n'
    'PARAMETER stop "<eos>"\n'
    "\n"
    f"SYSTEM {_TQ}You are HomeBotAI, an intelligent smart-home assistant powered by Home Assistant.\n"
    "The home is in India (IST timezone). Resident: Kanak.\n"
    "\n"
    "You have access to tools for:\n"
    "- Home Assistant device control (ha_call_service, ha_get_states, ha_search_entities)\n"
    "- Media management (sonarr_*, radarr_*, jellyfin_*, jellyseerr_*, prowlarr_*, transmission_*)\n"
    "- Network admin (deco_list_clients, deco_list_mesh_nodes, deco_reboot_nodes, deco_reservation_help)\n"
    "- Obsidian vault + persistent memory (obsidian_*, memory_*)\n"
    "- Link processing (process_and_save_link)\n"
    "- Interactive choices (offer_choices -- tap-able buttons; end your turn after calling it)\n"
    "- Shell execution (execute)\n"
    "\n"
    "Rules:\n"
    "1. Be efficient with tool calls -- 1-3 targeted calls over exhaustive searching.\n"
    "2. Always provide a short natural-language summary after tool calls.\n"
    '3. Use colloquial names in replies (e.g. "the purifier"), never raw entity_ids.\n'
    '4. For short ordinal replies like "3" or "the second one", resolve against your\n'
    "   previous message.\n"
    "5. Confirm actions in one line and stop -- no filler tails, no second-guessing.\n"
    "6. Synthesize redundant sensor readings (within ~1C / 5%RH) into one value instead\n"
    "   of dumping raw lists.\n"
    f"{_TQ}\n"
    f"{_TSQ}\n"
    "\n"
    'MODELFILE_PATH = f"{BUILD_TAG}.Modelfile"\n'
    'with open(MODELFILE_PATH, "w") as f:\n'
    "    f.write(MODELFILE_TEMPLATE)\n"
    'print(f"Wrote {MODELFILE_PATH} ({len(MODELFILE_TEMPLATE)} bytes)")\n'
    "\n"
    '_gguf_name = f"{BUILD_TAG}.Q4_K_M.gguf"\n'
    '_gguf_size = "~2.8 GB" if MODEL_SIZE == "E2B" else "~4.6 GB"\n'
    'print("\\n=== Next steps (run on your Mac, NOT in Colab) ===")\n'
    'print("1. Download both artifacts from the Colab file browser:")\n'
    'print(f"      {_gguf_name}  ({_gguf_size})")\n'
    'print(f"      {MODELFILE_PATH}")\n'
    'print("2. Put them in the same directory on the Mac.")\n'
    'print(f"3. ollama create {BUILD_TAG} -f {MODELFILE_PATH}")\n'
    'print("4. Quick sanity test:")\n'
    "print(f\"      ollama run {BUILD_TAG} 'turn off the air purifier'\")\n"
    'print("5. Point DeepAgent at the new model:")\n'
    'print(f"      MODEL=ollama:{BUILD_TAG}")\n'
    'print("   Then restart the DeepAgent server.")\n'
)


CELL_37_TROUBLESHOOTING = """\
---

**Troubleshooting**

- *`from unsloth import FastVisionModel` fails with `OSError: libavutil.so.*` or `undefined symbol: _ZN3c104cuda29c10_cuda_check_implementationEiPKcS2_jb`*: Colab's pre-installed `torchcodec` is built against a different PyTorch build than the one the install cell pins. Fix in-place with `!pip uninstall -y torchcodec`, then re-run the import cell. **Runtime restart NOT required.**
- *`RuntimeError: expected mat1 and mat2 to have the same dtype, but got: c10::BFloat16 != c10::Half`*: you loaded Gemma 4 with `FastLanguageModel` instead of `FastVisionModel`. Gemma 4 is a unified VLM; only the vision loader wires up dtypes correctly on T4 (you will see `Bfloat16 = FALSE -> Switching to 16bit LoRA` in the banner). Re-run step 3 + step 4 after confirming they use `FastVisionModel`.
- *OOM on T4 with `MODEL_SIZE = "E4B"`*: this is expected in bf16 (16 GB weights > 14.5 GB T4 VRAM). The registry in step 0 already forces `LOAD_IN_4BIT = True` for E4B; if you edited that, either flip it back or downgrade to `MODEL_SIZE = "E2B"`.
- *`transformers` version mismatch / `KeyError: 'gemma4'` inside `modeling_auto`*: the install cell pins `transformers==5.5.0`; restart the runtime if you installed an earlier version in this session.
- *`ImportError: cannot import name 'gemma4' from 'timm'`*: step 1's `pip install --no-deps --upgrade timm` didn't stick. Re-run it explicitly: `!pip install --no-deps --upgrade timm`, then re-run step 3.
- *`TemplateError: Conversation roles must alternate user/assistant/user/assistant/...`*: Gemma 4's stock Jinja chat template rejects `system` and `tool` roles (the OpenAI-tool-calling patch HF #45257 is not in `transformers==5.5.0`). Step 6 already works around this by flattening our multi-turn ChatML into strict user/assistant alternation via `_flatten_to_strict_alternation`. If you see this error, you are probably calling `tokenizer.apply_chat_template(convo, ...)` directly on the raw `messages`; route it through `_flatten_to_strict_alternation(convo)` first.
- *`Unsloth: Removed N out of M samples from train_dataset where all labels were -100`*: see the **Troubleshooting** section of `finetuning/README.md` (same root causes as the Qwen 3.5 notebook -- the primary one is forgetting `max_seq_length` on `FastVisionModel.from_pretrained`).
- *Low eval loss but bad tool calls*: inspect the rendered example in step 6 -- make sure tool messages show up as `<start_of_turn>tool ...`. If they collapse into the user turn, re-run step 5 and confirm the chat template resolved to `"gemma-4"` rather than silently falling back to the base tokenizer template.
- *Model only replies in natural language and never calls a tool*: you probably skipped step 8 (`train_on_responses_only`). Without it the model learns to reproduce the system prompt, crowding out tool-call patterns.
- *Tool calls fire but summary is verbose/robotic*: model is over-fitting the simulator style. Increase `REAL_OVERSAMPLE` in step 5.5 (try 6 or 8), or re-run `./run_pipeline.sh real --days 365 --limit 5000` locally to pull more genuine chats and re-merge.
- *GGUF export fails with "unsupported architecture"*: Unsloth's `save_pretrained_gguf` needs the merged 16-bit model. Re-run step 14; if it still fails, bypass via `model.save_pretrained_merged(...)` and quantize manually with `llama.cpp/convert-hf-to-gguf.py`.

**Iteration recipe**

1. Download the GGUF + Modelfile, `ollama create`, try 5-10 real Telegram-style messages.
2. If tool arguments are wrong (wrong entity_id, missing field), that usually means the dataset is too small for that skill. Run `./run_pipeline.sh generate` to add more synthetic queries for that skill family, then `simulate` a handful and re-merge.
3. If the reply text style is off but tool calls are right, oversample real data more aggressively (step 5.5) rather than adding more synthetic rows.
"""


CELL_5_DATA_HEADER = """\
## 2. Load the HomeBot dataset (fail-fast)

We pull the dataset **before** downloading Gemma 4 weights (~10 GB on E2B,
~16 GB on E4B) so any auth / repo / schema problem blows up in seconds
instead of after a full model download.

Default: HF Hub repo set in step 0 (`HUB_DATASET_REPO` -- reuses the
`kanakjr/homebot-qwen3.5` dataset unchanged because ChatML conversations are
model-agnostic). Flip `USE_HUB = False` in the cell below to upload
`qwen3_5_training.jsonl` + `qwen3_5_val.jsonl` from your laptop instead.
"""

CELL_9_LORA_HEADER = """\
## 4. Attach LoRA adapters (text-only)

`r=16, lora_alpha=16` is a solid Gemma 4 starting point. If you see under-fitting after 2 epochs, bump both to 32.

We use `FastVisionModel.get_peft_model(...)` with `finetune_vision_layers=False` -- the HomeBot dataset is 100% text (Telegram + synthetic chat), so there is no signal for the vision or audio towers. Everything else (attention, MLP, language layers) gets LoRA'd.
"""

CELL_15_RENDER_HEADER = """\
## 6. Render each conversation through the chat template

Gemma 4's `apply_chat_template` enforces **strict user/assistant alternation**
and raises `TemplateError: Conversation roles must alternate user/assistant/...`
the moment it sees a `system` or `tool` role. (Transformers PR #45257 adds
OpenAI-shape tool calling to the Gemma template but is not in the
`transformers==5.5.0` pin we use for Gemma 4 patching.)

Our HomeBot dataset has:

```
system -> user -> assistant+tool_calls -> tool -> assistant (final)
```

So before calling `apply_chat_template` we **flatten** the conversation into
strict `user/assistant/user/assistant` alternation:

- `system` content is prepended to the next `user` turn as plain text.
- `assistant.tool_calls` are serialised inline as
  `<tool_call>{...}</tool_call>` inside the assistant `content`. The model
  learns to emit these verbatim; Ollama's Gemma renderer re-wraps them as
  native tool calls at inference time.
- `role=tool` outputs become `user` turns wrapped in
  `<tool_response>...</tool_response>`. This preserves the alternation
  (previous assistant -> new user) and matches what Ollama's Gemma template
  produces when a tool result is injected at inference time.
- Accidental consecutive same-role turns are merged with `\\n\\n`.

This keeps the GGUF export compatible with Ollama's built-in Gemma template
while letting us train with the `transformers==5.5.0` Jinja template that
ships with Gemma 4's checkpoint.
"""

CELL_16_RENDER_CODE = """\
import json


def _flatten_to_strict_alternation(messages):
    \"\"\"Rewrite HomeBot ChatML into strict user/assistant alternation so
    Gemma 4's chat template accepts it. Gemma-specific; the Qwen notebook
    keeps the native system/tool roles because `qwen3-instruct` understands
    them.
    \"\"\"
    out = []
    pending_system = None

    def _serialize_tool_call(tc):
        fn = tc.get("function", {})
        name = fn.get("name", "")
        args = fn.get("arguments", "")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                pass
        return json.dumps({"name": name, "arguments": args}, ensure_ascii=False)

    for m in messages:
        role = m.get("role")
        content = m.get("content") or ""

        if role == "system":
            pending_system = content
            continue

        if role == "user":
            if pending_system:
                content = f"{pending_system}\\n\\n{content}"
                pending_system = None
            out.append({"role": "user", "content": content})
            continue

        if role == "assistant":
            parts = []
            if content:
                parts.append(content)
            for tc in m.get("tool_calls") or []:
                parts.append(f"<tool_call>\\n{_serialize_tool_call(tc)}\\n</tool_call>")
            out.append({"role": "assistant", "content": "\\n".join(parts)})
            continue

        if role == "tool":
            out.append({
                "role": "user",
                "content": f"<tool_response>\\n{content}\\n</tool_response>",
            })
            continue
        # Unknown role -- skip defensively rather than crash the whole run.

    # Merge accidental consecutive same-role turns (e.g. two `user` in a row
    # when a nudge follows a tool_response) so the template stays happy.
    collapsed = []
    for m in out:
        if collapsed and collapsed[-1]["role"] == m["role"]:
            collapsed[-1]["content"] = collapsed[-1]["content"] + "\\n\\n" + m["content"]
        else:
            collapsed.append(m)

    # Gemma also rejects a leading assistant turn; drop it if it ever slips
    # through (shouldn't happen with our dataset but defensive).
    while collapsed and collapsed[0]["role"] == "assistant":
        collapsed.pop(0)

    return collapsed


def formatting_prompts_func(examples):
    convos = examples["messages"]
    texts = [
        tokenizer.apply_chat_template(
            _flatten_to_strict_alternation(convo),
            tokenize=False,
            add_generation_prompt=False,
        )
        for convo in convos
    ]
    return {"text": texts}

# CRITICAL: drop every non-text column with `remove_columns=...`. If we leave
# `messages` in, SFTTrainer's default collator tries to tensorize the nested
# list-of-dicts and crashes with "Could not infer dtype of dict".
keep_only_text = lambda ds: ds.map(
    formatting_prompts_func,
    batched=True,
    remove_columns=ds.column_names,
)

train_ds = keep_only_text(ds_train)
val_ds = ds_val
if val_ds is not None and len(val_ds) > 0:
    val_ds = keep_only_text(val_ds)

print(f"train_ds size={len(train_ds)}  val_ds size={0 if val_ds is None else len(val_ds)}")
print(f"train_ds columns after render: {train_ds.column_names}  (should be ['text'])")
print("\\n--- Rendered example (truncated) ---\\n")
print(train_ds[0]["text"][:2000])
"""


CELL_17_SFT_HEADER = """\
## 7. Configure SFTTrainer

Small batch + high grad-accum fits Gemma 4 E2B bf16 LoRA on a 16 GB T4 with
headroom to spare (~10 GB base + ~0.5 GB adapters + ~2 GB activations for a
12k-token sequence). For E4B with `LOAD_IN_4BIT=True` the base drops to ~6 GB
so you can raise `per_device_train_batch_size` to 2 if you want. `max_length
= MAX_SEQ_LENGTH` covers the HomeBot system prompt + full multi-turn
conversation with some headroom.
"""

CELL_28_SANITY_CODE = """\
from transformers import TextStreamer

FastVisionModel.for_inference(model)

# Each row tests a different skill family the dataset actually covered.
# "Healthy" output means a `<tool_call>{...}</tool_call>` block with the
# expected entity_id, followed by a short natural-language summary.
SANITY_PROMPTS = [
    # Home Assistant device control
    "turn off the air purifier",
    "dim the bedroom light to 40%",
    # Sensor query + synthesis rule
    "what's the temperature in the bedroom?",
    # Media pipeline
    "add the movie Dune Part Two",
    "search jellyseerr for succession",
    # Persistent memory
    "remember that my standing desk is switch.monitor_plug",
    "what did I say about deep work hours?",
    # Network admin
    "which devices are online right now?",
    # Obsidian / notes
    "summarize my notes from yesterday",
    # Interactive UI
    "what are my 3 favourite lights?",
]

# Matches the Modelfile fallback system prompt so behaviour at sanity-check
# time is close to what DeepAgent sends at runtime. At serve time the
# DeepAgent injects the canonical get_system_prompt() which supersedes this.
SYSTEM_PROMPT = (
    "You are HomeBotAI, an intelligent smart-home assistant powered by Home "
    "Assistant. The home is in India (IST timezone). Resident: Kanak.\\n\\n"
    "You have access to tools for Home Assistant control, media management "
    "(Sonarr/Radarr/Jellyfin/Jellyseerr), network admin (Deco mesh), "
    "Obsidian vault + persistent memory, link processing, interactive "
    "choices, and shell execution.\\n\\n"
    "Rules: be efficient with tool calls (1-3), summarize results in one "
    "short line, use colloquial names (never raw entity_ids), and stop "
    "after confirming an action."
)

for prompt in SANITY_PROMPTS:
    print("\\n" + "=" * 60)
    print(f"USER: {prompt}")
    print("=" * 60)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": prompt},
    ]
    # Route through the same flattener we use at training time -- Gemma's
    # chat template rejects the `system` role, so we fold it into the user
    # turn to match what the model actually saw in step 6.
    text = tokenizer.apply_chat_template(
        _flatten_to_strict_alternation(messages),
        tokenize = False,
        add_generation_prompt = True,
    )
    # NB: loading Gemma 4 via FastVisionModel (the T4 dtype workaround)
    # makes `tokenizer` a Gemma-4 VLM *processor*. Calling a processor
    # positionally binds the first arg to `images`, which triggers
    # `load_image()` -> tries to base64-decode our chat template string
    # and raises `Incorrect image source` / `Incorrect padding`.
    # Fall through to the inner text tokenizer so plain text tokenises
    # cleanly; this is a no-op on FastLanguageModel (no .tokenizer attr).
    _text_tok = getattr(tokenizer, "tokenizer", tokenizer)
    inputs = _text_tok(text, return_tensors="pt").to("cuda")
    _ = model.generate(
        **inputs,
        max_new_tokens = 512,
        # Gemma 4 sampling defaults (matches Google's model card).
        temperature = 0.6, top_p = 0.9, top_k = 40,
        streamer = TextStreamer(tokenizer, skip_prompt=True),
    )
"""


CELL_35_MODELFILE_HEADER = """\
## 16. Emit a ready-to-paste Ollama Modelfile

Writes `{BUILD_TAG}.Modelfile` next to the GGUF (e.g. `homebot-gemma4-e2b.Modelfile`). Download both, then on your Mac run `ollama create {BUILD_TAG} -f {BUILD_TAG}.Modelfile`. The DeepAgent's `_resolve_model` accepts `ollama:<name>`, so point it at `ollama:homebot-gemma4-e2b` or `ollama:homebot-gemma4-e4b` depending on which build you shipped.
"""


REPLACEMENTS: dict[int, str] = {
    0: CELL_0_TITLE,
    1: CELL_1_CONFIG_HEADER,
    2: CELL_2_CONFIG_CODE,
    4: CELL_4_INSTALL_CODE,
    5: CELL_5_DATA_HEADER,
    7: CELL_7_MODEL_HEADER,
    8: CELL_8_MODEL_CODE,
    9: CELL_9_LORA_HEADER,
    11: CELL_11_CHAT_HEADER,
    12: CELL_12_CHAT_CODE,
    15: CELL_15_RENDER_HEADER,
    16: CELL_16_RENDER_CODE,
    17: CELL_17_SFT_HEADER,
    28: CELL_28_SANITY_CODE,
    19: CELL_19_RESP_HEADER,
    20: CELL_20_RESP_CODE,
    35: CELL_35_MODELFILE_HEADER,
    36: CELL_36_MODELFILE_CODE,
    37: CELL_37_TROUBLESHOOTING,
}


def main() -> None:
    with SRC.open() as f:
        nb = json.load(f)

    for idx, new_source in REPLACEMENTS.items():
        nb["cells"][idx]["source"] = src_lines(new_source)

    # Scrub top-level notebook metadata that pinned the Qwen Colab runtime.
    nb_meta = nb.get("metadata", {})
    if "widgets" in nb_meta:
        nb_meta["widgets"] = {}
    if "colab" in nb_meta:
        nb_meta["colab"] = {"provenance": [], "collapsed_sections": []}

    # Strip Qwen-run execution state from every code cell so the Gemma
    # notebook ships clean (no cached outputs, no dangling Colab widget
    # refs, no per-cell outputId that would try to replay widget state).
    for cell in nb["cells"]:
        if cell["cell_type"] != "code":
            continue
        cell["outputs"] = []
        cell["execution_count"] = None
        meta = cell.setdefault("metadata", {})
        meta.pop("outputId", None)
        meta.pop("executionInfo", None)
        if "colab" in meta:
            # Keep the colab block but strip its inner widget/height state.
            meta["colab"] = {}

    with DST.open("w") as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)
        f.write("\n")

    print(f"wrote {DST.relative_to(FINETUNE.parent.parent)} ({DST.stat().st_size:,} bytes)")
    print(f"cells: {len(nb['cells'])}")


if __name__ == "__main__":
    main()
