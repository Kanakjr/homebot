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
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
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
    model: str | None = None


class SkillCreate(BaseModel):
    id: str = Field(..., description="Unique skill identifier (slug)")
    name: str
    description: str
    trigger: dict = Field(default_factory=lambda: {"type": "manual"})
    mode: str = "static"
    ai_prompt: str = ""
    actions: list = Field(default_factory=list)
    notify: bool = False
    model: str | None = None


class SkillUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    trigger: dict | None = None
    mode: str | None = None
    ai_prompt: str | None = None
    actions: list | None = None
    notify: bool | None = None
    model: str | None = None


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

    t0 = time.monotonic()
    from bootstrap import create_app, shutdown_app

    connect_ha = not getattr(app.state, "no_ha", False)
    _app_ctx = await create_app(connect_ha=connect_ha, build_agent=False)
    log.info("API server ready in %.1fs (agent deferred to first chat)", time.monotonic() - t0)
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

_API_KEY = os.environ.get("API_KEY", "")
_AUTH_SKIP_PREFIXES = ("/docs", "/openapi.json", "/api/snapshots/")


@app.middleware("http")
async def verify_api_key(request: Request, call_next):
    if (
        _API_KEY
        and request.method != "OPTIONS"
        and request.url.path.startswith("/api/")
        and not any(request.url.path.startswith(p) for p in _AUTH_SKIP_PREFIXES)
    ):
        if request.headers.get("X-API-Key") != _API_KEY:
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API key"})
    return await call_next(request)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Send a message and get the full response (blocking)."""
    await _app_ctx.ensure_agent()
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
    await _app_ctx.ensure_agent()

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
        tools_registered=len(_app_ctx.tool_map) if _app_ctx.tool_map else 0,
        entities_loaded=len(_app_ctx.state_cache.all_entity_ids()),
        model=config.GEMINI_MODEL,
    )


@app.get("/api/models")
async def list_models():
    """Return available LLM models (Gemini + Ollama if enabled)."""
    models = [{"id": config.GEMINI_MODEL, "provider": "gemini", "name": f"Gemini ({config.GEMINI_MODEL})"}]
    if config.OLLAMA_ENABLED:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{config.OLLAMA_URL}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for m in data.get("models", []):
                            name = m.get("name", "")
                            models.append({"id": name, "provider": "ollama", "name": name})
        except Exception:
            pass
    return {"models": models}


@app.get("/api/tools", response_model=list[ToolInfo])
async def list_tools():
    """List all registered tools."""
    await _app_ctx.ensure_agent()
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
        actions=req.actions, notify=req.notify, model=req.model,
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


@app.post("/api/skills/{skill_id}/execute")
async def execute_skill(skill_id: str):
    """Execute a skill on demand and return the result."""
    await _app_ctx.ensure_agent()
    skill = await _app_ctx.procedural.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill not found")
    if not skill.get("active"):
        raise HTTPException(status_code=400, detail="Skill is disabled")

    t0 = time.monotonic()

    try:
        if skill["mode"] == "static":
            results = []
            for action in skill.get("actions", []):
                tool_name = action.get("tool")
                params = action.get("params", {})
                if _app_ctx.tool_map.has(tool_name):
                    result = await _app_ctx.tool_map.execute(tool_name, params)
                    results.append(f"{tool_name}: {str(result)[:200]}")
                else:
                    results.append(f"{tool_name}: unknown tool")
            result_text = f"Skill '{skill['name']}' executed:\n" + "\n".join(results)
        elif skill["mode"] == "ai":
            import random
            prompt = (
                f"[SKILL EXECUTION: {skill['name']}]\n"
                "You are executing a skill RIGHT NOW. Do NOT mention that the skill "
                "already exists or suggest waiting for it. Perform the task below "
                "immediately using your tools and live state data. Produce the "
                "requested output directly.\n\n"
            )
            prompt += skill.get("ai_prompt", "")
            event_log = await _app_ctx.procedural.get_event_log(hours=24)
            if event_log:
                log_text = "\n".join(
                    f"- [{e['ts']}] {e['entity_id']}: {e['old_state']} -> {e['new_state']} ({e['event_type']})"
                    for e in event_log[-50:]
                )
                prompt += f"\n\nRecent event log:\n{log_text}"

            skill_model = skill.get("model")
            if skill_model:
                from langchain_core.messages import SystemMessage as _Sys, HumanMessage as _Hum
                import llm as _llm
                sys_prompt = await _app_ctx.agent._build_system_prompt()
                result_text, _ = await _llm.invoke_with_fallback(
                    [_Sys(content=sys_prompt), _Hum(content=prompt)],
                    model=skill_model,
                )
            else:
                ephemeral_chat_id = -random.randint(1_000_000, 9_999_999)
                agent_result = await _app_ctx.agent.run(
                    chat_id=ephemeral_chat_id,
                    user_message=prompt,
                    system_prompt_override=await _app_ctx.agent._build_system_prompt(),
                )
                result_text = agent_result.text
        else:
            result_text = f"Unknown mode for skill '{skill['name']}'"

        if skill.get("notify"):
            await _app_ctx.notifier.send(result_text)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Skill execution failed: {e}")

    elapsed = int((time.monotonic() - t0) * 1000)
    return {
        "status": "ok",
        "skill_name": skill["name"],
        "result": result_text,
        "duration_ms": elapsed,
    }


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
            item["preset_mode"] = attrs.get("preset_mode")
            item["preset_modes"] = attrs.get("preset_modes", [])
            item["fan_mode"] = attrs.get("fan_mode")
            item["fan_modes"] = attrs.get("fan_modes", [])
        elif domain == "light":
            item["brightness"] = attrs.get("brightness")
            item["color_mode"] = attrs.get("color_mode")
            item["supported_color_modes"] = attrs.get("supported_color_modes", [])
            item["color_temp_kelvin"] = attrs.get("color_temp_kelvin")
            item["min_color_temp_kelvin"] = attrs.get("min_color_temp_kelvin")
            item["max_color_temp_kelvin"] = attrs.get("max_color_temp_kelvin")
            item["rgb_color"] = attrs.get("rgb_color")
            item["hs_color"] = attrs.get("hs_color")
        elif domain == "media_player":
            item["media_title"] = attrs.get("media_title")
            item["media_artist"] = attrs.get("media_artist")
        elif domain == "weather":
            item["temperature"] = attrs.get("temperature")
            item["humidity"] = attrs.get("humidity")
            item["pressure"] = attrs.get("pressure")
            item["wind_speed"] = attrs.get("wind_speed")
            item["wind_bearing"] = attrs.get("wind_bearing")
            item["cloud_coverage"] = attrs.get("cloud_coverage")
            item["uv_index"] = attrs.get("uv_index")
            item["dew_point"] = attrs.get("dew_point")
            item["temperature_unit"] = attrs.get("temperature_unit", "°C")
            item["wind_speed_unit"] = attrs.get("wind_speed_unit", "km/h")
            item["pressure_unit"] = attrs.get("pressure_unit", "hPa")
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
    allowed = {"light", "switch", "fan", "automation", "scene"}
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


class LightControlRequest(BaseModel):
    brightness: int | None = Field(default=None, ge=0, le=255)
    color_temp_kelvin: int | None = None
    rgb_color: list[int] | None = Field(default=None, min_length=3, max_length=3)


@app.post("/api/entities/{entity_id}/light")
async def control_light(entity_id: str, req: LightControlRequest):
    """Set light brightness, color temperature, or RGB color via HA."""
    if not entity_id.startswith("light."):
        raise HTTPException(status_code=400, detail="Not a light entity")

    if req.brightness is not None and req.brightness == 0:
        url = f"{config.HA_URL}/api/services/light/turn_off"
        payload = {"entity_id": entity_id}
    else:
        url = f"{config.HA_URL}/api/services/light/turn_on"
        payload: dict = {"entity_id": entity_id}
        if req.brightness is not None:
            payload["brightness"] = req.brightness
        if req.color_temp_kelvin is not None:
            payload["color_temp_kelvin"] = req.color_temp_kelvin
        if req.rgb_color is not None:
            payload["rgb_color"] = req.rgb_color

    headers = {"Authorization": f"Bearer {config.HA_TOKEN}", "Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    raise HTTPException(status_code=resp.status, detail=text[:300])
                return {"status": "ok", "entity_id": entity_id}
    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=str(e))


class ClimateControlRequest(BaseModel):
    preset_mode: str | None = None
    fan_mode: str | None = None
    temperature: float | None = None


@app.post("/api/entities/{entity_id}/climate")
async def control_climate(entity_id: str, req: ClimateControlRequest):
    """Set climate preset mode, fan mode, or temperature via HA."""
    if not entity_id.startswith("climate."):
        raise HTTPException(status_code=400, detail="Not a climate entity")

    headers = {"Authorization": f"Bearer {config.HA_TOKEN}", "Content-Type": "application/json"}
    results = []

    try:
        async with aiohttp.ClientSession() as session:
            if req.preset_mode is not None:
                url = f"{config.HA_URL}/api/services/climate/set_preset_mode"
                async with session.post(url, headers=headers, json={
                    "entity_id": entity_id, "preset_mode": req.preset_mode,
                }) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise HTTPException(status_code=resp.status, detail=text[:300])
                    results.append("preset_mode")

            if req.fan_mode is not None:
                url = f"{config.HA_URL}/api/services/climate/set_fan_mode"
                async with session.post(url, headers=headers, json={
                    "entity_id": entity_id, "fan_mode": req.fan_mode,
                }) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise HTTPException(status_code=resp.status, detail=text[:300])
                    results.append("fan_mode")

            if req.temperature is not None:
                url = f"{config.HA_URL}/api/services/climate/set_temperature"
                async with session.post(url, headers=headers, json={
                    "entity_id": entity_id, "temperature": req.temperature,
                }) as resp:
                    if resp.status != 200:
                        text = await resp.text()
                        raise HTTPException(status_code=resp.status, detail=text[:300])
                    results.append("temperature")

    except aiohttp.ClientError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {"status": "ok", "entity_id": entity_id, "updated": results}


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


HEALTH_ENTITIES = {
    "heart_rate": "sensor.galaxy_watch8_classic_krbx_heart_rate",
    "steps": "sensor.galaxy_watch8_classic_krbx_daily_steps",
    "steps_total": "sensor.galaxy_watch8_classic_krbx_steps_sensor",
    "calories": "sensor.galaxy_watch8_classic_krbx_daily_calories",
    "distance": "sensor.galaxy_watch8_classic_krbx_daily_distance",
    "floors": "sensor.galaxy_watch8_classic_krbx_daily_floors",
    "activity": "sensor.galaxy_watch8_classic_krbx_activity_state",
    "pressure": "sensor.galaxy_watch8_classic_krbx_pressure_sensor",
    "on_body": "binary_sensor.galaxy_watch8_classic_krbx_on_body_sensor",
    "watch_battery": "sensor.galaxy_watch8_classic_krbx_battery_level",
    "watch_battery_state": "sensor.galaxy_watch8_classic_krbx_battery_state",
    "watch_charger": "sensor.galaxy_watch8_classic_krbx_charger_type",
    "pixel_activity": "sensor.pixel_9_pro_detected_activity",
    "pixel_battery": "sensor.pixel_9_pro_battery_level",
    "pixel_battery_state": "sensor.pixel_9_pro_battery_state",
    "pixel_steps": "sensor.pixel_9_pro_daily_steps",
    "pixel_distance": "sensor.pixel_9_pro_daily_distance",
    "pixel_sleep": "sensor.pixel_9_pro_sleep_duration",
    "pixel_location": "sensor.pixel_9_pro_geocoded_location",
}

HISTORY_ENTITIES = [
    "sensor.galaxy_watch8_classic_krbx_heart_rate",
    "sensor.galaxy_watch8_classic_krbx_daily_steps",
    "sensor.galaxy_watch8_classic_krbx_daily_calories",
    "sensor.galaxy_watch8_classic_krbx_pressure_sensor",
]


@app.get("/api/health/data")
async def get_health_data(hours: int = 24):
    """Health dashboard data: current readings from Watch 8 + Pixel, plus HA history."""
    current: dict[str, dict] = {}
    for key, eid in HEALTH_ENTITIES.items():
        st = _app_ctx.state_cache.get(eid)
        if st:
            current[key] = {
                "entity_id": eid,
                "state": st.get("state"),
                "unit": st.get("attributes", {}).get("unit_of_measurement", ""),
                "friendly_name": st.get("attributes", {}).get("friendly_name", eid),
                "last_changed": st.get("last_changed", ""),
            }

    history: dict[str, list] = {}
    try:
        from datetime import datetime, timedelta, timezone as tz

        start = (datetime.now(tz.utc) - timedelta(hours=hours)).isoformat()
        filter_ids = ",".join(HISTORY_ENTITIES)
        url = f"{config.HA_URL}/api/history/period/{start}?filter_entity_id={filter_ids}&minimal_response&no_attributes"
        headers = {"Authorization": f"Bearer {config.HA_TOKEN}"}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, ssl=False, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    raw = await resp.json()
                    for entity_history in raw:
                        if not entity_history:
                            continue
                        eid = entity_history[0].get("entity_id", "")
                        points = []
                        for pt in entity_history:
                            try:
                                val = float(pt["state"])
                                points.append({"ts": pt.get("last_changed", ""), "value": round(val, 2)})
                            except (ValueError, TypeError, KeyError):
                                continue
                        if points:
                            key = next((k for k, v in HEALTH_ENTITIES.items() if v == eid), eid)
                            history[key] = points
    except Exception as exc:
        log.warning("Failed to fetch HA history for health: %s", exc)

    return {"current": current, "history": history, "hours": hours}


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


# --- Device aliases endpoints ---

class DeviceAliasRequest(BaseModel):
    alias: str = Field(..., description="Human-friendly device name")
    device_type: str = Field(default="", description="Device category")
    icon: str = Field(default="", description="Icon identifier")
    is_presence: bool = Field(default=False, description="Track this device for presence automations")


@app.get("/api/devices/aliases")
async def list_device_aliases():
    aliases = await _app_ctx.procedural.get_device_aliases()
    return {"aliases": [{"mac": mac, **info} for mac, info in aliases.items()]}


@app.put("/api/devices/aliases/{mac}")
async def set_device_alias(mac: str, req: DeviceAliasRequest):
    result = await _app_ctx.procedural.set_device_alias(
        mac, req.alias, req.device_type, req.icon, req.is_presence,
    )
    return result


@app.delete("/api/devices/aliases/{mac}")
async def delete_device_alias(mac: str):
    deleted = await _app_ctx.procedural.delete_device_alias(mac)
    if not deleted:
        raise HTTPException(status_code=404, detail="Alias not found")
    return {"status": "ok", "mac": mac}


# --- Notification rules endpoints ---

class NotificationRuleUpdate(BaseModel):
    enabled: bool | None = None
    config: dict | None = None
    cooldown_seconds: int | None = None


@app.get("/api/notifications/rules")
async def list_notification_rules():
    rules = await _app_ctx.procedural.get_notification_rules()
    return {"rules": rules}


@app.put("/api/notifications/rules/{rule_id}")
async def update_notification_rule(rule_id: str, req: NotificationRuleUpdate):
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    result = await _app_ctx.procedural.update_notification_rule(rule_id, updates)
    if not result:
        raise HTTPException(status_code=404, detail="Rule not found")
    return result


# --- Analytics endpoints ---

@app.get("/api/analytics")
async def get_analytics(metric: str = "activity", hours: int = 168):
    """Aggregated analytics: energy, presence, network, activity.

    For energy/network metrics beyond 720h (30d) HA long-term statistics
    are used instead of the local event_log, returning daily aggregates.
    """
    valid = {"energy", "presence", "network", "activity"}
    if metric not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid metric. Must be one of: {valid}")

    if metric in ("energy", "network") and hours > 720:
        from ha_history import fetch_ha_statistics

        if metric == "energy":
            sensors = _app_ctx.state_cache.get_energy_sensors()
            eids = [s["entity_id"] for s in sensors if s["device_class"] in ("power", "energy")]
        else:
            net = _app_ctx.state_cache.get_network_data()
            eids = [s["entity_id"] for s in net["bandwidth_sensors"]]

        points = await fetch_ha_statistics(eids, hours=hours, period="day")

        from collections import defaultdict
        by_day: dict[str, dict] = defaultdict(lambda: defaultdict(lambda: {"sum": 0.0, "count": 0, "max": 0.0}))
        for p in points:
            day = p["ts"][:10] if len(p["ts"]) >= 10 else p["ts"]
            eid = p["entity_id"]
            bucket = by_day[day][eid]
            bucket["sum"] += p["value"]
            bucket["count"] += 1
            bucket["max"] = max(bucket["max"], p["value"])

        data = []
        for day in sorted(by_day):
            for eid, b in by_day[day].items():
                avg = round(b["sum"] / b["count"], 2) if b["count"] else 0
                data.append({
                    "day": day,
                    "entity_id": eid,
                    "avg": avg,
                    "max": round(b["max"], 2),
                    "samples": b["count"],
                })

        return {"metric": metric, "data": data, "hours": hours}

    return await _app_ctx.procedural.get_analytics(metric=metric, hours=hours)


# --- Reports endpoint ---

@app.get("/api/reports/summary")
async def get_reports_summary(hours: int = 720):
    """Long-term report with daily aggregates, trends, and cost estimates.

    Pulls energy and network data from HA long-term statistics, plus
    activity/presence from the local event_log (capped at 30 days).
    """
    from collections import defaultdict
    from datetime import datetime, timedelta, timezone as tz
    from ha_history import fetch_ha_statistics

    energy_sensors = _app_ctx.state_cache.get_energy_sensors()
    power_eids = [s["entity_id"] for s in energy_sensors if s["device_class"] == "power"]
    energy_eids = [s["entity_id"] for s in energy_sensors if s["device_class"] == "energy"]

    net = _app_ctx.state_cache.get_network_data()
    bw_eids = [s["entity_id"] for s in net["bandwidth_sensors"]]

    energy_points = await fetch_ha_statistics(
        power_eids + energy_eids, hours=hours, period="day",
    )
    network_points = await fetch_ha_statistics(
        bw_eids, hours=hours, period="day",
    )

    local_hours = min(hours, 720)
    activity_data = (await _app_ctx.procedural.get_analytics(
        metric="activity", hours=local_hours,
    )).get("data", [])

    def _daily_agg(points: list[dict]) -> list[dict]:
        buckets: dict[str, dict] = defaultdict(lambda: defaultdict(
            lambda: {"sum": 0.0, "count": 0, "max": 0.0},
        ))
        for p in points:
            day = p["ts"][:10] if len(p.get("ts", "")) >= 10 else p.get("ts", "")
            eid = p["entity_id"]
            b = buckets[day][eid]
            b["sum"] += p["value"]
            b["count"] += 1
            b["max"] = max(b["max"], p["value"])
        rows = []
        for day in sorted(buckets):
            for eid, b in buckets[day].items():
                avg = round(b["sum"] / b["count"], 2) if b["count"] else 0
                rows.append({"day": day, "entity_id": eid, "avg": avg, "max": round(b["max"], 2)})
        return rows

    energy_daily = _daily_agg(energy_points)
    network_daily = _daily_agg(network_points)

    def _entity_summary(daily: list[dict]) -> list[dict]:
        totals: dict[str, dict] = defaultdict(lambda: {"sum": 0.0, "count": 0, "peak": 0.0})
        for row in daily:
            t = totals[row["entity_id"]]
            t["sum"] += row["avg"]
            t["count"] += 1
            t["peak"] = max(t["peak"], row["max"])
        result = []
        for eid, t in totals.items():
            result.append({
                "entity_id": eid,
                "avg": round(t["sum"] / t["count"], 2) if t["count"] else 0,
                "peak": round(t["peak"], 2),
                "days": t["count"],
            })
        result.sort(key=lambda x: x["avg"], reverse=True)
        return result

    energy_summary = _entity_summary(energy_daily)
    network_summary = _entity_summary(network_daily)

    half = hours // 2
    cutoff = (datetime.now(tz.utc) - timedelta(hours=half)).strftime("%Y-%m-%d")
    recent = [r for r in energy_daily if r["day"] >= cutoff]
    older = [r for r in energy_daily if r["day"] < cutoff]

    def _avg_power(rows: list[dict]) -> float:
        vals = [r["avg"] for r in rows]
        return round(sum(vals) / len(vals), 2) if vals else 0.0

    recent_avg = _avg_power(recent)
    older_avg = _avg_power(older)
    trend_pct = round((recent_avg - older_avg) / older_avg * 100, 1) if older_avg else 0.0

    total_kwh = sum(s["state"] for s in energy_sensors if s["device_class"] == "energy")
    total_cost = round(total_kwh * config.ENERGY_RATE, 2)
    peak_power = max((s["peak"] for s in energy_summary), default=0)

    return {
        "hours": hours,
        "energy": {
            "daily": energy_daily,
            "top_consumers": energy_summary[:10],
            "total_kwh": round(total_kwh, 2),
            "estimated_cost": total_cost,
            "peak_power_w": round(peak_power, 2),
            "rate": config.ENERGY_RATE,
            "currency": config.ENERGY_CURRENCY,
        },
        "network": {
            "daily": network_daily,
            "top_entities": network_summary[:10],
        },
        "activity": {
            "data": activity_data,
        },
        "trend": {
            "recent_avg_w": recent_avg,
            "previous_avg_w": older_avg,
            "change_pct": trend_pct,
        },
    }


# --- Dashboard config endpoints ---

SUMMARY_SYSTEM_PROMPT = (
    "You are a smart home assistant greeting the homeowner Kanak. "
    "Write a warm, conversational 3-5 sentence welcome summary. Include:\n"
    "- Current weather conditions (temperature, description)\n"
    "- Room environment (temperature, humidity, air quality / PM2.5)\n"
    "- Notable device states (which lights/switches are on, any doors open)\n"
    "- Network status if any devices are offline\n"
    "- Energy usage if notable (high power draw)\n"
    "- Who is home (presence detection)\n"
    "Be natural and conversational like a helpful butler. "
    "Do not use markdown, bullet points, or formatting. "
    "Do not use emojis. Keep it between 80-150 words. "
    "You MUST complete your response. Do not stop mid-sentence."
)


@app.get("/api/dashboard/summary")
async def get_dashboard_summary(regenerate: bool = False):
    """AI-generated dashboard welcome summary with smart caching."""
    if not regenerate:
        cached = await _app_ctx.dashboard_config.get_summary()
        if cached:
            return cached

    from langchain_core.messages import SystemMessage, HumanMessage
    from llm import invoke_with_fallback

    state_text = _app_ctx.state_cache.summarize(
        context_hint="weather temperature humidity power energy battery network bandwidth presence",
    )

    messages = [
        SystemMessage(content=SUMMARY_SYSTEM_PROMPT),
        HumanMessage(content=f"Current home state:\n{state_text}"),
    ]

    try:
        summary_text, provider = await invoke_with_fallback(
            messages,
            prefer_local=not regenerate,
            temperature=0.7,
            max_output_tokens=2048,
        )
    except Exception as e:
        log.warning("Summary generation failed: %s", e)
        summary_text, provider = "Welcome home. Everything is running smoothly.", "fallback"

    await _app_ctx.dashboard_config.save_summary(summary_text, provider)
    return await _app_ctx.dashboard_config.get_summary() or {
        "summary": summary_text,
        "generated_at": "",
        "provider": provider,
    }


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
Types: stat, toggle_group, sensor_grid, camera, quick_actions, weather, scene_buttons, weather_card, gauge, light_control, climate_control, printer, air_purifier, presence, power_chart, bandwidth_chart
Sizes: sm (1col), md (2col), lg (3col), full (full width)
Config by type:
- stat: {entity_id, unit?}
- toggle_group: {entities: [...]}
- sensor_grid: {entities: [...]}
- camera: {entity_id}
- quick_actions: {actions: [{label, entity_id, domain, service}]}
- weather: {entity_id}
- weather_card: {entity_id}
- scene_buttons: {scenes: [{entity_id, label}]}
- gauge: {entity_id, min, max, unit, thresholds: {warn, critical}}
- light_control: {entities: [...]}
- climate_control: {entity_id}
- printer: {camera_entity, status_entity, progress_entity, nozzle_temp_entity, nozzle_target_entity, bed_temp_entity, bed_target_entity, remaining_time_entity, current_layer_entity, total_layers_entity, weight_entity, filament_entity?, online_entity?}
- air_purifier: {fan_entity, pm25_entity, temperature_entity, humidity_entity, filter_life_entity, motor_speed_entity, climate_entity?}
- room_environment: {temperature_entity, humidity_entity, temp_thresholds?, humidity_thresholds?}
- health: {heart_rate_entity, steps_entity, activity_entity, sleep_entity?, battery_entity?, daily_distance_entity?, daily_floors_entity?, daily_calories_entity?, pressure_entity?, on_body_entity?}
- presence: {entities: [...]}  (person.* or device_tracker.* entities, shows home/away pills)
- power_chart: {hours?, entity_filter?}  (mini sparkline of power usage over time)
- bandwidth_chart: {hours?}  (mini chart of network download/upload speeds)
- smart_plug: {switch_entity, power_entity, today_entity, month_entity, voltage_entity, current_entity, overheated_entity?, overloaded_entity?}

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


WIDGET_BUILDER_SYSTEM_PROMPT = """You are a smart-home widget builder that generates json-render UI specs.

Given a set of entity IDs with their current states and a user description, generate a json-render spec
that creates an interactive widget. The spec MUST be a valid JSON object with:
- "root": string ID of the root element
- "elements": object mapping element IDs to component definitions

Each element has: "type" (component name), "props" (object), "children" (array of child IDs).

AVAILABLE COMPONENTS:

Layout (have children):
- Card: { title?: string, padding?: "sm"|"md"|"lg" }
- Stack: { direction?: "vertical"|"horizontal", gap?: "sm"|"md"|"lg" }
- Grid: { columns?: number, gap?: "sm"|"md"|"lg" }

Device controls (no children):
- DeviceToggle: { entity_id: string, label?: string } -- on/off toggle
- LightControl: { entity_id: string, label?: string } -- brightness slider + toggle
- ClimateControl: { entity_id: string, label?: string } -- preset modes + toggle

Display (no children):
- StatCard: { label: string, value: string, unit?: string } -- key metric
- SensorReading: { entity_id: string, label?: string } -- live sensor value

Actions (no children):
- ActionButton: { label: string, variant?: "primary"|"secondary"|"ghost", action_type: string, action_params?: object }
  action_type values: "toggle_entity", "set_light", "set_climate", "activate_scene"

RULES:
- Use only entity IDs from the provided list.
- Choose appropriate components based on entity domains (light.* -> LightControl, switch.*/fan.* -> DeviceToggle, sensor.* -> SensorReading, climate.* -> ClimateControl).
- Wrap everything in a root Card or Stack.
- Keep specs concise -- prefer 3-8 elements total.
- RESPOND WITH ONLY the JSON spec object. No markdown, no code fences, no explanation.
"""


class GenerateWidgetRequest(BaseModel):
    entity_ids: list[str]
    description: str
    size: str = "md"


@app.post("/api/dashboard/generate-widget")
async def generate_widget(req: GenerateWidgetRequest):
    """Generate a json-render UI spec for a custom dashboard widget."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.messages import SystemMessage, HumanMessage

    entities_info: list[dict] = []
    for eid in req.entity_ids:
        state = _app_ctx.state_cache.get(eid)
        if state:
            attrs = state.get("attributes", {})
            entities_info.append({
                "entity_id": eid,
                "state": state.get("state", "unknown"),
                "friendly_name": attrs.get("friendly_name", eid),
                "domain": eid.split(".")[0],
            })
        else:
            entities_info.append({
                "entity_id": eid,
                "state": "unknown",
                "friendly_name": eid,
                "domain": eid.split(".")[0],
            })

    user_prompt = (
        f"ENTITIES:\n{json.dumps(entities_info, indent=2)}\n\n"
        f"WIDGET SIZE: {req.size}\n\n"
        f"USER REQUEST: {req.description}"
    )

    llm = ChatGoogleGenerativeAI(
        model=config.GEMINI_MODEL,
        google_api_key=config.GEMINI_API_KEY,
        temperature=0.7,
        max_output_tokens=4096,
    )

    try:
        response = await llm.ainvoke([
            SystemMessage(content=WIDGET_BUILDER_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini error: {e}")

    raw_text = response.content.strip()

    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()

    json_start = raw_text.find("{")
    json_end = raw_text.rfind("}")
    if json_start != -1 and json_end != -1:
        raw_text = raw_text[json_start:json_end + 1]

    try:
        spec = json.loads(raw_text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="Failed to parse generated widget spec.")

    if "root" not in spec or "elements" not in spec:
        raise HTTPException(status_code=502, detail="Generated spec missing root or elements.")

    return {"spec": spec, "summary": "Widget generated successfully."}


WIDGET_SUGGEST_SYSTEM_PROMPT = """You are a smart-home dashboard assistant. Given a list of Home Assistant entities (with their friendly names, domains, and current states), suggest a concise widget title and a short description of what the widget should display.

RULES:
- The title should be 2-4 words, describing the group (e.g. "Bedroom Lights", "Living Room Climate", "Kitchen Sensors").
- The description should be 1-2 sentences telling the AI widget builder what controls and readings to include.
- Respond with ONLY a JSON object: {"title": "...", "description": "..."}
- No markdown, no code fences, no extra text.
"""


class SuggestWidgetRequest(BaseModel):
    entity_ids: list[str]


@app.post("/api/dashboard/suggest-widget")
async def suggest_widget(req: SuggestWidgetRequest):
    """Suggest a widget title and description based on selected entities."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.messages import SystemMessage, HumanMessage

    entities_info: list[dict] = []
    for eid in req.entity_ids:
        state = _app_ctx.state_cache.get(eid)
        if state:
            attrs = state.get("attributes", {})
            entities_info.append({
                "entity_id": eid,
                "state": state.get("state", "unknown"),
                "friendly_name": attrs.get("friendly_name", eid),
                "domain": eid.split(".")[0],
            })
        else:
            entities_info.append({
                "entity_id": eid,
                "state": "unknown",
                "friendly_name": eid,
                "domain": eid.split(".")[0],
            })

    llm = ChatGoogleGenerativeAI(
        model=config.GEMINI_MODEL,
        google_api_key=config.GEMINI_API_KEY,
        temperature=0.7,
        max_output_tokens=256,
    )

    try:
        response = await llm.ainvoke([
            SystemMessage(content=WIDGET_SUGGEST_SYSTEM_PROMPT),
            HumanMessage(content=f"ENTITIES:\n{json.dumps(entities_info, indent=2)}"),
        ])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Gemini error: {e}")

    raw_text = response.content.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()

    json_start = raw_text.find("{")
    json_end = raw_text.rfind("}")
    if json_start != -1 and json_end != -1:
        raw_text = raw_text[json_start:json_end + 1]

    try:
        result = json.loads(raw_text)
    except json.JSONDecodeError:
        raise HTTPException(status_code=502, detail="Failed to parse suggestion.")

    return {
        "title": result.get("title", "Custom Widget"),
        "description": result.get("description", ""),
    }


@app.get("/api/network")
async def get_network(hours: int = 24):
    """Network status: Deco mesh nodes, connected clients, bandwidth sensors + history.

    For ranges <= 168h (7d) history comes from the local event_log.
    For longer ranges HA Recorder long-term statistics are used.
    """
    from ha_history import fetch_ha_statistics

    aliases = await _app_ctx.procedural.get_device_aliases()
    network = _app_ctx.state_cache.get_network_data(aliases=aliases)

    bw_eids = {s["entity_id"] for s in network["bandwidth_sensors"]}

    if hours <= 168:
        history = await _app_ctx.procedural.get_energy_history(hours=hours)
        bw_history = [h for h in history if h["entity_id"] in bw_eids]
    else:
        bw_history = await fetch_ha_statistics(list(bw_eids), hours=hours)

    return {
        **network,
        "bandwidth_history": bw_history,
        "hours": hours,
    }


@app.get("/api/energy")
async def get_energy(hours: int = 24):
    """Current energy sensors + historical state change data + cost.

    For ranges <= 168h (7d) history comes from the local event_log.
    For longer ranges HA Recorder long-term statistics are used.
    """
    from ha_history import fetch_ha_statistics

    current = _app_ctx.state_cache.get_energy_sensors()
    energy_eids = {s["entity_id"] for s in current if s["device_class"] in ("power", "energy")}

    if hours <= 168:
        history = await _app_ctx.procedural.get_energy_history(hours=hours)
        filtered_history = [h for h in history if h["entity_id"] in energy_eids]
    else:
        filtered_history = await fetch_ha_statistics(
            list(energy_eids), hours=hours,
        )

    total_kwh = sum(s["state"] for s in current if s["device_class"] == "energy")
    total_cost = round(total_kwh * config.ENERGY_RATE, 2)

    return {
        "current": current,
        "history": filtered_history,
        "hours": hours,
        "cost": {
            "total": total_cost,
            "rate": config.ENERGY_RATE,
            "currency": config.ENERGY_CURRENCY,
        },
    }


# ---- Scenes ----

class SceneCreateRequest(BaseModel):
    name: str
    icon: str = "scene"
    entity_ids: list[str]


@app.get("/api/scenes")
async def list_scenes():
    """List all saved scenes."""
    scenes = await _app_ctx.procedural.get_scenes()
    return {"scenes": scenes}


@app.post("/api/scenes")
async def create_scene(req: SceneCreateRequest):
    """Snapshot current state of given entities and save as a scene."""
    entities = []
    for eid in req.entity_ids:
        entity = _app_ctx.state_cache.get(eid)
        if not entity:
            continue
        attrs = entity.get("attributes", {})
        domain = eid.split(".")[0]
        saved_attrs: dict = {}
        if domain == "light":
            for key in ("brightness", "color_temp_kelvin", "rgb_color", "hs_color", "color_mode"):
                if attrs.get(key) is not None:
                    saved_attrs[key] = attrs[key]
        elif domain == "climate":
            for key in ("temperature", "preset_mode", "fan_mode", "hvac_mode"):
                if attrs.get(key) is not None:
                    saved_attrs[key] = attrs[key]
        elif domain == "fan":
            for key in ("preset_mode", "percentage"):
                if attrs.get(key) is not None:
                    saved_attrs[key] = attrs[key]
        entities.append({
            "entity_id": eid,
            "state": entity.get("state", "unknown"),
            "attributes": saved_attrs,
        })

    if not entities:
        raise HTTPException(status_code=400, detail="No valid entities found in state cache")

    scene_id = req.name.lower().replace(" ", "_").replace("-", "_")
    scene_id = "".join(c for c in scene_id if c.isalnum() or c == "_")

    scene = await _app_ctx.procedural.create_scene(scene_id, req.name, entities, req.icon)
    return scene


@app.post("/api/scenes/{scene_id}/activate")
async def activate_scene(scene_id: str):
    """Restore all entity states saved in a scene."""
    scene = await _app_ctx.procedural.get_scene(scene_id)
    if not scene:
        raise HTTPException(status_code=404, detail="Scene not found")

    headers = {"Authorization": f"Bearer {config.HA_TOKEN}", "Content-Type": "application/json"}
    restored = 0

    async with aiohttp.ClientSession() as session:
        for entry in scene["entities"]:
            eid = entry["entity_id"]
            state = entry["state"]
            attrs = entry.get("attributes", {})
            domain = eid.split(".")[0]

            if domain in ("light", "switch", "fan"):
                service = "turn_on" if state == "on" else "turn_off"
                payload: dict = {"entity_id": eid}
                if service == "turn_on" and domain == "light":
                    for key in ("brightness", "color_temp_kelvin", "rgb_color"):
                        if key in attrs:
                            payload[key] = attrs[key]
                if service == "turn_on" and domain == "fan" and "preset_mode" in attrs:
                    payload["preset_mode"] = attrs["preset_mode"]
                url = f"{config.HA_URL}/api/services/{domain}/{service}"
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        restored += 1

            elif domain == "climate":
                if "preset_mode" in attrs:
                    url = f"{config.HA_URL}/api/services/climate/set_preset_mode"
                    async with session.post(url, headers=headers, json={"entity_id": eid, "preset_mode": attrs["preset_mode"]}) as resp:
                        if resp.status == 200:
                            restored += 1
                if "temperature" in attrs:
                    url = f"{config.HA_URL}/api/services/climate/set_temperature"
                    async with session.post(url, headers=headers, json={"entity_id": eid, "temperature": attrs["temperature"]}) as resp:
                        pass

            elif domain == "scene":
                url = f"{config.HA_URL}/api/services/scene/turn_on"
                async with session.post(url, headers=headers, json={"entity_id": eid}) as resp:
                    if resp.status == 200:
                        restored += 1

    return {"status": "ok", "scene": scene["name"], "restored": restored}


@app.delete("/api/scenes/{scene_id}")
async def delete_scene(scene_id: str):
    """Delete a saved scene."""
    deleted = await _app_ctx.procedural.delete_scene(scene_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Scene not found")
    return {"status": "ok", "deleted": scene_id}


# ---- Floorplan config ----

DEFAULT_FLOORPLAN_CONFIG = {
    "devices": [
        {"svg_id": "light_bed", "entity_id": "light.bedside", "type": "light", "label": "Bedroom Light"},
        {"svg_id": "light_foyer", "entity_id": "light.foyer", "type": "light", "label": "Foyer Light"},
        {"svg_id": "light_lamp", "entity_id": "light.desk_lamp", "type": "light", "label": "Desk Lamp"},
        {"svg_id": "plug_desk", "entity_id": "switch.desk", "type": "switch", "label": "Desk Plug"},
        {"svg_id": "plug_printer", "entity_id": "switch.workstation", "type": "switch", "label": "Printer Plug"},
        {"svg_id": "router_hallway", "entity_id": "device_tracker.hallway_deco", "type": "device_tracker", "label": "Hallway Router"},
        {"svg_id": "router_bedroom", "entity_id": "device_tracker.bedroom_deco", "type": "device_tracker", "label": "Bedroom Router"},
        {"svg_id": "camera_living", "entity_id": "camera.a1_03919d550407275_camera", "type": "camera", "label": "3D Printer Camera"},
        {"svg_id": "device_air_purifier", "entity_id": "fan.xiaomi_smart_air_purifier_4", "type": "fan", "label": "Air Purifier"},
        {"svg_id": "device_3d_printer", "entity_id": "sensor.a1_03919d550407275_print_status", "type": "sensor", "label": "3D Printer"},
        {"svg_id": "sensor_foyer", "entity_id": "sensor.sensor_temperature", "type": "sensor", "label": "Foyer Sensor"},
    ]
}


@app.get("/api/floorplan/config")
async def get_floorplan_config():
    """Get the SVG-to-entity mapping for the floorplan."""
    cfg = await _app_ctx.procedural.get_floorplan_config()
    return cfg or DEFAULT_FLOORPLAN_CONFIG


@app.put("/api/floorplan/config")
async def save_floorplan_config(req: dict):
    """Save the SVG-to-entity mapping for the floorplan."""
    await _app_ctx.procedural.save_floorplan_config(req)
    return {"status": "ok"}


# ---- Media service endpoints ----

class AddTorrentRequest(BaseModel):
    url: str = Field(..., description="Torrent URL or magnet link")


class TorrentActionRequest(BaseModel):
    action: str = Field(..., description="pause or resume")


class AddSeriesRequest(BaseModel):
    tvdb_id: int
    quality_profile_id: int = 1
    root_folder_path: str = "/data/tv"


class AddMovieRequest(BaseModel):
    tmdb_id: int
    quality_profile_id: int = 1
    root_folder_path: str = "/data/movies"


class MediaRequestCreate(BaseModel):
    media_id: int
    media_type: str = Field(..., description="movie or tv")


async def _transmission_rpc(method: str, arguments: dict | None = None) -> dict:
    """Direct Transmission RPC call for media endpoints."""
    rpc_url = f"{config.TRANSMISSION_URL}/transmission/rpc"
    headers = {"Content-Type": "application/json"}
    payload = {"method": method}
    if arguments:
        payload["arguments"] = arguments
    async with aiohttp.ClientSession() as session:
        async with session.post(rpc_url, headers=headers, json=payload) as resp:
            if resp.status == 409:
                headers["X-Transmission-Session-Id"] = resp.headers.get("X-Transmission-Session-Id", "")
                async with session.post(rpc_url, headers=headers, json=payload) as resp2:
                    return await resp2.json() if resp2.status == 200 else {}
            return await resp.json() if resp.status == 200 else {}


def _torrent_status(status: int) -> str:
    return {0: "stopped", 1: "queued_verify", 2: "verifying", 3: "queued_download",
            4: "downloading", 5: "queued_seed", 6: "seeding"}.get(status, "unknown")


@app.get("/api/media/overview")
async def media_overview():
    """Aggregated media overview: sessions, downloads, queue counts, requests."""
    results: dict = {
        "sessions": {"count": 0, "items": []},
        "downloads": {"count": 0, "active": 0, "download_speed": 0, "upload_speed": 0},
        "sonarr_queue": 0,
        "radarr_queue": 0,
        "requests_pending": 0,
    }

    async def fetch_sessions():
        try:
            headers = {"X-Emby-Token": config.JELLYFIN_API_KEY}
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{config.JELLYFIN_URL}/Sessions", headers=headers) as resp:
                    if resp.status == 200:
                        sessions = await resp.json()
                        items = []
                        for sess in sessions:
                            now_playing = sess.get("NowPlayingItem")
                            if now_playing:
                                play_state = sess.get("PlayState", {})
                                items.append({
                                    "device": sess.get("DeviceName"),
                                    "client": sess.get("Client"),
                                    "user": sess.get("UserName"),
                                    "playing": now_playing.get("Name"),
                                    "type": now_playing.get("Type"),
                                    "series": now_playing.get("SeriesName"),
                                    "season": now_playing.get("ParentIndexNumber"),
                                    "episode": now_playing.get("IndexNumber"),
                                    "paused": play_state.get("IsPaused", False),
                                })
                        results["sessions"] = {"count": len(items), "items": items}
        except Exception as e:
            log.warning("media overview: jellyfin sessions failed: %s", e)

    async def fetch_downloads():
        try:
            data = await _transmission_rpc("torrent-get", {
                "fields": ["id", "name", "status", "percentDone", "rateDownload",
                           "rateUpload", "eta", "totalSize", "sizeWhenDone"]
            })
            torrents = data.get("arguments", {}).get("torrents", [])
            active = [t for t in torrents if t.get("status") in (3, 4)]
            total_down = sum(t.get("rateDownload", 0) for t in torrents)
            total_up = sum(t.get("rateUpload", 0) for t in torrents)
            results["downloads"] = {
                "count": len(torrents),
                "active": len(active),
                "download_speed": total_down,
                "upload_speed": total_up,
            }
        except Exception as e:
            log.warning("media overview: transmission failed: %s", e)

    async def fetch_sonarr_queue():
        try:
            headers = {"X-Api-Key": config.SONARR_API_KEY}
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{config.SONARR_URL}/api/v3/queue", headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results["sonarr_queue"] = len(data.get("records", []))
        except Exception as e:
            log.warning("media overview: sonarr queue failed: %s", e)

    async def fetch_radarr_queue():
        try:
            headers = {"X-Api-Key": config.RADARR_API_KEY}
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{config.RADARR_URL}/api/v3/queue", headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results["radarr_queue"] = len(data.get("records", []))
        except Exception as e:
            log.warning("media overview: radarr queue failed: %s", e)

    async def fetch_requests():
        try:
            headers = {"X-Api-Key": config.JELLYSEERR_API_KEY}
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{config.JELLYSEERR_URL}/api/v1/request/count", headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        results["requests_pending"] = data.get("pending", 0)
        except Exception as e:
            log.warning("media overview: jellyseerr requests failed: %s", e)

    await asyncio.gather(
        fetch_sessions(), fetch_downloads(),
        fetch_sonarr_queue(), fetch_radarr_queue(), fetch_requests(),
    )
    return results


@app.get("/api/media/search")
async def media_search(q: str = "", type: str = ""):
    """Universal search across Jellyseerr, Prowlarr, and Jellyfin."""
    if not q:
        raise HTTPException(status_code=400, detail="Query parameter 'q' is required")

    search_types = {t.strip() for t in type.split(",") if t.strip()} if type else set()
    results: dict = {"jellyseerr": [], "prowlarr": [], "jellyfin": []}

    async def search_jellyseerr():
        if search_types and "torrent" in search_types:
            return
        try:
            from urllib.parse import quote
            headers = {"X-Api-Key": config.JELLYSEERR_API_KEY}
            url = f"{config.JELLYSEERR_URL}/api/v1/search?query={quote(q)}&page=1&language=en"
            async with aiohttp.ClientSession() as s:
                async with s.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for r in data.get("results", [])[:10]:
                            media_info = r.get("mediaInfo") or {}
                            results["jellyseerr"].append({
                                "id": r.get("id"),
                                "title": r.get("title") or r.get("name"),
                                "media_type": r.get("mediaType"),
                                "year": (r.get("releaseDate") or r.get("firstAirDate") or "")[:4],
                                "overview": (r.get("overview") or "")[:200],
                                "poster_path": r.get("posterPath"),
                                "status": media_info.get("status") if media_info else "not_requested",
                            })
        except Exception as e:
            log.warning("media search: jellyseerr failed: %s", e)

    async def search_prowlarr():
        if search_types and not search_types.intersection({"torrent", "all"}):
            return
        try:
            headers = {"X-Api-Key": config.PROWLARR_API_KEY}
            params: dict = {"query": q, "type": "search"}
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.get(f"{config.PROWLARR_URL}/api/v1/search", headers=headers, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for r in data[:15]:
                            download_url = r.get("downloadUrl", "")
                            guid = r.get("guid", "")
                            if not download_url and guid.startswith("magnet:"):
                                download_url = guid
                            results["prowlarr"].append({
                                "title": r.get("title"),
                                "indexer": r.get("indexer"),
                                "size_mb": round(r.get("size", 0) / 1024 / 1024),
                                "seeders": r.get("seeders"),
                                "leechers": r.get("leechers"),
                                "download_url": download_url,
                                "categories": [c.get("name") for c in r.get("categories", [])],
                            })
        except Exception as e:
            log.warning("media search: prowlarr failed: %s", e)

    async def search_jellyfin():
        if search_types and "torrent" in search_types:
            return
        try:
            headers = {"X-Emby-Token": config.JELLYFIN_API_KEY}
            params = {"searchTerm": q, "Recursive": "true",
                      "Fields": "Overview,Genres,RunTimeTicks,ProductionYear", "Limit": "10"}
            async with aiohttp.ClientSession() as s:
                async with s.get(f"{config.JELLYFIN_URL}/Items", headers=headers, params=params) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for it in data.get("Items", []):
                            ticks = it.get("RunTimeTicks")
                            duration = ""
                            if ticks:
                                secs = ticks // 10_000_000
                                h, rem = divmod(secs, 3600)
                                m, _ = divmod(rem, 60)
                                duration = f"{h}h{m:02d}m" if h else f"{m}m"
                            results["jellyfin"].append({
                                "id": it.get("Id"),
                                "name": it.get("Name"),
                                "type": it.get("Type"),
                                "year": it.get("ProductionYear"),
                                "duration": duration,
                                "genres": it.get("Genres", [])[:3],
                                "overview": (it.get("Overview") or "")[:200],
                            })
        except Exception as e:
            log.warning("media search: jellyfin failed: %s", e)

    await asyncio.gather(search_jellyseerr(), search_prowlarr(), search_jellyfin())
    return results


@app.get("/api/media/downloads")
async def media_downloads():
    """List all Transmission torrents with progress and speeds."""
    data = await _transmission_rpc("torrent-get", {
        "fields": ["id", "name", "status", "percentDone", "rateDownload",
                   "rateUpload", "eta", "totalSize", "sizeWhenDone",
                   "uploadedEver", "downloadedEver", "addedDate"]
    })
    torrents = data.get("arguments", {}).get("torrents", [])
    items = []
    for t in torrents:
        items.append({
            "id": t["id"],
            "name": t["name"],
            "status": _torrent_status(t.get("status", -1)),
            "progress": round(t.get("percentDone", 0) * 100, 1),
            "download_speed": t.get("rateDownload", 0),
            "upload_speed": t.get("rateUpload", 0),
            "eta": t.get("eta", -1),
            "size": t.get("sizeWhenDone", 0),
            "downloaded": t.get("downloadedEver", 0),
            "uploaded": t.get("uploadedEver", 0),
            "added": t.get("addedDate", 0),
        })
    return {"torrents": items, "count": len(items)}


@app.post("/api/media/downloads")
async def media_add_download(req: AddTorrentRequest):
    """Add a torrent by URL or magnet link."""
    result = await _transmission_rpc("torrent-add", {"filename": req.url})
    added = result.get("arguments", {}).get("torrent-added")
    if added:
        return {"status": "added", "name": added.get("name"), "id": added.get("id")}
    dup = result.get("arguments", {}).get("torrent-duplicate")
    if dup:
        return {"status": "duplicate", "name": dup.get("name")}
    raise HTTPException(status_code=400, detail="Failed to add torrent")


@app.post("/api/media/downloads/{torrent_id}/action")
async def media_torrent_action(torrent_id: int, req: TorrentActionRequest):
    """Pause or resume a torrent."""
    method = "torrent-stop" if req.action == "pause" else "torrent-start"
    result = await _transmission_rpc(method, {"ids": [torrent_id]})
    return {"status": "ok", "action": req.action, "torrent_id": torrent_id,
            "result": result.get("result", "unknown")}


@app.get("/api/media/tv")
async def media_tv():
    """Sonarr: series list + download queue + upcoming calendar."""
    headers = {"X-Api-Key": config.SONARR_API_KEY}
    result: dict = {"series": [], "queue": [], "calendar": []}

    async with aiohttp.ClientSession() as s:
        async with s.get(f"{config.SONARR_URL}/api/v3/series", headers=headers) as resp:
            if resp.status == 200:
                raw = await resp.json()
                for show in raw:
                    stats = show.get("statistics", {})
                    result["series"].append({
                        "id": show.get("id"),
                        "title": show.get("title"),
                        "year": show.get("year"),
                        "status": show.get("status"),
                        "monitored": show.get("monitored", False),
                        "seasons": show.get("seasonCount", 0),
                        "episodes_on_disk": stats.get("episodeFileCount", 0),
                        "total_episodes": stats.get("totalEpisodeCount", 0),
                        "size_on_disk": stats.get("sizeOnDisk", 0),
                        "overview": (show.get("overview") or "")[:200],
                    })

        async with s.get(f"{config.SONARR_URL}/api/v3/queue", headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                for r in data.get("records", [])[:20]:
                    result["queue"].append({
                        "title": r.get("title"),
                        "series_title": r.get("series", {}).get("title"),
                        "status": r.get("status"),
                        "size": r.get("size"),
                        "sizeleft": r.get("sizeleft"),
                    })

        from datetime import datetime, timedelta, timezone as tz
        now = datetime.now(tz.utc)
        start = now.strftime("%Y-%m-%d")
        end = (now + timedelta(days=7)).strftime("%Y-%m-%d")
        async with s.get(f"{config.SONARR_URL}/api/v3/calendar",
                        headers=headers, params={"start": start, "end": end}) as resp:
            if resp.status == 200:
                episodes = await resp.json()
                for ep in episodes[:20]:
                    result["calendar"].append({
                        "series_title": ep.get("series", {}).get("title"),
                        "episode_title": ep.get("title"),
                        "season": ep.get("seasonNumber"),
                        "episode": ep.get("episodeNumber"),
                        "air_date": ep.get("airDateUtc"),
                        "has_file": ep.get("hasFile", False),
                    })

    return result


@app.post("/api/media/tv")
async def media_add_tv(req: AddSeriesRequest):
    """Add a TV series to Sonarr."""
    headers = {"X-Api-Key": config.SONARR_API_KEY, "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{config.SONARR_URL}/api/v3/series/lookup",
                        headers=headers, params={"term": f"tvdb:{req.tvdb_id}"}) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=resp.status, detail="Sonarr lookup failed")
            results = await resp.json()
            if not results:
                raise HTTPException(status_code=404, detail="Show not found")
            show = results[0]

        show["qualityProfileId"] = req.quality_profile_id
        show["rootFolderPath"] = req.root_folder_path
        show["monitored"] = True
        show["addOptions"] = {"searchForMissingEpisodes": True}

        async with s.post(f"{config.SONARR_URL}/api/v3/series", headers=headers, json=show) as resp:
            if resp.status in (200, 201):
                result = await resp.json()
                return {"status": "added", "title": result.get("title"), "id": result.get("id")}
            text = await resp.text()
            raise HTTPException(status_code=resp.status, detail=text[:300])


@app.get("/api/media/movies")
async def media_movies():
    """Radarr: movie list + download queue."""
    headers = {"X-Api-Key": config.RADARR_API_KEY}
    result: dict = {"movies": [], "queue": []}

    async with aiohttp.ClientSession() as s:
        async with s.get(f"{config.RADARR_URL}/api/v3/movie", headers=headers) as resp:
            if resp.status == 200:
                raw = await resp.json()
                for m in raw:
                    result["movies"].append({
                        "id": m.get("id"),
                        "title": m.get("title"),
                        "year": m.get("year"),
                        "tmdb_id": m.get("tmdbId"),
                        "status": m.get("status"),
                        "monitored": m.get("monitored", False),
                        "has_file": m.get("hasFile", False),
                        "size_on_disk": m.get("sizeOnDisk", 0),
                        "overview": (m.get("overview") or "")[:200],
                        "runtime": m.get("runtime", 0),
                    })

        async with s.get(f"{config.RADARR_URL}/api/v3/queue", headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                for r in data.get("records", [])[:20]:
                    result["queue"].append({
                        "title": r.get("title"),
                        "movie_title": r.get("movie", {}).get("title"),
                        "status": r.get("status"),
                        "size": r.get("size"),
                        "sizeleft": r.get("sizeleft"),
                    })

    return result


@app.post("/api/media/movies")
async def media_add_movie(req: AddMovieRequest):
    """Add a movie to Radarr."""
    headers = {"X-Api-Key": config.RADARR_API_KEY, "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as s:
        async with s.get(f"{config.RADARR_URL}/api/v3/movie/lookup/tmdb",
                        headers=headers, params={"tmdbId": req.tmdb_id}) as resp:
            if resp.status != 200:
                raise HTTPException(status_code=resp.status, detail="Radarr lookup failed")
            movie = await resp.json()
            if not movie:
                raise HTTPException(status_code=404, detail="Movie not found")

        movie["qualityProfileId"] = req.quality_profile_id
        movie["rootFolderPath"] = req.root_folder_path
        movie["monitored"] = True
        movie["addOptions"] = {"searchForMovie": True}

        async with s.post(f"{config.RADARR_URL}/api/v3/movie", headers=headers, json=movie) as resp:
            if resp.status in (200, 201):
                result = await resp.json()
                return {"status": "added", "title": result.get("title"), "id": result.get("id")}
            text = await resp.text()
            raise HTTPException(status_code=resp.status, detail=text[:300])


@app.get("/api/media/library")
async def media_library():
    """Jellyfin: latest items + active sessions + library list."""
    headers = {"X-Emby-Token": config.JELLYFIN_API_KEY}
    result: dict = {"latest": [], "sessions": [], "libraries": []}

    async with aiohttp.ClientSession() as s:
        # Libraries
        async with s.get(f"{config.JELLYFIN_URL}/Library/VirtualFolders", headers=headers) as resp:
            if resp.status == 200:
                libs = await resp.json()
                for lib in libs:
                    result["libraries"].append({
                        "name": lib.get("Name"),
                        "type": lib.get("CollectionType", "unknown"),
                        "item_id": lib.get("ItemId"),
                    })

        # User ID for latest items
        user_id = None
        async with s.get(f"{config.JELLYFIN_URL}/Users", headers=headers) as resp:
            if resp.status == 200:
                users = await resp.json()
                if users:
                    user_id = users[0].get("Id")

        # Latest items
        if user_id:
            params = {"Limit": "20", "Fields": "Overview,RunTimeTicks,ProductionYear"}
            async with s.get(f"{config.JELLYFIN_URL}/Users/{user_id}/Items/Latest",
                            headers=headers, params=params) as resp:
                if resp.status == 200:
                    items = await resp.json()
                    for it in items:
                        ticks = it.get("RunTimeTicks")
                        duration = ""
                        if ticks:
                            secs = ticks // 10_000_000
                            h, rem = divmod(secs, 3600)
                            m, _ = divmod(rem, 60)
                            duration = f"{h}h{m:02d}m" if h else f"{m}m"
                        result["latest"].append({
                            "id": it.get("Id"),
                            "name": it.get("Name"),
                            "type": it.get("Type"),
                            "year": it.get("ProductionYear"),
                            "duration": duration,
                            "series_name": it.get("SeriesName"),
                            "season": it.get("ParentIndexNumber"),
                            "episode": it.get("IndexNumber"),
                        })

        # Active sessions
        async with s.get(f"{config.JELLYFIN_URL}/Sessions", headers=headers) as resp:
            if resp.status == 200:
                sessions = await resp.json()
                for sess in sessions:
                    now_playing = sess.get("NowPlayingItem")
                    if now_playing:
                        play_state = sess.get("PlayState", {})
                        result["sessions"].append({
                            "device": sess.get("DeviceName"),
                            "client": sess.get("Client"),
                            "user": sess.get("UserName"),
                            "playing": now_playing.get("Name"),
                            "type": now_playing.get("Type"),
                            "paused": play_state.get("IsPaused", False),
                        })

    return result


@app.get("/api/media/requests")
async def media_requests():
    """Jellyseerr: pending and recent requests."""
    headers = {"X-Api-Key": config.JELLYSEERR_API_KEY}
    result: dict = {"requests": [], "counts": {}}

    async with aiohttp.ClientSession() as s:
        async with s.get(f"{config.JELLYSEERR_URL}/api/v1/request/count", headers=headers) as resp:
            if resp.status == 200:
                result["counts"] = await resp.json()

        async with s.get(f"{config.JELLYSEERR_URL}/api/v1/request",
                        headers=headers, params={"take": "20", "skip": "0", "sort": "added"}) as resp:
            if resp.status == 200:
                data = await resp.json()
                for r in data.get("results", []):
                    media = r.get("media", {})
                    result["requests"].append({
                        "id": r.get("id"),
                        "media_type": r.get("type"),
                        "status": r.get("status"),
                        "title": media.get("title") or media.get("name") or
                                 r.get("media", {}).get("externalServiceSlug", "Unknown"),
                        "requested_by": r.get("requestedBy", {}).get("displayName"),
                        "created_at": r.get("createdAt"),
                    })

    return result


@app.post("/api/media/requests")
async def media_create_request(req: MediaRequestCreate):
    """Submit a Jellyseerr media request."""
    headers = {"X-Api-Key": config.JELLYSEERR_API_KEY, "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{config.JELLYSEERR_URL}/api/v1/request",
                         headers=headers, json={"mediaId": req.media_id, "mediaType": req.media_type}) as resp:
            if resp.status in (200, 201):
                return await resp.json()
            text = await resp.text()
            raise HTTPException(status_code=resp.status, detail=text[:300])


# ---------------------------------------------------------------------------
# Media Discovery: AI-powered trending content from Prowlarr indexers
# ---------------------------------------------------------------------------

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

_DISCOVER_CACHE: dict | None = None
_DISCOVER_CACHE_TIME: float = 0
_DISCOVER_TTL = 6 * 3600  # 6 hours
_DISCOVER_LOCK = asyncio.Lock()

_QUALITY_TAGS = re.compile(
    r"\b(2160p|1080p|720p|480p|4K|UHD|HDR|HDR10|DV|"
    r"WEB[-. ]?DL|WEBRip|BluRay|BDRip|BRRip|HDTV|DVDRip|"
    r"x264|x265|HEVC|AV1|AAC|DTS|ATMOS|10bit|REMUX|"
    r"PROPER|REPACK|NF|AMZN|DSNP|HMAX|ATVP)\b",
    re.IGNORECASE,
)
_GROUP_TAG = re.compile(r"[_\-\s]*\[?[A-Za-z0-9]+\]?\s*$")
_JUNK_PATTERNS = re.compile(
    r"\b(CAM|HDCAM|TS|TELESYNC|TC|TELECINE|SCR|SCREENER|DVDSCR|SAMPLE)\b",
    re.IGNORECASE,
)
_NON_MEDIA_EXT = re.compile(r"\.(zip|rar|7z|exe|iso|apk|pdf|epub|mobi|cbr|cbz)\s*$", re.IGNORECASE)
_CJK_HEAVY = re.compile(r"[\u3000-\u9fff\uf900-\ufaff]")
_ADULT_PATTERNS = re.compile(
    r"(同人誌|成年コミック|18禁|エロ|hentai|xxx|JAV|[Pp]orn|NSFW)",
)


def _is_junk_release(title: str) -> bool:
    """Return True if a torrent title looks like non-media or adult content."""
    if _JUNK_PATTERNS.search(title):
        return True
    if _NON_MEDIA_EXT.search(title):
        return True
    if _ADULT_PATTERNS.search(title):
        return True
    cjk_chars = len(_CJK_HEAVY.findall(title))
    if cjk_chars > 5 and cjk_chars / max(len(title), 1) > 0.3:
        return True
    return False


def _clean_title(raw: str) -> str:
    """Extract a human-readable title from a torrent name."""
    name = raw.replace(".", " ").replace("_", " ")
    name = re.sub(r"\(?\d{4}\)?", "", name, count=1)
    name = _QUALITY_TAGS.sub("", name)
    name = re.sub(r"\b(S\d{1,2}E?\d{0,2})\b", "", name, flags=re.IGNORECASE)
    name = _GROUP_TAG.sub("", name)
    name = re.sub(r"[^\w\s\'-]", " ", name)
    name = re.sub(r"\s{2,}", " ", name).strip()
    return name


def _extract_quality(raw: str) -> str:
    """Extract quality tags from a torrent title."""
    tags = _QUALITY_TAGS.findall(raw)
    return " ".join(dict.fromkeys(t.upper() for t in tags)) if tags else ""


TORZNAB_CATS = {
    "movies": "2000",
    "tv": "5000",
    "anime": "5070",
}
_DEFAULT_CATS = "2000,5000"


async def _fetch_prowlarr_rss(cats: str = _DEFAULT_CATS) -> list[dict]:
    """Fetch recent releases from all enabled Prowlarr indexers via torznab RSS."""
    headers = {"X-Api-Key": config.PROWLARR_API_KEY}
    results = []

    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(f"{config.PROWLARR_URL}/api/v1/indexer", headers=headers) as resp:
                if resp.status != 200:
                    log.warning("discover: failed to list indexers: HTTP %d", resp.status)
                    return []
                indexers = await resp.json()
    except Exception as e:
        log.warning("discover: indexer list failed: %s", e)
        return []

    enabled_ids = [i["id"] for i in indexers if i.get("enable")]
    if not enabled_ids:
        return []

    async def fetch_indexer(idx_id: int):
        try:
            url = f"{config.PROWLARR_URL}/{idx_id}/api"
            params = {"t": "search", "apikey": config.PROWLARR_API_KEY, "cat": cats}
            timeout = aiohttp.ClientTimeout(total=20)
            async with aiohttp.ClientSession(timeout=timeout) as s:
                async with s.get(url, params=params) as resp:
                    if resp.status != 200:
                        return
                    xml_text = await resp.text()
                    root = ET.fromstring(xml_text)
                    ns = {"atom": "http://www.w3.org/2005/Atom"}
                    channel = root.find("channel")
                    if channel is None:
                        return
                    for item in channel.findall("item"):
                        title = (item.findtext("title") or "").strip()
                        if not title or _is_junk_release(title):
                            continue
                        seeders = 0
                        peers = 0
                        size = 0
                        download_url = ""
                        for attr in item.findall("{http://torznab.com/schemas/2015/feed}attr"):
                            name = attr.get("name", "")
                            val = attr.get("value", "0")
                            if name == "seeders":
                                seeders = int(val)
                            elif name == "peers":
                                peers = int(val)
                            elif name == "size":
                                size = int(val)
                        link = item.findtext("link") or ""
                        enclosure = item.find("enclosure")
                        if enclosure is not None:
                            download_url = enclosure.get("url", link)
                        else:
                            download_url = link
                        if not download_url:
                            guid = item.findtext("guid") or ""
                            if guid.startswith("magnet:"):
                                download_url = guid
                        indexer_name = ""
                        for idx in indexers:
                            if idx["id"] == idx_id:
                                indexer_name = idx.get("name", str(idx_id))
                                break
                        results.append({
                            "raw_title": title,
                            "clean_title": _clean_title(title),
                            "seeders": seeders,
                            "peers": peers,
                            "size": size,
                            "download_url": download_url,
                            "indexer": indexer_name,
                            "quality": _extract_quality(title),
                        })
        except Exception as e:
            log.debug("discover: indexer %d RSS failed: %s", idx_id, e)

    await asyncio.gather(*(fetch_indexer(idx_id) for idx_id in enabled_ids))
    return results


async def _fetch_jellyseerr_trending() -> list[dict]:
    """Fetch trending titles from Jellyseerr (TMDB-sourced)."""
    trending = []
    try:
        headers = {"X-Api-Key": config.JELLYSEERR_API_KEY}
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as s:
            async with s.get(
                f"{config.JELLYSEERR_URL}/api/v1/discover/trending",
                headers=headers, params={"page": "1", "language": "en"},
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for r in data.get("results", [])[:20]:
                        trending.append({
                            "title": r.get("title") or r.get("name") or "",
                            "media_type": r.get("mediaType", ""),
                            "overview": (r.get("overview") or "")[:250],
                            "year": (r.get("releaseDate") or r.get("firstAirDate") or "")[:4],
                        })
    except Exception as e:
        log.debug("discover: jellyseerr trending failed: %s", e)
    return trending


_FLAT_SEEDER_INDEXERS = {"yts"}


def _effective_seeders(item: dict) -> int:
    """Return a sort-friendly seeder count, penalizing indexers with flat/fake values."""
    if item.get("indexer", "").lower() in _FLAT_SEEDER_INDEXERS:
        return 1
    return item["seeders"]


def _deduplicate_torrents(raw: list[dict], min_seeders: int = 10) -> list[dict]:
    """Group by clean title, keep highest-seeder variant, filter by threshold."""
    groups: dict[str, dict] = {}
    for item in raw:
        key = item["clean_title"].lower()
        if not key or len(key) < 3:
            continue
        if item["seeders"] < min_seeders:
            continue
        eff = _effective_seeders(item)
        existing = groups.get(key)
        if not existing or eff > _effective_seeders(existing):
            groups[key] = item
    ranked = sorted(groups.values(), key=_effective_seeders, reverse=True)
    return ranked[:40]


async def _enrich_with_llm(
    torrents: list[dict],
    trending: list[dict],
) -> tuple[dict[str, list[dict]], str]:
    """Use gemini-3-flash-preview via Ollama (or Gemini API fallback) to categorize torrents."""
    from langchain_core.messages import SystemMessage, HumanMessage
    from llm import invoke_with_fallback

    max_items = 20
    torrent_lines = []
    for i, t in enumerate(torrents[:max_items]):
        torrent_lines.append(
            f"{i+1}. \"{t['raw_title']}\" (seeders: {t['seeders']}, "
            f"size: {round(t['size'] / 1024 / 1024)}MB)"
        )

    trending_lines = []
    for t in trending[:15]:
        trending_lines.append(f"- {t['title']} ({t['year']}) [{t['media_type']}]: {t['overview'][:100]}")

    prompt = (
        "You are a media recommendation assistant. Below are two lists:\n\n"
        "## Top Trending Torrents (by seeder count)\n"
        + "\n".join(torrent_lines) + "\n\n"
    )
    if trending_lines:
        prompt += (
            "## TMDB Trending This Week\n"
            + "\n".join(trending_lines) + "\n\n"
        )
    prompt += (
        "Analyze and return a JSON object with this exact structure:\n"
        '{"items": [{"index": 1, "category": "Movie|TV Show|Documentary|Anime|Other", '
        '"title": "clean title", "description": "1-2 sentence summary of what this is and '
        'why it might be interesting", "score": 1-5}]}\n\n'
        "Rules:\n"
        "- Only include items you can identify as real movies, TV shows, anime, or documentaries\n"
        "- Skip anything that looks like spam, software, games, or adult content\n"
        "- The index field must match the torrent number from the list above\n"
        "- Score 5 = highly recommended, 1 = niche interest\n"
        "- If a torrent matches a TMDB trending title, boost its score\n"
        "- Return ONLY valid JSON, no markdown fences or explanation\n"
    )

    messages = [
        SystemMessage(content="You are a media expert. Respond with valid JSON only."),
        HumanMessage(content=prompt),
    ]

    try:
        discover_model = config.MEDIA_DISCOVER_MODEL
        text, provider = await invoke_with_fallback(
            messages, model=discover_model, provider="ollama",
            prefer_local=True, temperature=0.3,
            num_predict=8192, max_output_tokens=8192,
        )
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            text = json_match.group(0)

        text = re.sub(r",\s*([}\]])", r"\1", text)
        text = re.sub(r"'(\w+)'\s*:", r'"\1":', text)

        log.info("discover: LLM response (%d chars, provider=%s): %s", len(text), provider, text[:300])
        parsed = json.loads(text)
        items_raw = parsed.get("items", parsed if isinstance(parsed, list) else [])

        categories: dict[str, list[dict]] = {}
        for enriched in items_raw:
            idx = enriched.get("index", 0) - 1
            if idx < 0 or idx >= len(torrents):
                continue
            t = torrents[idx]
            cat = enriched.get("category", "Other")
            entry = {
                "title": enriched.get("title", t["clean_title"]),
                "description": enriched.get("description", ""),
                "score": max(1, min(5, int(enriched.get("score", 3)))),
                "quality": t["quality"],
                "seeders": t["seeders"],
                "seeders_approx": t.get("indexer", "").lower() in _FLAT_SEEDER_INDEXERS,
                "peers": t["peers"],
                "size_mb": round(t["size"] / 1024 / 1024),
                "download_url": t["download_url"],
                "indexer": t["indexer"],
                "raw_title": t["raw_title"],
            }
            categories.setdefault(cat, []).append(entry)

        for cat in categories:
            categories[cat].sort(key=lambda x: x["score"], reverse=True)

        return categories, provider
    except Exception as e:
        log.warning("discover: LLM enrichment failed: %s", e)
        categories: dict[str, list[dict]] = {"Uncategorized": []}
        for t in torrents[:max_items]:
            categories["Uncategorized"].append({
                "title": t["clean_title"],
                "description": "",
                "score": 3,
                "quality": t["quality"],
                "seeders": t["seeders"],
                "seeders_approx": t.get("indexer", "").lower() in _FLAT_SEEDER_INDEXERS,
                "peers": t["peers"],
                "size_mb": round(t["size"] / 1024 / 1024),
                "download_url": t["download_url"],
                "indexer": t["indexer"],
                "raw_title": t["raw_title"],
            })
        return categories, "none"


def _resolve_cats(cats_param: str | None) -> str:
    """Turn human-friendly category names into torznab codes.

    Accepts comma-separated mix of names (``movies``, ``tv``, ``anime``)
    and raw codes (``2000``, ``5000``).  Returns a comma-separated code string.
    """
    if not cats_param:
        return _DEFAULT_CATS
    parts = [p.strip().lower() for p in cats_param.split(",") if p.strip()]
    codes = []
    for p in parts:
        codes.append(TORZNAB_CATS.get(p, p))
    return ",".join(codes) if codes else _DEFAULT_CATS


def _cats_label(codes: str) -> str:
    """Human-readable label for torznab cat codes."""
    names = {v: k.title() for k, v in TORZNAB_CATS.items()}
    return ", ".join(f"{c} ({names.get(c, '?')})" for c in codes.split(","))


async def _build_discover_data(cats: str = _DEFAULT_CATS) -> dict:
    """Full discover pipeline: fetch, deduplicate, enrich, return."""
    raw_torrents, trending = await asyncio.gather(
        _fetch_prowlarr_rss(cats),
        _fetch_jellyseerr_trending(),
    )

    deduped = _deduplicate_torrents(raw_torrents)
    if not deduped:
        return {
            "categories": {},
            "total_indexed": len(raw_torrents),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "provider": "none",
            "search_info": {
                "torznab_cats": _cats_label(cats),
                "min_seeders": 10,
                "model": config.MEDIA_DISCOVER_MODEL,
            },
        }

    categories, provider = await _enrich_with_llm(deduped, trending)

    return {
        "categories": categories,
        "total_indexed": len(raw_torrents),
        "total_deduped": len(deduped),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "provider": provider,
        "search_info": {
            "torznab_cats": _cats_label(cats),
            "min_seeders": 10,
            "model": config.MEDIA_DISCOVER_MODEL,
        },
    }


_DISCOVER_CACHES: dict[str, tuple[dict, float]] = {}


@app.get("/api/media/discover")
async def media_discover(refresh: bool = False, cats: str | None = None):
    """AI-powered media discovery: trending torrents enriched by LLM.

    ``cats`` accepts comma-separated category names or torznab codes:
    ``movies`` (2000), ``tv`` (5000), ``anime`` (5070), or raw codes.
    Default: ``movies,tv``.
    """
    resolved = _resolve_cats(cats)
    now = time.time()
    cached = _DISCOVER_CACHES.get(resolved)
    if not refresh and cached and (now - cached[1]) < _DISCOVER_TTL:
        return cached[0]

    async with _DISCOVER_LOCK:
        cached = _DISCOVER_CACHES.get(resolved)
        if not refresh and cached and (now - cached[1]) < _DISCOVER_TTL:
            return cached[0]

        try:
            data = await _build_discover_data(resolved)
            _DISCOVER_CACHES[resolved] = (data, time.time())
            return data
        except Exception as e:
            log.error("discover: pipeline failed: %s", e)
            if cached:
                return cached[0]
            raise HTTPException(status_code=503, detail=f"Discovery unavailable: {e}")


# ---------------------------------------------------------------------------
# Server management: Docker containers + Cloudflare Tunnel routes
# ---------------------------------------------------------------------------

_CF_API_BASE = "https://api.cloudflare.com/client/v4"


def _cf_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {os.environ.get('CF_API_TOKEN', '')}",
        "Content-Type": "application/json",
    }


def _cf_tunnel_url(path: str = "") -> str:
    acct = os.environ.get("CF_ACCOUNT_ID", "")
    tid = os.environ.get("TUNNEL_ID", "")
    return f"{_CF_API_BASE}/accounts/{acct}/cfd_tunnel/{tid}/{path}"


@app.get("/api/server/containers")
async def server_containers():
    """List Docker containers with status, health, image, ports, and uptime."""
    import docker as docker_sdk
    from datetime import datetime, timezone as tz

    try:
        client = docker_sdk.from_env()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Docker unavailable: {e}")

    now = datetime.now(tz.utc)
    result = []
    for c in client.containers.list(all=True):
        attrs = c.attrs or {}
        state = attrs.get("State", {})
        health_obj = state.get("Health")
        health = health_obj.get("Status") if health_obj else None

        port_map: dict[str, int | None] = {}
        net_settings = attrs.get("NetworkSettings", {})
        for container_port, bindings in (net_settings.get("Ports") or {}).items():
            port_num = container_port.split("/")[0]
            host_port = None
            if bindings:
                for b in bindings:
                    hp = b.get("HostPort")
                    if hp:
                        host_port = int(hp)
                        break
            if host_port:
                port_map[port_num] = host_port

        started = state.get("StartedAt", "")
        uptime = ""
        if started and state.get("Running"):
            try:
                st = datetime.fromisoformat(started.replace("Z", "+00:00"))
                delta = now - st
                hours, rem = divmod(int(delta.total_seconds()), 3600)
                minutes = rem // 60
                if hours >= 24:
                    uptime = f"{hours // 24}d {hours % 24}h"
                elif hours > 0:
                    uptime = f"{hours}h {minutes}m"
                else:
                    uptime = f"{minutes}m"
            except Exception:
                pass

        img_tags = (c.image.tags or []) if c.image else []
        result.append({
            "name": c.name,
            "image": img_tags[0] if img_tags else (attrs.get("Config", {}).get("Image", "")),
            "status": state.get("Status", c.status),
            "health": health,
            "ports": port_map,
            "started_at": started,
            "uptime": uptime,
        })

    result.sort(key=lambda x: x["name"])
    return {"containers": result}


@app.get("/api/server/tunnel")
async def server_tunnel_list():
    """List Cloudflare Tunnel published application routes."""
    import httpx

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(_cf_tunnel_url("configurations"), headers=_cf_headers())
    data = resp.json()
    if not data.get("success"):
        errors = data.get("errors", [])
        detail = errors[0].get("message") if errors else "Unknown error"
        raise HTTPException(status_code=502, detail=f"Cloudflare API: {detail}")

    domain = os.environ.get("TUNNEL_DOMAIN", "")
    routes = []
    for rule in data["result"]["config"]["ingress"]:
        hostname = rule.get("hostname")
        if hostname:
            routes.append({"hostname": hostname, "service": rule["service"]})

    return {"routes": routes, "domain": domain}


class TunnelRouteRequest(BaseModel):
    subdomain: str = Field(..., description="Subdomain to add (e.g. 'uptime')")
    service: str = Field(..., description="Service URL (e.g. 'http://uptime-kuma:3001')")


@app.post("/api/server/tunnel")
async def server_tunnel_add(req: TunnelRouteRequest):
    """Add a published application route to the Cloudflare Tunnel."""
    import httpx

    domain = os.environ.get("TUNNEL_DOMAIN", "")
    hostname = f"{req.subdomain}.{domain}"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(_cf_tunnel_url("configurations"), headers=_cf_headers())
    data = resp.json()
    if not data.get("success"):
        raise HTTPException(status_code=502, detail="Failed to read tunnel config")

    ingress = data["result"]["config"]["ingress"]
    for rule in ingress:
        if rule.get("hostname") == hostname:
            raise HTTPException(status_code=409, detail=f"{hostname} already exists")

    ingress.insert(-1, {"service": req.service, "hostname": hostname, "originRequest": {}})

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.put(
            _cf_tunnel_url("configurations"),
            headers=_cf_headers(),
            json={"config": data["result"]["config"]},
        )
    result = resp.json()
    if not result.get("success"):
        errors = result.get("errors", [])
        detail = errors[0].get("message") if errors else "Unknown error"
        raise HTTPException(status_code=502, detail=f"Cloudflare API: {detail}")

    return {"status": "ok", "hostname": hostname, "service": req.service}


@app.delete("/api/server/tunnel/{subdomain}")
async def server_tunnel_remove(subdomain: str):
    """Remove a published application route from the Cloudflare Tunnel."""
    import httpx

    domain = os.environ.get("TUNNEL_DOMAIN", "")
    hostname = f"{subdomain}.{domain}"

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(_cf_tunnel_url("configurations"), headers=_cf_headers())
    data = resp.json()
    if not data.get("success"):
        raise HTTPException(status_code=502, detail="Failed to read tunnel config")

    ingress = data["result"]["config"]["ingress"]
    original_len = len(ingress)
    ingress = [r for r in ingress if r.get("hostname") != hostname]

    if len(ingress) == original_len:
        raise HTTPException(status_code=404, detail=f"{hostname} not found")

    data["result"]["config"]["ingress"] = ingress

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.put(
            _cf_tunnel_url("configurations"),
            headers=_cf_headers(),
            json={"config": data["result"]["config"]},
        )
    result = resp.json()
    if not result.get("success"):
        errors = result.get("errors", [])
        detail = errors[0].get("message") if errors else "Unknown error"
        raise HTTPException(status_code=502, detail=f"Cloudflare API: {detail}")

    return {"status": "ok", "hostname": hostname}


@app.get("/api/server/backups")
async def server_backups():
    """Return backup status from the JSON file written by homeserver.sh."""
    import json as _json
    from pathlib import Path

    status_file = Path(os.environ.get("DATA_DIR", "/app/data")) / "backup-status.json"
    if not status_file.exists():
        return {"status": "no_data"}
    try:
        return _json.loads(status_file.read_text())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read backup status: {e}")


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
