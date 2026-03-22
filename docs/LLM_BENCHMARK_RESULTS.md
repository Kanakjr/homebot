# LLM benchmark results

Aggregated from JSON output under `tests/llm/results/`. Regenerate with:

```bash
python tests/llm/aggregate_benchmark_doc.py
```

Suites:

- **Benchmark** (`test_benchmark.py`): tasks from `tests/llm/tasks.py` (chat, HA parsing, JSON, summarization, media query, skill-style prompt).
- **Tool calling** (`test_tool_calling.py`): LangChain `bind_tools` scenarios (light, media search, weather, thermostat).

## Benchmark suite (task quality)

- **Source:** `benchmark_2026-03-22_18-47-09.json`
- **Run id:** `benchmark_2026-03-22_18-47-09`
- **Timestamp:** 2026-03-22T18:47:09.131973+00:00

| Model | Pass rate | Avg latency | Min / max | Total tokens | Runs |
|-------|-----------|-------------|-----------|--------------|------|
| `gemini-2.5-flash` | 100.0% | 1.7s | 1.2s / 2.2s | 2428 | 12 |
| `qwen3.5:9b` | 75.0% | 76.5s | 25.1s / 109.0s | 9495 | 12 |
| `qwen3.5:4b` | 33.3% | 54.3s | 28.0s / 72.5s | 11607 | 12 |
| `qwen3.5:2b` | 33.3% | 38.9s | 25.1s / 51.0s | 11859 | 12 |
| `sorc/qwen3.5-claude-4.6-opus-q4:9b` | 83.3% | 24.7s | 14.9s / 57.1s | 3415 | 12 |
| `sorc/qwen3.5-claude-4.6-opus-q4:4b` | 91.7% | 33.1s | 12.1s / 77.2s | 6051 | 12 |
| `sorc/qwen3.5-claude-4.6-opus-q4:2b` | 100.0% | 8.5s | 4.2s / 19.5s | 3663 | 12 |

### Per-task pass rate (benchmark)

| Task | `gemini-2.5-flash` | `qwen3.5:9b` | `qwen3.5:4b` | `qwen3.5:2b` | `sorc/qwen3.5-claude-4.6-opus-q4:9b` | `sorc/qwen3.5-claude-4.6-opus-q4:4b` | `sorc/qwen3.5-claude-4.6-opus-q4:2b` |
|------|--------|--------|--------|--------|--------|--------|--------|
| `basic_chat` | 2/2 | 2/2 | 0/2 | 0/2 | 1/2 | 1/2 | 2/2 |
| `ha_parsing` | 2/2 | 1/2 | 0/2 | 0/2 | 2/2 | 2/2 | 2/2 |
| `json_structured` | 2/2 | 2/2 | 2/2 | 2/2 | 1/2 | 2/2 | 2/2 |
| `media_query` | 2/2 | 2/2 | 0/2 | 0/2 | 2/2 | 2/2 | 2/2 |
| `skill_prompt` | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| `summarization` | 2/2 | 0/2 | 0/2 | 0/2 | 2/2 | 2/2 | 2/2 |

## Tool calling suite

- **Source:** `tool_calling_2026-03-22_19-48-02.json`
- **Run id:** `tool_calling_2026-03-22_19-48-02`
- **Timestamp:** 2026-03-22T19:48:02.796926+00:00

| Model | Pass rate | Avg latency | Min / max | Total tokens | Runs |
|-------|-----------|-------------|-----------|--------------|------|
| `gemini-2.5-flash` | 100.0% | 1.5s | 1.1s / 1.8s | 2550 | 8 |
| `qwen3.5:9b` | 100.0% | 16.4s | 12.0s / 20.4s | 4872 | 8 |
| `qwen3.5:4b` | 100.0% | 11.8s | 9.0s / 15.5s | 4979 | 8 |
| `qwen3.5:2b` | 100.0% | 6.6s | 4.7s / 8.7s | 4951 | 8 |
| `sorc/qwen3.5-claude-4.6-opus-q4:9b` | 100.0% | 14.9s | 12.4s / 15.7s | 4755 | 8 |
| `sorc/qwen3.5-claude-4.6-opus-q4:4b` | 100.0% | 9.4s | 6.2s / 14.8s | 4749 | 8 |
| `sorc/qwen3.5-claude-4.6-opus-q4:2b` | 100.0% | 5.9s | 3.9s / 9.1s | 5079 | 8 |

### Per-scenario pass rate (tool calling)

| Scenario | `gemini-2.5-flash` | `qwen3.5:9b` | `qwen3.5:4b` | `qwen3.5:2b` | `sorc/qwen3.5-claude-4.6-opus-q4:9b` | `sorc/qwen3.5-claude-4.6-opus-q4:4b` | `sorc/qwen3.5-claude-4.6-opus-q4:2b` |
|----------|--------|--------|--------|--------|--------|--------|--------|
| `tool_light_control` | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| `tool_media_search` | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| `tool_thermostat_set` | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| `tool_weather_query` | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |

## Notes

- Latencies depend on hardware, Ollama load, and whether models were pre-warmed; benchmark runs use preload/unload per model for consistency.
- **Pass rate** is validator-based (format and heuristics), not human preference.
- Older or partial JSON files in `tests/llm/results/` are ignored unless they are the richest run for that suite.

