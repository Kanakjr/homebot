"""LLM Benchmark Runner -- tests latency, quality, and accuracy across all models.

Usage:
    python tests/llm/test_benchmark.py                          # all models
    python tests/llm/test_benchmark.py --models gemini-2.5-flash qwen3.5:9b
    python tests/llm/test_benchmark.py --iterations 5
    python tests/llm/test_benchmark.py --tasks basic_chat json_structured
"""

import argparse
import asyncio
import sys
from pathlib import Path

_TESTS_DIR = str(Path(__file__).resolve().parent.parent)
_BACKEND_DIR = str(Path(__file__).resolve().parent.parent.parent / "backend")
# tests/ must come first so tests/llm/ package shadows backend/llm.py
for p in (_BACKEND_DIR, _TESTS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from conftest import MODEL_REGISTRY, Timer, get_llm, is_model_available, preload_model, unload_model, unload_all_models  # noqa: E402
from llm.tasks import TASKS  # noqa: E402
from llm.results import ResultsWriter  # noqa: E402

from langchain_core.messages import SystemMessage, HumanMessage  # noqa: E402


def _extract_tokens(response) -> dict:
    """Pull token usage from LangChain response metadata when available."""
    meta = getattr(response, "usage_metadata", None)
    if meta and isinstance(meta, dict):
        return {
            "prompt_tokens": meta.get("input_tokens") or meta.get("prompt_tokens"),
            "completion_tokens": meta.get("output_tokens") or meta.get("completion_tokens"),
            "total_tokens": meta.get("total_tokens"),
        }
    resp_meta = getattr(response, "response_metadata", {})
    usage = resp_meta.get("usage", resp_meta.get("token_usage", {}))
    if usage:
        return {
            "prompt_tokens": usage.get("prompt_tokens") or usage.get("input_tokens"),
            "completion_tokens": usage.get("completion_tokens") or usage.get("output_tokens"),
            "total_tokens": usage.get("total_tokens"),
        }
    return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}


def _extract_text(response) -> str:
    raw = response.content
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, list):
        return "".join(
            block.get("text", "") for block in raw
            if isinstance(block, dict) and block.get("type") == "text"
        ).strip()
    return ""


async def run_single(llm, task: dict) -> dict:
    """Run a single task against a model, returning result dict."""
    messages = []
    if task.get("system"):
        messages.append(SystemMessage(content=task["system"]))
    messages.append(HumanMessage(content=task["prompt"]))

    error = None
    text = ""
    tokens = {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}

    with Timer() as t:
        try:
            response = await llm.ainvoke(messages)
            text = _extract_text(response)
            tokens = _extract_tokens(response)
        except Exception as e:
            error = str(e)

    passed = False
    detail = ""
    if not error:
        passed, detail = task["validate"](text)
    else:
        detail = f"ERROR: {error}"

    return {
        "passed": passed,
        "latency_ms": t.elapsed_ms,
        "text": text,
        "tokens": tokens,
        "error": error,
        "detail": detail,
    }


async def run_benchmarks(
    model_keys: list[str],
    task_ids: list[str] | None,
    iterations: int,
):
    from rich.console import Console
    from rich.table import Table

    console = Console()
    tasks_to_run = TASKS if not task_ids else [t for t in TASKS if t["id"] in task_ids]

    # Check model availability
    available = {}
    console.print("\n[bold]Checking model availability...[/bold]")
    for key in model_keys:
        ok = await is_model_available(key)
        available[key] = ok
        status = "[green]available[/green]" if ok else "[red]unavailable[/red]"
        console.print(f"  {key}: {status}")

    active_models = [k for k in model_keys if available[k]]
    if not active_models:
        console.print("[red]No models available. Exiting.[/red]")
        return

    console.print(f"\n[bold]Running {len(tasks_to_run)} tasks x {iterations} iterations "
                  f"x {len(active_models)} models[/bold]")

    console.print("\n[bold]Unloading all Ollama models for a clean slate...[/bold]")
    await unload_all_models()

    with ResultsWriter("benchmark") as writer:
        for model_key in active_models:
            entry = MODEL_REGISTRY[model_key]

            console.print(f"\n[bold magenta]===  {model_key}  ===[/bold magenta]")
            if entry["provider"] == "ollama":
                console.print("  Preloading model into VRAM...", end=" ")
                ok = await preload_model(model_key)
                console.print("[green]done[/green]" if ok else "[red]failed[/red]")

            llm = get_llm(model_key)

            for task in tasks_to_run:
                console.print(f"  [cyan]{task['name']}[/cyan]")

                for i in range(1, iterations + 1):
                    result = await run_single(llm, task)
                    mark = "[green]PASS[/green]" if result["passed"] else "[red]FAIL[/red]"
                    console.print(
                        f"    iter={i}: {mark}  "
                        f"{result['latency_ms']:.0f}ms  "
                        f"{result['detail'][:80]}"
                    )
                    writer.add(
                        model=model_key,
                        provider=entry["provider"],
                        task=task["id"],
                        iteration=i,
                        passed=result["passed"],
                        latency_ms=result["latency_ms"],
                        prompt_tokens=result["tokens"]["prompt_tokens"],
                        completion_tokens=result["tokens"]["completion_tokens"],
                        total_tokens=result["tokens"]["total_tokens"],
                        response_length=len(result["text"]),
                        response_text=result["text"],
                        error=result["error"],
                    )

            if entry["provider"] == "ollama":
                console.print(f"  Unloading {model_key} from VRAM...", end=" ")
                ok = await unload_model(model_key)
                console.print("[green]done[/green]" if ok else "[yellow]skipped[/yellow]")

        # Summary table
        summary = writer._build_summary()

        table = Table(title="Benchmark Summary", show_lines=True)
        table.add_column("Model", style="cyan", min_width=20)
        table.add_column("Avg Latency", justify="right")
        table.add_column("Min / Max", justify="right")
        table.add_column("Pass Rate", justify="right")
        table.add_column("Tokens", justify="right")
        table.add_column("Tasks", justify="right")

        for model in active_models:
            s = summary.get(model, {})
            avg = f"{s.get('avg_latency_ms', 0):.0f}ms" if s.get("avg_latency_ms") else "-"
            minmax = (
                f"{s.get('min_latency_ms', 0):.0f} / {s.get('max_latency_ms', 0):.0f}ms"
                if s.get("min_latency_ms") else "-"
            )
            rate = f"{s.get('pass_rate', 0) * 100:.0f}%"
            tok = str(s.get("total_tokens", 0) or "-")
            tasks_n = str(s.get("tasks_run", 0))
            table.add_row(model, avg, minmax, rate, tok, tasks_n)

        console.print()
        console.print(table)


def main():
    parser = argparse.ArgumentParser(description="LLM Benchmark Runner")
    parser.add_argument(
        "--models", nargs="*", default=None,
        help="Model keys to test (default: all in registry)",
    )
    parser.add_argument(
        "--tasks", nargs="*", default=None,
        help="Task IDs to run (default: all)",
    )
    parser.add_argument(
        "--iterations", type=int, default=3,
        help="Number of iterations per model+task (default: 3)",
    )
    args = parser.parse_args()

    model_keys = args.models or list(MODEL_REGISTRY.keys())
    invalid = [k for k in model_keys if k not in MODEL_REGISTRY]
    if invalid:
        print(f"Unknown model keys: {invalid}")
        print(f"Available: {list(MODEL_REGISTRY.keys())}")
        sys.exit(1)

    asyncio.run(run_benchmarks(model_keys, args.tasks, args.iterations))


if __name__ == "__main__":
    main()
