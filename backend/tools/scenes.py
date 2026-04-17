"""
Scene tools: create, list, and activate saved device-state snapshots.
"""

import json
import logging

import aiohttp
from langchain_core.tools import tool, StructuredTool

import config

log = logging.getLogger("homebot.tools.scenes")


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {config.HA_TOKEN}",
        "Content-Type": "application/json",
    }


def create_scene_tools(procedural, state_cache):
    """Create LangChain tools for scene management."""

    async def _create_scene(name: str, entity_ids: str) -> str:
        """Save the current state of specific entities as a reusable scene.
        name: Human-friendly scene name (e.g. "Movie Night", "Good Morning")
        entity_ids: Comma-separated entity_ids to snapshot (e.g. "light.bedside,switch.monitor_plug,fan.air_purifier")
        """
        ids = [e.strip() for e in entity_ids.split(",") if e.strip()]
        if not ids:
            return json.dumps({"status": "error", "detail": "No entity_ids provided"})

        entities = []
        for eid in ids:
            entity = state_cache.get(eid)
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
            return json.dumps({"status": "error", "detail": "No valid entities found in state cache"})

        scene_id = name.lower().replace(" ", "_").replace("-", "_")
        scene_id = "".join(c for c in scene_id if c.isalnum() or c == "_")

        scene = await procedural.create_scene(scene_id, name, entities)
        return json.dumps({
            "status": "ok",
            "scene_id": scene["id"],
            "name": scene["name"],
            "entities_count": len(scene["entities"]),
        })

    async def _activate_scene(scene_id: str) -> str:
        """Activate a saved scene, restoring all entity states to their saved values.
        scene_id: The scene identifier (e.g. "movie_night")
        """
        scene = await procedural.get_scene(scene_id)
        if not scene:
            return json.dumps({"status": "error", "detail": f"Scene '{scene_id}' not found"})

        headers = _headers()
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

        return json.dumps({"status": "ok", "scene": scene["name"], "restored": restored})

    async def _list_scenes() -> str:
        """List all saved scenes with their entity counts."""
        scenes = await procedural.get_scenes()
        result = []
        for s in scenes:
            result.append({
                "id": s["id"],
                "name": s["name"],
                "entities_count": len(s["entities"]),
            })
        return json.dumps({"scenes": result})

    return [
        StructuredTool.from_function(
            coroutine=_create_scene,
            name="create_scene",
            description="Save the current state of specific entities as a reusable scene that can be activated later.",
        ),
        StructuredTool.from_function(
            coroutine=_activate_scene,
            name="activate_scene",
            description="Activate a saved scene, restoring all entity states to their saved values.",
        ),
        StructuredTool.from_function(
            coroutine=_list_scenes,
            name="list_scenes",
            description="List all saved scenes.",
        ),
    ]
