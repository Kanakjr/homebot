"""Transmission RPC tools for torrent management."""

import json
import logging

import aiohttp

import config

log = logging.getLogger("deepagent.tools.transmission")


def _rpc_url() -> str:
    return f"{config.TRANSMISSION_URL}/transmission/rpc"


async def _rpc(method: str, arguments: dict | None = None) -> dict:
    headers = {"Content-Type": "application/json"}
    payload = {"method": method}
    if arguments:
        payload["arguments"] = arguments

    async with aiohttp.ClientSession() as session:
        async with session.post(_rpc_url(), headers=headers, json=payload) as resp:
            if resp.status == 409:
                csrf = resp.headers.get("X-Transmission-Session-Id", "")
                headers["X-Transmission-Session-Id"] = csrf
                async with session.post(_rpc_url(), headers=headers, json=payload) as resp2:
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


async def transmission_pause_resume(torrent_id: int, action: str) -> str:
    """Pause or resume a torrent in Transmission.
    torrent_id: Torrent ID
    action: Action to take (pause or resume)
    """
    method = "torrent-stop" if action == "pause" else "torrent-start"
    result = await _rpc(method, {"ids": [torrent_id]})
    return json.dumps({"status": "ok", "action": action, "torrent_id": torrent_id, "result": result.get("result")})


async def transmission_remove_torrent(torrent_id: int, delete_data: bool = False) -> str:
    """Remove a torrent from Transmission.
    torrent_id: Torrent ID to remove
    delete_data: If true, also delete the downloaded files from disk
    """
    result = await _rpc("torrent-remove", {
        "ids": [torrent_id],
        "delete-local-data": delete_data,
    })
    return json.dumps({
        "status": "ok",
        "action": "removed" if not delete_data else "removed_with_data",
        "torrent_id": torrent_id,
        "result": result.get("result"),
    })


async def transmission_set_alt_speed(enabled: bool, down_kbps: int = 0, up_kbps: int = 0) -> str:
    """Enable or disable Transmission alt-speed (turtle) mode for bandwidth limiting.
    enabled: True to enable speed limits, False to disable
    down_kbps: Download speed limit in KB/s (0 = keep current setting)
    up_kbps: Upload speed limit in KB/s (0 = keep current setting)
    """
    args: dict = {"alt-speed-enabled": enabled}
    if down_kbps > 0:
        args["alt-speed-down"] = down_kbps
    if up_kbps > 0:
        args["alt-speed-up"] = up_kbps
    result = await _rpc("session-set", args)
    return json.dumps({
        "status": "ok",
        "alt_speed_enabled": enabled,
        "down_limit_kbps": down_kbps or "unchanged",
        "up_limit_kbps": up_kbps or "unchanged",
        "result": result.get("result"),
    })


async def transmission_get_session_stats() -> str:
    """Get Transmission session and cumulative transfer statistics."""
    result = await _rpc("session-stats")
    stats = result.get("arguments", {})
    current = stats.get("current-stats", {})
    cumulative = stats.get("cumulative-stats", {})
    return json.dumps({
        "active_torrents": stats.get("activeTorrentCount", 0),
        "paused_torrents": stats.get("pausedTorrentCount", 0),
        "download_speed": _format_speed(stats.get("downloadSpeed", 0)),
        "upload_speed": _format_speed(stats.get("uploadSpeed", 0)),
        "session": {
            "downloaded_gb": round(current.get("downloadedBytes", 0) / 1073741824, 2),
            "uploaded_gb": round(current.get("uploadedBytes", 0) / 1073741824, 2),
        },
        "lifetime": {
            "downloaded_gb": round(cumulative.get("downloadedBytes", 0) / 1073741824, 2),
            "uploaded_gb": round(cumulative.get("uploadedBytes", 0) / 1073741824, 2),
        },
    })


async def transmission_set_priority(torrent_id: int, priority: str) -> str:
    """Set the bandwidth priority of a torrent in Transmission.
    torrent_id: Torrent ID
    priority: Priority level (low, normal, or high)
    """
    priority_map = {"low": -1, "normal": 0, "high": 1}
    pval = priority_map.get(priority.lower(), 0)
    result = await _rpc("torrent-set", {"ids": [torrent_id], "bandwidthPriority": pval})
    return json.dumps({"status": "ok", "torrent_id": torrent_id, "priority": priority, "result": result.get("result")})


async def transmission_get_free_space(path: str = "/data") -> str:
    """Check free disk space available to Transmission.
    path: Directory path to check (default: /data)
    """
    result = await _rpc("free-space", {"path": path})
    args = result.get("arguments", {})
    free_bytes = args.get("size-bytes", 0)
    total_bytes = args.get("total_size", 0)
    return json.dumps({
        "path": args.get("path", path),
        "free_gb": round(free_bytes / 1073741824, 2),
        "total_gb": round(total_bytes / 1073741824, 2) if total_bytes else "unknown",
    })


def get_transmission_tools():
    return [
        transmission_get_torrents,
        transmission_add_torrent,
        transmission_pause_resume,
        transmission_remove_torrent,
        transmission_set_alt_speed,
        transmission_get_session_stats,
        transmission_set_priority,
        transmission_get_free_space,
    ]
