"""Tool-calling capability tests across all models.

Tests whether each model can correctly select tools and extract arguments
using LangChain's bind_tools mechanism.

Usage:
    python tests/llm/test_tool_calling.py
    python tests/llm/test_tool_calling.py --models gemini-2.5-flash qwen3.5:9b
"""

import argparse
import asyncio
import sys
from pathlib import Path

_TESTS_DIR = str(Path(__file__).resolve().parent.parent)
_BACKEND_DIR = str(Path(__file__).resolve().parent.parent.parent / "backend")
for p in (_BACKEND_DIR, _TESTS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from conftest import MODEL_REGISTRY, Timer, get_llm, is_model_available, preload_model, unload_model, unload_all_models  # noqa: E402
from llm.results import ResultsWriter  # noqa: E402

from langchain_core.messages import HumanMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402


# ---------------------------------------------------------------------------
# Mock tools
# ---------------------------------------------------------------------------


@tool
def turn_on_light(room: str, brightness: int = 255) -> str:
    """Turn on a light in a specific room of the house."""
    return f"Turned on {room} light to brightness {brightness}"


@tool
def search_media(query: str, media_type: str = "movie") -> str:
    """Search for movies or TV shows by title or keywords."""
    return f"Found results for '{query}' ({media_type})"


@tool
def get_weather(city: str) -> str:
    """Get the current weather forecast for a city."""
    return f"Weather in {city}: 24C, sunny"


@tool
def set_thermostat(temperature: float, mode: str = "auto") -> str:
    """Set the thermostat to a specific temperature and mode."""
    return f"Thermostat set to {temperature}C in {mode} mode"


MOCK_TOOLS = [turn_on_light, search_media, get_weather, set_thermostat]

# ---------------------------------------------------------------------------
# Test scenarios
# ---------------------------------------------------------------------------

TOOL_TESTS = [
    {
        "id": "light_control",
        "name": "Light Control",
        "prompt": "Turn on the bedroom light to 50% brightness",
        "expected_tool": "turn_on_light",
        "expected_args": {"room": "bedroom"},
    },
    {
        "id": "media_search",
        "name": "Media Search",
        "prompt": "Search for sci-fi TV shows",
        "expected_tool": "search_media",
        "expected_args": {"media_type": "tv"},
    },
    {
        "id": "weather_query",
        "name": "Weather Query",
        "prompt": "What's the weather like in Mumbai?",
        "expected_tool": "get_weather",
        "expected_args": {"city": "Mumbai"},
    },
    {
        "id": "thermostat_set",
        "name": "Thermostat Control",
        "prompt": "Set the thermostat to 22 degrees in cooling mode",
        "expected_tool": "set_thermostat",
        "expected_args": {"temperature": 22},
    },
]


def _validate_tool_call(response, test: dict) -> tuple[bool, str]:
    """Check if the model selected the right tool with reasonable arguments."""
    tool_calls = getattr(response, "tool_calls", None)
    if not tool_calls:
        text = getattr(response, "content", "")
        if text:
            return False, f"No tool call; responded with text: {str(text)[:100]}"
        return False, "No tool call and no text response"

    tc = tool_calls[0]
    called_name = tc.get("name", "")

    if called_name != test["expected_tool"]:
        return False, f"Wrong tool: {called_name} (expected {test['expected_tool']})"

    args = tc.get("args", {})
    for key, expected_val in test["expected_args"].items():
        actual = args.get(key)
        if actual is None:
            return False, f"Missing arg '{key}'; got args={args}"
        if isinstance(expected_val, str):
            if expected_val.lower() not in str(actual).lower():
                return False, f"Arg '{key}': '{actual}' doesn't contain '{expected_val}'"
        elif isinstance(expected_val, (int, float)):
            try:
                if abs(float(actual) - expected_val) > 1:
                    return False, f"Arg '{key}': {actual} != {expected_val}"
            except (ValueError, TypeError):
                return False, f"Arg '{key}': '{actual}' is not numeric"

    return True, f"tool={called_name}, args={args}"


def _extract_tokens(response) -> dict:
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
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
        }
    return {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}


async def run_tool_tests(model_keys: list[str], iterations: int):
    from rich.console import Console
    from rich.table import Table

    console = Console()

    # Availability check
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

    console.print(f"\n[bold]Running {len(TOOL_TESTS)} tool tests x {iterations} iterations "
                  f"x {len(active_models)} models[/bold]")

    console.print("\n[bold]Unloading all Ollama models for a clean slate...[/bold]")
    await unload_all_models()

    with ResultsWriter("tool_calling") as writer:
        for model_key in active_models:
            entry = MODEL_REGISTRY[model_key]

            console.print(f"\n[bold magenta]===  {model_key}  ===[/bold magenta]")
            if entry["provider"] == "ollama":
                console.print("  Preloading model into VRAM...", end=" ")
                ok = await preload_model(model_key)
                console.print("[green]done[/green]" if ok else "[red]failed[/red]")

            for test in TOOL_TESTS:
                console.print(f"  [cyan]{test['name']}[/cyan]")

                for i in range(1, iterations + 1):
                    error = None
                    passed = False
                    detail = ""
                    text = ""
                    tokens = {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}

                    with Timer() as t:
                        try:
                            llm = get_llm(model_key)
                            llm_with_tools = llm.bind_tools(MOCK_TOOLS)
                            response = await llm_with_tools.ainvoke(
                                [HumanMessage(content=test["prompt"])]
                            )
                            passed, detail = _validate_tool_call(response, test)
                            tokens = _extract_tokens(response)
                            text = str(getattr(response, "tool_calls", "")) or str(getattr(response, "content", ""))
                        except Exception as e:
                            error_str = str(e)
                            if "does not support" in error_str.lower() or "bind_tools" in error_str.lower():
                                detail = f"Tool calling not supported: {error_str[:80]}"
                            else:
                                error = error_str
                                detail = f"ERROR: {error_str[:80]}"

                    mark = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
                    console.print(
                        f"    iter={i}: {mark}  "
                        f"{t.elapsed_ms:.0f}ms  "
                        f"{detail[:80]}"
                    )

                    writer.add(
                        model=model_key,
                        provider=entry["provider"],
                        task=f"tool_{test['id']}",
                        iteration=i,
                        passed=passed,
                        latency_ms=t.elapsed_ms,
                        prompt_tokens=tokens["prompt_tokens"],
                        completion_tokens=tokens["completion_tokens"],
                        total_tokens=tokens["total_tokens"],
                        response_length=len(text),
                        response_text=text[:500],
                        error=error,
                    )

            if entry["provider"] == "ollama":
                console.print(f"  Unloading {model_key} from VRAM...", end=" ")
                ok = await unload_model(model_key)
                console.print("[green]done[/green]" if ok else "[yellow]skipped[/yellow]")

        # Summary table
        summary = writer._build_summary()

        table = Table(title="Tool Calling Summary", show_lines=True)
        table.add_column("Model", style="cyan", min_width=20)
        table.add_column("Avg Latency", justify="right")
        table.add_column("Pass Rate", justify="right")
        table.add_column("Tasks", justify="right")

        for model in active_models:
            s = summary.get(model, {})
            avg = f"{s.get('avg_latency_ms', 0):.0f}ms" if s.get("avg_latency_ms") else "-"
            rate = f"{s.get('pass_rate', 0) * 100:.0f}%"
            tasks_n = str(s.get("tasks_run", 0))
            table.add_row(model, avg, rate, tasks_n)

        console.print()
        console.print(table)


def main():
    parser = argparse.ArgumentParser(description="LLM Tool Calling Tests")
    parser.add_argument(
        "--models", nargs="*", default=None,
        help="Model keys to test (default: all in registry)",
    )
    parser.add_argument(
        "--iterations", type=int, default=2,
        help="Iterations per model+test (default: 2)",
    )
    args = parser.parse_args()

    model_keys = args.models or list(MODEL_REGISTRY.keys())
    invalid = [k for k in model_keys if k not in MODEL_REGISTRY]
    if invalid:
        print(f"Unknown model keys: {invalid}")
        print(f"Available: {list(MODEL_REGISTRY.keys())}")
        sys.exit(1)

    asyncio.run(run_tool_tests(model_keys, args.iterations))


if __name__ == "__main__":
    main()
