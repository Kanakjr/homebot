"""Sonarr API tools for TV show management."""

import json
import logging

import aiohttp

import config

log = logging.getLogger("deepagent.tools.sonarr")


def _headers() -> dict:
    return {"X-Api-Key": config.SONARR_API_KEY, "Content-Type": "application/json"}


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


async def sonarr_get_series() -> str:
    """List all monitored TV series in Sonarr with episode counts and status."""
    url = f"{config.SONARR_URL}/api/v3/series"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers()) as resp:
            if resp.status != 200:
                return json.dumps({"error": f"HTTP {resp.status}"})
            series = await resp.json()
            summary = [{
                "id": s.get("id"),
                "title": s.get("title"),
                "year": s.get("year"),
                "status": s.get("status"),
                "monitored": s.get("monitored"),
                "seasons": s.get("seasonCount"),
                "episodes_have": s.get("statistics", {}).get("episodeFileCount", 0),
                "episodes_total": s.get("statistics", {}).get("totalEpisodeCount", 0),
                "size_gb": round(s.get("statistics", {}).get("sizeOnDisk", 0) / 1073741824, 1),
            } for s in series]
            return json.dumps({"series": summary, "count": len(summary)})


async def sonarr_get_calendar(start_date: str = "", end_date: str = "") -> str:
    """Get upcoming TV episodes from Sonarr calendar.
    start_date: Start date in YYYY-MM-DD format (default: today)
    end_date: End date in YYYY-MM-DD format (default: 7 days from start)
    """
    from datetime import date, timedelta
    if not start_date:
        start_date = date.today().isoformat()
    if not end_date:
        end_date = (date.fromisoformat(start_date) + timedelta(days=7)).isoformat()

    url = f"{config.SONARR_URL}/api/v3/calendar"
    params = {"start": start_date, "end": end_date, "includeSeries": "true"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers(), params=params) as resp:
            if resp.status != 200:
                return json.dumps({"error": f"HTTP {resp.status}"})
            episodes = await resp.json()
            summary = [{
                "series": ep.get("series", {}).get("title"),
                "season": ep.get("seasonNumber"),
                "episode": ep.get("episodeNumber"),
                "title": ep.get("title"),
                "air_date": ep.get("airDate"),
                "has_file": ep.get("hasFile", False),
            } for ep in episodes]
            return json.dumps({"upcoming": summary, "count": len(summary)})


async def sonarr_delete_series(series_id: int, delete_files: bool = False) -> str:
    """Delete a TV series from Sonarr.
    series_id: Sonarr series ID (from sonarr_get_series)
    delete_files: If true, also delete downloaded episode files from disk
    """
    url = f"{config.SONARR_URL}/api/v3/series/{series_id}"
    params = {"deleteFiles": str(delete_files).lower()}
    async with aiohttp.ClientSession() as session:
        async with session.delete(url, headers=_headers(), params=params) as resp:
            if resp.status in (200, 204):
                return json.dumps({"status": "deleted", "series_id": series_id, "files_deleted": delete_files})
            text = await resp.text()
            return json.dumps({"error": f"HTTP {resp.status}", "detail": text[:300]})


async def sonarr_episode_search(series_id: int) -> str:
    """Trigger a search for all missing episodes of a series in Sonarr.
    series_id: Sonarr series ID
    """
    url = f"{config.SONARR_URL}/api/v3/command"
    payload = {"name": "SeriesSearch", "seriesId": series_id}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=_headers(), json=payload) as resp:
            if resp.status in (200, 201):
                result = await resp.json()
                return json.dumps({"status": "search_started", "command_id": result.get("id"), "series_id": series_id})
            text = await resp.text()
            return json.dumps({"error": f"HTTP {resp.status}", "detail": text[:300]})


async def sonarr_get_history(limit: int = 20) -> str:
    """Get recent Sonarr download history.
    limit: Number of records to return (default 20)
    """
    url = f"{config.SONARR_URL}/api/v3/history"
    params = {"pageSize": str(limit), "sortKey": "date", "sortDirection": "descending",
              "includeSeries": "true", "includeEpisode": "true"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers(), params=params) as resp:
            if resp.status != 200:
                return json.dumps({"error": f"HTTP {resp.status}"})
            data = await resp.json()
            records = data.get("records", [])
            summary = [{
                "series": r.get("series", {}).get("title"),
                "episode": r.get("episode", {}).get("title"),
                "season": r.get("episode", {}).get("seasonNumber"),
                "episode_num": r.get("episode", {}).get("episodeNumber"),
                "event": r.get("eventType"),
                "quality": r.get("quality", {}).get("quality", {}).get("name"),
                "date": r.get("date"),
            } for r in records]
            return json.dumps({"history": summary, "count": len(summary)})


def get_sonarr_tools():
    return [
        sonarr_search, sonarr_add_series, sonarr_get_queue,
        sonarr_get_series, sonarr_get_calendar, sonarr_delete_series,
        sonarr_episode_search, sonarr_get_history,
    ]
