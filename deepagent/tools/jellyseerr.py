"""Jellyseerr API tools for media requests."""

import json
import logging

import aiohttp

import config

log = logging.getLogger("deepagent.tools.jellyseerr")


def _headers() -> dict:
    return {"X-Api-Key": config.JELLYSEERR_API_KEY, "Content-Type": "application/json"}


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


async def jellyseerr_get_requests(status: str = "", count: int = 20) -> str:
    """List media requests on Jellyseerr.
    status: Filter by status: pending, approved, declined, available, processing (empty = all)
    count: Number of requests to return (default 20)
    """
    url = f"{config.JELLYSEERR_URL}/api/v1/request"
    params: dict = {"take": str(count), "sort": "modified", "sortDirection": "desc"}
    if status:
        params["filter"] = status
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers(), params=params) as resp:
            if resp.status != 200:
                return json.dumps({"error": f"HTTP {resp.status}"})
            data = await resp.json()
            results = data.get("results", [])
            summary = [{
                "id": r.get("id"),
                "type": r.get("type"),
                "status_code": r.get("status"),
                "media_title": r.get("media", {}).get("title") or r.get("media", {}).get("name"),
                "media_status": r.get("media", {}).get("status"),
                "requested_by": r.get("requestedBy", {}).get("displayName"),
                "created": r.get("createdAt"),
            } for r in results]
            return json.dumps({"requests": summary, "count": len(summary), "total": data.get("pageInfo", {}).get("results")})


async def jellyseerr_approve_decline(request_id: int, action: str) -> str:
    """Approve or decline a media request on Jellyseerr.
    request_id: Request ID (from jellyseerr_get_requests)
    action: Either 'approve' or 'decline'
    """
    url = f"{config.JELLYSEERR_URL}/api/v1/request/{request_id}/{action}"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=_headers()) as resp:
            if resp.status in (200, 201):
                result = await resp.json()
                return json.dumps({"status": "ok", "action": action, "request_id": request_id,
                                   "new_status": result.get("status")})
            text = await resp.text()
            return json.dumps({"error": f"HTTP {resp.status}", "detail": text[:300]})


async def jellyseerr_get_request_status(request_id: int) -> str:
    """Get the current status of a specific Jellyseerr media request.
    request_id: Request ID
    """
    url = f"{config.JELLYSEERR_URL}/api/v1/request/{request_id}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers()) as resp:
            if resp.status != 200:
                return json.dumps({"error": f"HTTP {resp.status}"})
            r = await resp.json()
            return json.dumps({
                "id": r.get("id"),
                "type": r.get("type"),
                "status_code": r.get("status"),
                "media_title": r.get("media", {}).get("title") or r.get("media", {}).get("name"),
                "media_status": r.get("media", {}).get("status"),
                "requested_by": r.get("requestedBy", {}).get("displayName"),
                "created": r.get("createdAt"),
                "updated": r.get("updatedAt"),
            })


def get_jellyseerr_tools():
    return [
        jellyseerr_search,
        jellyseerr_request,
        jellyseerr_get_requests,
        jellyseerr_approve_decline,
        jellyseerr_get_request_status,
    ]
