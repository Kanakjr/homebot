"""Smoke tests for ChatOllamaRaw -- run directly against the real Ollama server.

Usage:
    docker exec homebot-deepagent python /app/tests/test_ollama_raw_chat.py
"""
from __future__ import annotations

import asyncio
import json
import sys

sys.path.insert(0, "/app")

from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import tool

from ollama_raw_chat import ChatOllamaRaw


@tool
def ha_call_service(
    domain: str, service: str, entity_id: str = "", data: dict | None = None
) -> str:
    """Call a Home Assistant service. domain/service required; entity_id/data optional."""
    return "ok"


@tool
def ha_get_states(domain: str = "") -> str:
    """Return states of all entities, optionally filtered to one domain."""
    return "[]"


SYSTEM = (
    "You are HomeBotAI, a smart-home assistant. The home has light.bedside, "
    "light.table_lamp, and an Alexa-proxied RGB strip controlled via "
    'script.rgb_strip_* (with data={"level": 0-100}). "Bedroom" is a scope '
    "that means all three. Fan out in the same turn; do not ask which one."
)


async def test_simple_text():
    print("\n=== test_simple_text ===")
    chat = ChatOllamaRaw(
        base_url="http://host.docker.internal:11434",
        model="homebot-qwen3_5-2b",
        num_predict=100,
    )
    resp = await chat.ainvoke(
        [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content="Say hi in three words."),
        ]
    )
    print(f"type={type(resp).__name__}")
    print(f"content={resp.content!r}")
    print(f"tool_calls={resp.tool_calls}")
    assert isinstance(resp, AIMessage)
    assert resp.content
    assert not resp.tool_calls


async def test_with_tools_single():
    print("\n=== test_with_tools_single ===")
    chat = ChatOllamaRaw(
        base_url="http://host.docker.internal:11434",
        model="homebot-qwen3_5-2b",
        num_predict=400,
    ).bind_tools([ha_call_service, ha_get_states])
    resp = await chat.ainvoke(
        [
            SystemMessage(content=SYSTEM),
            HumanMessage(content="turn off the air purifier"),
        ]
    )
    print(f"content={resp.content!r}")
    print(f"tool_calls={json.dumps(resp.tool_calls, indent=2)}")
    assert resp.tool_calls, "expected at least one tool_call"
    tc = resp.tool_calls[0]
    assert tc["name"] in {"ha_call_service", "ha_get_states"}
    assert tc.get("id", "").startswith("call_")


async def test_with_tools_fanout():
    print("\n=== test_with_tools_fanout (bedroom -> 3 calls) ===")
    chat = ChatOllamaRaw(
        base_url="http://host.docker.internal:11434",
        model="homebot-qwen3_5-2b",
        num_predict=500,
    ).bind_tools([ha_call_service, ha_get_states])
    resp = await chat.ainvoke(
        [
            SystemMessage(content=SYSTEM),
            HumanMessage(content="Set bedroom to full brightness"),
        ]
    )
    print(f"content={resp.content!r}")
    print(f"tool_calls count={len(resp.tool_calls)}")
    for tc in resp.tool_calls:
        print(f"  - {tc['name']}({json.dumps(tc['args'])})")
    assert resp.tool_calls, "expected tool_calls for bedroom scope"


async def test_multi_turn_with_tool_results():
    print("\n=== test_multi_turn_with_tool_results ===")
    chat = ChatOllamaRaw(
        base_url="http://host.docker.internal:11434",
        model="homebot-qwen3_5-2b",
        num_predict=200,
    ).bind_tools([ha_call_service, ha_get_states])
    ai_msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "ha_call_service",
                "args": {
                    "domain": "light",
                    "service": "turn_on",
                    "entity_id": "light.bedside",
                    "data": {"brightness_pct": 100},
                },
                "id": "call_abc",
                "type": "tool_call",
            },
            {
                "name": "ha_call_service",
                "args": {
                    "domain": "light",
                    "service": "turn_on",
                    "entity_id": "light.table_lamp",
                    "data": {"brightness_pct": 100},
                },
                "id": "call_def",
                "type": "tool_call",
            },
            {
                "name": "ha_call_service",
                "args": {
                    "domain": "script",
                    "service": "rgb_strip_brightness",
                    "data": {"level": 100},
                },
                "id": "call_ghi",
                "type": "tool_call",
            },
        ],
    )
    resp = await chat.ainvoke(
        [
            SystemMessage(content=SYSTEM),
            HumanMessage(content="Set bedroom to full brightness"),
            ai_msg,
            ToolMessage(content='{"status":"ok"}', tool_call_id="call_abc"),
            ToolMessage(content='{"status":"ok"}', tool_call_id="call_def"),
            ToolMessage(content='{"status":"ok","changed":2}', tool_call_id="call_ghi"),
        ]
    )
    print(f"content={resp.content!r}")
    print(f"tool_calls={resp.tool_calls}")
    assert resp.content, "expected a text confirmation after tool results"
    assert not resp.tool_calls, "should not call more tools on confirmation turn"


async def test_streaming():
    print("\n=== test_streaming ===")
    chat = ChatOllamaRaw(
        base_url="http://host.docker.internal:11434",
        model="homebot-qwen3_5-2b",
        num_predict=400,
    ).bind_tools([ha_call_service, ha_get_states])
    content_chunks: list[str] = []
    tool_call_chunks: list[dict] = []
    async for chunk in chat.astream(
        [
            SystemMessage(content=SYSTEM),
            HumanMessage(content="turn off the bedside lamp"),
        ]
    ):
        if chunk.content:
            content_chunks.append(chunk.content)
        if chunk.tool_call_chunks:
            for tcc in chunk.tool_call_chunks:
                tool_call_chunks.append(tcc)
    full_content = "".join(content_chunks)
    print(f"content_chunks={len(content_chunks)} full={full_content!r}")
    print(f"tool_call_chunks={tool_call_chunks}")
    assert tool_call_chunks, "expected at least one tool_call via streaming"


async def main():
    await test_simple_text()
    await test_with_tools_single()
    await test_with_tools_fanout()
    await test_multi_turn_with_tool_results()
    await test_streaming()
    print("\nAll ChatOllamaRaw smoke tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
