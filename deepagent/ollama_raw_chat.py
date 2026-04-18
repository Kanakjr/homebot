"""ChatOllamaRaw -- raw /api/generate wrapper for fine-tuned Ollama models.

Why this exists
---------------
Ollama 0.21's built-in `qwen3.5` RENDERER + PARSER produce XML tool-call
errors ("XML syntax error on line 5: unexpected EOF",
"expected element type <function> but have <parameter>") when our fine-tune
runs inside DeepAgent's full persona+telegram+62-tool context. Debugging
isolated the root cause to the /api/chat path: Ollama's renderer rewrites
the system prompt with tool descriptions in a Qwen3-Coder style that our
Qwen3.5 fine-tune was not trained to emit, so the model either mints
`<function>/<parameter>` XML (mis-parsed) or the streaming parser
truncates mid-block.

The raw /api/generate path works 100% -- the model always emits a clean
`<tool_call>\n{JSON}\n</tool_call>` block. This wrapper hand-builds the
ChatML prompt, lists tools in the Qwen canonical `<tools></tools>`
format, and parses `<tool_call>` blocks out of the completion. DeepAgent
then sees a normal tool-calling ChatModel with populated
`message.tool_calls`.

Activate via `_resolve_model` in agent.py for `ollama:homebot-*` specs.
Other Ollama models (e.g. `ollama:gemma4:e2b`) keep using the standard
`langchain_ollama.ChatOllama` because their renderer/parser work.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
from typing import Any, AsyncIterator, Iterator, Sequence

import httpx
from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.chat_models import LanguageModelInput
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.messages.tool import ToolCallChunk
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field

log = logging.getLogger("deepagent.ollama_raw_chat")

_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)


class ChatOllamaRaw(BaseChatModel):
    """Ollama chat model that bypasses the built-in tool-call renderer/parser."""

    base_url: str = "http://localhost:11434"
    model: str
    temperature: float = 0.7
    top_p: float = 0.8
    top_k: int = 20
    num_ctx: int = 16384
    num_predict: int = 1024
    repeat_penalty: float = 1.05
    timeout: float = 180.0

    tools_spec: list[dict] | None = Field(default=None)

    @property
    def _llm_type(self) -> str:
        return "ollama-raw"

    @property
    def _identifying_params(self) -> dict:
        return {"model": self.model, "base_url": self.base_url}

    def bind_tools(
        self,
        tools: Sequence[BaseTool | dict],
        *,
        tool_choice: Any = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, BaseMessage]:
        specs: list[dict] = []
        for t in tools:
            if isinstance(t, dict):
                specs.append(t)
            else:
                specs.append(convert_to_openai_tool(t))
        return self.model_copy(update={"tools_spec": specs})

    def _format_tools_section(self) -> str:
        if not self.tools_spec:
            return ""
        lines = [
            "",
            "# Tools",
            "",
            "You may call one or more functions to assist with the user query.",
            "",
            "Function signatures are inside <tools></tools>:",
            "<tools>",
        ]
        for spec in self.tools_spec:
            lines.append(json.dumps(spec, separators=(",", ":")))
        lines.append("</tools>")
        lines.append("")
        lines.append(
            "For each function call, return a json object with the function "
            "name and arguments inside a <tool_call></tool_call> block:"
        )
        lines.append("<tool_call>")
        lines.append('{"name": "function_name", "arguments": {"arg1": "value1"}}')
        lines.append("</tool_call>")
        lines.append("")
        lines.append(
            "Emit multiple <tool_call> blocks in the same turn to call "
            "several tools in parallel."
        )
        return "\n".join(lines)

    def _build_prompt(self, messages: Sequence[BaseMessage]) -> str:
        system_parts: list[str] = []
        chat_parts: list[BaseMessage] = []
        for m in messages:
            if isinstance(m, SystemMessage):
                content = m.content if isinstance(m.content, str) else str(m.content)
                if content.strip():
                    system_parts.append(content)
            else:
                chat_parts.append(m)

        system_text = "\n\n".join(system_parts).rstrip()
        system_text += self._format_tools_section()

        buf: list[str] = []
        if system_text.strip():
            buf.append(f"<|im_start|>system\n{system_text}<|im_end|>")

        i = 0
        while i < len(chat_parts):
            m = chat_parts[i]
            if isinstance(m, HumanMessage):
                content = m.content if isinstance(m.content, str) else str(m.content)
                buf.append(f"<|im_start|>user\n{content}<|im_end|>")
                i += 1
            elif isinstance(m, AIMessage):
                parts: list[str] = []
                content = m.content if isinstance(m.content, str) else ""
                if content:
                    parts.append(content)
                if m.tool_calls:
                    for tc in m.tool_calls:
                        obj = {
                            "name": tc["name"],
                            "arguments": tc.get("args", {}),
                        }
                        parts.append(
                            "<tool_call>\n"
                            + json.dumps(obj, separators=(",", ":"))
                            + "\n</tool_call>"
                        )
                body = "\n".join(parts) if parts else ""
                buf.append(f"<|im_start|>assistant\n{body}<|im_end|>")
                i += 1
            elif isinstance(m, ToolMessage):
                tool_parts: list[str] = []
                while i < len(chat_parts) and isinstance(chat_parts[i], ToolMessage):
                    tm = chat_parts[i]
                    tc = (
                        tm.content
                        if isinstance(tm.content, str)
                        else json.dumps(tm.content)
                    )
                    tool_parts.append(f"<tool_response>\n{tc}\n</tool_response>")
                    i += 1
                buf.append("<|im_start|>user\n" + "\n".join(tool_parts) + "<|im_end|>")
            else:
                content = getattr(m, "content", "")
                if not isinstance(content, str):
                    content = str(content)
                buf.append(f"<|im_start|>user\n{content}<|im_end|>")
                i += 1

        buf.append("<|im_start|>assistant\n")
        return "\n".join(buf)

    def _parse_completion(self, text: str) -> tuple[str, list[dict]]:
        tool_calls: list[dict] = []
        for m in _TOOL_CALL_RE.finditer(text):
            try:
                obj = json.loads(m.group(1))
                tool_calls.append(
                    {
                        "name": obj.get("name", ""),
                        "args": obj.get("arguments", {}),
                        "id": f"call_{secrets.token_hex(6)}",
                        "type": "tool_call",
                    }
                )
            except json.JSONDecodeError as e:
                log.warning(
                    "Failed to parse tool_call JSON: %s in %r",
                    e,
                    m.group(1)[:200],
                )
        content = _TOOL_CALL_RE.sub("", text).strip()
        return content, tool_calls

    def _build_options(self, stop: list[str] | None) -> dict:
        opts: dict[str, Any] = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "num_ctx": self.num_ctx,
            "num_predict": self.num_predict,
            "repeat_penalty": self.repeat_penalty,
        }
        stops = list(stop) if stop else []
        stops.extend(["<|im_end|>", "<|im_start|>"])
        opts["stop"] = stops
        return opts

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        prompt = self._build_prompt(messages)
        payload = {
            "model": self.model,
            "prompt": prompt,
            "raw": True,
            "stream": False,
            "options": self._build_options(stop),
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.post(f"{self.base_url}/api/generate", json=payload)
            r.raise_for_status()
            body = r.json()

        if "error" in body:
            raise RuntimeError(f"ollama error: {body['error']}")

        raw_text = body.get("response", "")
        content, tool_calls = self._parse_completion(raw_text)

        log.debug(
            "ChatOllamaRaw: content=%d chars, tool_calls=%d, eval=%s, ms=%s",
            len(content),
            len(tool_calls),
            body.get("eval_count"),
            (body.get("total_duration") or 0) // 1_000_000,
        )

        msg = AIMessage(
            content=content,
            tool_calls=tool_calls,
            response_metadata={
                "model": self.model,
                "eval_count": body.get("eval_count"),
                "prompt_eval_count": body.get("prompt_eval_count"),
                "total_duration": body.get("total_duration"),
                "done_reason": body.get("done_reason"),
            },
            usage_metadata={
                "input_tokens": body.get("prompt_eval_count", 0) or 0,
                "output_tokens": body.get("eval_count", 0) or 0,
                "total_tokens": (body.get("prompt_eval_count", 0) or 0)
                + (body.get("eval_count", 0) or 0),
            },
        )
        return ChatResult(generations=[ChatGeneration(message=msg)])

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        prompt = self._build_prompt(messages)
        payload = {
            "model": self.model,
            "prompt": prompt,
            "raw": True,
            "stream": True,
            "options": self._build_options(stop),
        }

        open_tag = "<tool_call>"
        close_tag = "</tool_call>"
        keep_tail = len(open_tag) - 1

        buffer = ""
        in_tool_call = False
        tool_buffer = ""
        tool_idx = 0
        final_meta: dict | None = None

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST", f"{self.base_url}/api/generate", json=payload
            ) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if "error" in chunk:
                        raise RuntimeError(f"ollama stream error: {chunk['error']}")
                    if chunk.get("done"):
                        final_meta = chunk
                    text = chunk.get("response", "")
                    if not text:
                        continue

                    for ch in text:
                        if in_tool_call:
                            tool_buffer += ch
                            if tool_buffer.endswith(close_tag):
                                json_str = tool_buffer[: -len(close_tag)].strip()
                                try:
                                    obj = json.loads(json_str)
                                    name = obj.get("name", "")
                                    args_str = json.dumps(obj.get("arguments", {}))
                                    call_id = f"call_{secrets.token_hex(6)}"
                                    yield ChatGenerationChunk(
                                        message=AIMessageChunk(
                                            content="",
                                            tool_call_chunks=[
                                                ToolCallChunk(
                                                    name=name,
                                                    args=args_str,
                                                    id=call_id,
                                                    index=tool_idx,
                                                )
                                            ],
                                        ),
                                    )
                                    tool_idx += 1
                                except json.JSONDecodeError as e:
                                    log.warning(
                                        "tool_call JSON parse failed: %s; emitting raw",
                                        e,
                                    )
                                    yield ChatGenerationChunk(
                                        message=AIMessageChunk(
                                            content=f"{open_tag}{tool_buffer}"
                                        ),
                                    )
                                in_tool_call = False
                                tool_buffer = ""
                        else:
                            buffer += ch
                            if buffer.endswith(open_tag):
                                prefix = buffer[: -len(open_tag)]
                                if prefix:
                                    yield ChatGenerationChunk(
                                        message=AIMessageChunk(content=prefix),
                                    )
                                buffer = ""
                                in_tool_call = True
                                tool_buffer = ""
                            elif len(buffer) > keep_tail:
                                safe_len = len(buffer) - keep_tail
                                yield ChatGenerationChunk(
                                    message=AIMessageChunk(content=buffer[:safe_len]),
                                )
                                buffer = buffer[safe_len:]

        if in_tool_call and tool_buffer:
            yield ChatGenerationChunk(
                message=AIMessageChunk(content=f"{open_tag}{tool_buffer}"),
            )
        elif buffer:
            yield ChatGenerationChunk(message=AIMessageChunk(content=buffer))

        if final_meta is not None:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="",
                    response_metadata={
                        "model": self.model,
                        "eval_count": final_meta.get("eval_count"),
                        "prompt_eval_count": final_meta.get("prompt_eval_count"),
                        "done_reason": final_meta.get("done_reason"),
                    },
                    usage_metadata={
                        "input_tokens": final_meta.get("prompt_eval_count", 0) or 0,
                        "output_tokens": final_meta.get("eval_count", 0) or 0,
                        "total_tokens": (
                            final_meta.get("prompt_eval_count", 0) or 0
                        )
                        + (final_meta.get("eval_count", 0) or 0),
                    },
                ),
            )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            raise RuntimeError(
                "ChatOllamaRaw._generate called from within a running event loop; "
                "use the async path (ainvoke/astream) instead."
            )
        return asyncio.run(
            self._agenerate(messages, stop=stop, run_manager=None, **kwargs)
        )

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        raise NotImplementedError(
            "ChatOllamaRaw sync streaming is not implemented. "
            "DeepAgent uses the async path; call astream instead."
        )
