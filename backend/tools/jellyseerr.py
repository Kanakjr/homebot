"""
Jellyseerr API tools for media requests.
"""

import json
import logging

import aiohttp
from langchain_core.tools import tool

import config

log = logging.getLogger("homebot.tools.jellyseerr")


def _headers() -> dict:
    return {"X-Api-Key": config.JELLYSEERR_API_KEY, "Content-Type": "application/json"}


@tool
async def jellyseerr_search(query: str) -> str:
    """Search for movies and TV shows on Jellyseerr.
    query: Movie or show name to search for
    """
    from urllib.parse import quote
    url = f"{config.JELLYSEERR_URL}/api/v1/search?query={quote(query)}&page=1&language=en"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers()) as resp:
            if resp.status == 200:
                data = await resp.json()
                results = data.get("results", [])
                summary = [{"id": r.get("id"), "title": r.get("title") or r.get("name"),
                            "media_type": r.get("mediaType"),
                            "year": (r.get("releaseDate") or r.get("firstAirDate") or "")[:4],
                            "overview": (r.get("overview") or "")[:150],
                            "status": r.get("mediaInfo", {}).get("status") if r.get("mediaInfo") else "not_requested"}
                           for r in results[:10]]
                return json.dumps({"results": summary, "count": len(summary)})
            return json.dumps({"error": f"HTTP {resp.status}"})


@tool
async def jellyseerr_request(media_id: int, media_type: str) -> str:
    """Submit a media request on Jellyseerr for a movie or TV show.
    media_id: Media ID from jellyseerr_search results
    media_type: Type of media (movie or tv)
    """
    url = f"{config.JELLYSEERR_URL}/api/v1/request"
    payload = {"mediaId": media_id, "mediaType": media_type}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=_headers(), json=payload) as resp:
            if resp.status in (200, 201):
                result = await resp.json()
                return json.dumps({"status": "requested", "id": result.get("id"),
                                   "media": result.get("media", {}).get("title")})
            text = await resp.text()
            return json.dumps({"error": f"HTTP {resp.status}", "detail": text[:300]})


def create_jellyseerr_tools():
    return [jellyseerr_search, jellyseerr_request]
