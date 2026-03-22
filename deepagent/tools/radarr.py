"""Radarr API tools for movie management."""

import json
import logging

import aiohttp

import config

log = logging.getLogger("deepagent.tools.radarr")


def _headers() -> dict:
    return {"X-Api-Key": config.RADARR_API_KEY, "Content-Type": "application/json"}


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


async def radarr_get_movies() -> str:
    """List all monitored movies in Radarr with download status."""
    url = f"{config.RADARR_URL}/api/v3/movie"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers()) as resp:
            if resp.status != 200:
                return json.dumps({"error": f"HTTP {resp.status}"})
            movies = await resp.json()
            summary = [{
                "id": m.get("id"),
                "title": m.get("title"),
                "year": m.get("year"),
                "status": m.get("status"),
                "monitored": m.get("monitored"),
                "has_file": m.get("hasFile", False),
                "size_gb": round(m.get("sizeOnDisk", 0) / 1073741824, 1),
                "quality": m.get("movieFile", {}).get("quality", {}).get("quality", {}).get("name") if m.get("movieFile") else None,
            } for m in movies]
            return json.dumps({"movies": summary, "count": len(summary)})


async def radarr_get_calendar(start_date: str = "", end_date: str = "") -> str:
    """Get upcoming movie releases from Radarr calendar.
    start_date: Start date in YYYY-MM-DD format (default: today)
    end_date: End date in YYYY-MM-DD format (default: 30 days from start)
    """
    from datetime import date, timedelta
    if not start_date:
        start_date = date.today().isoformat()
    if not end_date:
        end_date = (date.fromisoformat(start_date) + timedelta(days=30)).isoformat()

    url = f"{config.RADARR_URL}/api/v3/calendar"
    params = {"start": start_date, "end": end_date}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers(), params=params) as resp:
            if resp.status != 200:
                return json.dumps({"error": f"HTTP {resp.status}"})
            movies = await resp.json()
            summary = [{
                "title": m.get("title"),
                "year": m.get("year"),
                "release_date": m.get("digitalRelease") or m.get("physicalRelease") or m.get("inCinemas"),
                "status": m.get("status"),
                "has_file": m.get("hasFile", False),
                "monitored": m.get("monitored"),
            } for m in movies]
            return json.dumps({"upcoming": summary, "count": len(summary)})


async def radarr_delete_movie(movie_id: int, delete_files: bool = False) -> str:
    """Delete a movie from Radarr.
    movie_id: Radarr movie ID (from radarr_get_movies)
    delete_files: If true, also delete the downloaded movie file from disk
    """
    url = f"{config.RADARR_URL}/api/v3/movie/{movie_id}"
    params = {"deleteFiles": str(delete_files).lower()}
    async with aiohttp.ClientSession() as session:
        async with session.delete(url, headers=_headers(), params=params) as resp:
            if resp.status in (200, 204):
                return json.dumps({"status": "deleted", "movie_id": movie_id, "files_deleted": delete_files})
            text = await resp.text()
            return json.dumps({"error": f"HTTP {resp.status}", "detail": text[:300]})


async def radarr_movie_search(movie_id: int) -> str:
    """Trigger a manual search for a specific movie in Radarr.
    movie_id: Radarr movie ID
    """
    url = f"{config.RADARR_URL}/api/v3/command"
    payload = {"name": "MoviesSearch", "movieIds": [movie_id]}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=_headers(), json=payload) as resp:
            if resp.status in (200, 201):
                result = await resp.json()
                return json.dumps({"status": "search_started", "command_id": result.get("id"), "movie_id": movie_id})
            text = await resp.text()
            return json.dumps({"error": f"HTTP {resp.status}", "detail": text[:300]})


async def radarr_get_history(limit: int = 20) -> str:
    """Get recent Radarr download history.
    limit: Number of records to return (default 20)
    """
    url = f"{config.RADARR_URL}/api/v3/history"
    params = {"pageSize": str(limit), "sortKey": "date", "sortDirection": "descending",
              "includeMovie": "true"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=_headers(), params=params) as resp:
            if resp.status != 200:
                return json.dumps({"error": f"HTTP {resp.status}"})
            data = await resp.json()
            records = data.get("records", [])
            summary = [{
                "movie": r.get("movie", {}).get("title"),
                "event": r.get("eventType"),
                "quality": r.get("quality", {}).get("quality", {}).get("name"),
                "date": r.get("date"),
                "source": r.get("sourceTitle"),
            } for r in records]
            return json.dumps({"history": summary, "count": len(summary)})


def get_radarr_tools():
    return [
        radarr_search, radarr_add_movie, radarr_get_queue,
        radarr_get_movies, radarr_get_calendar, radarr_delete_movie,
        radarr_movie_search, radarr_get_history,
    ]
