"""FastAPI server for the HomeBotAI Deep Agent service."""

import json
import logging
import time

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import BaseModel

import config
from agent import build_agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-28s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("deepagent.api")

app = FastAPI(title="HomeBotAI Deep Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_agent = None
_skills_files: dict = {}


def _get_agent():
    global _agent, _skills_files
    if _agent is None:
        _agent, _skills_files = build_agent()
    return _agent


# -- Auth middleware ----------------------------------------------------------

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
    if config.API_KEY and request.url.path.startswith("/api/"):
        key = request.headers.get("X-API-Key", "")
        if key != config.API_KEY:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


# -- Models -------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"


# -- Endpoints ----------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": "deep-agent",
        "model": config.MODEL,
        "skills_dir": config.SKILLS_DIR,
    }


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """Send a message and receive SSE events matching the standard backend format.

    Event types: thinking, tool_call, tool_result, response, error, done.
    """
    agent = _get_agent()

    async def event_generator():
        final_text = ""
        response_emitted = False
        pending_tool_times: dict[str, float] = {}
        last_tool_results: list[str] = []

        try:
            yield _sse("thinking", {"type": "thinking"})

            async for chunk in agent.astream(
                {
                    "messages": [{"role": "user", "content": req.message}],
                    "files": _skills_files,
                },
                config={"configurable": {"thread_id": req.thread_id}},
            ):
                for node_name, update in chunk.items():
                    messages = _extract_messages(update)
                    log.debug("node=%s msgs=%d", node_name, len(messages))
                    for msg in messages:
                        log.debug("  msg type=%s content=%r tool_calls=%s",
                                  type(msg).__name__,
                                  (msg.content[:200] if hasattr(msg, 'content') else ''),
                                  bool(getattr(msg, 'tool_calls', None)))
                        if isinstance(msg, AIMessage):
                            if msg.tool_calls:
                                for tc in msg.tool_calls:
                                    tc_id = tc.get("id", tc["name"])
                                    pending_tool_times[tc_id] = time.monotonic()
                                    yield _sse("tool_call", {
                                        "type": "tool_call",
                                        "name": tc["name"],
                                        "args": tc["args"],
                                        "id": tc.get("id", ""),
                                    })

                            text = _extract_text(msg.content)
                            if text:
                                final_text = text
                                if not msg.tool_calls:
                                    response_emitted = True
                                    yield _sse("response", {
                                        "type": "response",
                                        "content": final_text,
                                    })

                        elif isinstance(msg, ToolMessage):
                            call_id = getattr(msg, "tool_call_id", "")
                            t_start = pending_tool_times.pop(call_id, None)
                            duration = int((time.monotonic() - t_start) * 1000) if t_start else 0
                            content_str = (msg.content or "")[:2000]
                            last_tool_results.append(content_str)
                            yield _sse("tool_result", {
                                "type": "tool_result",
                                "name": msg.name or "",
                                "content": content_str,
                                "duration_ms": duration,
                            })

        except Exception:
            log.exception("Deep agent stream failed")
            yield _sse("error", {
                "type": "error",
                "content": "Sorry, something went wrong processing your request.",
            })

        if not response_emitted and final_text:
            yield _sse("response", {"type": "response", "content": final_text})
        elif not response_emitted and last_tool_results:
            fallback = await _summarize_tool_results(
                req.message, last_tool_results
            )
            yield _sse("response", {"type": "response", "content": fallback})

        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _summarize_tool_results(
    user_question: str, tool_results: list[str]
) -> str:
    """Quick LLM call to summarize tool results when the agent returns empty."""
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI

        model_name = config.MODEL.split(":", 1)[-1] if ":" in config.MODEL else config.MODEL
        llm = ChatGoogleGenerativeAI(
            model=model_name, google_api_key=config.GOOGLE_API_KEY
        )
        combined = "\n---\n".join(tool_results[:5])
        prompt = (
            f"The user asked: {user_question}\n\n"
            f"Here are the tool results:\n{combined}\n\n"
            "Provide a concise, friendly summary answering the user's question."
        )
        resp = await llm.ainvoke(prompt)
        return _extract_text(resp.content) or "I found some results but couldn't summarize them."
    except Exception:
        log.exception("Fallback summarization failed")
        return "I retrieved the data above but couldn't generate a summary."


def _extract_messages(update) -> list:
    """Extract message list from a graph update, handling Overwrite wrappers."""
    if isinstance(update, dict):
        msgs = update.get("messages", [])
    else:
        return []

    if hasattr(msgs, "value"):
        msgs = msgs.value

    if isinstance(msgs, list):
        return msgs
    return []


def _sse(event_type: str, data: dict) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"


def _extract_text(content) -> str:
    """Extract text from AIMessage content (may be str or list of blocks)."""
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


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=config.PORT, log_level="info")
