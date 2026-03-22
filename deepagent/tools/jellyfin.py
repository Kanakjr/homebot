"""Jellyfin API tools for media library browsing, search, and playback info."""

import json
import logging

import aiohttp

import config

log = logging.getLogger("deepagent.tools.jellyfin")


def _headers() -> dict:
    return {"X-Emby-Token": config.JELLYFIN_API_KEY, "Content-Type": "application/json"}


_user_id_cache: str | None = None


async def _get_user_id() -> str | None:
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
                    "id": s.get("Id"),
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


async def jellyfin_playback_control(session_id: str, command: str) -> str:
    """Control playback on an active Jellyfin session (play, pause, stop, next, previous).
    session_id: Session ID from jellyfin_get_sessions (use the 'id' field)
    command: One of: PlayPause, Stop, NextTrack, PreviousTrack, Seek, Rewind, FastForward
    """
    url = f"{config.JELLYFIN_URL}/Sessions/{session_id}/Playing/{command}"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=_headers()) as resp:
            if resp.status in (200, 204):
                return json.dumps({"status": "ok", "command": command, "session_id": session_id})
            text = await resp.text()
            return json.dumps({"error": f"HTTP {resp.status}", "detail": text[:300]})


async def jellyfin_mark_played(item_id: str, played: bool = True) -> str:
    """Mark a Jellyfin item as watched or unwatched.
    item_id: Jellyfin item ID (from jellyfin_search results)
    played: True to mark as watched, False to mark as unwatched
    """
    user_id = await _get_user_id()
    if not user_id:
        return json.dumps({"error": "Could not discover Jellyfin user ID"})

    url = f"{config.JELLYFIN_URL}/Users/{user_id}/PlayedItems/{item_id}"
    async with aiohttp.ClientSession() as session:
        if played:
            async with session.post(url, headers=_headers()) as resp:
                if resp.status == 200:
                    return json.dumps({"status": "ok", "item_id": item_id, "played": True})
                text = await resp.text()
                return json.dumps({"error": f"HTTP {resp.status}", "detail": text[:300]})
        else:
            async with session.delete(url, headers=_headers()) as resp:
                if resp.status == 200:
                    return json.dumps({"status": "ok", "item_id": item_id, "played": False})
                text = await resp.text()
                return json.dumps({"error": f"HTTP {resp.status}", "detail": text[:300]})


async def jellyfin_get_item_details(item_id: str) -> str:
    """Get detailed information about a specific Jellyfin item (movie, episode, album).
    item_id: Jellyfin item ID
    """
    user_id = await _get_user_id()
    if not user_id:
        return json.dumps({"error": "Could not discover Jellyfin user ID"})

    url = f"{config.JELLYFIN_URL}/Users/{user_id}/Items/{item_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers()) as resp:
            if resp.status != 200:
                return json.dumps({"error": f"HTTP {resp.status}"})
            it = await resp.json()
            return json.dumps({
                "id": it.get("Id"),
                "name": it.get("Name"),
                "type": it.get("Type"),
                "year": it.get("ProductionYear"),
                "duration": _format_ticks(it.get("RunTimeTicks")),
                "genres": it.get("Genres", []),
                "overview": (it.get("Overview") or "")[:500],
                "community_rating": it.get("CommunityRating"),
                "official_rating": it.get("OfficialRating"),
                "studios": [s.get("Name") for s in it.get("Studios", [])],
                "people": [{"name": p.get("Name"), "role": p.get("Role") or p.get("Type")}
                           for p in it.get("People", [])[:10]],
                "played": it.get("UserData", {}).get("Played", False),
                "play_count": it.get("UserData", {}).get("PlayCount", 0),
            })


async def jellyfin_get_resume() -> str:
    """Get the 'Continue Watching' list from Jellyfin (items with partial progress)."""
    user_id = await _get_user_id()
    if not user_id:
        return json.dumps({"error": "Could not discover Jellyfin user ID"})

    url = f"{config.JELLYFIN_URL}/Users/{user_id}/Items/Resume"
    params = {"Limit": "15", "Fields": "Overview,RunTimeTicks,ProductionYear"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers(), params=params) as resp:
            if resp.status != 200:
                return json.dumps({"error": f"HTTP {resp.status}"})
            data = await resp.json()
            items = data.get("Items", [])
            summary = [{
                "id": it.get("Id"),
                "name": it.get("Name"),
                "type": it.get("Type"),
                "series": it.get("SeriesName"),
                "season": it.get("ParentIndexNumber"),
                "episode": it.get("IndexNumber"),
                "duration": _format_ticks(it.get("RunTimeTicks")),
                "progress": _format_ticks(it.get("UserData", {}).get("PlaybackPositionTicks")),
                "percent": round(it.get("UserData", {}).get("PlayedPercentage", 0), 1),
            } for it in items]
            return json.dumps({"resume": summary, "count": len(summary)})


def get_jellyfin_tools():
    return [
        jellyfin_search,
        jellyfin_get_libraries,
        jellyfin_get_latest,
        jellyfin_get_sessions,
        jellyfin_system_info,
        jellyfin_playback_control,
        jellyfin_mark_played,
        jellyfin_get_item_details,
        jellyfin_get_resume,
    ]
