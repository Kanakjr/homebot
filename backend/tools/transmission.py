"""
Transmission RPC tools for torrent management.
"""

import json
import logging

import aiohttp
from langchain_core.tools import tool

import config

log = logging.getLogger("homebot.tools.transmission")

TRANSMISSION_RPC = f"{config.TRANSMISSION_URL}/transmission/rpc"


async def _rpc(method: str, arguments: dict | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    payload = {"method": method}
    if arguments:
        payload["arguments"] = arguments

    async with aiohttp.ClientSession() as session:
        async with session.post(TRANSMISSION_RPC, headers=headers, json=payload) as resp:
            if resp.status == 409:
                csrf = resp.headers.get("X-Transmission-Session-Id", "")
                headers["X-Transmission-Session-Id"] = csrf
                async with session.post(TRANSMISSION_RPC, headers=headers, json=payload) as resp2:
                    if resp2.status == 200:
                        return await resp2.json()
                    return {"result": "error", "status": resp2.status}
            elif resp.status == 200:
                return await resp.json()
            return {"result": "error", "status": resp.status}


def _status_label(status: int) -> str:
    return {0: "stopped", 1: "queued_verify", 2: "verifying", 3: "queued_download",
            4: "downloading", 5: "queued_seed", 6: "seeding"}.get(status, "unknown")


def _format_speed(bps: int) -> str:
    if bps < 1024:
        return f"{bps} B/s"
    if bps < 1024 * 1024:
        return f"{bps / 1024:.1f} KB/s"
    return f"{bps / 1024 / 1024:.1f} MB/s"


@tool
async def transmission_get_torrents() -> str:
    """List all torrents in Transmission with progress, speed, and status."""
    result = await _rpc("torrent-get", {
        "fields": ["id", "name", "status", "percentDone", "rateDownload", "rateUpload", "eta", "totalSize"]
    })
    torrents = result.get("arguments", {}).get("torrents", [])
    summary = [{"id": t["id"], "name": t["name"],
                "progress": f"{t['percentDone'] * 100:.1f}%",
                "status": _status_label(t.get("status", -1)),
                "download_speed": _format_speed(t.get("rateDownload", 0)),
                "eta": t.get("eta", -1)}
               for t in torrents]
    return json.dumps({"torrents": summary, "count": len(summary)})


@tool
async def transmission_add_torrent(url: str) -> str:
    """Add a torrent to Transmission by URL or magnet link.
    url: Torrent URL or magnet link
    """
    result = await _rpc("torrent-add", {"filename": url})
    added = result.get("arguments", {}).get("torrent-added")
    if added:
        return json.dumps({"status": "added", "name": added.get("name"), "id": added.get("id")})
    dup = result.get("arguments", {}).get("torrent-duplicate")
    if dup:
        return json.dumps({"status": "duplicate", "name": dup.get("name")})
    return json.dumps({"status": "error", "detail": str(result)[:300]})


@tool
async def transmission_pause_resume(torrent_id: int, action: str) -> str:
    """Pause or resume a torrent in Transmission.
    torrent_id: Torrent ID
    action: Action to take (pause or resume)
    """
    method = "torrent-stop" if action == "pause" else "torrent-start"
    result = await _rpc(method, {"ids": [torrent_id]})
    return json.dumps({"status": "ok", "action": action, "torrent_id": torrent_id, "result": result.get("result")})


def create_transmission_tools():
    return [transmission_get_torrents, transmission_add_torrent, transmission_pause_resume]
