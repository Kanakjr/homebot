"""
Prowlarr API tools for indexer management and torrent/usenet search.
"""

import json
import logging

import aiohttp
from langchain_core.tools import tool

import config

log = logging.getLogger("homebot.tools.prowlarr")


def _headers() -> dict:
    return {"X-Api-Key": config.PROWLARR_API_KEY, "Content-Type": "application/json"}


@tool
async def prowlarr_search(query: str, indexer_ids: str = "", categories: str = "") -> str:
    """Search across all Prowlarr indexers for torrents/usenet releases.
    Returns results with download_url (magnet link or torrent URL) ready for transmission_add_torrent.
    query: Search term (movie name, show name, etc.)
    indexer_ids: Comma-separated indexer IDs to search (empty = all)
    categories: Comma-separated category IDs to filter (e.g. 2000 for Movies, 5000 for TV)
    """
    url = f"{config.PROWLARR_URL}/api/v1/search"
    params: dict = {"query": query, "type": "search"}
    if indexer_ids:
        params["indexerIds"] = [int(x.strip()) for x in indexer_ids.split(",")]
    if categories:
        params["categories"] = [int(x.strip()) for x in categories.split(",")]

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers(), params=params) as resp:
            if resp.status != 200:
                return json.dumps({"error": f"HTTP {resp.status}", "detail": (await resp.text())[:300]})
            results = await resp.json()
            summary = []
            for r in results[:15]:
                download_url = r.get("downloadUrl", "")
                guid = r.get("guid", "")
                if not download_url and guid.startswith("magnet:"):
                    download_url = guid
                summary.append({
                    "title": r.get("title"),
                    "indexer": r.get("indexer"),
                    "size_mb": round(r.get("size", 0) / 1024 / 1024),
                    "seeders": r.get("seeders"),
                    "leechers": r.get("leechers"),
                    "download_url": download_url,
                    "categories": [c.get("name") for c in r.get("categories", [])],
                })
            return json.dumps({"results": summary, "count": len(summary)})


@tool
async def prowlarr_get_indexers() -> str:
    """List all configured indexers in Prowlarr with their status."""
    url = f"{config.PROWLARR_URL}/api/v1/indexer"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers()) as resp:
            if resp.status != 200:
                return json.dumps({"error": f"HTTP {resp.status}"})
            indexers = await resp.json()
            summary = [
                {
                    "id": i.get("id"),
                    "name": i.get("name"),
                    "protocol": i.get("protocol"),
                    "enable": i.get("enable"),
                    "priority": i.get("priority"),
                }
                for i in indexers
            ]
            return json.dumps({"indexers": summary, "count": len(summary)})


@tool
async def prowlarr_get_indexer_stats() -> str:
    """Get Prowlarr indexer statistics (queries, grabs, failures)."""
    url = f"{config.PROWLARR_URL}/api/v1/indexerstats"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers()) as resp:
            if resp.status != 200:
                return json.dumps({"error": f"HTTP {resp.status}"})
            data = await resp.json()
            indexers = data.get("indexers", [])
            summary = [
                {
                    "name": i.get("indexerName"),
                    "queries": i.get("numberOfQueries", 0),
                    "grabs": i.get("numberOfGrabs", 0),
                    "failures": i.get("numberOfFailedQueries", 0),
                }
                for i in indexers
            ]
            return json.dumps({"stats": summary, "count": len(summary)})


def create_prowlarr_tools():
    return [prowlarr_search, prowlarr_get_indexers, prowlarr_get_indexer_stats]
