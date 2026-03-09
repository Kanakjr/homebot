"""
LangChain agent: uses ChatGoogleGenerativeAI with create_react_agent from LangGraph.
Builds dynamic system prompt with live state + skills + memory, and lets the
agent loop handle tool calling automatically.

Exposes two run methods:
- run()        : returns the final response string (used by Telegram bot)
- run_stream() : async generator yielding events (used by CLI and API)
"""

import base64
import json
import logging
import time
from dataclasses import dataclass, field
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


@dataclass
class AgentResponse:
    text: str
    images: list[str] = field(default_factory=list)


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


def _extract_image_paths(content: str) -> list[str]:
    """Extract image_path values from JSON tool result strings."""
    try:
        data = json.loads(content)
        if isinstance(data, dict) and "image_path" in data:
            return [data["image_path"]]
    except (json.JSONDecodeError, TypeError):
        pass
    return []


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

    async def _build_system_prompt(self, context_hint: str | None = None) -> str:
        state_summary = self.state.summarize(context_hint=context_hint)
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
            "- Check Live state first for quick answers. If the info isn't there, use ha_find_entities to search all 280+ entities.\n"
            "- Use ha_call_service for device actions (lights, fans, climate, media, etc.).\n"
            "- For camera snapshots, always call ha_get_camera_snapshot -- the image will be displayed to the user automatically.\n"
            "- When the user describes a routine, create_skill. When they invoke one, execute_skill.\n"
            "- Use remember() when the user states a preference.\n"
            "- Be resourceful: if you can't find something, search for it before saying you don't know.\n"
            "- Confirm before disruptive actions. Be concise.\n"
            "\n"
            "Multi-step planning:\n"
            "- For complex requests, plan the full tool chain before starting. For example: 'download latest X' = search Sonarr -> check Prowlarr -> add to Transmission.\n"
            "- For media requests: search the library first (Jellyfin/Sonarr), then search for downloads (Prowlarr), then add to Transmission.\n"
            "- If a step fails, explain what happened and suggest alternatives.\n"
            "- For destructive actions (deleting torrents, clearing history, disabling automations), always confirm with the user first.\n"
            "- When the user says 'yes'/'go ahead'/'do it' after you asked for confirmation, proceed with the action.\n"
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
    ) -> AgentResponse:
        if not self._agent:
            self.build_agent()

        system_prompt = system_prompt_override or await self._build_system_prompt(context_hint=user_message)
        history = await self.episodic.get_history(chat_id, limit=10)
        messages = self._build_messages(history, system_prompt, user_message, image_bytes)
        images: list[str] = []

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

            for msg in out_messages:
                if isinstance(msg, ToolMessage) and msg.content:
                    images.extend(_extract_image_paths(msg.content))

        except Exception:
            log.exception("Agent invocation failed")
            final_text = "Sorry, something went wrong processing your request."

        await self.episodic.add(chat_id, "user", user_message)
        await self.episodic.add(chat_id, "model", final_text)
        return AgentResponse(text=final_text, images=images)

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

        system_prompt = system_prompt_override or await self._build_system_prompt(context_hint=user_message)
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
                            content = msg.content or ""
                            yield {
                                "type": "tool_result",
                                "name": msg.name or "",
                                "content": content,
                                "duration_ms": duration,
                            }
                            for img_path in _extract_image_paths(content):
                                filename = img_path.rsplit("/", 1)[-1]
                                yield {"type": "image", "path": img_path, "filename": filename}

        except Exception:
            log.exception("Agent stream failed")
            final_text = "Sorry, something went wrong processing your request."
            yield {"type": "error", "content": final_text}

        finally:
            await self.episodic.add(chat_id, "user", user_message)
            await self.episodic.add(chat_id, "model", final_text)
