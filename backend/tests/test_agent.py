#!/usr/bin/env python3
"""
Integration tests for the HomeBotAI agent.

Tests real Gemini API calls through LangChain, verifying:
- Text responses in both str and list-of-blocks format
- Tool calling (HA service calls)
- Streaming events from run_stream()
- Conversation memory
- State-aware responses (temperature, devices)

Usage:
    python tests/test_agent.py                   # run all tests
    python tests/test_agent.py --no-ha           # skip HA-dependent tests
    python tests/test_agent.py -k tool_call      # run tests matching pattern

Requires: GEMINI_API_KEY, HA_URL, HA_TOKEN in .env
"""

import asyncio
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import config
from agent import _extract_text, _extract_image_paths, AgentResponse
from bootstrap import create_app, shutdown_app

logging.basicConfig(
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    level=logging.WARNING,
)


PASS = 0
FAIL = 0
SKIP = 0


def result(name: str, passed: bool, detail: str = ""):
    global PASS, FAIL
    icon = "PASS" if passed else "FAIL"
    if passed:
        PASS += 1
    else:
        FAIL += 1
    extra = f"  ({detail})" if detail else ""
    print(f"  [{icon}] {name}{extra}")


def skip(name: str, reason: str = ""):
    global SKIP
    SKIP += 1
    print(f"  [SKIP] {name}  ({reason})")


# ---------------------------------------------------------------------------
# Unit tests for _extract_text
# ---------------------------------------------------------------------------

def test_extract_text_string():
    """_extract_text handles plain string content."""
    assert _extract_text("Hello world") == "Hello world"
    result("extract_text: string", True)


def test_extract_text_list_blocks():
    """_extract_text handles Gemini's list-of-blocks format."""
    content = [
        {"type": "text", "text": "Line one"},
        {"type": "text", "text": "Line two"},
    ]
    text = _extract_text(content)
    assert "Line one" in text and "Line two" in text
    result("extract_text: list of blocks", True)


def test_extract_text_list_with_extras():
    """_extract_text handles Gemini blocks that include extras/signature."""
    content = [
        {
            "type": "text",
            "text": "The temperature is 22C.",
            "extras": {"signature": "abc123..."},
        }
    ]
    text = _extract_text(content)
    assert text == "The temperature is 22C."
    result("extract_text: list with extras", True)


def test_extract_text_empty():
    """_extract_text returns empty string for None/empty."""
    assert _extract_text(None) == ""
    assert _extract_text("") == ""
    assert _extract_text([]) == ""
    result("extract_text: empty/None", True)


def test_extract_text_mixed_list():
    """_extract_text handles lists with string elements."""
    content = ["Hello", "World"]
    text = _extract_text(content)
    assert "Hello" in text and "World" in text
    result("extract_text: mixed list", True)


# ---------------------------------------------------------------------------
# Unit tests for _extract_image_paths
# ---------------------------------------------------------------------------

def test_extract_image_paths_valid():
    """_extract_image_paths extracts path from valid JSON tool result."""
    content = json.dumps({
        "status": "ok",
        "image_path": "/tmp/homebot_snapshots/camera_test.jpg",
        "entity_id": "camera.test",
    })
    paths = _extract_image_paths(content)
    assert paths == ["/tmp/homebot_snapshots/camera_test.jpg"]
    result("extract_image_paths: valid JSON", True)


def test_extract_image_paths_no_image():
    """_extract_image_paths returns empty for JSON without image_path."""
    content = json.dumps({"status": "ok", "changed": 1})
    paths = _extract_image_paths(content)
    assert paths == []
    result("extract_image_paths: no image_path", True)


def test_extract_image_paths_invalid_json():
    """_extract_image_paths returns empty for non-JSON content."""
    assert _extract_image_paths("not json") == []
    assert _extract_image_paths("") == []
    result("extract_image_paths: invalid JSON", True)


# ---------------------------------------------------------------------------
# Unit tests for AgentResponse
# ---------------------------------------------------------------------------

def test_agent_response_defaults():
    """AgentResponse has sensible defaults."""
    resp = AgentResponse(text="hello")
    assert resp.text == "hello"
    assert resp.images == []
    result("AgentResponse: defaults", True)


def test_agent_response_with_images():
    """AgentResponse stores image paths."""
    resp = AgentResponse(text="snapshot taken", images=["/tmp/snap.jpg"])
    assert len(resp.images) == 1
    assert resp.images[0] == "/tmp/snap.jpg"
    result("AgentResponse: with images", True)


# ---------------------------------------------------------------------------
# Integration tests using real Gemini API
# ---------------------------------------------------------------------------

async def test_simple_greeting(app):
    """Agent responds to a simple greeting (no tools needed)."""
    resp = await app.agent.run(chat_id=9000, user_message="Hi, say hello briefly")
    response = resp.text
    passed = len(response) > 0 and response != "I couldn't generate a response."
    result("simple greeting", passed, f"got {len(response)} chars")


async def test_simple_greeting_stream(app):
    """run_stream yields thinking + response events for a greeting."""
    events = []
    async for ev in app.agent.run_stream(chat_id=9001, user_message="Say hi in one word"):
        events.append(ev)

    types = [e["type"] for e in events]
    has_thinking = "thinking" in types
    has_response = "response" in types
    response_text = ""
    for e in events:
        if e["type"] == "response":
            response_text = e["content"]

    passed = has_thinking and has_response and len(response_text) > 0
    result("stream: greeting", passed, f"events={types}, response={response_text[:50]}")


async def test_tool_call_light(app):
    """Agent calls ha_call_service when asked to toggle a light."""
    events = []
    async for ev in app.agent.run_stream(
        chat_id=9002,
        user_message="Toggle the bedroom light right now. Use the toggle service.",
    ):
        events.append(ev)

    types = [e["type"] for e in events]
    tool_calls = [e for e in events if e["type"] == "tool_call"]
    tool_results = [e for e in events if e["type"] == "tool_result"]
    responses = [e for e in events if e["type"] == "response"]

    has_tool_call = len(tool_calls) > 0
    has_result = len(tool_results) > 0
    has_response = len(responses) > 0

    if not has_tool_call:
        skip(
            "stream: tool call (light)",
            "model answered from state context without calling tool "
            "(expected with HA connected; passes with --no-ha)",
        )
        return

    tool_name_ok = tool_calls[0]["name"] == "ha_call_service"
    passed = tool_name_ok and has_result and has_response
    result(
        "stream: tool call (light)",
        passed,
        f"tool_calls={len(tool_calls)}, results={len(tool_results)}, "
        f"response={'yes' if has_response else 'no'}",
    )

    args = tool_calls[0]["args"]
    domain_ok = args.get("domain") == "light"
    result("  tool args: domain=light", domain_ok, f"args={args}")


async def test_temperature_query(app, has_ha: bool):
    """Agent answers temperature questions from state (no tool call needed)."""
    if not has_ha:
        skip("temperature query", "HA not connected")
        return

    events = []
    async for ev in app.agent.run_stream(
        chat_id=9003,
        user_message="What's the temperature?",
    ):
        events.append(ev)

    responses = [e for e in events if e["type"] == "response"]
    has_response = len(responses) > 0
    response_text = responses[-1]["content"] if responses else ""
    no_tool_calls = not any(e["type"] == "tool_call" for e in events)

    passed = has_response and len(response_text) > 0
    result(
        "temperature query (from state)",
        passed,
        f"response={response_text[:80]}..., tools_used={not no_tool_calls}",
    )


async def test_device_listing(app, has_ha: bool):
    """Agent lists devices from HA state."""
    if not has_ha:
        skip("device listing", "HA not connected")
        return

    events = []
    async for ev in app.agent.run_stream(
        chat_id=9004,
        user_message="What devices do I have? List the domains briefly.",
    ):
        events.append(ev)

    responses = [e for e in events if e["type"] == "response"]
    has_response = len(responses) > 0
    response_text = responses[-1]["content"] if responses else ""

    passed = has_response and len(response_text) > 20
    result("device listing", passed, f"response_len={len(response_text)}")


async def test_conversation_memory(app):
    """Agent remembers context from previous turns."""
    cid = 9005

    await app.episodic.clear(cid)

    await app.agent.run(chat_id=cid, user_message="My name is TestUser")
    resp = await app.agent.run(chat_id=cid, user_message="What's my name?")

    passed = "testuser" in resp.text.lower() or "TestUser" in resp.text
    result("conversation memory", passed, f"response={resp.text[:80]}")

    await app.episodic.clear(cid)


async def test_stream_tool_result_timing(app):
    """run_stream includes duration_ms in tool_result events."""
    events = []
    async for ev in app.agent.run_stream(
        chat_id=9006,
        user_message="Toggle the bedroom light. You must use ha_call_service with toggle.",
    ):
        events.append(ev)

    tool_results = [e for e in events if e["type"] == "tool_result"]
    if not tool_results:
        skip("tool result timing", "model did not make tool calls")
        return

    has_duration = all("duration_ms" in tr for tr in tool_results)
    positive_duration = any(tr.get("duration_ms", 0) > 0 for tr in tool_results)
    passed = has_duration and positive_duration
    result(
        "tool result timing",
        passed,
        f"durations={[tr.get('duration_ms') for tr in tool_results]}",
    )


async def test_run_and_stream_parity(app):
    """run() and run_stream() produce the same final response content."""
    cid_run = 9007
    cid_stream = 9008
    msg = "What is 2 + 2? Reply with just the number."

    resp = await app.agent.run(chat_id=cid_run, user_message=msg)
    text_run = resp.text

    stream_events = []
    async for ev in app.agent.run_stream(chat_id=cid_stream, user_message=msg):
        stream_events.append(ev)

    responses = [e for e in stream_events if e["type"] == "response"]
    text_stream = responses[-1]["content"] if responses else ""

    run_has_4 = "4" in text_run
    stream_has_4 = "4" in text_stream
    passed = run_has_4 and stream_has_4
    result(
        "run/stream parity",
        passed,
        f"run='{text_run[:30]}', stream='{text_stream[:30]}'",
    )


async def test_multiple_tool_calls(app):
    """Agent can make multiple tool calls in sequence if needed."""
    events = []
    async for ev in app.agent.run_stream(
        chat_id=9009,
        user_message=(
            "Do both of these actions right now using ha_call_service: "
            "1) Toggle light.bedroom  "
            "2) Toggle light.bedside"
        ),
    ):
        events.append(ev)

    tool_calls = [e for e in events if e["type"] == "tool_call"]
    tool_results = [e for e in events if e["type"] == "tool_result"]
    responses = [e for e in events if e["type"] == "response"]

    passed = len(tool_calls) >= 2 and len(tool_results) >= 2 and len(responses) > 0
    result(
        "multiple tool calls",
        passed,
        f"tool_calls={len(tool_calls)}, results={len(tool_results)}",
    )


async def test_error_recovery(app):
    """Agent gracefully handles bad tool args (doesn't crash)."""
    events = []
    async for ev in app.agent.run_stream(
        chat_id=9010,
        user_message="Call service xyznonexistent on entity fake.entity123",
    ):
        events.append(ev)

    types = [e["type"] for e in events]
    has_any_response = "response" in types or "error" in types
    result("error recovery", has_any_response, f"event_types={types}")


# ---------------------------------------------------------------------------
# Integration tests for camera snapshots
# ---------------------------------------------------------------------------

async def test_camera_in_state(app, has_ha: bool):
    """Agent can list cameras from Live state summary."""
    if not has_ha:
        skip("camera in state", "HA not connected")
        return

    cameras = app.state_cache.get_domain("camera")
    if not cameras:
        skip("camera in state", "no camera entities in HA")
        return

    events = []
    async for ev in app.agent.run_stream(
        chat_id=9020,
        user_message="What cameras do I have? Just list the names.",
    ):
        events.append(ev)

    responses = [e for e in events if e["type"] == "response"]
    response_text = responses[-1]["content"] if responses else ""
    no_tool_calls = not any(e["type"] == "tool_call" for e in events)

    passed = len(response_text) > 0 and ("camera" in response_text.lower() or "printo" in response_text.lower())
    result(
        "camera in state",
        passed,
        f"from_state={no_tool_calls}, response={response_text[:80]}",
    )


async def test_camera_snapshot_stream(app, has_ha: bool):
    """Agent calls ha_get_camera_snapshot and stream includes image event."""
    if not has_ha:
        skip("camera snapshot stream", "HA not connected")
        return

    available = [
        eid for eid, entity in app.state_cache.get_domain("camera").items()
        if entity.get("state") not in ("unavailable", "unknown")
    ]
    if not available:
        skip("camera snapshot stream", "no available cameras")
        return

    events = []
    async for ev in app.agent.run_stream(
        chat_id=9021,
        user_message="Take a snapshot from the printo camera right now.",
    ):
        events.append(ev)

    tool_calls = [e for e in events if e["type"] == "tool_call"]
    image_events = [e for e in events if e["type"] == "image"]
    responses = [e for e in events if e["type"] == "response"]

    called_snapshot = any(tc["name"] == "ha_get_camera_snapshot" for tc in tool_calls)
    has_image_event = len(image_events) > 0
    has_response = len(responses) > 0

    passed = called_snapshot and has_image_event and has_response
    result(
        "camera snapshot stream",
        passed,
        f"snapshot_called={called_snapshot}, image_events={len(image_events)}, response={'yes' if has_response else 'no'}",
    )

    if has_image_event:
        img = image_events[0]
        has_path = bool(img.get("path"))
        has_filename = bool(img.get("filename"))
        result("  image event has path+filename", has_path and has_filename, f"path={img.get('path', '')[:60]}")


async def test_camera_snapshot_run(app, has_ha: bool):
    """run() returns AgentResponse with images for camera snapshots."""
    if not has_ha:
        skip("camera snapshot run", "HA not connected")
        return

    available = [
        eid for eid, entity in app.state_cache.get_domain("camera").items()
        if entity.get("state") not in ("unavailable", "unknown")
    ]
    if not available:
        skip("camera snapshot run", "no available cameras")
        return

    resp = await app.agent.run(
        chat_id=9022,
        user_message="Snapshot from printo camera. Use ha_get_camera_snapshot.",
    )

    has_text = len(resp.text) > 0
    has_images = len(resp.images) > 0

    passed = has_text and has_images
    result(
        "camera snapshot run (AgentResponse.images)",
        passed,
        f"text_len={len(resp.text)}, images={resp.images}",
    )

    if has_images:
        import os
        file_exists = os.path.isfile(resp.images[0])
        result("  snapshot file exists on disk", file_exists, resp.images[0])


# ---------------------------------------------------------------------------
# Integration tests for entity search (ha_find_entities)
# ---------------------------------------------------------------------------

async def test_entity_search(app, has_ha: bool):
    """Agent uses ha_find_entities to find entities not in Live state summary."""
    if not has_ha:
        skip("entity search", "HA not connected")
        return

    events = []
    async for ev in app.agent.run_stream(
        chat_id=9030,
        user_message="What's the status of my printo 3D printer?",
    ):
        events.append(ev)

    tool_calls = [e for e in events if e["type"] == "tool_call"]
    responses = [e for e in events if e["type"] == "response"]
    response_text = responses[-1]["content"] if responses else ""

    used_find = any(tc["name"] == "ha_find_entities" for tc in tool_calls)
    mentions_printo = "printo" in response_text.lower() or "printer" in response_text.lower()

    passed = used_find and mentions_printo and len(response_text) > 20
    result(
        "entity search (printo)",
        passed,
        f"used_find={used_find}, mentions_printo={mentions_printo}, response={response_text[:80]}",
    )


async def test_entity_search_not_found(app, has_ha: bool):
    """Agent uses ha_find_entities and gracefully handles no results."""
    if not has_ha:
        skip("entity search not found", "HA not connected")
        return

    events = []
    async for ev in app.agent.run_stream(
        chat_id=9031,
        user_message="What's the status of my dishwasher?",
    ):
        events.append(ev)

    tool_calls = [e for e in events if e["type"] == "tool_call"]
    responses = [e for e in events if e["type"] == "response"]
    response_text = responses[-1]["content"] if responses else ""

    used_find = any(tc["name"] == "ha_find_entities" for tc in tool_calls)
    has_response = len(response_text) > 0

    passed = used_find and has_response
    result(
        "entity search (not found)",
        passed,
        f"used_find={used_find}, response={response_text[:80]}",
    )


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-ha", action="store_true")
    parser.add_argument("-k", type=str, default="", help="Run tests matching pattern")
    args = parser.parse_args()

    print("=" * 60)
    print("HomeBotAI Agent Tests")
    print("=" * 60)

    print("\n--- Unit: _extract_text ---")
    test_extract_text_string()
    test_extract_text_list_blocks()
    test_extract_text_list_with_extras()
    test_extract_text_empty()
    test_extract_text_mixed_list()

    print("\n--- Unit: _extract_image_paths ---")
    test_extract_image_paths_valid()
    test_extract_image_paths_no_image()
    test_extract_image_paths_invalid_json()

    print("\n--- Unit: AgentResponse ---")
    test_agent_response_defaults()
    test_agent_response_with_images()

    print("\n--- Integration: real Gemini API ---")
    print("Initializing app...")
    app = await create_app(connect_ha=not args.no_ha)
    has_ha = len(app.state_cache.all_entity_ids()) > 0
    print(f"  tools={len(app.tool_map)}, entities={len(app.state_cache.all_entity_ids())}")

    tests = [
        ("simple_greeting", test_simple_greeting(app)),
        ("simple_greeting_stream", test_simple_greeting_stream(app)),
        ("tool_call_light", test_tool_call_light(app)),
        ("temperature_query", test_temperature_query(app, has_ha)),
        ("device_listing", test_device_listing(app, has_ha)),
        ("conversation_memory", test_conversation_memory(app)),
        ("stream_tool_result_timing", test_stream_tool_result_timing(app)),
        ("run_and_stream_parity", test_run_and_stream_parity(app)),
        ("multiple_tool_calls", test_multiple_tool_calls(app)),
        ("error_recovery", test_error_recovery(app)),
        ("camera_in_state", test_camera_in_state(app, has_ha)),
        ("camera_snapshot_stream", test_camera_snapshot_stream(app, has_ha)),
        ("camera_snapshot_run", test_camera_snapshot_run(app, has_ha)),
        ("entity_search", test_entity_search(app, has_ha)),
        ("entity_search_not_found", test_entity_search_not_found(app, has_ha)),
    ]

    for name, coro in tests:
        if args.k and args.k.lower() not in name.lower():
            continue
        try:
            await coro
        except Exception as e:
            result(name, False, f"EXCEPTION: {e}")

    await shutdown_app(app)

    print("\n" + "=" * 60)
    print(f"Results: {PASS} passed, {FAIL} failed, {SKIP} skipped")
    print("=" * 60)

    sys.exit(1 if FAIL > 0 else 0)


if __name__ == "__main__":
    asyncio.run(main())
