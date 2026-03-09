#!/usr/bin/env python3
"""
HomeBotAI REST API -- lightweight HTTP interface for testing and integrations.

Usage:
    python api.py                    # default: port 8321, connect HA
    python api.py --port 9000        # custom port
    python api.py --no-ha            # skip HA WebSocket

Endpoints:
    POST /api/chat                  Send a message, get a response
    POST /api/chat/stream           Send a message, get SSE event stream
    GET  /api/chat/threads          List conversation threads
    GET  /api/chat/{id}/history     Get message history for a thread
    DELETE /api/chat/{id}/history   Clear a thread's history
    GET  /api/health                Service health and stats
    GET  /api/tools                 List registered tools
    GET  /api/skills                List / CRUD skills
    GET  /api/entities              HA entities summary by domain
    POST /api/entities/{id}/toggle  Toggle a switch/light/fan entity
    GET  /api/events                Event log with time filtering
    GET  /api/memory                Semantic memory facts
    POST /api/cameras/{id}/snapshot Request a fresh camera snapshot
    GET  /api/dashboard              Dashboard widget config
    PUT  /api/dashboard              Save dashboard config
    POST /api/dashboard/edit         AI-edit dashboard layout

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

import aiohttp
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


class SkillDetail(BaseModel):
    id: str
    name: str
    description: str
    trigger: dict
    mode: str
    ai_prompt: str
    actions: list
    notify: bool
    active: bool


class SkillCreate(BaseModel):
    id: str = Field(..., description="Unique skill identifier (slug)")
    name: str
    description: str
    trigger: dict = Field(default_factory=lambda: {"type": "manual"})
    mode: str = "static"
    ai_prompt: str = ""
    actions: list = Field(default_factory=list)
    notify: bool = False


class SkillUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    trigger: dict | None = None
    mode: str | None = None
    ai_prompt: str | None = None
    actions: list | None = None
    notify: bool | None = None


class ToggleRequest(BaseModel):
    action: str = Field(default="toggle", description="toggle, turn_on, or turn_off")


class MemoryEntry(BaseModel):
    key: str
    value: str


class DashboardEditRequest(BaseModel):
    message: str = Field(..., description="Natural language request to edit the dashboard layout")


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


@app.get("/api/chat/threads")
async def list_threads():
    """List all conversation threads with last message preview."""
    threads = await _app_ctx.episodic.list_threads()
    return {"threads": threads}


@app.get("/api/chat/{chat_id}/history")
async def get_history(chat_id: int, limit: int = 50):
    """Get message history for a conversation thread."""
    messages = await _app_ctx.episodic.get_history(chat_id, limit=limit)
    return {"chat_id": chat_id, "messages": messages}


@app.delete("/api/chat/{chat_id}/history")
async def clear_history(chat_id: int):
    """Clear all messages in a conversation thread."""
    await _app_ctx.episodic.clear(chat_id)
    return {"status": "ok", "chat_id": chat_id}


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


@app.get("/api/skills", response_model=list[SkillDetail])
async def list_skills():
    """List all learned skills with full detail."""
    skills = await _app_ctx.procedural.list_skills()
    return [SkillDetail(**s) for s in skills]


@app.post("/api/skills", response_model=SkillDetail)
async def create_skill(req: SkillCreate):
    """Create a new skill."""
    existing = await _app_ctx.procedural.get_skill(req.id)
    if existing:
        raise HTTPException(status_code=409, detail="Skill already exists")
    skill = await _app_ctx.procedural.create_skill(
        skill_id=req.id, name=req.name, description=req.description,
        trigger=req.trigger, mode=req.mode, ai_prompt=req.ai_prompt,
        actions=req.actions, notify=req.notify,
    )
    return SkillDetail(**skill)


@app.get("/api/skills/{skill_id}", response_model=SkillDetail)
async def get_skill(skill_id: str):
    """Get a single skill by ID."""
    skill = await _app_ctx.procedural.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return SkillDetail(**skill)


@app.put("/api/skills/{skill_id}", response_model=SkillDetail)
async def update_skill(skill_id: str, req: SkillUpdate):
    """Update a skill's fields."""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    skill = await _app_ctx.procedural.update_skill(skill_id, updates)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return SkillDetail(**skill)


@app.delete("/api/skills/{skill_id}")
async def delete_skill(skill_id: str):
    """Delete a skill."""
    deleted = await _app_ctx.procedural.delete_skill(skill_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Skill not found")
    return {"status": "ok"}


@app.post("/api/skills/{skill_id}/toggle")
async def toggle_skill(skill_id: str, active: bool = True):
    """Toggle a skill's active state."""
    skill = await _app_ctx.procedural.toggle_skill(skill_id, active)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    return SkillDetail(**skill)


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
        attrs = entity.get("attributes", {}) if entity else {}
        item = {
            "entity_id": eid,
            "state": state_val,
            "friendly_name": friendly,
        }
        if domain == "climate":
            item["temperature"] = attrs.get("temperature")
            item["current_temperature"] = attrs.get("current_temperature")
            item["hvac_modes"] = attrs.get("hvac_modes", [])
        elif domain == "light":
            item["brightness"] = attrs.get("brightness")
        elif domain == "media_player":
            item["media_title"] = attrs.get("media_title")
            item["media_artist"] = attrs.get("media_artist")
        elif domain == "camera":
            item["is_streaming"] = attrs.get("is_streaming", state_val == "streaming")
        domains.setdefault(domain, []).append(item)
    return {
        "total": len(_app_ctx.state_cache.all_entity_ids()),
        "domains": {d: {"count": len(ents), "entities": ents} for d, ents in sorted(domains.items())},
    }


@app.post("/api/entities/{entity_id}/toggle")
async def toggle_entity(entity_id: str, req: ToggleRequest = ToggleRequest()):
    """Toggle, turn_on, or turn_off a switch/light/fan entity via HA."""
    domain = entity_id.split(".")[0]
    allowed = {"light", "switch", "fan", "automation"}
    if domain not in allowed:
        raise HTTPException(status_code=400, detail=f"Domain '{domain}' not toggleable via this endpoint")

    action = req.action if req.action in ("toggle", "turn_on", "turn_off") else "toggle"
    url = f"{config.HA_URL}/api/services/{domain}/{action}"
    headers = {"Authorization": f"Bearer {config.HA_TOKEN}", "Content-Type": "application/json"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json={"entity_id": entity_id}) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise HTTPException(status_code=resp.status, detail=text[:300])
                return {"status": "ok", "entity_id": entity_id, "action": action}
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/api/cameras/{entity_id}/snapshot")
async def take_camera_snapshot(entity_id: str):
    """Request a fresh snapshot from a camera entity."""
    if not entity_id.startswith("camera."):
        raise HTTPException(status_code=400, detail="Not a camera entity")

    url = f"{config.HA_URL}/api/camera_proxy/{entity_id}"
    headers = {"Authorization": f"Bearer {config.HA_TOKEN}"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    raise HTTPException(status_code=resp.status, detail="Failed to get snapshot")
                image_bytes = await resp.read()
                SNAPSHOT_DIR.mkdir(exist_ok=True)
                safe_name = entity_id.replace(".", "_")
                path = SNAPSHOT_DIR / f"{safe_name}.jpg"
                path.write_bytes(image_bytes)
                return {"status": "ok", "filename": f"{safe_name}.jpg", "entity_id": entity_id}
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/api/events")
async def get_events(hours: int = 24, limit: int = 200):
    """Get event log entries."""
    events = await _app_ctx.procedural.get_event_log(hours=hours, limit=limit)
    return {"events": events, "hours": hours}


@app.get("/api/memory")
async def list_memory():
    """List all semantic memory facts."""
    facts = await _app_ctx.semantic.all_facts()
    return {"facts": [{"key": k, "value": v} for k, v in facts.items()]}


@app.post("/api/memory")
async def add_memory(entry: MemoryEntry):
    """Add or update a semantic memory fact."""
    await _app_ctx.semantic.remember(entry.key, entry.value)
    return {"status": "ok", "key": entry.key}


@app.delete("/api/memory/{key:path}")
async def delete_memory(key: str):
    """Delete a semantic memory fact."""
    await _app_ctx.semantic.delete(key)
    return {"status": "ok", "key": key}


# --- Dashboard config endpoints ---

@app.get("/api/dashboard")
async def get_dashboard():
    """Get the current dashboard widget config."""
    cfg = await _app_ctx.dashboard_config.get()
    return cfg


@app.put("/api/dashboard")
async def save_dashboard(config_body: dict):
    """Save a new dashboard widget config."""
    await _app_ctx.dashboard_config.save(config_body)
    return {"status": "ok"}


DASHBOARD_SYSTEM_PROMPT = """You are a smart-home dashboard layout editor.
You receive the CURRENT dashboard config JSON, a list of AVAILABLE entity IDs, and a user request.

RESPONSE FORMAT -- you MUST respond with exactly two lines:
Line 1: A valid JSON object with the updated (or unchanged) dashboard config. No markdown, no code fences.
Line 2: Starting with "SUMMARY:" -- a short human-friendly message (1-2 sentences). If the user asked a question, answer it here.

If the user asks a QUESTION (e.g. "what switches can I add?"), return the CURRENT config unchanged on line 1 and answer on line 2.
If the user asks for a CHANGE, return the updated config on line 1 and describe what changed on line 2.

WIDGET SCHEMA:
Each widget: {id, type, title, config, size}
Types: stat, toggle_group, sensor_grid, camera, quick_actions, weather, scene_buttons
Sizes: sm (1col), md (2col), lg (3col), full (full width)
Config by type:
- stat: {entity_id, unit?}
- toggle_group: {entities: [...]}
- sensor_grid: {entities: [...]}
- camera: {entity_id}
- quick_actions: {actions: [{label, entity_id, domain, service}]}
- weather: {entity_id}
- scene_buttons: {scenes: [{entity_id, label}]}

RULES:
- Preserve widgets the user did not ask to change.
- Use only entity IDs from the available list.
- Output compact JSON (no pretty-printing) to save tokens.
"""


@app.post("/api/dashboard/edit")
async def edit_dashboard(req: DashboardEditRequest):
    """Use AI to edit the dashboard layout based on a natural language request."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.messages import SystemMessage, HumanMessage

    current_config = await _app_ctx.dashboard_config.get()

    entities_by_domain: dict[str, list[str]] = {}
    for eid in _app_ctx.state_cache.all_entity_ids():
        domain = eid.split(".")[0]
        entities_by_domain.setdefault(domain, []).append(eid)

    user_prompt = (
        f"CURRENT CONFIG:\n{json.dumps(current_config)}\n\n"
        f"AVAILABLE ENTITIES:\n{json.dumps(entities_by_domain)}\n\n"
        f"USER REQUEST: {req.message}"
    )

    llm = ChatGoogleGenerativeAI(
        model=config.GEMINI_MODEL,
        google_api_key=config.GEMINI_API_KEY,
        temperature=0.2,
        max_output_tokens=16384,
    )

    try:
        response = await llm.ainvoke([
            SystemMessage(content=DASHBOARD_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini error: {e}")

    raw_text = response.content.strip()

    # Strip markdown code fences if present
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()

    # Split SUMMARY from JSON
    summary = ""
    if "SUMMARY:" in raw_text:
        parts = raw_text.split("SUMMARY:", 1)
        json_part = parts[0].strip()
        summary = parts[1].strip()
    else:
        json_part = raw_text

    # Try to extract JSON from the text -- find the outermost { ... }
    json_start = json_part.find("{")
    json_end = json_part.rfind("}")
    if json_start != -1 and json_end != -1:
        json_part = json_part[json_start:json_end + 1]

    try:
        new_config = json.loads(json_part)
    except json.JSONDecodeError:
        # If JSON parsing fails, return current config with the AI's text as the message
        return {
            "config": current_config,
            "message": summary or raw_text[:300],
        }

    if "widgets" not in new_config:
        return {
            "config": current_config,
            "message": summary or "Could not parse a valid dashboard config.",
        }

    await _app_ctx.dashboard_config.save(new_config)

    return {
        "config": new_config,
        "message": summary or "Dashboard updated.",
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
