"""Generate finalize_gguf_colab.ipynb from inline cell sources.

This Colab notebook is the fast-path alternative to
`scripts/finalize_gguf_mac.sh` when you'd rather let Google's network do the
heavy HF download + llama.cpp build + multi-quant export, then push every
quantization level back to HF Hub for trivial Mac-side `hf download`.

Keep the Modelfile TEMPLATE / SYSTEM content in sync with:
  - finetuning/unsloth_qwen3_5_4b_homebot.ipynb cell 36
  - finetuning/scripts/finalize_gguf_mac.sh
  - finetuning/homebot_qwen3_5.Modelfile

Run:
  cd Apps/homebot/finetuning
  python3 scripts/build_finalize_colab_notebook.py
"""
from __future__ import annotations

import json
import pathlib


OUT_PATH = pathlib.Path(__file__).resolve().parent.parent / "finalize_gguf_colab.ipynb"


CELLS: list[dict] = []


def md(text: str) -> None:
    CELLS.append(
        {
            "cell_type": "markdown",
            "metadata": {},
            "source": _as_lines(text),
        }
    )


def code(text: str) -> None:
    CELLS.append(
        {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": _as_lines(text),
        }
    )


def _as_lines(text: str) -> list[str]:
    # jupyter stores source as a list of lines, each terminated with "\n"
    # except possibly the last.
    text = text.rstrip("\n")
    lines = text.split("\n")
    return [ln + "\n" for ln in lines[:-1]] + [lines[-1]]


# ---------------------------------------------------------------------------
# 0. Title + intro
# ---------------------------------------------------------------------------
md(
    """\
# HomeBot GGUF Finalizer (Colab)

This notebook takes the merged fp16 safetensors pushed by the Unsloth
fine-tune notebook (`model.push_to_hub_merged(..., save_method="merged_16bit")`)
and produces Ollama-ready GGUFs at multiple quantization levels, then pushes
them back to a dedicated HF Hub repo for trivial Mac-side `hf download`.

## Why Colab instead of your Mac?

- Google's network downloads the 4-9 GB merged repo in ~30 s vs. several minutes on residential fibre.
- Colab's pre-provisioned Python 3.11 avoids PyTorch-wheel-availability issues on Mac Python 3.13 / 3.14.
- Apt has `sudo`, so llama.cpp compiles cleanly.
- We quantize to every level in one shot (Q4_K_M, Q5_K_M, Q6_K, Q8_0) so you can A/B levels locally later without rerunning.
- Everything ends up on HF Hub, so your Mac pulls only the GGUFs it wants.

## Prerequisites

You must have already run the Unsloth training notebook and pushed the merged fp16 weights:

```python
model.push_to_hub_merged(
    HUB_MODEL_REPO + "-merged16",
    tokenizer,
    save_method = "merged_16bit",
    token = HF_TOKEN,
)
```

...so that `kanakjr/homebot-qwen3.5-2b-gguf-merged16` (or the 4B equivalent) exists on HF Hub.

## Runtime

CPU runtime is fine -- we don't need a GPU for quantization. It's the cheapest runtime Colab offers.

## Output

- Local (Colab): `{BUILD_TAG}.fp16.gguf`, `{BUILD_TAG}.{QUANT}.gguf` for each quant, `{BUILD_TAG}.Modelfile`
- Remote (HF Hub): `kanakjr/homebot-qwen3.5-{size}-gguf` (or Gemma equivalent) with all GGUFs + the Modelfile attached."""
)


# ---------------------------------------------------------------------------
# 1. Config (markdown)
# ---------------------------------------------------------------------------
md(
    """\
## 0. Configuration

Set the model family and size. The notebook derives source/target HF Hub
repos, chat template, and Modelfile parameters from these two knobs.

For HomeBot today the primary path is **`MODEL_FAMILY = "qwen3.5"`** with
`MODEL_SIZE = "2B"` or `"4B"`. Gemma 4 is supported for parity.

`PRIMARY_QUANT` is the quant the Modelfile's `FROM` line will reference --
typically `Q8_0` for M-series Macs with >= 16 GB unified memory (~1-2%
quality gap vs. fp16, plenty of RAM headroom). Drop to `Q6_K` or `Q4_K_M`
if you're targeting smaller machines."""
)


# ---------------------------------------------------------------------------
# 2. Config (code)
# ---------------------------------------------------------------------------
code(
    '''\
import os
from getpass import getpass

# ---------- knobs ----------
MODEL_FAMILY = "qwen3.5"  # "qwen3.5" or "gemma4"
MODEL_SIZE   = "2B"       # Qwen: "2B" | "4B" ;  Gemma: "E2B" | "E4B"
QUANT_LEVELS = ["Q4_K_M", "Q5_K_M", "Q6_K", "Q8_0"]
PRIMARY_QUANT = "Q8_0"    # which quant the Modelfile FROM line references

HF_USER = "kanakjr"
# ---------------------------

try:
    from google.colab import userdata  # type: ignore
    HF_TOKEN = userdata.get("HF_TOKEN") or os.environ.get("HF_TOKEN")
except Exception:
    HF_TOKEN = os.environ.get("HF_TOKEN")

if not HF_TOKEN:
    HF_TOKEN = getpass("HF_TOKEN (needs write scope to push GGUFs): ")

os.environ["HF_TOKEN"] = HF_TOKEN  # so `hf` CLI picks it up automatically

# derive repo names + chat family
size_lc = MODEL_SIZE.lower()
if MODEL_FAMILY == "qwen3.5":
    BUILD_TAG    = f"homebot-qwen3_5-{size_lc}"
    SOURCE_REPO  = f"{HF_USER}/homebot-qwen3.5-{size_lc}-gguf-merged16"
    TARGET_REPO  = f"{HF_USER}/homebot-qwen3.5-{size_lc}-gguf"
    CHAT_FAMILY  = "qwen"
elif MODEL_FAMILY == "gemma4":
    BUILD_TAG    = f"homebot-gemma4-{size_lc}"
    SOURCE_REPO  = f"{HF_USER}/homebot-gemma4-{size_lc}-gguf-merged16"
    TARGET_REPO  = f"{HF_USER}/homebot-gemma4-{size_lc}-gguf"
    CHAT_FAMILY  = "gemma"
else:
    raise ValueError(f"Unknown MODEL_FAMILY: {MODEL_FAMILY!r}")

assert PRIMARY_QUANT in QUANT_LEVELS, (
    f"PRIMARY_QUANT={PRIMARY_QUANT!r} must be one of QUANT_LEVELS={QUANT_LEVELS!r}"
)

print(f"BUILD_TAG    = {BUILD_TAG}")
print(f"SOURCE_REPO  = {SOURCE_REPO}")
print(f"TARGET_REPO  = {TARGET_REPO}")
print(f"CHAT_FAMILY  = {CHAT_FAMILY}")
print(f"QUANT_LEVELS = {QUANT_LEVELS}")
print(f"PRIMARY_QUANT= {PRIMARY_QUANT}")
'''
)


# ---------------------------------------------------------------------------
# 3. Install deps (markdown)
# ---------------------------------------------------------------------------
md(
    """\
## 1. Install apt + pip dependencies

- `cmake`, `build-essential`, `libcurl4-openssl-dev`, `libssl-dev` -- for compiling llama.cpp.
- `gguf`, `transformers`, `safetensors`, `sentencepiece`, `protobuf` -- convert_hf_to_gguf.py's imports.
- `huggingface_hub[cli]` -- the `hf` CLI for download + upload. `huggingface_hub>=1.0` renamed `huggingface-cli` to `hf`; we use the new name throughout."""
)


# ---------------------------------------------------------------------------
# 4. Install deps (code)
# ---------------------------------------------------------------------------
code(
    """\
%%capture
!sudo apt-get update -qq
!sudo apt-get install -y -qq cmake build-essential libcurl4-openssl-dev libssl-dev

!pip install -q -U "huggingface_hub[cli]" gguf safetensors sentencepiece protobuf
# transformers is already pre-installed on Colab; bump only if convert_hf_to_gguf
# complains about a too-old version (rare).
"""
)


# ---------------------------------------------------------------------------
# 5. Build llama.cpp (markdown)
# ---------------------------------------------------------------------------
md(
    """\
## 2. Clone + build llama.cpp

We need two artifacts from the llama.cpp repo:

1. `convert_hf_to_gguf.py` -- pure-Python HF-safetensors -> GGUF converter.
2. `build/bin/llama-quantize` -- the CPU quantizer binary.

The build takes ~3-5 minutes on Colab's CPU runtime. Idempotent -- skipped on rerun."""
)


# ---------------------------------------------------------------------------
# 6. Build llama.cpp (code)
# ---------------------------------------------------------------------------
code(
    """\
import os, subprocess

LLAMA_CPP_DIR = "/content/llama.cpp"

if not os.path.exists(LLAMA_CPP_DIR):
    !git clone --depth 1 https://github.com/ggerganov/llama.cpp {LLAMA_CPP_DIR}
else:
    print(f"llama.cpp already cloned at {LLAMA_CPP_DIR}")

QUANTIZE_BIN = f"{LLAMA_CPP_DIR}/build/bin/llama-quantize"
if not os.path.exists(QUANTIZE_BIN):
    # GGML_NATIVE=OFF: don't tune for the specific host CPU so the binary runs
    # on any Colab instance if we ever shuffle runtimes.
    !cmake -S {LLAMA_CPP_DIR} -B {LLAMA_CPP_DIR}/build -DGGML_NATIVE=OFF -DLLAMA_CURL=OFF
    !cmake --build {LLAMA_CPP_DIR}/build --config Release -j$(nproc)
else:
    print(f"llama-quantize already built at {QUANTIZE_BIN}")

# sanity: both tools work
!{QUANTIZE_BIN} --help 2>&1 | head -3
!python {LLAMA_CPP_DIR}/convert_hf_to_gguf.py --help 2>&1 | head -3
"""
)


# ---------------------------------------------------------------------------
# 7. Download merged (markdown)
# ---------------------------------------------------------------------------
md(
    """\
## 3. Download merged fp16 safetensors from HF Hub

`hf download` is resumable and idempotent at the file level -- rerun this
cell and it'll only fetch files that are missing or incomplete.

For a 2B model the download is ~4.5 GB; for a 4B model ~8.5 GB. Colab
downloads at 100-300 MB/s from HF Hub, so expect ~30-60 seconds."""
)


# ---------------------------------------------------------------------------
# 8. Download merged (code)
# ---------------------------------------------------------------------------
code(
    '''\
import os, glob

MERGED_DIR = f"/content/{BUILD_TAG}-merged"
!hf download {SOURCE_REPO} --local-dir {MERGED_DIR}

shards = sorted(glob.glob(f"{MERGED_DIR}/*.safetensors"))
assert shards, (
    f"No *.safetensors files found in {MERGED_DIR}.\\n"
    f"Either {SOURCE_REPO} doesn't exist, or the token lacks read scope, or the "
    f"Unsloth notebook pushed only metadata. Re-run the push step."
)
total_bytes = sum(os.path.getsize(s) for s in shards)
print(f"\\nDownloaded {len(shards)} safetensor shard(s), {total_bytes/1e9:.2f} GB total")
for s in shards:
    print(f"  {os.path.basename(s)}  ({os.path.getsize(s)/1e9:.2f} GB)")
'''
)


# ---------------------------------------------------------------------------
# 9. Convert fp16 (markdown)
# ---------------------------------------------------------------------------
md(
    """\
## 4. Convert HF safetensors -> GGUF fp16

Pure-Python step using `convert_hf_to_gguf.py`. No quantization yet --
this is just the GGUF container around the fp16 weights (~same size as the
source safetensors)."""
)


# ---------------------------------------------------------------------------
# 10. Convert fp16 (code)
# ---------------------------------------------------------------------------
code(
    '''\
import os

FP16_GGUF = f"/content/{BUILD_TAG}.fp16.gguf"

# Re-run if the existing artifact is a <100MB stub from a previous aborted run.
if os.path.exists(FP16_GGUF) and os.path.getsize(FP16_GGUF) < 100 * 1024 * 1024:
    print(f"Stale {FP16_GGUF} ({os.path.getsize(FP16_GGUF)} bytes); removing and redoing.")
    os.remove(FP16_GGUF)

if not os.path.exists(FP16_GGUF):
    !python {LLAMA_CPP_DIR}/convert_hf_to_gguf.py {MERGED_DIR} --outfile {FP16_GGUF} --outtype f16
else:
    print(f"fp16 GGUF already present: {FP16_GGUF} ({os.path.getsize(FP16_GGUF)/1e9:.2f} GB)")

size_bytes = os.path.getsize(FP16_GGUF)
assert size_bytes > 500 * 1024 * 1024, (
    f"fp16 GGUF only {size_bytes} bytes -- conversion failed. "
    f"Check convert_hf_to_gguf.py output above for errors."
)
print(f"fp16 GGUF: {FP16_GGUF} ({size_bytes/1e9:.2f} GB)")
'''
)


# ---------------------------------------------------------------------------
# 11. Quantize all levels (markdown)
# ---------------------------------------------------------------------------
md(
    """\
## 5. Quantize to every level in QUANT_LEVELS

`llama-quantize` is CPU-bound but fast -- ~30-60 seconds per level for a 2B
model, ~1-2 minutes per level for a 4B model. We build the whole menu so the
Mac side can A/B between Q4_K_M / Q5_K_M / Q6_K / Q8_0 without re-running
this pipeline.

| Quant | 2B size | 4B size | Quality gap vs. fp16 |
|-------|---------|---------|----------------------|
| Q4_K_M | ~1.5 GB | ~2.5 GB | ~4-6% |
| Q5_K_M | ~1.8 GB | ~3.0 GB | ~2-3% |
| Q6_K   | ~2.2 GB | ~3.5 GB | ~1-2% |
| Q8_0   | ~2.8 GB | ~4.5 GB | < 1% |"""
)


# ---------------------------------------------------------------------------
# 12. Quantize all levels (code)
# ---------------------------------------------------------------------------
code(
    '''\
import os

QUANT_FILES: dict[str, str] = {}
for q in QUANT_LEVELS:
    out_path = f"/content/{BUILD_TAG}.{q}.gguf"
    if os.path.exists(out_path) and os.path.getsize(out_path) > 100 * 1024 * 1024:
        print(f"\\n=== {q}: already quantized ({os.path.getsize(out_path)/1e9:.2f} GB), skipping ===")
        QUANT_FILES[q] = out_path
        continue
    print(f"\\n=== Quantizing to {q} ===")
    !{QUANTIZE_BIN} {FP16_GGUF} {out_path} {q}
    assert os.path.exists(out_path), f"{q}: llama-quantize did not produce {out_path}"
    QUANT_FILES[q] = out_path
    print(f"  -> {os.path.basename(out_path)}  ({os.path.getsize(out_path)/1e9:.2f} GB)")

print("\\n=== All quants ===")
for q, p in QUANT_FILES.items():
    print(f"  {q}: {p} ({os.path.getsize(p)/1e9:.2f} GB)")
'''
)


# ---------------------------------------------------------------------------
# 13. Write Modelfile (markdown)
# ---------------------------------------------------------------------------
md(
    """\
## 6. Write the Ollama Modelfile

Keep this in sync with `finetuning/unsloth_qwen3_5_4b_homebot.ipynb` cell 36
and `finetuning/scripts/finalize_gguf_mac.sh`.

The `FROM` line references the `PRIMARY_QUANT` GGUF. At import time on your
Mac, `ollama create` reads the GGUF bytes into its own blob store, so the
relative path only has to resolve during the one-shot import.

For Qwen we use Ollama's built-in `qwen3.5` renderer + parser (available
since Ollama 0.11) so the model's `tools` capability flag is set and
langchain_ollama / OpenAI-style callers see `supports_tools: true`.
For Gemma we rely on Ollama's built-in auto-detection from the GGUF
metadata (the tokenizer's Jinja template is serialised inside the GGUF)."""
)


# ---------------------------------------------------------------------------
# 14. Write Modelfile (code)
# ---------------------------------------------------------------------------
code(
    r'''
MODELFILE_PATH = f"/content/{BUILD_TAG}.Modelfile"
PRIMARY_GGUF_NAME = f"{BUILD_TAG}.{PRIMARY_QUANT}.gguf"

SYSTEM_PROMPT = """You are HomeBotAI, an intelligent smart-home assistant powered by Home Assistant.
The home is in India (IST timezone). Resident: Kanak.

You have access to tools for:
- Home Assistant device control (ha_call_service, ha_get_states, ha_search_entities)
- Media management (sonarr_*, radarr_*, jellyfin_*, jellyseerr_*, prowlarr_*, transmission_*)
- Network admin (deco_list_clients, deco_list_mesh_nodes, deco_reboot_nodes, deco_reservation_help)
- Obsidian vault + persistent memory (obsidian_*, memory_*)
- Link processing (process_and_save_link)
- Interactive choices (offer_choices -- tap-able buttons; end your turn after calling it)
- Shell execution (execute)

Rules:
1. Be efficient with tool calls -- 1-3 targeted calls over exhaustive searching.
2. Always provide a short natural-language summary after tool calls.
3. Use colloquial names in replies (e.g. "the purifier"), never raw entity_ids.
4. For short ordinal replies like "3" or "the second one", resolve against your
   previous message.
5. Confirm actions in one line and stop -- no filler tails, no second-guessing.
6. Synthesize redundant sensor readings (within ~1C / 5%RH) into one value instead
   of dumping raw lists.
"""

if CHAT_FAMILY == "qwen":
    # Size-aware Qwen3.5 modelfile:
    #   <=3B: Ollama's built-in qwen3.5 renderer/parser works cleanly. This
    #         sets supports_tools: true so langchain_ollama / OpenAI-style
    #         callers get structured tool_calls.
    #   >=4B: Qwen3.5-4B defaults to thinking-on, and our fine-tune inherits
    #         that. Ollama 0.21's qwen3.5 PARSER consistently errors with
    #         `EOF` when parsing the thinking+tool_call stream from our 4B
    #         fine-tune (stock qwen3.5:4b with the same parser works, so
    #         something in the fine-tune's token distribution trips it). We
    #         therefore fall back to the hand-rolled ChatML TEMPLATE for 4B+,
    #         which means direct /api/generate + /api/chat work but
    #         `bind_tools()` is not supported (capability flag off); callers
    #         need to parse <tool_call> JSON manually. Revisit when Ollama's
    #         qwen3.5 parser gets fixed upstream.
    is_small_qwen = MODEL_SIZE.upper() in ("2B",)  # extend if future 1.5B/3B land
    if is_small_qwen:
        modelfile = (
            f"FROM ./{PRIMARY_GGUF_NAME}\n"
            "\n"
            "TEMPLATE {{ .Prompt }}\n"
            "RENDERER qwen3.5\n"
            "PARSER qwen3.5\n"
            "\n"
            "# Non-thinking Qwen3.5 sampling (matches Unsloth + Qwen docs).\n"
            "PARAMETER temperature 0.7\n"
            "PARAMETER top_p 0.8\n"
            "PARAMETER top_k 20\n"
            "PARAMETER repeat_penalty 1.05\n"
            "PARAMETER num_ctx 8192\n"
            "\n"
            f'SYSTEM """{SYSTEM_PROMPT}"""\n'
        )
    else:
        qwen_template = (
            'TEMPLATE """{{- if .Messages }}\n'
            '{{- range $i, $_ := .Messages }}\n'
            '{{- if eq .Role "system" }}<|im_start|>system\n'
            '{{ .Content }}<|im_end|>\n'
            '{{ else if eq .Role "user" }}<|im_start|>user\n'
            '{{ .Content }}<|im_end|>\n'
            '{{ else if eq .Role "assistant" }}<|im_start|>assistant\n'
            '{{- if .Content }}\n'
            '{{ .Content }}\n'
            '{{- end }}\n'
            '{{- if .ToolCalls }}\n'
            '<tool_call>\n'
            '{{ range .ToolCalls }}{"name": "{{ .Function.Name }}", "arguments": {{ .Function.Arguments }}}\n'
            '{{ end }}</tool_call>\n'
            '{{- end }}<|im_end|>\n'
            '{{ else if eq .Role "tool" }}<|im_start|>user\n'
            '<tool_response>\n'
            '{{ .Content }}\n'
            '</tool_response><|im_end|>\n'
            '{{ end }}\n'
            '{{- end }}<|im_start|>assistant\n'
            '{{ end }}"""\n'
        )
        modelfile = (
            f"FROM ./{PRIMARY_GGUF_NAME}\n"
            "\n"
            "# Hand-rolled Qwen3 ChatML template: the 4B+ fine-tune defaults to\n"
            "# thinking-on and Ollama 0.21's built-in qwen3.5 PARSER EOFs on\n"
            "# the resulting thinking+tool_call stream. This template lets the\n"
            "# model be used directly via /api/generate and /api/chat; callers\n"
            "# parse <tool_call> JSON manually (bind_tools is NOT supported).\n"
            "PARAMETER temperature 0.7\n"
            "PARAMETER top_p 0.8\n"
            "PARAMETER top_k 20\n"
            "PARAMETER repeat_penalty 1.05\n"
            "PARAMETER num_ctx 8192\n"
            'PARAMETER stop "<|im_end|>"\n'
            'PARAMETER stop "<|im_start|>"\n'
            'PARAMETER stop "<|endoftext|>"\n'
            "\n"
            + qwen_template
            + "\n"
            + f'SYSTEM """{SYSTEM_PROMPT}"""\n'
        )
elif CHAT_FAMILY == "gemma":
    # Gemma 4: rely on Ollama's built-in chat-template auto-detection from
    # GGUF metadata. Gemma 4's template is complex (tool-calling PR #45257)
    # and manually re-rendering it is a footgun.
    modelfile = (
        f"FROM ./{PRIMARY_GGUF_NAME}\n"
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
        f'SYSTEM """{SYSTEM_PROMPT}"""\n'
    )
else:
    raise ValueError(f"Unknown CHAT_FAMILY: {CHAT_FAMILY!r}")

with open(MODELFILE_PATH, "w") as f:
    f.write(modelfile)

print(f"Wrote {MODELFILE_PATH} ({len(modelfile)} bytes)")
print("\n--- first 30 lines ---")
print("\n".join(modelfile.splitlines()[:30]))
'''
)


# ---------------------------------------------------------------------------
# 15. Push to HF Hub (markdown)
# ---------------------------------------------------------------------------
md(
    """\
## 7. Push every GGUF + Modelfile to the target repo

Creates `{TARGET_REPO}` on HF Hub (if missing) and uploads:

- `{BUILD_TAG}.{QUANT}.gguf` for every `QUANT` in `QUANT_LEVELS`
- `{BUILD_TAG}.Modelfile` (references `PRIMARY_QUANT`)

The fp16 GGUF is intentionally NOT uploaded -- it's huge (~4.5-8.5 GB)
and can always be regenerated from the `-merged16` repo if needed."""
)


# ---------------------------------------------------------------------------
# 16. Push to HF Hub (code)
# ---------------------------------------------------------------------------
code(
    '''\
import os
from huggingface_hub import HfApi, create_repo

api = HfApi(token=HF_TOKEN)

create_repo(TARGET_REPO, repo_type="model", exist_ok=True, token=HF_TOKEN, private=False)

# Write a short README so the repo has a proper landing page.
readme_path = "/content/README.md"
readme = f"""---
license: apache-2.0
tags:
  - gguf
  - ollama
  - homebot
  - {MODEL_FAMILY}
  - {MODEL_SIZE}
  - text-generation
pipeline_tag: text-generation
base_model: {SOURCE_REPO}
---

# {BUILD_TAG}

HomeBot {MODEL_FAMILY} {MODEL_SIZE} fine-tune exported to GGUF for local Ollama inference.

Built by `finetuning/finalize_gguf_colab.ipynb` from the merged fp16 weights at
[`{SOURCE_REPO}`](https://huggingface.co/{SOURCE_REPO}).

## Available quantizations

| Quant   | Approx. size | Recommended for |
|---------|--------------|-----------------|
| Q4_K_M  | smallest     | < 8 GB RAM machines |
| Q5_K_M  |              | good balance |
| Q6_K    |              | ~1-2% quality gap vs. fp16 |
| Q8_0    | largest      | > 16 GB RAM -- default for M-series Macs |

## Quick start on a Mac

```bash
hf download {TARGET_REPO} --include "*.Q8_0.gguf" --include "*.Modelfile" --local-dir ~/homebot-model
cd ~/homebot-model
ollama create {BUILD_TAG} -f {BUILD_TAG}.Modelfile
ollama run {BUILD_TAG} "turn off the air purifier"
```

See `finetuning/README.md` in the HomeBot repo for the full pipeline.
"""
with open(readme_path, "w") as f:
    f.write(readme)

upload_paths = list(QUANT_FILES.values()) + [MODELFILE_PATH, readme_path]

print(f"Uploading {len(upload_paths)} file(s) to https://huggingface.co/{TARGET_REPO}")
for p in upload_paths:
    size_gb = os.path.getsize(p) / 1e9
    name = os.path.basename(p)
    print(f"\\n  {name}  ({size_gb:.2f} GB)")
    api.upload_file(
        path_or_fileobj = p,
        path_in_repo   = name,
        repo_id        = TARGET_REPO,
        repo_type      = "model",
        token          = HF_TOKEN,
        commit_message = f"upload {name}",
    )

print(f"\\n=== Done ===")
print(f"Repo: https://huggingface.co/{TARGET_REPO}")
'''
)


# ---------------------------------------------------------------------------
# 17. Next steps (markdown)
# ---------------------------------------------------------------------------
md(
    """\
## 8. Next steps (run on your Mac)

```bash
mkdir -p ~/homebot-model && cd ~/homebot-model

# Pull the primary quant + Modelfile (smallest useful set):
hf download {TARGET_REPO} \\
    --include "*.${PRIMARY_QUANT}.gguf" \\
    --include "*.Modelfile" \\
    --local-dir .

# Register with Ollama:
ollama create {BUILD_TAG} -f {BUILD_TAG}.Modelfile

# Sanity test:
ollama run {BUILD_TAG} "turn off the air purifier"

# Point DeepAgent at the new build:
export MODEL=ollama:{BUILD_TAG}
```

To A/B a different quant later, just change the `--include` pattern and rerun `ollama create` with a tag suffix (e.g. `{BUILD_TAG}-q5km`) so both coexist:

```bash
hf download {TARGET_REPO} --include "*.Q5_K_M.gguf" --local-dir .

# Edit Modelfile's FROM to point at the new .gguf, or inline it:
printf 'FROM ./{BUILD_TAG}.Q5_K_M.gguf\\n' > {BUILD_TAG}-q5km.Modelfile
tail -n +2 {BUILD_TAG}.Modelfile >> {BUILD_TAG}-q5km.Modelfile
ollama create {BUILD_TAG}-q5km -f {BUILD_TAG}-q5km.Modelfile
```

## Troubleshooting

- *`No safetensors files found in /content/{BUILD_TAG}-merged`*: the SOURCE_REPO is either wrong, private without `HF_TOKEN`, or the Unsloth notebook's `push_to_hub_merged` step never completed. Verify `SOURCE_REPO` opens in a browser while logged in to HF.
- *`llama-quantize: unknown model architecture`*: the base model checkpoint pushed to `-merged16` is newer than the llama.cpp master we cloned. `cd /content/llama.cpp && git pull && cmake --build build --config Release -j$(nproc)` to rebuild against a fresher master.
- *`convert_hf_to_gguf.py ... Model <X> is not supported`*: same root cause; bump llama.cpp.
- *`OSError: [Errno 28] No space left on device`*: switch to a bigger Colab runtime, or prune cached merged dirs: `!rm -rf /content/*-merged /content/*.fp16.gguf` between runs."""
)


# ---------------------------------------------------------------------------
# assemble + write
# ---------------------------------------------------------------------------
notebook = {
    "cells": CELLS,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "codemirror_mode": {"name": "ipython", "version": 3},
            "file_extension": ".py",
            "mimetype": "text/x-python",
            "name": "python",
            "nbconvert_exporter": "python",
            "pygments_lexer": "ipython3",
            "version": "3.11",
        },
        "colab": {"provenance": []},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}


def main() -> None:
    OUT_PATH.write_text(json.dumps(notebook, indent=2) + "\n", encoding="utf-8")
    n_code = sum(1 for c in CELLS if c["cell_type"] == "code")
    n_md = sum(1 for c in CELLS if c["cell_type"] == "markdown")
    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"wrote {OUT_PATH} ({size_kb:.1f} KB, {len(CELLS)} cells: {n_md} md + {n_code} code)")


if __name__ == "__main__":
    main()
