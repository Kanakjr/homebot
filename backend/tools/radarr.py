"""
Radarr API tools for movie management.
"""

import json
import logging

import aiohttp
from langchain_core.tools import tool

import config

log = logging.getLogger("homebot.tools.radarr")


def _headers() -> dict:
    return {"X-Api-Key": config.RADARR_API_KEY, "Content-Type": "application/json"}


@tool
async def radarr_search(query: str) -> str:
    """Search for movies on Radarr.
    query: Movie name to search for
    """
    url = f"{config.RADARR_URL}/api/v3/movie/lookup"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers(), params={"term": query}) as resp:
            if resp.status == 200:
                results = await resp.json()
                summary = [{"title": r.get("title"), "year": r.get("year"), "tmdbId": r.get("tmdbId"),
                            "overview": (r.get("overview") or "")[:150], "status": r.get("status"),
                            "hasFile": r.get("hasFile", False)}
                           for r in results[:10]]
                return json.dumps({"results": summary, "count": len(summary)})
            return json.dumps({"error": f"HTTP {resp.status}"})


@tool
async def radarr_add_movie(tmdb_id: int, quality_profile_id: int = 1, root_folder_path: str = "/data/movies") -> str:
    """Add a movie to Radarr for monitoring and automatic downloading.
    tmdb_id: TMDB ID of the movie (from radarr_search results)
    quality_profile_id: Quality profile ID (default 1)
    root_folder_path: Root folder for movies (default /data/movies)
    """
    lookup_url = f"{config.RADARR_URL}/api/v3/movie/lookup/tmdb"
    async with aiohttp.ClientSession() as session:
        async with session.get(lookup_url, headers=_headers(), params={"tmdbId": tmdb_id}) as resp:
            if resp.status != 200:
                return json.dumps({"error": f"Lookup failed: HTTP {resp.status}"})
            movie = await resp.json()
            if not movie:
                return json.dumps({"error": "Movie not found"})

        movie["qualityProfileId"] = quality_profile_id
        movie["rootFolderPath"] = root_folder_path
        movie["monitored"] = True
        movie["addOptions"] = {"searchForMovie": True}

        add_url = f"{config.RADARR_URL}/api/v3/movie"
        async with session.post(add_url, headers=_headers(), json=movie) as resp:
            if resp.status in (200, 201):
                result = await resp.json()
                return json.dumps({"status": "added", "title": result.get("title"), "id": result.get("id")})
            text = await resp.text()
            return json.dumps({"error": f"HTTP {resp.status}", "detail": text[:300]})


@tool
async def radarr_get_queue() -> str:
    """Get the current Radarr download queue."""
    url = f"{config.RADARR_URL}/api/v3/queue"
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


def create_radarr_tools():
    return [radarr_search, radarr_add_movie, radarr_get_queue]
