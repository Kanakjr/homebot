"""
Fetch long-term time series data from Home Assistant.

Two strategies:
  - WebSocket ``recorder/statistics_during_period`` for pre-aggregated
    hourly/daily statistics (ideal for 7d+ ranges).
  - REST ``/api/history/period`` for raw state history (fallback).
"""

import json
import logging
from datetime import datetime, timedelta, timezone

import aiohttp
import websockets

import config

log = logging.getLogger("homebot.ha_history")

_WS_TIMEOUT = 30  # seconds


async def fetch_ha_statistics(
    entity_ids: list[str],
    hours: int = 720,
    period: str | None = None,
) -> list[dict]:
    """Query HA Recorder long-term statistics via a one-shot WebSocket call.

    Returns normalised points: ``[{entity_id, value, ts}]`` where *value*
    is the hourly/daily ``mean``.  *period* is auto-selected when omitted:
      - hours <= 720  (30d) -> ``"hour"``
      - hours >  720         -> ``"day"``
    """
    if not entity_ids or not config.HA_TOKEN:
        return []

    if period is None:
        period = "hour" if hours <= 720 else "day"

    now = datetime.now(timezone.utc)
    start = (now - timedelta(hours=hours)).isoformat()
    end = now.isoformat()

    try:
        async with websockets.connect(
            config.HA_WS_URL, proxy=None, close_timeout=5
        ) as ws:
            msg = json.loads(await ws.recv())
            if msg.get("type") != "auth_required":
                log.error("Unexpected HA WS handshake: %s", msg)
                return []

            await ws.send(json.dumps({
                "type": "auth",
                "access_token": config.HA_TOKEN,
            }))
            auth = json.loads(await ws.recv())
            if auth.get("type") != "auth_ok":
                log.error("HA WS auth failed for statistics query")
                return []

            await ws.send(json.dumps({
                "id": 1,
                "type": "recorder/statistics_during_period",
                "start_time": start,
                "end_time": end,
                "statistic_ids": entity_ids,
                "period": period,
            }))

            import asyncio
            raw = await asyncio.wait_for(ws.recv(), timeout=_WS_TIMEOUT)
            result = json.loads(raw)

            if not result.get("success"):
                log.warning(
                    "HA statistics query failed: %s",
                    result.get("error", {}).get("message", "unknown"),
                )
                return []

            points: list[dict] = []
            for eid, entries in (result.get("result") or {}).items():
                for entry in entries:
                    mean = entry.get("mean")
                    if mean is None:
                        mean = entry.get("state")
                    if mean is None:
                        continue
                    try:
                        val = float(mean)
                    except (ValueError, TypeError):
                        continue
                    raw_ts = entry.get("start", "")
                    if isinstance(raw_ts, (int, float)):
                        ts_sec = raw_ts / 1000 if raw_ts > 1e12 else raw_ts
                        ts_str = datetime.fromtimestamp(
                            ts_sec, tz=timezone.utc,
                        ).strftime("%Y-%m-%dT%H:%M:%S")
                    else:
                        ts_str = str(raw_ts)
                    points.append({
                        "entity_id": eid,
                        "value": round(val, 2),
                        "ts": ts_str,
                    })
            return points

    except Exception:
        log.exception("Failed to fetch HA statistics")
        return []


async def fetch_ha_history_rest(
    entity_ids: list[str],
    hours: int = 24,
) -> list[dict]:
    """Fetch raw state history via HA REST API (``/api/history/period``).

    Returns normalised points: ``[{entity_id, value, ts}]``.
    Best for ranges up to a few days; for longer ranges prefer
    :func:`fetch_ha_statistics`.
    """
    if not entity_ids or not config.HA_TOKEN:
        return []

    start = (
        datetime.now(timezone.utc) - timedelta(hours=hours)
    ).isoformat()
    filter_ids = ",".join(entity_ids)
    url = (
        f"{config.HA_URL}/api/history/period/{start}"
        f"?filter_entity_id={filter_ids}&minimal_response&no_attributes"
    )
    headers = {"Authorization": f"Bearer {config.HA_TOKEN}"}

    points: list[dict] = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, headers=headers, ssl=False,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as resp:
                if resp.status != 200:
                    log.warning("HA history REST returned %d", resp.status)
                    return []
                raw = await resp.json()
                for entity_history in raw:
                    if not entity_history:
                        continue
                    eid = entity_history[0].get("entity_id", "")
                    for pt in entity_history:
                        try:
                            val = float(pt["state"])
                        except (ValueError, TypeError, KeyError):
                            continue
                        points.append({
                            "entity_id": eid,
                            "value": round(val, 2),
                            "ts": pt.get("last_changed", ""),
                        })
    except Exception:
        log.exception("Failed to fetch HA REST history")

    return points
