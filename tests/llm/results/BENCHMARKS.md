# LLM Benchmark Results

**System:** Kanaks-Mac-mini.local  
**Ollama URL:** http://host.docker.internal:11434  
**Last updated:** 2026-04-04

---

## Models Tested

| Model | Provider | Params | Quantization |
|-------|----------|--------|--------------|
| gemini-2.5-flash | Gemini API | - | - |
| qwen3.5:9b | Ollama | 9.7B | default |
| qwen3.5:4b | Ollama | 4.7B | default |
| qwen3.5:2b | Ollama | 2.3B | default |
| sorc/qwen3.5-claude-4.6-opus-q4:9b | Ollama | 9.7B | Q4 |
| sorc/qwen3.5-claude-4.6-opus-q4:4b | Ollama | 4.7B | Q4 |
| sorc/qwen3.5-claude-4.6-opus-q4:2b | Ollama | 2.3B | Q4 |
| gemma4:e2b | Ollama | 5.1B | Q4_K_M |
| gemma4:latest | Ollama | 8.0B | Q4_K_M |

---

## 1. Benchmark Summary (6 tasks, 2 iterations)

Tests: basic_chat, ha_parsing, json_structured, summarization, media_query, skill_prompt

| Model | Avg Latency | Min | Max | Pass Rate | Tokens | Date |
|-------|-------------|-----|-----|-----------|--------|------|
| gemini-2.5-flash | 1,674ms | 1,154ms | 2,223ms | **100%** | 2,428 | 2026-03-22 |
| gemma4:latest (8B) | 5,096ms | 868ms | 14,357ms | **100%** | 2,516 | 2026-04-04 |
| gemma4:e2b (5.1B) | 5,868ms | 4,305ms | 7,954ms | **100%** | 4,410 | 2026-04-04 |
| sorc/qwen3.5-claude-q4:2b | 8,531ms | 4,220ms | 19,493ms | **100%** | 3,663 | 2026-03-22 |
| sorc/qwen3.5-claude-q4:9b | 24,709ms | 14,873ms | 57,084ms | 83% | 3,415 | 2026-03-22 |
| sorc/qwen3.5-claude-q4:4b | 33,059ms | 12,100ms | 77,229ms | 92% | 6,051 | 2026-03-22 |
| qwen3.5:2b | 38,948ms | 25,137ms | 51,022ms | 33% | 11,859 | 2026-03-22 |
| qwen3.5:4b | 54,286ms | 28,027ms | 72,488ms | 33% | 11,607 | 2026-03-22 |
| qwen3.5:9b | 76,512ms | 25,079ms | 108,991ms | 75% | 9,495 | 2026-03-22 |

### Per-task Pass/Fail Breakdown

| Model | basic_chat | ha_parsing | json_structured | summarization | media_query | skill_prompt |
|-------|------------|------------|-----------------|---------------|-------------|--------------|
| gemini-2.5-flash | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| gemma4:latest | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| gemma4:e2b | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| sorc/qwen3.5-claude-q4:2b | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| sorc/qwen3.5-claude-q4:9b | 1/2 | 2/2 | 1/2 | 2/2 | 2/2 | 2/2 |
| sorc/qwen3.5-claude-q4:4b | 1/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| qwen3.5:9b | 2/2 | 1/2 | 2/2 | 0/2 | 2/2 | 2/2 |
| qwen3.5:4b | 0/2 | 0/2 | 2/2 | 0/2 | 0/2 | 2/2 |
| qwen3.5:2b | 0/2 | 0/2 | 2/2 | 0/2 | 0/2 | 2/2 |

> The base qwen3.5 2b/4b models produce empty responses (hitting the 1024 token limit
> on internal thinking without outputting visible text) on most tasks.

---

## 2. Tool Calling Summary (4 tests, 2 iterations)

Tests: light_control, media_search, weather_query, thermostat_set

| Model | Avg Latency | Min | Max | Pass Rate | Tokens | Date |
|-------|-------------|-----|-----|-----------|--------|------|
| gemini-2.5-flash | 1,503ms | 1,144ms | 1,757ms | **100%** | 2,550 | 2026-03-22 |
| gemma4:e2b (5.1B) | 5,734ms | 4,843ms | 6,703ms | **100%** | 4,218 | 2026-04-04 |
| sorc/qwen3.5-claude-q4:2b | 5,933ms | 3,873ms | 9,076ms | **100%** | 5,079 | 2026-03-22 |
| gemma4:latest (8B) | 6,465ms | 724ms | 11,515ms | **100%** | 3,354 | 2026-04-04 |
| qwen3.5:2b | 6,575ms | 4,697ms | 8,726ms | **100%** | 4,951 | 2026-03-22 |
| sorc/qwen3.5-claude-q4:4b | 9,396ms | 6,195ms | 14,848ms | **100%** | 4,749 | 2026-03-22 |
| qwen3.5:4b | 11,784ms | 9,042ms | 15,457ms | **100%** | 4,979 | 2026-03-22 |
| sorc/qwen3.5-claude-q4:9b | 14,861ms | 12,404ms | 15,726ms | **100%** | 4,755 | 2026-03-22 |
| qwen3.5:9b | 16,380ms | 11,968ms | 20,363ms | **100%** | 4,872 | 2026-03-22 |

> All models achieved 100% pass rate on tool calling.
> Tool selection and argument extraction is a simpler task than free-form generation.

---

## 3. Gemma 4 vs Qwen 3.5 -- Head-to-head

### Benchmark (quality + speed)

| Comparison | Gemma 4 | Qwen 3.5 | Improvement |
|------------|---------|----------|-------------|
| gemma4:e2b vs qwen3.5:4b | 5,868ms / 100% | 54,286ms / 33% | **9.3x faster, 3x accuracy** |
| gemma4:e2b vs qwen3.5:2b | 5,868ms / 100% | 38,948ms / 33% | **6.6x faster, 3x accuracy** |
| gemma4:latest vs qwen3.5:9b | 5,096ms / 100% | 76,512ms / 75% | **15x faster, 33% more accurate** |
| gemma4:latest vs sorc/claude-q4:9b | 5,096ms / 100% | 24,709ms / 83% | **4.8x faster, 20% more accurate** |
| gemma4:e2b vs sorc/claude-q4:2b | 5,868ms / 100% | 8,531ms / 100% | **1.5x faster, same accuracy** |

### Token efficiency

| Model | Avg Tokens/Task | Notes |
|-------|-----------------|-------|
| gemma4:latest | 210 | Minimal thinking overhead |
| gemini-2.5-flash | 202 | API-optimized |
| gemma4:e2b | 368 | Moderate thinking tokens |
| sorc/qwen3.5-claude-q4:2b | 305 | Distilled, efficient |
| sorc/qwen3.5-claude-q4:9b | 285 | Distilled |
| qwen3.5:9b | 791 | Heavy internal reasoning |
| qwen3.5:4b | 967 | Wastes tokens on thinking |
| qwen3.5:2b | 988 | Wastes tokens on thinking |

---

## 4. Recommendations

**Best local model (quality):** `gemma4:latest` (8B) -- 100% pass rate, fast, token-efficient.

**Best local model (speed/size):** `gemma4:e2b` (5.1B) -- 100% pass rate, consistent latency, good for constrained VRAM.

**Previous best local:** `sorc/qwen3.5-claude-4.6-opus-q4:2b` -- still solid at 100% benchmark pass rate but slower than gemma4:e2b.

**Not recommended:** Base `qwen3.5:2b` and `qwen3.5:4b` -- only 33% pass rate due to exhausting token budget on internal thinking without producing output.

---

## Run Details

| Run ID | Type | Date | Models |
|--------|------|------|--------|
| benchmark_2026-03-22_18-47-09 | Benchmark | 2026-03-22 | gemini, qwen3.5, sorc/qwen3.5-claude |
| tool_calling_2026-03-22_19-48-02 | Tool Calling | 2026-03-22 | gemini, qwen3.5, sorc/qwen3.5-claude |
| benchmark_2026-04-04_12-15-00 | Benchmark | 2026-04-04 | gemma4:e2b, gemma4:latest |
| tool_calling_2026-04-04_12-17-34 | Tool Calling | 2026-04-04 | gemma4:e2b, gemma4:latest |
