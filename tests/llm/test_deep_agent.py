"""Deep Agent model evaluation -- tests whether a model can handle
multi-tool agentic scenarios with a large tool surface.

Evaluates: tool selection accuracy, multi-step reasoning, system prompt
adherence, and response quality when given 15+ tools (simulating the deep
agent's 49-tool environment).

Usage:
    python tests/llm/test_deep_agent.py
    python tests/llm/test_deep_agent.py --models "gemma4:e2b" "gemma4:latest"
    python tests/llm/test_deep_agent.py --models "gemma4:e2b" --iterations 3
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

_TESTS_DIR = str(Path(__file__).resolve().parent.parent)
_BACKEND_DIR = str(Path(__file__).resolve().parent.parent.parent / "backend")
for p in (_BACKEND_DIR, _TESTS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

from conftest import MODEL_REGISTRY, Timer, get_llm, is_model_available, preload_model, unload_model, unload_all_models  # noqa: E402
from llm.results import ResultsWriter  # noqa: E402

from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402


# ---------------------------------------------------------------------------
# Mock tools -- a broad surface mimicking the deep agent
# ---------------------------------------------------------------------------

@tool
def ha_call_service(domain: str, service: str, entity_id: str, data: str = "{}") -> str:
    """Call a Home Assistant service on an entity. domain: HA domain (light, switch, fan, etc). service: Service name (turn_on, turn_off, toggle). entity_id: Target entity. data: Optional JSON service data."""
    return json.dumps({"status": "ok", "domain": domain, "service": service, "entity_id": entity_id})

@tool
def ha_get_states(domain: str = "") -> str:
    """Get current states of Home Assistant entities, optionally filtered by domain."""
    states = [
        {"entity_id": "light.bedside", "state": "off", "attributes": {"friendly_name": "Bedside", "brightness": 0}},
        {"entity_id": "light.chamber_light", "state": "on", "attributes": {"friendly_name": "3D Printer Chamber"}},
        {"entity_id": "switch.monitor_plug", "state": "on", "attributes": {"friendly_name": "Monitor Plug"}},
        {"entity_id": "fan.air_purifier", "state": "off", "attributes": {"friendly_name": "Air Purifier"}},
        {"entity_id": "sensor.temperature", "state": "26", "attributes": {"unit": "C", "friendly_name": "Room Temperature"}},
        {"entity_id": "sensor.humidity", "state": "52", "attributes": {"unit": "%", "friendly_name": "Room Humidity"}},
        {"entity_id": "person.kanak", "state": "home", "attributes": {"friendly_name": "Kanak"}},
    ]
    if domain:
        states = [s for s in states if s["entity_id"].startswith(f"{domain}.")]
    return json.dumps(states)

@tool
def ha_search_entities(query: str) -> str:
    """Search for Home Assistant entities by name or keyword."""
    results = [
        {"entity_id": "light.bedside", "friendly_name": "Bedside", "state": "off"},
        {"entity_id": "switch.monitor_plug", "friendly_name": "Monitor Plug", "state": "on"},
    ]
    return json.dumps(results)

@tool
def sonarr_search(term: str) -> str:
    """Search for TV series in Sonarr."""
    return json.dumps([
        {"title": "Severance", "year": 2022, "tvdbId": 371980, "monitored": True, "status": "continuing"},
    ])

@tool
def sonarr_get_queue() -> str:
    """Get the current Sonarr download queue."""
    return json.dumps({"totalRecords": 1, "records": [
        {"title": "Severance S02E08", "status": "downloading", "sizeleft": 524288000, "timeleft": "00:12:00"},
    ]})

@tool
def radarr_search(term: str) -> str:
    """Search for movies in Radarr."""
    return json.dumps([
        {"title": "Dune: Part Two", "year": 2024, "tmdbId": 693134, "hasFile": True},
    ])

@tool
def jellyfin_search(query: str, media_type: str = "Movie") -> str:
    """Search the Jellyfin media library."""
    return json.dumps({"items": [
        {"Name": "Dune: Part Two", "Type": "Movie", "Id": "abc123", "UserData": {"Played": True}},
    ]})

@tool
def transmission_get_torrents() -> str:
    """Get active torrents from Transmission."""
    return json.dumps({"torrents": [
        {"name": "Severance.S02E08.1080p", "percentDone": 0.85, "status": 4, "rateDownload": 5242880},
    ]})

@tool
def jellyseerr_search(query: str) -> str:
    """Search for media in Jellyseerr (request tracking)."""
    return json.dumps({"results": [
        {"title": "Severance", "mediaType": "tv", "status": 5},
    ]})

@tool
def prowlarr_search(query: str) -> str:
    """Search indexers via Prowlarr."""
    return json.dumps({"results": [
        {"title": "Severance.S02E08.1080p.WEB-DL", "size": 1073741824, "seeders": 150, "indexer": "1337x"},
    ]})

@tool
def render_ui(spec: str) -> str:
    """Render an interactive UI component in the dashboard chat. spec: JSON UI specification."""
    return json.dumps({"status": "rendered"})

@tool
def memory_search_notes(query: str) -> str:
    """Search long-term memory notes."""
    return json.dumps({"results": [
        {"path": "preferences.md", "snippet": "Kanak prefers warm white light at 40% brightness for evening."},
    ]})

@tool
def memory_read_note(path: str) -> str:
    """Read a long-term memory note by path."""
    return "Kanak prefers warm white light at 40% brightness for evening.\nSarath prefers cool white at full brightness."


DEEP_AGENT_TOOLS = [
    ha_call_service, ha_get_states, ha_search_entities,
    sonarr_search, sonarr_get_queue,
    radarr_search, jellyfin_search,
    transmission_get_torrents,
    jellyseerr_search, prowlarr_search,
    render_ui,
    memory_search_notes, memory_read_note,
]

SYSTEM_PROMPT = """\
You are HomeBotAI, an intelligent smart-home assistant powered by Home Assistant.
The home is in India (IST timezone). Residents: Kanak and Sarath.

Lights: light.bedside (Bedside lamp), light.chamber_light (3D printer chamber)
Plugs: switch.monitor_plug (Desk monitor), switch.workstation
Fans: fan.air_purifier
Sensors: sensor.temperature, sensor.humidity

Tools available: ha_call_service, ha_get_states, ha_search_entities, \
sonarr_search, sonarr_get_queue, radarr_search, jellyfin_search, \
transmission_get_torrents, jellyseerr_search, prowlarr_search, \
render_ui, memory_search_notes, memory_read_note

Rules:
1. Use ha_get_states for quick lookups. Use ha_search_entities only when you \
need to find entities not listed above.
2. For device control, use ha_call_service with the correct domain, service, and entity_id.
3. For media queries, use the dedicated service tools directly.
4. Always provide a natural-language response summarizing results.
5. Be concise and friendly.
"""


# ---------------------------------------------------------------------------
# Test scenarios
# ---------------------------------------------------------------------------

DEEP_AGENT_TESTS = [
    {
        "id": "simple_device_control",
        "name": "Simple Device Control",
        "prompt": "Turn on the bedside light",
        "validate": lambda response, tool_calls: _validate_device_control(
            response, tool_calls,
            expected_tool="ha_call_service",
            expected_args={"entity_id": "light.bedside", "service": "turn_on"},
        ),
    },
    {
        "id": "state_query",
        "name": "State Query",
        "prompt": "What's the temperature and humidity right now?",
        "validate": lambda response, tool_calls: _validate_state_query(response, tool_calls),
    },
    {
        "id": "tool_selection_media",
        "name": "Media Tool Selection",
        "prompt": "Is Severance downloading? Check the status.",
        "validate": lambda response, tool_calls: _validate_media_query(response, tool_calls),
    },
    {
        "id": "multi_tool_device",
        "name": "Multi-tool: Check then Act",
        "prompt": "Check if the bedside light is on, and if not, turn it on to 50% brightness.",
        "validate": lambda response, tool_calls: _validate_multi_tool_device(response, tool_calls),
    },
    {
        "id": "correct_tool_routing",
        "name": "Correct Tool Routing (Sonarr vs Radarr)",
        "prompt": "Search for the movie Dune Part Two",
        "validate": lambda response, tool_calls: _validate_tool_routing(
            response, tool_calls,
            expected_tool="radarr_search",
            wrong_tools=["sonarr_search"],
        ),
    },
    {
        "id": "memory_aware",
        "name": "Memory-aware Response",
        "prompt": "What light settings does Kanak prefer for evening?",
        "validate": lambda response, tool_calls: _validate_memory_query(response, tool_calls),
    },
    {
        "id": "system_prompt_adherence",
        "name": "System Prompt Adherence",
        "prompt": "Who lives in the house?",
        "validate": lambda response, tool_calls: _validate_system_knowledge(response, tool_calls),
    },
    {
        "id": "complex_media_pipeline",
        "name": "Complex: Media Pipeline",
        "prompt": "What's currently downloading and what's the Sonarr queue look like?",
        "validate": lambda response, tool_calls: _validate_complex_media(response, tool_calls),
    },
]


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def _get_tool_names(tool_calls: list[dict]) -> list[str]:
    return [tc.get("name", "") for tc in tool_calls]


def _validate_device_control(response, tool_calls, expected_tool, expected_args):
    names = _get_tool_names(tool_calls)
    if expected_tool not in names:
        if response and len(response) > 20:
            return False, f"No {expected_tool} call; text response given"
        return False, f"Expected {expected_tool}, got {names}"

    for tc in tool_calls:
        if tc["name"] == expected_tool:
            args = tc.get("args", {})
            for key, val in expected_args.items():
                actual = str(args.get(key, "")).lower()
                if val.lower() not in actual:
                    return False, f"Arg {key}: expected '{val}', got '{args.get(key)}'"
            return True, f"tool={expected_tool}, args={args}"
    return False, "Unexpected state"


def _validate_state_query(response, tool_calls):
    names = _get_tool_names(tool_calls)
    has_state_tool = "ha_get_states" in names or "ha_search_entities" in names
    if not has_state_tool and not response:
        return False, "No state query tool called and no text response"

    text = response.lower()
    has_temp = any(w in text for w in ["temperature", "26", "temp"])
    has_humidity = any(w in text for w in ["humidity", "52", "humid"])

    if has_temp and has_humidity:
        return True, "Both temp and humidity mentioned"
    if has_temp or has_humidity:
        return True, f"Partial: temp={has_temp}, humidity={has_humidity}"
    if has_state_tool:
        return True, f"Used {[n for n in names if n.startswith('ha_')]}"
    return False, "No relevant data in response"


def _validate_media_query(response, tool_calls):
    names = _get_tool_names(tool_calls)
    media_tools = {"sonarr_get_queue", "transmission_get_torrents", "sonarr_search"}
    used = media_tools & set(names)
    if used:
        return True, f"Used media tools: {used}"
    if "severance" in response.lower():
        return True, "Mentioned Severance in response"
    return False, f"No media tools used. Tools called: {names}"


def _validate_multi_tool_device(response, tool_calls):
    names = _get_tool_names(tool_calls)
    has_check = "ha_get_states" in names or "ha_search_entities" in names
    has_action = "ha_call_service" in names
    if has_check and has_action:
        return True, f"Both check and action: {names}"
    if has_action:
        return True, f"Direct action (skipped check, used system prompt knowledge): {names}"
    if has_check:
        return False, f"Checked state but didn't act: {names}"
    return False, f"Neither check nor action: {names}"


def _validate_tool_routing(response, tool_calls, expected_tool, wrong_tools):
    names = _get_tool_names(tool_calls)
    used_wrong = [t for t in wrong_tools if t in names]
    if expected_tool in names:
        if used_wrong:
            return True, f"Used {expected_tool} (also used wrong: {used_wrong})"
        return True, f"Correctly routed to {expected_tool}"
    if used_wrong:
        return False, f"Wrong tool routing: used {used_wrong} instead of {expected_tool}"
    if "dune" in response.lower():
        return True, "Responded about Dune without tool call"
    return False, f"Expected {expected_tool}, got {names}"


def _validate_memory_query(response, tool_calls):
    names = _get_tool_names(tool_calls)
    has_memory = "memory_search_notes" in names or "memory_read_note" in names
    text = response.lower()
    has_pref = any(w in text for w in ["warm", "40%", "brightness", "prefer"])
    if has_memory and has_pref:
        return True, "Used memory + returned preference"
    if has_memory:
        return True, f"Used memory tools: {[n for n in names if 'memory' in n]}"
    if has_pref:
        return True, "Returned preference info (may have used system knowledge)"
    return False, f"No memory lookup and no preference in response. Tools: {names}"


def _validate_system_knowledge(response, tool_calls):
    text = response.lower()
    has_kanak = "kanak" in text
    has_sarath = "sarath" in text
    if has_kanak and has_sarath:
        return True, "Both residents mentioned"
    if has_kanak or has_sarath:
        return True, f"Partial: kanak={has_kanak}, sarath={has_sarath}"
    return False, "Neither resident mentioned in response"


def _validate_complex_media(response, tool_calls):
    names = _get_tool_names(tool_calls)
    transmission = "transmission_get_torrents" in names
    sonarr = "sonarr_get_queue" in names
    if transmission and sonarr:
        return True, "Both transmission and sonarr queue checked"
    if transmission or sonarr:
        return True, f"Partial: transmission={transmission}, sonarr={sonarr}"
    return False, f"Expected media tools, got {names}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

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


async def run_deep_agent_tests(model_keys: list[str], iterations: int):
    from rich.console import Console
    from rich.table import Table

    console = Console()

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

    console.print(f"\n[bold]Running {len(DEEP_AGENT_TESTS)} deep agent tests x {iterations} iterations "
                  f"x {len(active_models)} models[/bold]")
    console.print(f"  Tool surface: {len(DEEP_AGENT_TOOLS)} tools")

    console.print("\n[bold]Unloading all Ollama models for a clean slate...[/bold]")
    await unload_all_models()

    with ResultsWriter("deep_agent") as writer:
        for model_key in active_models:
            entry = MODEL_REGISTRY[model_key]

            console.print(f"\n[bold magenta]===  {model_key}  ===[/bold magenta]")
            if entry["provider"] == "ollama":
                console.print("  Preloading model into VRAM...", end=" ")
                ok = await preload_model(model_key)
                console.print("[green]done[/green]" if ok else "[red]failed[/red]")

            for test in DEEP_AGENT_TESTS:
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
                            llm_with_tools = llm.bind_tools(DEEP_AGENT_TOOLS)
                            messages = [
                                SystemMessage(content=SYSTEM_PROMPT),
                                HumanMessage(content=test["prompt"]),
                            ]
                            response = await llm_with_tools.ainvoke(messages)
                            text = _extract_text(response)
                            tokens = _extract_tokens(response)
                            tool_calls = getattr(response, "tool_calls", []) or []
                            passed, detail = test["validate"](text, tool_calls)
                        except Exception as e:
                            error = str(e)
                            detail = f"ERROR: {error[:80]}"

                    mark = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"
                    console.print(
                        f"    iter={i}: {mark}  "
                        f"{t.elapsed_ms:.0f}ms  "
                        f"{detail[:90]}"
                    )

                    writer.add(
                        model=model_key,
                        provider=entry["provider"],
                        task=f"deep_{test['id']}",
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

        summary = writer._build_summary()

        table = Table(title="Deep Agent Test Summary", show_lines=True)
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
    parser = argparse.ArgumentParser(description="Deep Agent Model Evaluation")
    parser.add_argument(
        "--models", nargs="*", default=None,
        help="Model keys to test (default: gemma4:e2b gemma4:latest gemini-2.5-flash)",
    )
    parser.add_argument(
        "--iterations", type=int, default=2,
        help="Iterations per model+test (default: 2)",
    )
    args = parser.parse_args()

    model_keys = args.models or ["gemma4:e2b", "gemma4:latest", "gemini-2.5-flash"]
    invalid = [k for k in model_keys if k not in MODEL_REGISTRY]
    if invalid:
        print(f"Unknown model keys: {invalid}")
        print(f"Available: {list(MODEL_REGISTRY.keys())}")
        sys.exit(1)

    asyncio.run(run_deep_agent_tests(model_keys, args.iterations))


if __name__ == "__main__":
    main()
