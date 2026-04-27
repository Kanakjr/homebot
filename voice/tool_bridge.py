"""Tool functions exposed to the Gemini Live session.

Hybrid strategy:

* **Direct tools** talk straight to Home Assistant / media services over HTTP
  from this process. They exist for single-shot actions the user expects to
  land in under a second (flip a light, query a sensor, check what's playing).

* **`delegate_to_homebot`** forwards a natural-language query to the existing
  Deep Agent (`/api/chat/stream` on :8322) and returns its final text. Use
  this for anything that needs multi-step reasoning, skill knowledge,
  Obsidian memory lookups, link processing, media discovery, etc.

All functions are plain ``async def`` with typed parameters and detailed
docstrings -- the ``google.genai`` SDK turns them into ``FunctionDeclaration``
objects automatically when passed via ``LiveConnectConfig(tools=[...])``.
Keep return values compact strings (or short JSON): the model speaks them
back, so verbosity = latency.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp
import httpx
from httpx_sse import aconnect_sse

import voice.config as cfg

log = logging.getLogger("voice.tools")


# ---------------------------------------------------------------------------
# Session control flag. `live_session` sets the event to request close.
# ---------------------------------------------------------------------------

_end_session_event: asyncio.Event | None = None


def bind_end_session_event(event: asyncio.Event) -> None:
    """Wire an asyncio Event that the `end_session` tool will set."""
    global _end_session_event
    _end_session_event = event


# ---------------------------------------------------------------------------
# Home Assistant helpers
# ---------------------------------------------------------------------------


def _ha_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {cfg.HA_TOKEN}",
        "Content-Type": "application/json",
    }


async def _ha_call(domain: str, service: str, payload: dict[str, Any]) -> dict:
    url = f"{cfg.HA_URL}/api/services/{domain}/{service}"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=_ha_headers(), json=payload) as resp:
            text = await resp.text()
            if resp.status == 200:
                try:
                    return {"ok": True, "changed": len(json.loads(text) or [])}
                except Exception:
                    return {"ok": True}
            return {"ok": False, "status": resp.status, "detail": text[:200]}


async def _ha_get_state(entity_id: str) -> dict | None:
    url = f"{cfg.HA_URL}/api/states/{entity_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_ha_headers()) as resp:
            if resp.status != 200:
                return None
            return await resp.json()


async def _ha_get_all() -> list[dict]:
    url = f"{cfg.HA_URL}/api/states"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_ha_headers()) as resp:
            if resp.status != 200:
                return []
            return await resp.json()


# ---------------------------------------------------------------------------
# Direct tools -- lights, switches, fans, scenes
# ---------------------------------------------------------------------------


async def control_light(
    entity_id: str,
    state: str,
    brightness_pct: int | None = None,
    color_temp_kelvin: int | None = None,
    rgb_color: list[int] | None = None,
) -> str:
    """Turn a Home Assistant light on or off and optionally set brightness or color.

    Use for any entity under the ``light.*`` domain (e.g. ``light.bedside``,
    ``light.table_lamp``). For the Homemate RGB LED strip use
    ``control_rgb_strip`` instead -- it has no light entity.

    Args:
        entity_id: Full HA entity id, e.g. ``light.table_lamp``.
        state: ``on`` or ``off``.
        brightness_pct: Optional 1-100 brightness percent (ignored for ``off``).
        color_temp_kelvin: Optional warm/cool temperature, e.g. 2700, 4000, 6500.
        rgb_color: Optional [r, g, b] 0-255 list. Only for RGB-capable lights.
    """
    service = "turn_on" if state.lower() in {"on", "true", "1"} else "turn_off"
    payload: dict[str, Any] = {"entity_id": entity_id}
    if service == "turn_on":
        if brightness_pct is not None:
            payload["brightness_pct"] = max(1, min(100, int(brightness_pct)))
        if color_temp_kelvin is not None:
            payload["color_temp_kelvin"] = int(color_temp_kelvin)
        if rgb_color:
            payload["rgb_color"] = [int(v) for v in rgb_color][:3]
    result = await _ha_call("light", service, payload)
    return json.dumps({"entity_id": entity_id, "service": service, **result})


async def control_switch(entity_id: str, state: str) -> str:
    """Turn a Home Assistant switch on or off.

    Args:
        entity_id: Full HA entity id, e.g. ``switch.monitor_plug``, ``switch.workstation``.
        state: ``on`` or ``off``.
    """
    service = "turn_on" if state.lower() in {"on", "true", "1"} else "turn_off"
    result = await _ha_call("switch", service, {"entity_id": entity_id})
    return json.dumps({"entity_id": entity_id, "service": service, **result})


async def control_fan(
    entity_id: str,
    state: str,
    preset_mode: str | None = None,
) -> str:
    """Turn a Home Assistant fan on/off and optionally set a preset mode.

    Args:
        entity_id: Full HA entity id, e.g. ``fan.air_purifier``, ``fan.printer_fan``.
        state: ``on`` or ``off``.
        preset_mode: Optional mode like ``auto``, ``sleep``, ``favorite``.
    """
    service = "turn_on" if state.lower() in {"on", "true", "1"} else "turn_off"
    payload: dict[str, Any] = {"entity_id": entity_id}
    if service == "turn_on" and preset_mode:
        payload["preset_mode"] = preset_mode
    result = await _ha_call("fan", service, payload)
    return json.dumps({"entity_id": entity_id, "service": service, **result})


async def control_rgb_strip(
    state: str,
    brightness_pct: int | None = None,
    color: str | None = None,
) -> str:
    """Control the Alexa-proxied Homemate RGB LED strip.

    This device has **no** ``light.*`` entity -- it is driven by helper
    scripts that have an Echo Dot speak a voice command at it. Expect a
    1-2 second delay and a faint "okay" from the Echo.

    Args:
        state: ``on`` or ``off``.
        brightness_pct: Optional 1-100 brightness (calls
            ``script.rgb_strip_brightness`` with ``{level}``).
        color: Optional color name. Valid: red, green, blue, yellow, orange,
            purple, pink, warm white, cool white, daylight.
    """
    want_on = state.lower() in {"on", "true", "1"}
    results: list[dict] = []
    if want_on:
        results.append(await _ha_call("script", "rgb_strip_on", {}))
        if brightness_pct is not None:
            lvl = max(1, min(100, int(brightness_pct)))
            results.append(
                await _ha_call("script", "rgb_strip_brightness", {"level": lvl})
            )
        if color:
            results.append(
                await _ha_call("script", "rgb_strip_color", {"color": color})
            )
    else:
        results.append(await _ha_call("script", "rgb_strip_off", {}))
    ok = all(r.get("ok") for r in results)
    return json.dumps({"ok": ok, "state": "on" if want_on else "off", "calls": len(results)})


async def set_scene(scene_entity_id: str) -> str:
    """Activate a Home Assistant scene.

    Args:
        scene_entity_id: Either a ``scene.*`` entity id or a ``script.*``
            entity id (scripts are routed through ``script.turn_on``).
    """
    if scene_entity_id.startswith("script."):
        domain = "script"
    elif scene_entity_id.startswith("scene."):
        domain = "scene"
    else:
        domain = "scene"
        scene_entity_id = f"scene.{scene_entity_id}"
    result = await _ha_call(domain, "turn_on", {"entity_id": scene_entity_id})
    return json.dumps({"entity_id": scene_entity_id, **result})


async def get_entity_state(entity_id: str) -> str:
    """Fetch the current state and key attributes of a single HA entity.

    Args:
        entity_id: Full HA entity id, e.g. ``sensor.bedroom_temperature``,
            ``light.bedside``, ``person.kanak``.
    """
    data = await _ha_get_state(entity_id)
    if not data:
        return json.dumps({"error": f"Entity {entity_id} not found"})
    attrs = data.get("attributes", {}) or {}
    compact = {
        "entity_id": data.get("entity_id"),
        "state": data.get("state"),
        "friendly_name": attrs.get("friendly_name"),
    }
    for key in ("unit_of_measurement", "brightness", "color_temp_kelvin",
                "rgb_color", "preset_mode", "device_class", "battery_level"):
        if key in attrs:
            compact[key] = attrs[key]
    return json.dumps(compact)


async def search_entities(query: str, domain: str = "") -> str:
    """Search Home Assistant entities by substring of id or friendly name.

    Use this when the user refers to a device by a phrase ("the desk lamp",
    "the printer camera") that you don't recognise. For device control with
    a known entity id, call ``control_*`` directly.

    Args:
        query: Search text, case-insensitive. Matches entity_id or friendly_name.
        domain: Optional HA domain filter like ``light``, ``sensor``, ``switch``.
    """
    states = await _ha_get_all()
    q = query.lower()
    results = []
    for s in states:
        eid = s.get("entity_id", "")
        if domain and not eid.startswith(domain + "."):
            continue
        attrs = s.get("attributes", {}) or {}
        name = attrs.get("friendly_name", "") or ""
        if q in eid.lower() or q in name.lower():
            results.append({
                "entity_id": eid,
                "state": s.get("state"),
                "friendly_name": name,
            })
            if len(results) >= 15:
                break
    return json.dumps({"results": results, "count": len(results)})


async def get_sensor_summary(kind: str = "environment") -> str:
    """Return a pre-synthesized summary of common bedroom sensors.

    This avoids round-tripping a bunch of individual ``get_entity_state``
    calls when the user asks generic questions ("what's the temperature",
    "how's the air in here").

    Args:
        kind: One of ``environment`` (temperature + humidity + PM2.5),
            ``power`` (live wattage draw), ``battery`` (all battery levels),
            ``presence`` (who/what device trackers report home). Defaults to
            ``environment``.
    """
    states = await _ha_get_all()

    def _extract(pattern: str, dc: str = "") -> list[dict]:
        out = []
        for s in states:
            eid = s.get("entity_id", "")
            attrs = s.get("attributes", {}) or {}
            if not eid.startswith("sensor."):
                continue
            if dc and attrs.get("device_class") != dc:
                continue
            if pattern not in eid.lower() and pattern not in (attrs.get("friendly_name", "") or "").lower():
                continue
            out.append({
                "name": attrs.get("friendly_name") or eid,
                "value": s.get("state"),
                "unit": attrs.get("unit_of_measurement", ""),
            })
        return out

    kind = kind.lower().strip()
    if kind == "power":
        return json.dumps({"power": _extract("power", "power")})
    if kind == "battery":
        return json.dumps({"battery": _extract("battery", "battery")})
    if kind == "presence":
        people = [
            {"name": (s.get("attributes", {}) or {}).get("friendly_name") or s["entity_id"],
             "state": s.get("state")}
            for s in states if s.get("entity_id", "").startswith("person.")
        ]
        trackers_home = sum(
            1 for s in states
            if s.get("entity_id", "").startswith("device_tracker.")
            and s.get("state") == "home"
        )
        return json.dumps({"people": people, "trackers_home": trackers_home})

    temp = _extract("temperature", "temperature")
    hum = _extract("humidity", "humidity")
    pm = _extract("pm2", "")
    return json.dumps({
        "temperature": temp[:3],
        "humidity": hum[:3],
        "pm2_5": pm[:3],
    })


# ---------------------------------------------------------------------------
# 3D printer status (Bambu Lab via ha-bambulab, entity ids under sensor.printer_*)
# ---------------------------------------------------------------------------


# Entities we batch-read in one `/api/states` call to avoid N separate
# round trips. Order doesn't matter -- the function picks the fields it
# needs by key.
_PRINTER_ENTITIES = (
    "binary_sensor.printer_online",
    "binary_sensor.printer_error",
    "sensor.printer_current_stage",
    "sensor.printer_status",
    "sensor.printer_progress",
    "sensor.printer_current_layer",
    "sensor.printer_total_layers",
    "sensor.printer_remaining_time",
    "sensor.printer_end_time",
    "sensor.printer_start_time",
    "sensor.printer_task_name",
    "sensor.printer_gcode",
    "sensor.printer_bed_temp",
    "sensor.printer_bed_target",
    "sensor.printer_nozzle_temp",
    "sensor.printer_nozzle_target",
    "sensor.printer_fan_speed",
    "sensor.printer_spool",
)


def _fmt_hours(value) -> str:
    """Convert a Home Assistant duration value (hours, possibly fractional)
    into a short spoken form like "1h 34m", "34m", "< 1m"."""
    try:
        hours = float(value)
    except (TypeError, ValueError):
        return str(value)
    if hours <= 0:
        return "less than a minute"
    total_min = int(round(hours * 60))
    if total_min < 1:
        return "less than a minute"
    h, m = divmod(total_min, 60)
    if h and m:
        return f"{h}h {m}m"
    if h:
        return f"{h}h"
    return f"{m}m"


async def get_printer_status() -> str:
    """Return a single voice-friendly summary of the 3D printer.

    Use this whenever the user asks about the printer, an ongoing print,
    ETA, progress, layers, bed/nozzle temperature, or whether a print is
    running. Reads a set of ``sensor.printer_*`` entities in one HTTP
    call and synthesises a compact JSON the model can read aloud.

    Returns JSON with keys:
      online (bool), error (bool), stage (string, e.g. "printing",
      "idle", "heatbed_preheating"), status (string), progress_pct (int),
      layer ("6/113" style string or null), task_name, remaining (spoken
      string like "1h 34m"), eta (HH:MM local), bed (string like "65 /
      65 C"), nozzle (string like "220 / 220 C"), spool, summary
      (one-line English summary).

    When the printer is offline or idle, most fields will be null; use
    the ``summary`` field directly.
    """
    try:
        states = await _ha_get_all()
    except Exception as e:
        return json.dumps({"error": f"Home Assistant unreachable: {e}"})

    by_id = {s.get("entity_id"): s for s in states}

    def g(eid: str) -> str | None:
        s = by_id.get(eid)
        if not s:
            return None
        val = s.get("state")
        if val in (None, "", "unknown", "unavailable"):
            return None
        return val

    online = g("binary_sensor.printer_online") == "on"
    error = g("binary_sensor.printer_error") == "on"
    stage = g("sensor.printer_current_stage") or "unknown"
    status = g("sensor.printer_status") or "unknown"
    task = g("sensor.printer_task_name") or g("sensor.printer_gcode")
    spool = g("sensor.printer_spool")

    try:
        progress = int(float(g("sensor.printer_progress") or 0))
    except ValueError:
        progress = 0

    cur_layer = g("sensor.printer_current_layer")
    tot_layer = g("sensor.printer_total_layers")
    layer = f"{cur_layer}/{tot_layer}" if cur_layer and tot_layer else None

    remaining_hours = g("sensor.printer_remaining_time")
    remaining = _fmt_hours(remaining_hours) if remaining_hours else None

    end_time_raw = g("sensor.printer_end_time")
    eta = None
    if end_time_raw:
        # HA returns either a datetime string or a time string.
        eta = end_time_raw.split(" ")[-1][:5] if " " in end_time_raw else end_time_raw[:5]

    bed_t = g("sensor.printer_bed_temp")
    bed_tgt = g("sensor.printer_bed_target")
    noz_t = g("sensor.printer_nozzle_temp")
    noz_tgt = g("sensor.printer_nozzle_target")
    bed = f"{round(float(bed_t))} / {round(float(bed_tgt))} C" if bed_t and bed_tgt else None
    nozzle = f"{round(float(noz_t))} / {round(float(noz_tgt))} C" if noz_t and noz_tgt else None

    if not online:
        summary = "The printer is offline."
    elif error:
        summary = "The printer is reporting an error."
    elif stage == "idle":
        summary = "The printer is idle."
    elif stage == "printing":
        parts = [f"printing {task}" if task else "printing"]
        parts.append(f"{progress}%")
        if layer:
            parts.append(f"layer {layer}")
        if remaining:
            parts.append(f"{remaining} left")
        if eta:
            parts.append(f"ETA {eta}")
        summary = ", ".join(parts) + "."
    else:
        summary = f"Printer stage: {stage.replace('_', ' ')}."
        if progress:
            summary += f" Progress {progress}%."
        if remaining:
            summary += f" About {remaining} remaining."

    return json.dumps({
        "online": online,
        "error": error,
        "stage": stage,
        "status": status,
        "progress_pct": progress,
        "layer": layer,
        "task_name": task,
        "remaining": remaining,
        "eta": eta,
        "bed": bed,
        "nozzle": nozzle,
        "spool": spool,
        "summary": summary,
    })


# ---------------------------------------------------------------------------
# Media status tools (fast, read-only)
# ---------------------------------------------------------------------------


async def media_now_playing() -> str:
    """Return a short summary of what's currently playing on Jellyfin.

    Returns an empty list if Jellyfin is not configured or nothing is
    active.
    """
    if not cfg.JELLYFIN_URL or not cfg.JELLYFIN_API_KEY:
        return json.dumps({"sessions": [], "note": "Jellyfin not configured"})

    headers = {"X-Emby-Token": cfg.JELLYFIN_API_KEY}
    url = f"{cfg.JELLYFIN_URL}/Sessions"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status != 200:
                    return json.dumps({"error": f"HTTP {resp.status}"})
                data = await resp.json()
    except Exception as e:
        return json.dumps({"error": str(e)[:200]})

    active = []
    for s in data:
        npi = s.get("NowPlayingItem")
        if not npi:
            continue
        active.append({
            "title": npi.get("Name"),
            "series": npi.get("SeriesName"),
            "type": npi.get("Type"),
            "device": s.get("DeviceName"),
            "user": s.get("UserName"),
        })
    return json.dumps({"sessions": active, "count": len(active)})


async def media_downloads_status() -> str:
    """Summarize Transmission downloads: active count and top 3 by progress."""
    if not cfg.TRANSMISSION_URL:
        return json.dumps({"torrents": [], "note": "Transmission not configured"})

    rpc = f"{cfg.TRANSMISSION_URL}/transmission/rpc"
    auth = aiohttp.BasicAuth(cfg.TRANSMISSION_USERNAME, cfg.TRANSMISSION_PASSWORD) \
        if cfg.TRANSMISSION_USERNAME else None
    payload = {
        "method": "torrent-get",
        "arguments": {
            "fields": ["name", "status", "percentDone", "rateDownload", "eta"],
        },
    }
    headers = {"Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession(auth=auth) as session:
            async with session.post(rpc, headers=headers, json=payload,
                                    timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 409:
                    headers["X-Transmission-Session-Id"] = resp.headers.get("X-Transmission-Session-Id", "")
                    async with session.post(rpc, headers=headers, json=payload) as resp2:
                        data = await resp2.json() if resp2.status == 200 else {}
                elif resp.status == 200:
                    data = await resp.json()
                else:
                    return json.dumps({"error": f"HTTP {resp.status}"})
    except Exception as e:
        return json.dumps({"error": str(e)[:200]})

    torrents = data.get("arguments", {}).get("torrents", []) if data else []
    active = [t for t in torrents if t.get("status") in (3, 4)]
    active.sort(key=lambda t: t.get("percentDone", 0), reverse=True)
    top = [
        {
            "name": t.get("name", "")[:60],
            "progress": round((t.get("percentDone") or 0) * 100, 1),
            "eta_sec": t.get("eta", -1),
        }
        for t in active[:3]
    ]
    return json.dumps({"active": len(active), "top": top, "total": len(torrents)})


# ---------------------------------------------------------------------------
# Session control
# ---------------------------------------------------------------------------


async def end_session(reason: str = "user_requested") -> str:
    """End the current voice session and return to wake-word listening.

    Call when the user says goodbye, thanks, "that's all", "stop listening",
    or otherwise signals they're done. Always send a brief spoken goodbye
    in the same turn before or after calling this.

    Args:
        reason: Short tag, e.g. ``user_requested``, ``timeout``, ``idle``.
    """
    if _end_session_event is not None:
        _end_session_event.set()
    log.info("end_session tool fired (reason=%s)", reason)
    return json.dumps({"ended": True, "reason": reason})


# ---------------------------------------------------------------------------
# Delegate to the Deep Agent
# ---------------------------------------------------------------------------


async def delegate_to_homebot(query: str) -> str:
    """Forward a complex request to the Deep Agent and return its reply.

    Use **only** when a request can't be satisfied by the direct tools
    above -- i.e. it needs multi-step reasoning, the Obsidian memory,
    link processing, media discovery, Sonarr/Radarr management, or a
    tool we don't expose here. Typical triggers:

    * "Search the web / read this link / save this article"
    * "Recommend me a show / movie"
    * "Add <series> to Sonarr / request <movie>"
    * "What's on my calendar / in my notes about X"
    * Anything that obviously needs the full agent's reasoning chain.

    The Deep Agent already knows the house layout and has its own memory
    and skills; pass the user's request verbatim (plus any context you've
    already gathered).

    Args:
        query: The natural-language task for the Deep Agent to handle.
    """
    url = f"{cfg.DEEPAGENT_URL}/api/chat/stream"
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if cfg.DEEPAGENT_API_KEY:
        headers["X-API-Key"] = cfg.DEEPAGENT_API_KEY
    payload = {"message": query, "thread_id": cfg.VOICE_THREAD_ID, "context": "skill"}

    last_response = ""
    log.info("Delegating to deepagent: %s", query[:120])

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90.0)) as client:
            async with aconnect_sse(client, "POST", url, json=payload, headers=headers) as sse:
                async for event in sse.aiter_sse():
                    if not event.data:
                        continue
                    try:
                        data = json.loads(event.data)
                    except json.JSONDecodeError:
                        continue
                    evt_type = event.event or data.get("type", "")
                    if evt_type == "response":
                        content = data.get("content", "")
                        if content:
                            last_response = content
                    elif evt_type == "error":
                        last_response = data.get("content") or "Deep agent error"
    except Exception as e:
        log.exception("delegate_to_homebot failed")
        return f"I couldn't reach the backend agent: {e}"

    return last_response.strip() or "The backend agent did not return a response."


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------


def get_live_tools() -> list:
    """Return the list of callables to pass into ``LiveConnectConfig(tools=...)``.

    Order is intentional: the model tends to try tools in the order they
    are declared when the signatures are similar, so put the common
    household controls first and the delegate tool last.
    """
    return [
        control_light,
        control_switch,
        control_fan,
        control_rgb_strip,
        set_scene,
        get_entity_state,
        search_entities,
        get_sensor_summary,
        get_printer_status,
        media_now_playing,
        media_downloads_status,
        end_session,
        delegate_to_homebot,
    ]
