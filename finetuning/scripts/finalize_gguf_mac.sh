#!/usr/bin/env bash
# Mac-side finalizer for HomeBot Unsloth builds.
#
# Run this after the Unsloth notebook has done:
#   model.save_pretrained_merged(..., save_method="merged_16bit")
#   model.push_to_hub_merged(HUB_MODEL_REPO + "-merged16", ...)
#
# It pulls the merged fp16 safetensors from HF Hub, converts to GGUF fp16,
# quantizes to Q4_K_M (or whatever QUANT is set to), writes an Ollama
# Modelfile matching the Qwen3.5 chat template, and registers the model in
# Ollama. Designed for sudo-less environments like Unsloth Studio / shared
# JupyterHub where `save_pretrained_gguf` breaks because it needs to
# `sudo apt-get install build-essential cmake libcurl4-openssl-dev`.
#
# Idempotent -- rerun to swap QUANT levels; only the cheap quantize step
# runs again, the fp16 GGUF and merged download are cached.
#
# Usage:
#   ./finalize_gguf_mac.sh [SIZE] [QUANT]
#     SIZE   one of: 2b, 4b (default: 2b).
#     QUANT  llama-quantize level, e.g. Q4_K_M, Q5_K_M, Q6_K, Q8_0 (default: Q4_K_M).
#
#   ./finalize_gguf_mac.sh 2b
#   ./finalize_gguf_mac.sh 4b
#   ./finalize_gguf_mac.sh 4b Q5_K_M
#
# Advanced overrides via env vars (take priority over positional args):
#   HF_REPO, BUILD_TAG, QUANT, WORK_DIR, LLAMA_SRC

set -euo pipefail

SIZE="${1:-2b}"
case "$SIZE" in
  2b|2B) SIZE_LOW="2b" ;;
  4b|4B) SIZE_LOW="4b" ;;
  *)
    echo "error: unknown SIZE '$SIZE'. Expected 2b or 4b." >&2
    exit 2
    ;;
esac

# Derive defaults from size, allow env-var overrides for edge cases.
HF_REPO="${HF_REPO:-kanakjr/homebot-qwen3.5-${SIZE_LOW}-gguf-merged16}"
BUILD_TAG="${BUILD_TAG:-homebot-qwen3_5-${SIZE_LOW}}"
QUANT="${QUANT:-${2:-Q4_K_M}}"

WORK_DIR="${WORK_DIR:-$HOME/homebot-model}"
LLAMA_SRC="${LLAMA_SRC:-$HOME/src/llama.cpp}"

log() { printf '\n==> %s\n' "$*"; }

log "Config"
printf '  HF_REPO   = %s\n' "$HF_REPO"
printf '  BUILD_TAG = %s\n' "$BUILD_TAG"
printf '  QUANT     = %s\n' "$QUANT"
printf '  WORK_DIR  = %s\n' "$WORK_DIR"
printf '  LLAMA_SRC = %s\n' "$LLAMA_SRC"

log "Installing llama.cpp via Homebrew (skipped if already present)"
if ! brew list llama.cpp >/dev/null 2>&1; then
  brew install llama.cpp
else
  echo "llama.cpp already installed: $(brew --prefix llama.cpp)"
fi

log "Cloning llama.cpp source for convert_hf_to_gguf.py (skipped if already cloned)"
if [ ! -d "$LLAMA_SRC" ]; then
  mkdir -p "$(dirname "$LLAMA_SRC")"
  git clone --depth 1 https://github.com/ggerganov/llama.cpp "$LLAMA_SRC"
else
  echo "llama.cpp source already at $LLAMA_SRC"
fi

mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

log "Setting up Python venv for conversion deps"
# llama.cpp's requirements-convert_hf_to_gguf.txt pins torch~=2.6.0 and
# numpy~=1.26.4, neither of which have wheels for Python >= 3.13. Instead of
# chasing the pin file, install unpinned latest versions -- convert_hf_to_gguf
# only uses very basic torch / transformers interfaces that are stable across
# versions.
VENV_MARKER="$WORK_DIR/.venv/.deps_installed"
if [ ! -f "$VENV_MARKER" ]; then
  # Blow away any half-baked venv from a previous failed run.
  rm -rf "$WORK_DIR/.venv"
  python3 -m venv "$WORK_DIR/.venv"
  # shellcheck source=/dev/null
  source "$WORK_DIR/.venv/bin/activate"
  pip install --upgrade pip wheel >/dev/null
  pip install --upgrade \
    "numpy" \
    "torch" \
    "transformers" \
    "sentencepiece" \
    "protobuf" \
    "gguf" \
    "safetensors" \
    "huggingface_hub[cli]"
  touch "$VENV_MARKER"
else
  # shellcheck source=/dev/null
  source "$WORK_DIR/.venv/bin/activate"
  echo "venv reused: $WORK_DIR/.venv"
fi

MERGED_DIR="merged-${BUILD_TAG}"
log "Downloading merged fp16 safetensors from $HF_REPO"
# Always call the HF CLI -- it is itself idempotent (checks each file's size
# and only fetches what is missing or incomplete). The previous "skip if
# config.json exists" gate was too coarse: a killed download leaves config.json
# behind before any safetensor shard comes down, and that would silently
# produce a 0-tensor GGUF on rerun.
# huggingface_hub >= 1.0 renamed the CLI from `huggingface-cli` to `hf`
# and dropped the --local-dir-use-symlinks flag (no-symlinks is now default).
if command -v hf >/dev/null 2>&1; then
  hf download "$HF_REPO" --local-dir "$MERGED_DIR"
else
  huggingface-cli download "$HF_REPO" --local-dir "$MERGED_DIR"
fi

# Sanity: download must have produced at least one safetensor shard.
if ! ls "$MERGED_DIR"/*.safetensors >/dev/null 2>&1; then
  echo "error: no *.safetensors files found in $MERGED_DIR after download." >&2
  echo "       Repo may be private (set HF_TOKEN) or the name is wrong." >&2
  exit 1
fi

FP16_GGUF="${BUILD_TAG}.fp16.gguf"
log "Converting HF safetensors -> GGUF fp16"
# A legit 2B fp16 GGUF is > 3 GB; anything under 100 MB is a stub from a
# previous partial / failed run (zero-tensor output), redo the conversion.
FP16_BYTES=0
if [ -f "$FP16_GGUF" ]; then
  FP16_BYTES=$(stat -f%z "$FP16_GGUF" 2>/dev/null || stat -c%s "$FP16_GGUF" 2>/dev/null || echo 0)
fi
if [ "$FP16_BYTES" -lt 104857600 ]; then
  [ -f "$FP16_GGUF" ] && echo "Stale $FP16_GGUF (${FP16_BYTES} bytes); redoing conversion." && rm -f "$FP16_GGUF"
  python "$LLAMA_SRC/convert_hf_to_gguf.py" "$MERGED_DIR" \
      --outfile "$FP16_GGUF" \
      --outtype f16
else
  printf 'Already converted: %s (%s)\n' "$FP16_GGUF" "$(du -h "$FP16_GGUF" | awk '{print $1}')"
fi

QUANT_GGUF="${BUILD_TAG}.${QUANT}.gguf"
log "Quantizing $FP16_GGUF -> $QUANT_GGUF ($QUANT)"
llama-quantize "$FP16_GGUF" "$QUANT_GGUF" "$QUANT"

MODELFILE_PATH="${BUILD_TAG}.Modelfile"
log "Writing $MODELFILE_PATH (size-aware: 2B uses qwen3.5 parser, 4B+ uses hand-rolled template)"
# Size-aware Qwen3.5 modelfile:
#   2B -> Ollama's built-in qwen3.5 RENDERER + PARSER. This flips the
#         supports_tools capability on so langchain_ollama bind_tools()
#         works and <tool_call> JSON gets parsed into structured tool_calls.
#   4B -> Qwen3.5-4B defaults to thinking-on, and our fine-tune inherits it.
#         Ollama 0.21's qwen3.5 PARSER reliably errors with "EOF" on the
#         resulting thinking+tool_call stream from our 4B fine-tune (the
#         stock qwen3.5:4b with the same parser works, so the fine-tune's
#         token distribution trips a parser edge case). The hand-rolled
#         ChatML TEMPLATE below works for direct /api/generate and /api/chat
#         (tool calls come through as raw <tool_call> JSON in .content);
#         bind_tools() will report "Tool calling not supported" because the
#         model doesn't advertise the capability without a PARSER. Revisit
#         when Ollama's qwen3.5 parser gets patched upstream.
if [ "$SIZE_LOW" = "2b" ]; then
cat > "$MODELFILE_PATH" <<EOF
FROM ./${QUANT_GGUF}

TEMPLATE {{ .Prompt }}
RENDERER qwen3.5
PARSER qwen3.5

PARAMETER temperature 0.7
PARAMETER top_p 0.8
PARAMETER top_k 20
PARAMETER repeat_penalty 1.05
# DeepAgent's full telegram+persona+62-tool context lands around 9.3K tokens
# on the first turn; 8192 was silently truncating and masking itself as
# Ollama parser EOF. Bump further only if tool count grows.
PARAMETER num_ctx 16384

SYSTEM """You are HomeBotAI, an intelligent smart-home assistant powered by Home Assistant.
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
EOF
else
# 4B+ path: hand-rolled Qwen3 ChatML template (see note at top of block).
cat > "$MODELFILE_PATH" <<'EOF_TEMPLATE'
FROM ./__QUANT_GGUF__

PARAMETER temperature 0.7
PARAMETER top_p 0.8
PARAMETER top_k 20
PARAMETER repeat_penalty 1.05
# DeepAgent full context lands around 9.3K tokens (persona+telegram+62 tools).
# 8192 silently truncated; 16384 gives headroom for multi-turn tool histories.
PARAMETER num_ctx 16384
PARAMETER stop "<|im_end|>"
PARAMETER stop "<|im_start|>"
PARAMETER stop "<|endoftext|>"

TEMPLATE """{{- if .Messages }}
{{- range $i, $_ := .Messages }}
{{- if eq .Role "system" }}<|im_start|>system
{{ .Content }}<|im_end|>
{{ else if eq .Role "user" }}<|im_start|>user
{{ .Content }}<|im_end|>
{{ else if eq .Role "assistant" }}<|im_start|>assistant
{{- if .Content }}
{{ .Content }}
{{- end }}
{{- if .ToolCalls }}
<tool_call>
{{ range .ToolCalls }}{"name": "{{ .Function.Name }}", "arguments": {{ .Function.Arguments }}}
{{ end }}</tool_call>
{{- end }}<|im_end|>
{{ else if eq .Role "tool" }}<|im_start|>user
<tool_response>
{{ .Content }}
</tool_response><|im_end|>
{{ end }}
{{- end }}<|im_start|>assistant
{{ end }}"""

SYSTEM """You are HomeBotAI, an intelligent smart-home assistant powered by Home Assistant.
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
EOF_TEMPLATE
# quoted heredoc disables $VAR expansion; substitute filename now.
sed -i.bak "s|__QUANT_GGUF__|${QUANT_GGUF}|" "$MODELFILE_PATH" && rm -f "${MODELFILE_PATH}.bak"
fi

if command -v ollama >/dev/null 2>&1; then
  log "Registering Ollama model: $BUILD_TAG"
  ollama create "$BUILD_TAG" -f "$MODELFILE_PATH"

  log "Sanity test (one-shot generation)"
  echo 'turn off the air purifier' | ollama run "$BUILD_TAG" --verbose=false || true
else
  log "Ollama not found on PATH -- skipped 'ollama create'. To finish:"
  printf '  cd %s\n' "$WORK_DIR"
  printf '  ollama create %s -f %s\n' "$BUILD_TAG" "$MODELFILE_PATH"
fi

log "Done"
printf 'GGUF         : %s/%s (%s)\n' "$WORK_DIR" "$QUANT_GGUF" \
  "$(du -h "$WORK_DIR/$QUANT_GGUF" 2>/dev/null | awk '{print $1}')"
printf 'Modelfile    : %s/%s\n' "$WORK_DIR" "$MODELFILE_PATH"
printf 'Ollama alias : %s\n' "$BUILD_TAG"
printf '\nPoint DeepAgent at this build with: MODEL=ollama:%s\n' "$BUILD_TAG"
