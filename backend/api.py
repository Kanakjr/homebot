#!/usr/bin/env python3
"""
HomeBotAI REST API -- lightweight HTTP interface for testing and integrations.

Usage:
    python api.py                    # default: port 8321, connect HA
    python api.py --port 9000        # custom port
    python api.py --no-ha            # skip HA WebSocket

Endpoints:
    POST /api/chat          Send a message, get a response
    POST /api/chat/stream   Send a message, get SSE event stream
    GET  /api/health        Service health and stats
    GET  /api/tools         List registered tools
    GET  /api/skills        List learned skills
    GET  /api/entities      HA entities summary by domain

Swagger docs available at /docs
"""

import argparse
import asyncio
import json
import logging
import os
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, Field

import config

log = logging.getLogger("homebot.api")

_app_ctx = None  # bootstrap.App instance


class ChatRequest(BaseModel):
    message: str = Field(..., description="User message to send to the agent")
    chat_id: int = Field(default=0, description="Conversation thread ID")


class ChatResponse(BaseModel):
    response: str
    tool_calls: list[dict] = []
    duration_ms: int = 0


class HealthResponse(BaseModel):
    status: str
    tools_registered: int
    entities_loaded: int
    model: str


class ToolInfo(BaseModel):
    name: str
    description: str


class SkillInfo(BaseModel):
    name: str
    description: str
    mode: str
    trigger_type: str
    active: bool


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize homebot on startup, clean up on shutdown."""
    global _app_ctx

    from bootstrap import create_app, shutdown_app

    connect_ha = not getattr(app.state, "no_ha", False)
    _app_ctx = await create_app(connect_ha=connect_ha)
    log.info("API server ready")
    yield
    await shutdown_app(_app_ctx)
    _app_ctx = None


app = FastAPI(
    title="HomeBotAI API",
    description="REST API for HomeBotAI smart home assistant",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get(
        "CORS_ORIGINS", "http://localhost:3001"
    ).split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Send a message and get the full response (blocking)."""
    t0 = time.monotonic()
    tool_calls = []
    response_text = ""

    async for event in _app_ctx.agent.run_stream(
        chat_id=req.chat_id,
        user_message=req.message,
    ):
        etype = event["type"]
        if etype == "tool_call":
            tool_calls.append({
                "name": event["name"],
                "args": event["args"],
            })
        elif etype == "tool_result":
            for tc in tool_calls:
                if tc["name"] == event["name"] and "result" not in tc:
                    tc["result"] = event["content"]
                    tc["duration_ms"] = event.get("duration_ms", 0)
                    break
        elif etype == "response":
            response_text = event["content"]
        elif etype == "error":
            response_text = event["content"]

    elapsed = int((time.monotonic() - t0) * 1000)
    return ChatResponse(
        response=response_text,
        tool_calls=tool_calls,
        duration_ms=elapsed,
    )


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """Send a message and receive Server-Sent Events as the agent works."""

    async def event_generator():
        async for event in _app_ctx.agent.run_stream(
            chat_id=req.chat_id,
            user_message=req.message,
        ):
            data = json.dumps(event, default=str)
            yield f"event: {event['type']}\ndata: {data}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/health", response_model=HealthResponse)
async def health():
    """Service health check and stats."""
    return HealthResponse(
        status="ok",
        tools_registered=len(_app_ctx.tool_map),
        entities_loaded=len(_app_ctx.state_cache.all_entity_ids()),
        model=config.GEMINI_MODEL,
    )


@app.get("/api/tools", response_model=list[ToolInfo])
async def list_tools():
    """List all registered tools."""
    return [
        ToolInfo(
            name=t.name,
            description=(t.description or "").split("\n")[0],
        )
        for t in _app_ctx.tool_map.get_tools()
    ]


@app.get("/api/skills", response_model=list[SkillInfo])
async def list_skills():
    """List all learned skills."""
    skills = await _app_ctx.procedural.list_skills()
    return [
        SkillInfo(
            name=s["name"],
            description=s["description"],
            mode=s.get("mode", "static"),
            trigger_type=s.get("trigger", {}).get("type", "manual"),
            active=s.get("active", True),
        )
        for s in skills
    ]


SNAPSHOT_DIR = Path(tempfile.gettempdir()) / "homebot_snapshots"


@app.get("/api/snapshots/{filename}")
async def get_snapshot(filename: str):
    """Serve a camera snapshot image."""
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    path = SNAPSHOT_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Snapshot not found")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/entities")
async def list_entities():
    """HA entities grouped by domain with counts."""
    domains: dict[str, list[dict]] = {}
    for eid in _app_ctx.state_cache.all_entity_ids():
        domain = eid.split(".")[0]
        entity = _app_ctx.state_cache.get(eid)
        state_val = entity.get("state", "unknown") if entity else "unknown"
        friendly = entity.get("attributes", {}).get("friendly_name", eid) if entity else eid
        domains.setdefault(domain, []).append({
            "entity_id": eid,
            "state": state_val,
            "friendly_name": friendly,
        })
    return {
        "total": len(_app_ctx.state_cache.all_entity_ids()),
        "domains": {d: {"count": len(ents), "entities": ents} for d, ents in sorted(domains.items())},
    }


def main():
    parser = argparse.ArgumentParser(description="HomeBotAI REST API")
    parser.add_argument("--port", type=int, default=8321, help="Port (default: 8321)")
    parser.add_argument("--host", default="0.0.0.0", help="Host (default: 0.0.0.0)")
    parser.add_argument("--no-ha", action="store_true", help="Skip HA WebSocket")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        level=logging.INFO if args.verbose else logging.WARNING,
    )
    logging.getLogger("homebot").setLevel(logging.INFO)

    app.state.no_ha = args.no_ha

    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
