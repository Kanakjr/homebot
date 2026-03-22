#!/usr/bin/env python3
"""Aggregate tests/llm/results/*.json into docs/LLM_BENCHMARK_RESULTS.md.

Picks the richest run per suite type (most models). Re-run after new benchmarks:

    python tests/llm/aggregate_benchmark_doc.py
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

# tests/llm -> tests -> homebot
_HOMEBOT = Path(__file__).resolve().parent.parent.parent
_DOCS = _HOMEBOT / "docs"
_RESULTS = Path(__file__).resolve().parent / "results"

# Preferred table order (matches conftest MODEL_REGISTRY)
_MODEL_ORDER = [
    "gemini-2.5-flash",
    "qwen3.5:9b",
    "qwen3.5:4b",
    "qwen3.5:2b",
    "sorc/qwen3.5-claude-4.6-opus-q4:9b",
    "sorc/qwen3.5-claude-4.6-opus-q4:4b",
    "sorc/qwen3.5-claude-4.6-opus-q4:2b",
]


def _model_sort_key(name: str) -> tuple[int, str]:
    try:
        return (_MODEL_ORDER.index(name), name)
    except ValueError:
        return (999, name)


def _pick_best_run(files: list[Path]) -> Path | None:
    """Choose file with the most distinct models; tie-break on newer mtime."""
    best: Path | None = None
    best_n = -1
    best_mtime = 0.0
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        models = {r["model"] for r in data.get("results", [])}
        n = len(models)
        mtime = f.stat().st_mtime
        if n > best_n or (n == best_n and mtime > best_mtime):
            best_n = n
            best_mtime = mtime
            best = f
    return best


def _per_task_stats(results: list[dict]) -> dict[str, dict[str, tuple[int, int]]]:
    """model -> task_id -> (passes, total)."""
    acc: dict[str, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
    for r in results:
        acc[r["model"]][r["task"]].append(r["passed"])
    out: dict[str, dict[str, tuple[int, int]]] = {}
    for model, tasks in acc.items():
        out[model] = {}
        for task, passes in tasks.items():
            out[model][task] = (sum(1 for p in passes if p), len(passes))
    return out


def _fmt_latency(ms: float | None) -> str:
    if ms is None:
        return "-"
    if ms >= 1000:
        return f"{ms / 1000:.1f}s"
    return f"{ms:.0f}ms"


def _fmt_rate(p: float) -> str:
    return f"{p * 100:.1f}%"


def _build_md(
    benchmark_file: Path | None,
    tool_file: Path | None,
) -> str:
    lines: list[str] = [
        "# LLM benchmark results",
        "",
        "Aggregated from JSON output under `tests/llm/results/`. Regenerate with:",
        "",
        "```bash",
        "python tests/llm/aggregate_benchmark_doc.py",
        "```",
        "",
        "Suites:",
        "",
        "- **Benchmark** (`test_benchmark.py`): tasks from `tests/llm/tasks.py` (chat, HA parsing, JSON, summarization, media query, skill-style prompt).",
        "- **Tool calling** (`test_tool_calling.py`): LangChain `bind_tools` scenarios (light, media search, weather, thermostat).",
        "",
    ]

    b_data = json.loads(benchmark_file.read_text(encoding="utf-8")) if benchmark_file else None
    t_data = json.loads(tool_file.read_text(encoding="utf-8")) if tool_file else None

    if b_data:
        lines.extend(
            [
                "## Benchmark suite (task quality)",
                "",
                f"- **Source:** `{benchmark_file.name}`",
                f"- **Run id:** `{b_data.get('run_id', '')}`",
                f"- **Timestamp:** {b_data.get('timestamp', '')}",
                "",
            ]
        )
        summ = b_data.get("summary") or {}
        models = sorted(summ.keys(), key=_model_sort_key)
        lines.append("| Model | Pass rate | Avg latency | Min / max | Total tokens | Runs |")
        lines.append("|-------|-----------|-------------|-----------|--------------|------|")
        for m in models:
            s = summ[m]
            pr = s.get("pass_rate", 0) or 0
            avg = s.get("avg_latency_ms")
            lo = s.get("min_latency_ms")
            hi = s.get("max_latency_ms")
            tok = s.get("total_tokens", 0)
            tr = s.get("tasks_run", 0)
            lat_range = f"{_fmt_latency(lo)} / {_fmt_latency(hi)}" if lo is not None else "-"
            lines.append(
                f"| `{m}` | {_fmt_rate(pr)} | {_fmt_latency(avg)} | {lat_range} | {tok} | {tr} |"
            )
        lines.append("")

        # Per-task pass matrix
        pt = _per_task_stats(b_data.get("results", []))
        all_tasks = sorted({r["task"] for r in b_data.get("results", [])})
        if all_tasks and pt:
            lines.append("### Per-task pass rate (benchmark)")
            lines.append("")
            header = "| Task | " + " | ".join(f"`{m}`" for m in models) + " |"
            sep = "|------|" + "|".join(["--------"] * len(models)) + "|"
            lines.append(header)
            lines.append(sep)
            for task in all_tasks:
                cells = []
                for m in models:
                    if m in pt and task in pt[m]:
                        passed, total = pt[m][task]
                        cells.append(f"{passed}/{total}")
                    else:
                        cells.append("-")
                lines.append(f"| `{task}` | " + " | ".join(cells) + " |")
            lines.append("")

    if t_data:
        lines.extend(
            [
                "## Tool calling suite",
                "",
                f"- **Source:** `{tool_file.name}`",
                f"- **Run id:** `{t_data.get('run_id', '')}`",
                f"- **Timestamp:** {t_data.get('timestamp', '')}",
                "",
            ]
        )
        summ = t_data.get("summary") or {}
        models = sorted(summ.keys(), key=_model_sort_key)
        lines.append("| Model | Pass rate | Avg latency | Min / max | Total tokens | Runs |")
        lines.append("|-------|-----------|-------------|-----------|--------------|------|")
        for m in models:
            s = summ[m]
            pr = s.get("pass_rate", 0) or 0
            avg = s.get("avg_latency_ms")
            lo = s.get("min_latency_ms")
            hi = s.get("max_latency_ms")
            tok = s.get("total_tokens", 0)
            tr = s.get("tasks_run", 0)
            lat_range = f"{_fmt_latency(lo)} / {_fmt_latency(hi)}" if lo is not None else "-"
            lines.append(
                f"| `{m}` | {_fmt_rate(pr)} | {_fmt_latency(avg)} | {lat_range} | {tok} | {tr} |"
            )
        lines.append("")

        pt = _per_task_stats(t_data.get("results", []))
        all_tasks = sorted({r["task"] for r in t_data.get("results", [])})
        if all_tasks and pt:
            lines.append("### Per-scenario pass rate (tool calling)")
            lines.append("")
            header = "| Scenario | " + " | ".join(f"`{m}`" for m in models) + " |"
            sep = "|----------|" + "|".join(["--------"] * len(models)) + "|"
            lines.append(header)
            lines.append(sep)
            for task in all_tasks:
                cells = []
                for m in models:
                    if m in pt and task in pt[m]:
                        passed, total = pt[m][task]
                        cells.append(f"{passed}/{total}")
                    else:
                        cells.append("-")
                lines.append(f"| `{task}` | " + " | ".join(cells) + " |")
            lines.append("")

    lines.extend(
        [
            "## Notes",
            "",
            "- Latencies depend on hardware, Ollama load, and whether models were pre-warmed; benchmark runs use preload/unload per model for consistency.",
            "- **Pass rate** is validator-based (format and heuristics), not human preference.",
            "- Older or partial JSON files in `tests/llm/results/` are ignored unless they are the richest run for that suite.",
            "",
        ]
    )

    return "\n".join(lines) + "\n"


def main() -> int:
    if not _RESULTS.is_dir():
        print(f"No results dir: {_RESULTS}", file=sys.stderr)
        return 1

    benchmark_files = sorted(_RESULTS.glob("benchmark_*.json"))
    tool_files = sorted(_RESULTS.glob("tool_calling_*.json"))

    b_best = _pick_best_run(benchmark_files)
    t_best = _pick_best_run(tool_files)

    if not b_best and not t_best:
        print("No benchmark_*.json or tool_calling_*.json found.", file=sys.stderr)
        return 1

    md = _build_md(b_best, t_best)
    _DOCS.mkdir(parents=True, exist_ok=True)
    out = _DOCS / "LLM_BENCHMARK_RESULTS.md"
    out.write_text(md, encoding="utf-8")
    print(f"Wrote {out}")
    if b_best:
        bm = {r["model"] for r in json.loads(b_best.read_text(encoding="utf-8")).get("results", [])}
        print(f"  benchmark: {b_best.name} ({len(bm)} models)")
    if t_best:
        tm = {r["model"] for r in json.loads(t_best.read_text(encoding="utf-8")).get("results", [])}
        print(f"  tool_calling: {t_best.name} ({len(tm)} models)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
