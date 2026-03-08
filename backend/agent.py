"""
LangChain agent: uses ChatGoogleGenerativeAI with create_react_agent from LangGraph.
Builds dynamic system prompt with live state + skills + memory, and lets the
agent loop handle tool calling automatically.

Exposes two run methods:
- run()        : returns the final response string (used by Telegram bot)
- run_stream() : async generator yielding events (used by CLI and API)
"""

import base64
import logging
import time
from typing import AsyncGenerator

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.prebuilt import create_react_agent

import config
from state import StateCache
from memory.episodic import EpisodicMemory
from memory.semantic import SemanticMemory
from memory.procedural import ProceduralMemory
from tools.registry import ToolMap

log = logging.getLogger("homebot.agent")

MAX_RECURSION = 25


def _extract_text(content) -> str:
    """Extract text from AIMessage content which may be str or list of blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return ""


class Agent:
    def __init__(
        self,
        state_cache: StateCache,
        episodic: EpisodicMemory,
        semantic: SemanticMemory,
        procedural: ProceduralMemory,
        tool_map: ToolMap,
    ):
        self.state = state_cache
        self.episodic = episodic
        self.semantic = semantic
        self.procedural = procedural
        self.tool_map = tool_map

        self.llm = ChatGoogleGenerativeAI(
            model=config.GEMINI_MODEL,
            google_api_key=config.GEMINI_API_KEY,
            temperature=0.7,
        )
        self._agent = None

    def build_agent(self):
        """Build (or rebuild) the agent graph with current tools."""
        tools = self.tool_map.get_tools()
        self._agent = create_react_agent(self.llm, tools)
        log.info("Agent built with %d tools", len(tools))

    async def _build_system_prompt(self) -> str:
        state_summary = self.state.summarize()
        skills = await self.procedural.list_skills()
        semantic_facts = await self.semantic.all_facts()

        skills_block = ""
        if skills:
            lines = []
            for s in skills:
                trigger = s.get("trigger", {})
                ttype = trigger.get("type", "manual")
                if ttype == "schedule":
                    label = f"cron:{trigger.get('cron', '?')}"
                elif ttype == "state_change":
                    eid = trigger.get("entity_id", "?")
                    cond = trigger.get("to", "") or trigger.get("above", "") or trigger.get("below", "")
                    label = f"{eid}->{cond}"
                else:
                    label = "manual"
                lines.append(f"  {s['name']} [{label}] - {s['description']}")
            skills_block = "\nSkills:\n" + "\n".join(lines)

        memory_block = ""
        if semantic_facts:
            items = ", ".join(f"{k}={v}" for k, v in semantic_facts.items())
            memory_block = f"\nMemory: {items}"

        return (
            "You are HomeBotAI, Kanak's smart-home assistant.\n"
            "\n"
            f"Live state:\n{state_summary}\n"
            f"{skills_block}"
            f"{memory_block}\n"
            "\n"
            "Rules:\n"
            "- Answer state questions from Live state above; do NOT call tools to read state.\n"
            "- Use ha_call_service for device actions (lights, fans, climate, media, etc.).\n"
            "- When the user describes a routine, create_skill. When they invoke one, execute_skill.\n"
            "- Use remember() when the user states a preference.\n"
            "- Confirm before disruptive actions. Be concise.\n"
        )

    def _build_messages(
        self, history: list[dict], system_prompt: str, user_message: str,
        image_bytes: bytes | None = None,
    ) -> list:
        messages = [SystemMessage(content=system_prompt)]
        for entry in history:
            if entry["role"] == "user":
                messages.append(HumanMessage(content=entry["text"]))
            else:
                messages.append(AIMessage(content=entry["text"]))

        if image_bytes:
            b64 = base64.b64encode(image_bytes).decode()
            messages.append(HumanMessage(content=[
                {"type": "text", "text": user_message},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            ]))
        else:
            messages.append(HumanMessage(content=user_message))
        return messages

    async def run(
        self,
        chat_id: int,
        user_message: str,
        image_bytes: bytes | None = None,
        system_prompt_override: str | None = None,
    ) -> str:
        if not self._agent:
            self.build_agent()

        system_prompt = system_prompt_override or await self._build_system_prompt()
        history = await self.episodic.get_history(chat_id, limit=10)
        messages = self._build_messages(history, system_prompt, user_message, image_bytes)

        try:
            result = await self._agent.ainvoke(
                {"messages": messages},
                config={"recursion_limit": MAX_RECURSION},
            )

            out_messages = result.get("messages", [])
            final_text = "I couldn't generate a response."
            for msg in reversed(out_messages):
                if isinstance(msg, AIMessage) and msg.content:
                    text = _extract_text(msg.content)
                    if text:
                        final_text = text
                        break
        except Exception:
            log.exception("Agent invocation failed")
            final_text = "Sorry, something went wrong processing your request."

        await self.episodic.add(chat_id, "user", user_message)
        await self.episodic.add(chat_id, "model", final_text)
        return final_text

    async def run_stream(
        self,
        chat_id: int,
        user_message: str,
        image_bytes: bytes | None = None,
        system_prompt_override: str | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Async generator yielding events during agent execution.

        Event types:
            {"type": "thinking"}                  - agent is reasoning
            {"type": "tool_call", "name", "args"} - tool invoked
            {"type": "tool_result", "name", "content", "duration_ms"} - tool finished
            {"type": "response", "content"}       - final text response
            {"type": "error", "content"}          - something went wrong
        """
        if not self._agent:
            self.build_agent()

        system_prompt = system_prompt_override or await self._build_system_prompt()
        history = await self.episodic.get_history(chat_id, limit=10)
        messages = self._build_messages(history, system_prompt, user_message, image_bytes)

        final_text = "I couldn't generate a response."
        pending_tool_times: dict[str, float] = {}

        try:
            yield {"type": "thinking"}

            async for chunk in self._agent.astream(
                {"messages": messages},
                config={"recursion_limit": MAX_RECURSION},
                stream_mode="updates",
            ):
                for node_name, update in chunk.items():
                    for msg in update.get("messages", []):
                        if isinstance(msg, AIMessage):
                            if msg.tool_calls:
                                for tc in msg.tool_calls:
                                    pending_tool_times[tc.get("id", tc["name"])] = time.monotonic()
                                    yield {
                                        "type": "tool_call",
                                        "name": tc["name"],
                                        "args": tc["args"],
                                        "id": tc.get("id", ""),
                                    }
                            text = _extract_text(msg.content)
                            if text:
                                final_text = text
                                yield {"type": "response", "content": final_text}

                        elif isinstance(msg, ToolMessage):
                            call_id = getattr(msg, "tool_call_id", "")
                            t_start = pending_tool_times.pop(call_id, None)
                            duration = int((time.monotonic() - t_start) * 1000) if t_start else 0
                            yield {
                                "type": "tool_result",
                                "name": msg.name or "",
                                "content": msg.content or "",
                                "duration_ms": duration,
                            }

        except Exception:
            log.exception("Agent stream failed")
            final_text = "Sorry, something went wrong processing your request."
            yield {"type": "error", "content": final_text}

        finally:
            await self.episodic.add(chat_id, "user", user_message)
            await self.episodic.add(chat_id, "model", final_text)
