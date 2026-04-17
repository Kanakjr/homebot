"""
Home Assistant action tools (write-only).
All state reads come from the live state cache -- these tools only hit the
HA REST API for actions that change state.
"""

import json
import logging
import tempfile
from pathlib import Path

import aiohttp
from langchain_core.tools import tool

import config

log = logging.getLogger("homebot.tools.ha")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {config.HA_TOKEN}",
        "Content-Type": "application/json",
    }


@tool
async def ha_call_service(
    domain: str,
    service: str,
    entity_id: str = "",
    data: str = "{}",
) -> str:
    """Call a Home Assistant service to control a device (turn on/off lights, set temperature, activate scene, etc.).
    domain: Service domain (light, switch, scene, fan, climate, media_player, etc.)
    service: Service name (turn_on, turn_off, toggle, set_temperature, etc.)
    entity_id: Target entity_id (e.g. light.bedside, switch.monitor_plug)
    data: Additional service data as JSON string, e.g. {"brightness": 128}
    """
    try:
        extra_data = json.loads(data) if isinstance(data, str) and data else {}
    except json.JSONDecodeError:
        extra_data = {}

    payload = {}
    if entity_id:
        payload["entity_id"] = entity_id
    payload.update(extra_data)

    url = f"{config.HA_URL}/api/services/{domain}/{service}"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=_headers(), json=payload) as resp:
            if resp.status == 200:
                result = await resp.json()
                return json.dumps({"status": "ok", "changed": len(result) if isinstance(result, list) else 1})
            text = await resp.text()
            return json.dumps({"status": "error", "code": resp.status, "detail": text[:300]})


@tool
async def ha_get_camera_snapshot(entity_id: str) -> str:
    """Get a snapshot image from a Home Assistant camera entity.
    entity_id: Camera entity_id (e.g. camera.bedroom_camera_hd_stream)
    """
    url = f"{config.HA_URL}/api/camera_proxy/{entity_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers()) as resp:
            if resp.status == 200:
                image_bytes = await resp.read()
                snapshot_dir = Path(tempfile.gettempdir()) / "homebot_snapshots"
                snapshot_dir.mkdir(exist_ok=True)
                safe_name = entity_id.replace(".", "_")
                path = snapshot_dir / f"{safe_name}.jpg"
                path.write_bytes(image_bytes)
                return json.dumps({
                    "status": "ok",
                    "message": f"Camera snapshot from {entity_id} captured and saved.",
                    "entity_id": entity_id,
                    "image_path": str(path),
                })
            return json.dumps({"status": "error", "code": resp.status})


@tool
async def ha_trigger_automation(automation_id: str) -> str:
    """Manually trigger a Home Assistant automation.
    automation_id: Automation entity_id (e.g. automation.start_movie)
    """
    entity_id = automation_id if automation_id.startswith("automation.") else f"automation.{automation_id}"
    url = f"{config.HA_URL}/api/services/automation/trigger"
    payload = {"entity_id": entity_id}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=_headers(), json=payload) as resp:
            if resp.status == 200:
                return json.dumps({"status": "ok", "triggered": entity_id})
            text = await resp.text()
            return json.dumps({"status": "error", "code": resp.status, "detail": text[:300]})


@tool
async def ha_fire_event(event_type: str, event_data: str = "{}") -> str:
    """Fire a custom event in Home Assistant.
    event_type: Event type name
    event_data: Event data as JSON string
    """
    try:
        payload = json.loads(event_data) if isinstance(event_data, str) else event_data
    except json.JSONDecodeError:
        payload = {}

    url = f"{config.HA_URL}/api/events/{event_type}"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=_headers(), json=payload) as resp:
            if resp.status == 200:
                return json.dumps({"status": "ok", "event": event_type})
            text = await resp.text()
            return json.dumps({"status": "error", "code": resp.status, "detail": text[:300]})


def create_ha_tools():
    return [ha_call_service, ha_get_camera_snapshot, ha_trigger_automation, ha_fire_event]


def create_ha_state_tools(state_cache):
    """Tools that query the live state cache (read-only)."""
    from langchain_core.tools import StructuredTool

    async def _find_entities(query: str, domain: str = "") -> str:
        """Search Home Assistant entities by name, entity_id, or domain. Use this when
        the user asks about a device, sensor, or entity not visible in the Live state summary.
        query: Search term to match against entity_id or friendly_name (case-insensitive)
        domain: Optional domain filter (e.g. sensor, light, switch, camera, automation)
        """
        query_lower = query.lower()
        matches = []
        for eid in state_cache.all_entity_ids():
            if domain and not eid.startswith(domain + "."):
                continue
            entity = state_cache.get(eid)
            if not entity:
                continue
            friendly = entity.get("attributes", {}).get("friendly_name", "")
            if query_lower in eid.lower() or query_lower in friendly.lower():
                state_val = entity.get("state", "unknown")
                attrs = entity.get("attributes", {})
                entry = {
                    "entity_id": eid,
                    "state": state_val,
                    "friendly_name": friendly,
                }
                unit = attrs.get("unit_of_measurement")
                if unit:
                    entry["unit"] = unit
                device_class = attrs.get("device_class")
                if device_class:
                    entry["device_class"] = device_class
                matches.append(entry)
        return json.dumps({"results": matches[:30], "total": len(matches)})

    return [
        StructuredTool.from_function(
            coroutine=_find_entities,
            name="ha_find_entities",
            description=(
                "Search Home Assistant entities by name or domain. "
                "Use when the user asks about a device or entity not in the Live state summary."
            ),
        ),
    ]
