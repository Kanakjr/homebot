"""
Jellyfin API tools for media library browsing, search, and playback control.
"""

import json
import logging

import aiohttp
from langchain_core.tools import tool

import config

log = logging.getLogger("homebot.tools.jellyfin")


def _headers() -> dict:
    return {"X-Emby-Token": config.JELLYFIN_API_KEY, "Content-Type": "application/json"}


_user_id_cache: str | None = None


async def _get_user_id() -> str | None:
    """Discover the first Jellyfin user ID (cached after first call)."""
    global _user_id_cache
    if _user_id_cache:
        return _user_id_cache
    url = f"{config.JELLYFIN_URL}/Users"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers()) as resp:
            if resp.status == 200:
                users = await resp.json()
                if users:
                    _user_id_cache = users[0].get("Id")
                    return _user_id_cache
    return None


def _format_ticks(ticks: int | None) -> str:
    if not ticks:
        return ""
    seconds = ticks // 10_000_000
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m"
    return f"{m}m{s:02d}s"


@tool
async def jellyfin_search(query: str, media_type: str = "") -> str:
    """Search the Jellyfin media library.
    query: Search term (movie title, show name, artist, etc.)
    media_type: Filter by type: Movie, Series, Episode, Audio, MusicAlbum (empty = all)
    """
    url = f"{config.JELLYFIN_URL}/Items"
    params: dict = {
        "searchTerm": query,
        "Recursive": "true",
        "Fields": "Overview,Genres,RunTimeTicks,ProductionYear",
        "Limit": "15",
    }
    if media_type:
        params["IncludeItemTypes"] = media_type

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers(), params=params) as resp:
            if resp.status != 200:
                return json.dumps({"error": f"HTTP {resp.status}", "detail": (await resp.text())[:300]})
            data = await resp.json()
            items = data.get("Items", [])
            summary = [
                {
                    "id": it.get("Id"),
                    "name": it.get("Name"),
                    "type": it.get("Type"),
                    "year": it.get("ProductionYear"),
                    "duration": _format_ticks(it.get("RunTimeTicks")),
                    "genres": it.get("Genres", [])[:3],
                    "overview": (it.get("Overview") or "")[:150],
                }
                for it in items
            ]
            return json.dumps({"results": summary, "count": len(summary)})


@tool
async def jellyfin_get_libraries() -> str:
    """List all Jellyfin media libraries (movies, TV, music, etc.)."""
    url = f"{config.JELLYFIN_URL}/Library/VirtualFolders"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers()) as resp:
            if resp.status != 200:
                return json.dumps({"error": f"HTTP {resp.status}"})
            libraries = await resp.json()
            summary = [
                {
                    "name": lib.get("Name"),
                    "type": lib.get("CollectionType", "unknown"),
                    "item_id": lib.get("ItemId"),
                    "paths": lib.get("Locations", []),
                }
                for lib in libraries
            ]
            return json.dumps({"libraries": summary, "count": len(summary)})


@tool
async def jellyfin_get_latest(library_id: str = "", limit: int = 10) -> str:
    """Get recently added items from Jellyfin.
    library_id: Library/parent ID to filter (empty = all libraries)
    limit: Max items to return (default 10)
    """
    user_id = await _get_user_id()
    if not user_id:
        return json.dumps({"error": "Could not discover Jellyfin user ID"})
    url = f"{config.JELLYFIN_URL}/Users/{user_id}/Items/Latest"
    params: dict = {"Limit": str(limit), "Fields": "Overview,RunTimeTicks,ProductionYear"}
    if library_id:
        params["ParentId"] = library_id

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers(), params=params) as resp:
            if resp.status != 200:
                return json.dumps({"error": f"HTTP {resp.status}"})
            items = await resp.json()
            summary = [
                {
                    "id": it.get("Id"),
                    "name": it.get("Name"),
                    "type": it.get("Type"),
                    "year": it.get("ProductionYear"),
                    "duration": _format_ticks(it.get("RunTimeTicks")),
                }
                for it in items
            ]
            return json.dumps({"latest": summary, "count": len(summary)})


@tool
async def jellyfin_get_sessions() -> str:
    """Get active Jellyfin playback sessions (who is watching what)."""
    url = f"{config.JELLYFIN_URL}/Sessions"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers()) as resp:
            if resp.status != 200:
                return json.dumps({"error": f"HTTP {resp.status}"})
            sessions = await resp.json()
            active = []
            for s in sessions:
                now_playing = s.get("NowPlayingItem")
                entry = {
                    "device": s.get("DeviceName"),
                    "client": s.get("Client"),
                    "user": s.get("UserName"),
                }
                if now_playing:
                    entry["playing"] = now_playing.get("Name")
                    entry["type"] = now_playing.get("Type")
                    play_state = s.get("PlayState", {})
                    entry["paused"] = play_state.get("IsPaused", False)
                    entry["position"] = _format_ticks(play_state.get("PositionTicks"))
                active.append(entry)
            return json.dumps({"sessions": active, "count": len(active)})


@tool
async def jellyfin_system_info() -> str:
    """Get Jellyfin server system information (version, OS, etc.)."""
    url = f"{config.JELLYFIN_URL}/System/Info"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers()) as resp:
            if resp.status != 200:
                return json.dumps({"error": f"HTTP {resp.status}"})
            info = await resp.json()
            return json.dumps({
                "server_name": info.get("ServerName"),
                "version": info.get("Version"),
                "os": info.get("OperatingSystem"),
                "has_update": info.get("HasUpdateAvailable", False),
                "local_address": info.get("LocalAddress"),
            })


def create_jellyfin_tools():
    return [
        jellyfin_search,
        jellyfin_get_libraries,
        jellyfin_get_latest,
        jellyfin_get_sessions,
        jellyfin_system_info,
    ]
