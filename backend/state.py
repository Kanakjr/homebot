"""
Live Home Assistant state cache via WebSocket.

On boot: connects to HA WS API, fetches all states, subscribes to
state_changed events. Maintains an always-current in-memory mirror so the
agent never needs an API call to read state.
"""

import asyncio
import json
import logging
import time
from collections import deque
from typing import Callable, Awaitable

import websockets

import config

log = logging.getLogger("homebot.state")

StateChangeCallback = Callable[[str, dict | None, dict], Awaitable[None]]

RECENT_CHANGES_MAX = 30
RECENT_CHANGES_WINDOW = 600  # 10 minutes


class StateCache:
    def __init__(self):
        self._states: dict[str, dict] = {}
        self._ws = None
        self._task: asyncio.Task | None = None
        self._msg_id = 0
        self._on_change_callbacks: list[StateChangeCallback] = []
        self._connected = asyncio.Event()
        self._recent_changes: deque[tuple[float, str, str, str]] = deque(maxlen=RECENT_CHANGES_MAX)

    def on_state_change(self, callback: StateChangeCallback):
        self._on_change_callbacks.append(callback)

    def get(self, entity_id: str) -> dict | None:
        return self._states.get(entity_id)

    def get_domain(self, domain: str) -> dict[str, dict]:
        return {
            eid: st
            for eid, st in self._states.items()
            if eid.startswith(domain + ".")
        }

    def all_entity_ids(self) -> list[str]:
        return list(self._states.keys())

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    async def connect(self):
        if not config.HA_TOKEN:
            log.warning("HA_TOKEN not set -- state cache disabled")
            return
        self._task = asyncio.create_task(self._run_forever())
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=15)
        except asyncio.TimeoutError:
            log.warning("Timed out waiting for HA WebSocket initial state")

    async def disconnect(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()
        log.info("State cache disconnected")

    async def _run_forever(self):
        while True:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("HA WebSocket error, reconnecting in 10s")
                await asyncio.sleep(10)

    async def _connect_and_listen(self):
        log.info("Connecting to HA WebSocket: %s", config.HA_WS_URL)
        async with websockets.connect(config.HA_WS_URL, proxy=None) as ws:
            self._ws = ws

            auth_required = json.loads(await ws.recv())
            if auth_required.get("type") != "auth_required":
                log.error("Unexpected HA WS message: %s", auth_required)
                return

            await ws.send(json.dumps({
                "type": "auth",
                "access_token": config.HA_TOKEN,
            }))
            auth_result = json.loads(await ws.recv())
            if auth_result.get("type") != "auth_ok":
                log.error("HA WS auth failed: %s", auth_result)
                return
            log.info("HA WebSocket authenticated")

            get_states_id = self._next_id()
            await ws.send(json.dumps({
                "id": get_states_id,
                "type": "get_states",
            }))

            subscribe_id = self._next_id()
            await ws.send(json.dumps({
                "id": subscribe_id,
                "type": "subscribe_events",
                "event_type": "state_changed",
            }))

            async for raw in ws:
                msg = json.loads(raw)

                if msg.get("id") == get_states_id and msg.get("type") == "result":
                    for entity in msg.get("result", []):
                        eid = entity["entity_id"]
                        self._states[eid] = entity
                    log.info("Loaded %d entities from HA", len(self._states))
                    self._connected.set()

                elif msg.get("type") == "event":
                    event_data = msg.get("event", {}).get("data", {})
                    entity_id = event_data.get("entity_id")
                    old_state = event_data.get("old_state")
                    new_state = event_data.get("new_state")
                    if entity_id and new_state:
                        old_val = old_state.get("state", "") if old_state else ""
                        new_val = new_state.get("state", "")
                        if old_val != new_val:
                            self._recent_changes.append(
                                (time.monotonic(), entity_id, old_val, new_val)
                            )
                        self._states[entity_id] = new_state
                        for cb in self._on_change_callbacks:
                            try:
                                await cb(entity_id, old_state, new_state)
                            except Exception:
                                log.exception("State change callback error")

    # Sensor device classes worth including in the summary
    _USEFUL_SENSOR_CLASSES = frozenset({
        "temperature", "humidity", "pm25", "pm10", "aqi",
        "power", "energy", "battery", "illuminance",
        "carbon_dioxide", "carbon_monoxide", "volatile_organic_compounds",
    })

    # Domains to skip entirely -- internal / config / low-value
    _SKIP_DOMAINS = frozenset({
        "ai_task", "button", "calendar", "conversation",
        "event", "image", "number", "remote", "scene", "script",
        "select", "siren", "stt", "sun", "tts", "zone",
    })

    # Substrings in entity_id to skip (noise entities)
    _NOISE_PATTERNS = (
        "auto-update", "auto_update", "firmware", "cloud_connection",
        "calibration", "pairing", "restart", "led_brightness",
        "daily_calories", "daily_steps", "gamerpic", "avatar",
        "now_playing", "target_temperature", "prompt_sound",
        "image_sensor", "pick_image", "cover_image",
    )

    def summarize(self, context_hint: str | None = None) -> str:
        """Build a compact, relevance-filtered state summary.

        Prioritizes entities humans actually ask about: lights, climate,
        persons, weather, active media, and useful sensors (temp, humidity,
        AQI, power, battery). Skips internal/config entities to keep the
        context lean.

        Args:
            context_hint: Optional user message to enable context-aware
                filtering (include extra entities matching mentioned topics).
        """
        if not self._states:
            return "No entities loaded yet."

        sections: dict[str, list[str]] = {}

        def _add(section: str, line: str):
            sections.setdefault(section, []).append(line)

        # Context-aware: extract keywords from user message for extra inclusion
        context_keywords = set()
        if context_hint:
            hint_lower = context_hint.lower()
            for keyword in ("printer", "printo", "3d", "print",
                            "xbox", "tv", "media", "spotify", "jellyfin",
                            "camera", "purifier", "energy", "power",
                            "battery", "watch", "phone", "pixel", "ipad"):
                if keyword in hint_lower:
                    context_keywords.add(keyword)

        for eid, entity in sorted(self._states.items()):
            domain = eid.split(".")[0]
            if domain in self._SKIP_DOMAINS:
                continue

            attrs = entity.get("attributes", {})
            state_val = entity.get("state", "unknown")
            friendly = attrs.get("friendly_name", eid)

            if state_val in ("unavailable", "unknown"):
                continue

            eid_lower = eid.lower()
            if any(p in eid_lower for p in self._NOISE_PATTERNS):
                continue

            friendly_lower = friendly.lower()

            # Context boost: if user mentioned a topic, relax some filters
            context_match = any(kw in friendly_lower or kw in eid_lower for kw in context_keywords)

            if domain == "person":
                _add("People", f"{friendly}: {state_val}")

            elif domain == "device_tracker":
                loc = state_val
                source = attrs.get("source_type", "")
                extra = f" ({source})" if source else ""
                _add("Presence", f"{friendly}: {loc}{extra}")

            elif domain == "weather":
                temp = attrs.get("temperature", "")
                unit = attrs.get("temperature_unit", "")
                _add("Weather", f"{state_val}, {temp}{unit}")

            elif domain == "light":
                if not context_match and ("printo" in friendly_lower or "a1_03919d" in eid_lower):
                    continue
                brightness = attrs.get("brightness")
                pct = f" {round(brightness / 255 * 100)}%" if brightness else ""
                _add("Lights", f"{friendly}: {state_val}{pct}")

            elif domain in ("climate", "fan"):
                if state_val == "off" and not context_match:
                    continue
                mode = attrs.get("preset_mode", "")
                speed = attrs.get("percentage", "")
                extra_parts = [x for x in (mode, f"{speed}%" if speed else "") if x]
                extra = f" ({', '.join(extra_parts)})" if extra_parts else ""
                _add("Climate", f"{friendly}: {state_val}{extra}")

            elif domain == "camera":
                _add("Cameras", f"{friendly} ({state_val}) [entity_id: {eid}]")

            elif domain == "media_player":
                if state_val not in ("playing", "paused") and not context_match:
                    continue
                title = attrs.get("media_title", "")
                extra = f" - {title}" if title else ""
                _add("Media", f"{friendly}: {state_val}{extra}")

            elif domain == "automation":
                if state_val == "on":
                    _add("Automations", friendly)

            elif domain == "sensor":
                dev_class = attrs.get("device_class", "")
                if dev_class not in self._USEFUL_SENSOR_CLASSES and not context_match:
                    continue
                unit = attrs.get("unit_of_measurement", "")
                try:
                    val = round(float(state_val), 1)
                except (ValueError, TypeError):
                    val = state_val
                if dev_class == "temperature" and (
                    "printo" in friendly_lower or "a1_03919d" in eid_lower
                ):
                    if not context_match:
                        try:
                            if float(state_val) < 50:
                                continue
                        except (ValueError, TypeError):
                            pass
                if dev_class == "battery":
                    try:
                        if float(state_val) >= 30 and not context_match:
                            continue
                    except (ValueError, TypeError):
                        pass
                _add("Sensors", f"{friendly}: {val}{unit}")

            elif domain == "binary_sensor":
                dev_class = attrs.get("device_class", "")
                if dev_class not in ("motion", "door", "window", "occupancy", "smoke") and not context_match:
                    continue
                _add("Sensors", f"{friendly}: {state_val}")

            elif domain == "switch":
                skip_keywords = (
                    "led", "buzzer", "child lock", "ionizer",
                    "enable camera", "printo", "turtle mode",
                )
                if any(kw in friendly_lower for kw in skip_keywords) and not context_match:
                    continue
                _add("Switches", f"{friendly}: {state_val}")

        # Recent changes (last 10 minutes)
        now = time.monotonic()
        recent = [
            (eid, old, new)
            for ts, eid, old, new in self._recent_changes
            if now - ts < RECENT_CHANGES_WINDOW
        ]
        if recent:
            # Deduplicate: keep only the latest change per entity
            seen = {}
            for eid, old, new in recent:
                seen[eid] = (old, new)
            change_lines = [f"{eid}: {old}->{new}" for eid, (old, new) in seen.items()]
            _add("Recent Changes", " | ".join(change_lines[-10:]))

        # Anomaly detection
        anomalies = self._detect_anomalies()
        if anomalies:
            _add("Alerts", " | ".join(anomalies))

        lines = []
        for section_name, items in sections.items():
            lines.append(f"{section_name}: " + " | ".join(items))
        return "\n".join(lines) if lines else "No notable state."

    def _detect_anomalies(self) -> list[str]:
        """Flag unusual states worth highlighting to the agent."""
        alerts = []
        for eid, entity in self._states.items():
            attrs = entity.get("attributes", {})
            state_val = entity.get("state", "")
            friendly = attrs.get("friendly_name", eid)
            dev_class = attrs.get("device_class", "")

            # Battery critically low (< 15%)
            if dev_class == "battery":
                try:
                    if float(state_val) < 15:
                        alerts.append(f"LOW BATTERY: {friendly} at {state_val}%")
                except (ValueError, TypeError):
                    pass

            # High power consumption (> 500W)
            if dev_class == "power":
                try:
                    if float(state_val) > 500:
                        alerts.append(f"HIGH POWER: {friendly} at {state_val}W")
                except (ValueError, TypeError):
                    pass

            # Door/window open
            if dev_class in ("door", "window") and state_val == "on":
                alerts.append(f"OPEN: {friendly}")

        return alerts
