"""ResultsWriter -- structured JSON output for LLM benchmark runs.

Usage:
    with ResultsWriter("benchmark") as w:
        w.add(model="qwen3.5:9b", provider="ollama", task="basic_chat",
              iteration=1, passed=True, latency_ms=1234.5,
              prompt_tokens=24, completion_tokens=87, total_tokens=111,
              response_length=312, response_text="...", error=None)
    # writes tests/llm/results/benchmark_2026-03-22_14-30-00.json
"""

import json
import platform
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

_BACKEND_DIR = str(Path(__file__).resolve().parent.parent.parent / "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

RESULTS_DIR = Path(__file__).resolve().parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


class ResultsWriter:
    """Context manager that collects benchmark entries and writes JSON on exit."""

    def __init__(self, test_type: str):
        self.test_type = test_type
        self.timestamp = datetime.now(timezone.utc)
        self.run_id = f"{test_type}_{self.timestamp.strftime('%Y-%m-%d_%H-%M-%S')}"
        self.entries: list[dict] = []
        self._models_seen: set[str] = set()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._write()

    def add(
        self,
        *,
        model: str,
        provider: str,
        task: str,
        iteration: int,
        passed: bool,
        latency_ms: float,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        total_tokens: int | None = None,
        response_length: int = 0,
        response_text: str = "",
        error: str | None = None,
    ):
        self._models_seen.add(model)
        self.entries.append({
            "model": model,
            "provider": provider,
            "task": task,
            "iteration": iteration,
            "passed": passed,
            "latency_ms": round(latency_ms, 2),
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "response_length": response_length,
            "response_text": response_text,
            "error": error,
        })

    def _build_summary(self) -> dict:
        by_model: dict[str, list[dict]] = defaultdict(list)
        for e in self.entries:
            by_model[e["model"]].append(e)

        summary = {}
        for model, runs in by_model.items():
            latencies = [r["latency_ms"] for r in runs if r["error"] is None]
            passes = [r for r in runs if r["passed"]]
            total_tok = sum(r["total_tokens"] or 0 for r in runs)
            summary[model] = {
                "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
                "min_latency_ms": round(min(latencies), 2) if latencies else None,
                "max_latency_ms": round(max(latencies), 2) if latencies else None,
                "pass_rate": round(len(passes) / len(runs), 3) if runs else 0,
                "total_tokens": total_tok,
                "tasks_run": len(runs),
            }
        return summary

    def _write(self):
        import config  # noqa: E402

        ollama_url = getattr(config, "OLLAMA_URL", "http://localhost:11434")

        payload = {
            "run_id": self.run_id,
            "timestamp": self.timestamp.isoformat(),
            "system": {
                "hostname": platform.node(),
                "ollama_url": ollama_url,
            },
            "models_tested": sorted(self._models_seen),
            "results": self.entries,
            "summary": self._build_summary(),
        }

        outfile = RESULTS_DIR / f"{self.run_id}.json"
        outfile.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"\nResults written to {outfile}")
