"""Home Assistant tools that talk directly to the HA REST API."""

import json
import logging

import aiohttp

import config

log = logging.getLogger("deepagent.tools.ha")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {config.HA_TOKEN}",
        "Content-Type": "application/json",
    }


async def ha_call_service(
    domain: str,
    service: str,
    entity_id: str = "",
    data: str = "{}",
) -> str:
    """Call a Home Assistant service to control a device.

    Args:
        domain: Service domain (light, switch, fan, climate, media_player, scene, automation, etc.)
        service: Service name (turn_on, turn_off, toggle, set_temperature, set_hvac_mode, etc.)
        entity_id: Target entity_id (e.g. light.bedroom, switch.printer_plug)
        data: Additional service data as JSON string, e.g. {"brightness": 128, "color_temp_kelvin": 4000}
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
                changed = len(result) if isinstance(result, list) else 1
                return json.dumps({"status": "ok", "service": f"{domain}.{service}", "entity_id": entity_id, "changed": changed})
            text = await resp.text()
            return json.dumps({"status": "error", "code": resp.status, "detail": text[:300]})


async def ha_get_states(domain: str = "", limit: int = 150) -> str:
    """Get current states of Home Assistant entities.

    Args:
        domain: Filter by domain (e.g. "light", "sensor", "switch"). Empty = all domains.
        limit: Max entities to return (default 150). For targeted lookups prefer ha_search_entities.
    """
    url = f"{config.HA_URL}/api/states"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers()) as resp:
            if resp.status != 200:
                text = await resp.text()
                return json.dumps({"status": "error", "code": resp.status, "detail": text[:300]})

            states = await resp.json()

    if domain:
        states = [s for s in states if s.get("entity_id", "").startswith(domain + ".")]

    results = []
    for s in states[:limit]:
        attrs = s.get("attributes", {})
        entry = {
            "entity_id": s["entity_id"],
            "state": s.get("state", "unknown"),
            "friendly_name": attrs.get("friendly_name", ""),
        }
        unit = attrs.get("unit_of_measurement")
        if unit:
            entry["unit"] = unit
        device_class = attrs.get("device_class")
        if device_class:
            entry["device_class"] = device_class
        results.append(entry)

    return json.dumps({"entities": results, "total": len(states), "returned": len(results)})


async def ha_search_entities(query: str, domain: str = "") -> str:
    """Search Home Assistant entities by name or entity_id.

    Args:
        query: Search term to match against entity_id or friendly_name (case-insensitive).
        domain: Optional domain filter (e.g. sensor, light, switch, camera).
    """
    url = f"{config.HA_URL}/api/states"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers()) as resp:
            if resp.status != 200:
                text = await resp.text()
                return json.dumps({"status": "error", "code": resp.status, "detail": text[:300]})
            states = await resp.json()

    query_lower = query.lower()
    matches = []
    for s in states:
        eid = s.get("entity_id", "")
        if domain and not eid.startswith(domain + "."):
            continue
        attrs = s.get("attributes", {})
        friendly = attrs.get("friendly_name", "")
        if query_lower in eid.lower() or query_lower in friendly.lower():
            entry = {
                "entity_id": eid,
                "state": s.get("state", "unknown"),
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


def get_ha_tools() -> list:
    """Return all HA tools as plain async functions (deepagents accepts callables)."""
    return [ha_call_service, ha_get_states, ha_search_entities, ha_trigger_automation, ha_fire_event]
