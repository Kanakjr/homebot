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
from model_policy import ollama_name_eligible_for_deepagent, ollama_id_eligible_for_deepagent

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

_agents: dict[str, tuple] = {}
_skills_files: dict = {}


def _get_agent(model: str | None = None):
    global _skills_files
    model_key = model or config.MODEL
    if model_key not in _agents:
        agent, files = build_agent(model=model_key)
        _agents[model_key] = (agent, files)
        if not _skills_files:
            _skills_files = files
    return _agents[model_key]


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
    model: str | None = None


# -- Endpoints ----------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": "deep-agent",
        "model": config.MODEL,
        "skills_dir": config.SKILLS_DIR,
    }


@app.get("/api/models")
async def list_models():
    """Return available LLM models for the deep agent.

    Ollama models are filtered by the eligibility policy (Qwen > MAX_B excluded).
    The configured default model is always included.
    """
    import aiohttp

    model_name = config.MODEL.split(":", 1)[-1] if ":" in config.MODEL else config.MODEL
    provider = config.MODEL.split(":", 1)[0] if ":" in config.MODEL else "google_genai"
    models = [{"id": config.MODEL, "provider": provider, "name": model_name}]

    try:
        async with aiohttp.ClientSession() as session:
            ollama_url = config.OLLAMA_URL.rstrip("/")
            async with session.get(
                f"{ollama_url}/api/tags",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for m in data.get("models", []):
                        name = m.get("name", "")
                        model_id = f"ollama:{name}"
                        if model_id == config.MODEL:
                            continue
                        if not ollama_name_eligible_for_deepagent(name):
                            continue
                        models.append({"id": model_id, "provider": "ollama", "name": name})
    except Exception:
        pass

    return {"models": models}


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """Send a message and receive SSE events matching the standard backend format.

    Event types: thinking, tool_call, tool_result, response, error, done.
    """
    if req.model and req.model.startswith("ollama:"):
        if not ollama_id_eligible_for_deepagent(req.model):
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=400,
                content={"detail": f"Model {req.model} is not eligible for Deep Agent (Qwen > {config.DEEPAGENT_MAX_QWEN_B}B excluded)."},
            )

    agent, skills_files = _get_agent(req.model)

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
                    "files": skills_files,
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
                                    if tc["name"] == "render_ui":
                                        spec = tc["args"].get("spec", tc["args"])
                                        yield _sse("ui_spec", {
                                            "type": "ui_spec",
                                            "spec": spec,
                                        })
                                    else:
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
                            if msg.name == "render_ui":
                                continue
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
                req.message, last_tool_results, model=req.model
            )
            yield _sse("response", {"type": "response", "content": fallback})

        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-store, no-transform, must-revalidate",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _summarize_tool_results(
    user_question: str, tool_results: list[str], *, model: str | None = None,
) -> str:
    """Quick LLM call to summarize tool results when the agent returns empty.

    Uses the same provider as *model* (or config.MODEL): ``ollama:...`` vs ``google_genai:...``.
    """
    effective = model or config.MODEL
    combined = "\n---\n".join(tool_results[:5])
    text_prompt = (
        f"The user asked: {user_question}\n\n"
        f"Here are the tool results:\n{combined}\n\n"
        "Provide a concise, friendly summary answering the user's question."
    )
    try:
        if effective.startswith("ollama:"):
            from langchain_ollama import ChatOllama

            ollama_name = effective.split(":", 1)[1]
            llm = ChatOllama(
                base_url=config.OLLAMA_URL,
                model=ollama_name,
                temperature=0.3,
            )
            from langchain_core.messages import HumanMessage

            resp = await llm.ainvoke([HumanMessage(content=text_prompt)])
            return _extract_text(resp.content) or "I found some results but couldn't summarize them."

        from langchain_google_genai import ChatGoogleGenerativeAI

        # google_genai:gemini-... or bare gemini id
        gemini_name = effective.split(":", 1)[-1] if ":" in effective else effective
        llm = ChatGoogleGenerativeAI(
            model=gemini_name, google_api_key=config.GOOGLE_API_KEY
        )
        resp = await llm.ainvoke(text_prompt)
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
