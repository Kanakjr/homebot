"""
Sonarr API tools for TV show management.
"""

import json
import logging

import aiohttp
from langchain_core.tools import tool

import config

log = logging.getLogger("homebot.tools.sonarr")


def _headers() -> dict:
    return {"X-Api-Key": config.SONARR_API_KEY, "Content-Type": "application/json"}


@tool
async def sonarr_search(query: str) -> str:
    """Search for TV shows on Sonarr.
    query: Show name to search for
    """
    url = f"{config.SONARR_URL}/api/v3/series/lookup"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers(), params={"term": query}) as resp:
            if resp.status == 200:
                results = await resp.json()
                summary = [{"title": r.get("title"), "year": r.get("year"), "tvdbId": r.get("tvdbId"),
                            "overview": (r.get("overview") or "")[:150], "status": r.get("status")}
                           for r in results[:10]]
                return json.dumps({"results": summary, "count": len(summary)})
            return json.dumps({"error": f"HTTP {resp.status}"})


@tool
async def sonarr_add_series(tvdb_id: int, quality_profile_id: int = 1, root_folder_path: str = "/data/tv") -> str:
    """Add a TV series to Sonarr for monitoring and automatic downloading.
    tvdb_id: TVDB ID of the show (from sonarr_search results)
    quality_profile_id: Quality profile ID (default 1)
    root_folder_path: Root folder for TV shows (default /data/tv)
    """
    lookup_url = f"{config.SONARR_URL}/api/v3/series/lookup"
    async with aiohttp.ClientSession() as session:
        async with session.get(lookup_url, headers=_headers(), params={"term": f"tvdb:{tvdb_id}"}) as resp:
            if resp.status != 200:
                return json.dumps({"error": f"Lookup failed: HTTP {resp.status}"})
            results = await resp.json()
            if not results:
                return json.dumps({"error": "Show not found"})
            show = results[0]

        show["qualityProfileId"] = quality_profile_id
        show["rootFolderPath"] = root_folder_path
        show["monitored"] = True
        show["addOptions"] = {"searchForMissingEpisodes": True}

        add_url = f"{config.SONARR_URL}/api/v3/series"
        async with session.post(add_url, headers=_headers(), json=show) as resp:
            if resp.status in (200, 201):
                result = await resp.json()
                return json.dumps({"status": "added", "title": result.get("title"), "id": result.get("id")})
            text = await resp.text()
            return json.dumps({"error": f"HTTP {resp.status}", "detail": text[:300]})


@tool
async def sonarr_get_queue() -> str:
    """Get the current Sonarr download queue."""
    url = f"{config.SONARR_URL}/api/v3/queue"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers()) as resp:
            if resp.status == 200:
                data = await resp.json()
                records = data.get("records", [])
                summary = [{"title": r.get("title"), "status": r.get("status"),
                            "size": r.get("size"), "sizeleft": r.get("sizeleft")}
                           for r in records[:20]]
                return json.dumps({"queue": summary, "count": len(summary)})
            return json.dumps({"error": f"HTTP {resp.status}"})


def create_sonarr_tools():
    return [sonarr_search, sonarr_add_series, sonarr_get_queue]
