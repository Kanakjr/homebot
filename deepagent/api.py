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


async def _get_agent(model: str | None = None, context: str = "dashboard"):
    global _skills_files
    use_render_ui = context == "dashboard"
    use_persona = context in ("telegram", "skill")
    use_telegram = context == "telegram"

    if use_persona and not model:
        model = config.TELEGRAM_MODEL

    model_key = model or config.MODEL
    cache_key = (
        f"{model_key}"
        f":{'ui' if use_render_ui else 'no-ui'}"
        f":{'persona' if use_persona else 'neutral'}"
        f":{'tg' if use_telegram else 'any'}"
    )

    if cache_key not in _agents:
        agent, files = await build_agent(
            model=model_key,
            include_render_ui=use_render_ui,
            include_persona=use_persona,
            include_telegram=use_telegram,
        )
        _agents[cache_key] = (agent, files)
        if not _skills_files:
            _skills_files = files
    return _agents[cache_key]


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

class ImageInput(BaseModel):
    mime: str = "image/jpeg"
    b64: str


class ChatRequest(BaseModel):
    message: str
    thread_id: str = "default"
    model: str | None = None
    tags: list[str] = []
    context: str = "dashboard"  # "dashboard", "telegram", or "skill"
    images: list[ImageInput] = []


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

    seen = {config.MODEL}
    for extra in config.EXTRA_MODELS:
        if extra in seen:
            continue
        seen.add(extra)
        ep = extra.split(":", 1)[0] if ":" in extra else "google_genai"
        en = extra.split(":", 1)[-1] if ":" in extra else extra
        models.append({"id": extra, "provider": ep, "name": en})

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


@app.delete("/api/chat/threads/{thread_id}")
async def clear_thread(thread_id: str):
    """Remove all checkpoint state for a thread so the next turn starts fresh.

    LangGraph's SqliteSaver stores checkpoints keyed by ``thread_id`` in the
    ``checkpoints`` and ``writes`` tables. Deleting the rows is safe: the next
    invocation will simply create a new snapshot.
    """
    import aiosqlite

    try:
        async with aiosqlite.connect(config.CHECKPOINT_DB) as conn:
            await conn.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
            await conn.execute("DELETE FROM writes WHERE thread_id = ?", (thread_id,))
            await conn.commit()
        return {"status": "ok", "thread_id": thread_id}
    except Exception as e:
        log.exception("Failed to clear thread %s", thread_id)
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={"detail": str(e)})


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """Send a message and receive SSE events matching the standard backend format.

    Event types: thinking, tool_call, tool_result, response, error, done.
    """
    if req.model and req.model.startswith("ollama:") and req.context not in ("skill", "telegram"):
        if not ollama_id_eligible_for_deepagent(req.model):
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=400,
                content={"detail": f"Model {req.model} is not eligible for Deep Agent (Qwen > {config.DEEPAGENT_MAX_QWEN_B}B excluded)."},
            )

    agent, skills_files = await _get_agent(req.model, context=req.context)

    async def event_generator():
        final_text = ""
        response_emitted = False
        choices_emitted = False
        pending_tool_times: dict[str, float] = {}
        last_tool_results: list[str] = []

        try:
            yield _sse("thinking", {"type": "thinking"})

            run_config = {"configurable": {"thread_id": req.thread_id}}
            if req.tags:
                run_config["tags"] = req.tags

            user_content = _build_user_content(req.message, req.images)

            async for chunk in agent.astream(
                {
                    "messages": [{"role": "user", "content": user_content}],
                    "files": skills_files,
                },
                config=run_config,
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
                                    elif tc["name"] == "offer_choices":
                                        choices_prompt = tc["args"].get("prompt", "")
                                        opts = tc["args"].get("options") or []
                                        yield _sse("choices", {
                                            "type": "choices",
                                            "prompt": choices_prompt,
                                            "options": [str(o) for o in opts][:8],
                                        })
                                        # Mark as presented so trailing AI text
                                        # (the model often restates the prompt)
                                        # is dropped and the typing indicator
                                        # stops cleanly.
                                        response_emitted = True
                                        choices_emitted = True
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
                                if not msg.tool_calls and not choices_emitted:
                                    response_emitted = True
                                    yield _sse("response", {
                                        "type": "response",
                                        "content": final_text,
                                    })

                        elif isinstance(msg, ToolMessage):
                            call_id = getattr(msg, "tool_call_id", "")
                            t_start = pending_tool_times.pop(call_id, None)
                            duration = int((time.monotonic() - t_start) * 1000) if t_start else 0
                            if msg.name in ("render_ui", "offer_choices"):
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

        if not response_emitted and final_text and not choices_emitted:
            yield _sse("response", {"type": "response", "content": final_text})
        elif not response_emitted and last_tool_results and not choices_emitted:
            fallback = await _summarize_tool_results(
                req.message, last_tool_results, model=req.model
            )
            yield _sse("response", {"type": "response", "content": fallback})

        trace_url = _langsmith_trace_url()
        if trace_url:
            yield _sse("trace", {"type": "trace", "url": trace_url})

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


def _build_user_content(text: str, images: list) -> list | str:
    """Build a LangChain message content block from text + optional images.

    When there are no images, we return the plain string (cheapest path).
    With images, each becomes a content block of type ``image_url`` with a
    ``data:<mime>;base64,...`` URL, which LangChain translates to the
    provider-native multimodal format for both Gemini and Ollama vision models.
    """
    if not images:
        return text

    blocks: list[dict] = [{"type": "text", "text": text}]
    for img in images:
        if hasattr(img, "mime"):
            mime = img.mime
            b64 = img.b64
        else:
            mime = img.get("mime", "image/jpeg")
            b64 = img.get("b64", "")
        if not b64:
            continue
        blocks.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{b64}"},
        })
    return blocks


def _langsmith_trace_url() -> str | None:
    """Return the URL of the current LangSmith run, if tracing is active.

    LangSmith exposes the active run via its RunTree context. Returns None
    silently if tracing is disabled or the SDK is not installed.
    """
    if str(config.LANGSMITH_TRACING).lower() not in ("true", "1", "yes"):
        return None
    try:
        from langsmith.run_helpers import get_current_run_tree
    except Exception:
        return None
    try:
        rt = get_current_run_tree()
        if rt is None:
            return None
        url = getattr(rt, "url", None)
        if url:
            return url
        run_id = getattr(rt, "id", None) or getattr(rt, "trace_id", None)
        if run_id:
            return f"https://smith.langchain.com/public/{run_id}/r"
    except Exception:
        return None
    return None


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
