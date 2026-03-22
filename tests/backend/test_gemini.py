"""Test LangChain + Gemini: basic chat, tool calling, system prompt, and LangSmith tracing."""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

import config

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_core.tools import tool


async def test_basic_chat():
    print("=" * 60)
    print("1. Testing LangChain + Gemini basic chat")
    print("=" * 60)
    llm = ChatGoogleGenerativeAI(
        model=config.GEMINI_MODEL,
        google_api_key=config.GEMINI_API_KEY,
        temperature=0.3,
    )
    response = await llm.ainvoke([HumanMessage(content="Say hello in one short sentence. You are a home assistant bot.")])
    print(f"   Model: {config.GEMINI_MODEL}")
    print(f"   Response: {response.content}")
    return bool(response.content)


async def test_tool_calling():
    print("\n" + "=" * 60)
    print("2. Testing LangChain function calling (bind_tools)")
    print("=" * 60)

    @tool
    def turn_on_light(room: str, brightness: int = 255) -> str:
        """Turn on a light in the house."""
        return f"Turned on {room} light to brightness {brightness}"

    llm = ChatGoogleGenerativeAI(
        model=config.GEMINI_MODEL,
        google_api_key=config.GEMINI_API_KEY,
        temperature=0.1,
    )
    llm_with_tools = llm.bind_tools([turn_on_light])

    response = await llm_with_tools.ainvoke([HumanMessage(content="Turn on the bedroom light to 50% brightness")])

    if response.tool_calls:
        for tc in response.tool_calls:
            print(f"   Tool call: {tc['name']}")
            print(f"   Args: {tc['args']}")
        return True
    else:
        print(f"   No tool call! Got text: {response.content[:200]}")
        return False


async def test_system_prompt():
    print("\n" + "=" * 60)
    print("3. Testing LangChain with system prompt + state context")
    print("=" * 60)
    llm = ChatGoogleGenerativeAI(
        model=config.GEMINI_MODEL,
        google_api_key=config.GEMINI_API_KEY,
        temperature=0.3,
    )

    system_prompt = """You are HomeBotAI. Current home state:
- Lights: bedroom OFF, living room ON (warm white 60%)
- Sensors: temperature 24C, humidity 45%
- Persons: Kanak is home

Answer from the state above. Do NOT make API calls to read state."""

    response = await llm.ainvoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content="Is the bedroom light on? What's the temperature?"),
    ])
    print(f"   Q: Is the bedroom light on? What's the temperature?")
    print(f"   A: {response.content}")
    return bool(response.content)


async def test_langsmith_tracing():
    print("\n" + "=" * 60)
    print("4. Testing LangSmith tracing config")
    print("=" * 60)
    import os
    tracing = os.environ.get("LANGSMITH_TRACING", "false")
    project = os.environ.get("LANGSMITH_PROJECT", "")
    api_key = os.environ.get("LANGSMITH_API_KEY", "")
    print(f"   LANGSMITH_TRACING: {tracing}")
    print(f"   LANGSMITH_PROJECT: {project}")
    print(f"   LANGSMITH_API_KEY: {'set (' + api_key[:10] + '...)' if api_key else 'NOT SET'}")
    if tracing.lower() == "true" and api_key:
        print("   LangSmith tracing is ENABLED - traces should appear in dashboard")
        return True
    print("   LangSmith tracing is DISABLED")
    return False


async def main():
    print(f"GEMINI_API_KEY: {config.GEMINI_API_KEY[:15]}...")
    print(f"GEMINI_MODEL:   {config.GEMINI_MODEL}")
    print()

    ok = True
    ok = await test_basic_chat() and ok
    ok = await test_tool_calling() and ok
    ok = await test_system_prompt() and ok
    ok = await test_langsmith_tracing() and ok

    print("\n" + "=" * 60)
    if ok:
        print("All LangChain + Gemini tests passed.")
    else:
        print("Some tests FAILED - check output above.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
