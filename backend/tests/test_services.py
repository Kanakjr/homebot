"""
Test connectivity and basic operations for media services:
  - Transmission (torrent management)
  - Jellyseerr (media requests)
  - Prowlarr (indexer search)
  - Jellyfin (media library)

Usage:
    python tests/test_services.py              # run all
    python tests/test_services.py transmission # run one service
    python tests/test_services.py jellyfin prowlarr  # run specific services
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import aiohttp
import config

PASS = 0
FAIL = 0
SKIP = 0


def ok(label: str, detail: str = ""):
    global PASS
    PASS += 1
    extra = f"  ({detail})" if detail else ""
    print(f"  [PASS] {label}{extra}")


def fail(label: str, detail: str = ""):
    global FAIL
    FAIL += 1
    extra = f"  ({detail})" if detail else ""
    print(f"  [FAIL] {label}{extra}")


def skip(label: str, reason: str = ""):
    global SKIP
    SKIP += 1
    extra = f"  ({reason})" if reason else ""
    print(f"  [SKIP] {label}{extra}")


# ── Transmission ──────────────────────────────────────────────

async def test_transmission():
    print("\n" + "=" * 60)
    print("TRANSMISSION")
    print(f"  URL: {config.TRANSMISSION_URL}")
    print("=" * 60)

    from tools.transmission import _rpc

    # Test 1: session-get (basic connectivity)
    try:
        result = await _rpc("session-get")
        if result.get("result") == "success":
            args = result.get("arguments", {})
            ok("session-get", f"version={args.get('version')}, download_dir={args.get('download-dir')}")
        else:
            fail("session-get", str(result)[:200])
            return
    except Exception as e:
        fail("session-get", str(e))
        return

    # Test 2: torrent-get (list torrents)
    try:
        result = await _rpc("torrent-get", {
            "fields": ["id", "name", "status", "percentDone", "rateDownload", "totalSize"]
        })
        torrents = result.get("arguments", {}).get("torrents", [])
        ok("torrent-get", f"{len(torrents)} torrents")
        for t in torrents[:5]:
            pct = f"{t['percentDone'] * 100:.0f}%"
            size_mb = t.get("totalSize", 0) // (1024 * 1024)
            print(f"    - {t['name'][:60]} [{pct}, {size_mb}MB]")
        if len(torrents) > 5:
            print(f"    ... and {len(torrents) - 5} more")
    except Exception as e:
        fail("torrent-get", str(e))

    # Test 3: session-stats
    try:
        result = await _rpc("session-stats")
        if result.get("result") == "success":
            stats = result.get("arguments", {})
            current = stats.get("current-stats", {})
            ok("session-stats",
               f"uploaded={current.get('uploadedBytes', 0) // (1024**3)}GB, "
               f"downloaded={current.get('downloadedBytes', 0) // (1024**3)}GB")
        else:
            fail("session-stats", str(result)[:200])
    except Exception as e:
        fail("session-stats", str(e))

    # Test 4: LangChain tool wrapper
    try:
        from tools.transmission import transmission_get_torrents
        result = await transmission_get_torrents.ainvoke({})
        data = json.loads(result)
        if "torrents" in data:
            ok("tool: transmission_get_torrents", f"{data['count']} torrents")
        else:
            fail("tool: transmission_get_torrents", str(data)[:200])
    except Exception as e:
        fail("tool: transmission_get_torrents", str(e))


# ── Jellyseerr ────────────────────────────────────────────────

async def test_jellyseerr():
    print("\n" + "=" * 60)
    print("JELLYSEERR")
    print(f"  URL: {config.JELLYSEERR_URL}")
    print(f"  API Key: {'set' if config.JELLYSEERR_API_KEY else 'MISSING'}")
    print("=" * 60)

    if not config.JELLYSEERR_API_KEY:
        skip("all", "JELLYSEERR_API_KEY not set")
        return

    headers = {"X-Api-Key": config.JELLYSEERR_API_KEY}

    # Test 1: health/status
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{config.JELLYSEERR_URL}/api/v1/status", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    ok("status", f"version={data.get('version')}, commit={data.get('commitTag', '')[:8]}")
                else:
                    fail("status", f"HTTP {resp.status}")
                    return
    except Exception as e:
        fail("status", str(e))
        return

    # Test 2: search
    try:
        from urllib.parse import quote
        async with aiohttp.ClientSession() as session:
            url = f"{config.JELLYSEERR_URL}/api/v1/search?query={quote('Breaking Bad')}&page=1&language=en"
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", [])
                    ok("search 'Breaking Bad'", f"{len(results)} results")
                    for r in results[:3]:
                        title = r.get("title") or r.get("name")
                        year = (r.get("releaseDate") or r.get("firstAirDate") or "")[:4]
                        mtype = r.get("mediaType")
                        print(f"    - {title} ({year}) [{mtype}]")
                else:
                    fail("search", f"HTTP {resp.status}")
    except Exception as e:
        fail("search", str(e))

    # Test 3: request count
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{config.JELLYSEERR_URL}/api/v1/request/count", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    ok("request count",
                       f"total={data.get('total', 0)}, pending={data.get('pending', 0)}, "
                       f"approved={data.get('approved', 0)}")
                else:
                    fail("request count", f"HTTP {resp.status}")
    except Exception as e:
        fail("request count", str(e))

    # Test 4: LangChain tool wrapper
    try:
        from tools.jellyseerr import jellyseerr_search
        result = await jellyseerr_search.ainvoke({"query": "Inception"})
        data = json.loads(result)
        if "results" in data:
            ok("tool: jellyseerr_search", f"{data['count']} results")
        else:
            fail("tool: jellyseerr_search", str(data)[:200])
    except Exception as e:
        fail("tool: jellyseerr_search", str(e))


# ── Prowlarr ──────────────────────────────────────────────────

async def test_prowlarr():
    print("\n" + "=" * 60)
    print("PROWLARR")
    print(f"  URL: {config.PROWLARR_URL}")
    print(f"  API Key: {'set' if config.PROWLARR_API_KEY else 'MISSING'}")
    print("=" * 60)

    if not config.PROWLARR_API_KEY:
        skip("all", "PROWLARR_API_KEY not set")
        return

    headers = {"X-Api-Key": config.PROWLARR_API_KEY}

    # Test 1: system status
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{config.PROWLARR_URL}/api/v1/system/status", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    ok("system/status", f"version={data.get('version')}, os={data.get('osName')}")
                else:
                    fail("system/status", f"HTTP {resp.status}")
                    return
    except Exception as e:
        fail("system/status", str(e))
        return

    # Test 2: list indexers
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{config.PROWLARR_URL}/api/v1/indexer", headers=headers) as resp:
                if resp.status == 200:
                    indexers = await resp.json()
                    enabled = [i for i in indexers if i.get("enable")]
                    ok("indexers", f"{len(indexers)} total, {len(enabled)} enabled")
                    for idx in indexers[:5]:
                        status = "enabled" if idx.get("enable") else "disabled"
                        print(f"    - {idx['name']} ({idx.get('protocol')}) [{status}]")
                    if len(indexers) > 5:
                        print(f"    ... and {len(indexers) - 5} more")
                else:
                    fail("indexers", f"HTTP {resp.status}")
    except Exception as e:
        fail("indexers", str(e))

    # Test 3: indexer stats
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{config.PROWLARR_URL}/api/v1/indexerstats", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    stats = data.get("indexers", [])
                    ok("indexer stats", f"{len(stats)} indexers with stats")
                    for s in stats[:3]:
                        print(f"    - {s.get('indexerName')}: {s.get('numberOfQueries', 0)} queries, "
                              f"{s.get('numberOfGrabs', 0)} grabs")
                else:
                    fail("indexer stats", f"HTTP {resp.status}")
    except Exception as e:
        fail("indexer stats", str(e))

    # Test 4: search (only if indexers exist)
    try:
        from tools.prowlarr import prowlarr_search
        result = await prowlarr_search.ainvoke({"query": "ubuntu"})
        data = json.loads(result)
        if "results" in data:
            ok("tool: prowlarr_search", f"{data['count']} results")
            for r in data["results"][:3]:
                seeders = r.get("seeders", "?")
                size = r.get("size_mb", 0)
                print(f"    - {r['title'][:60]} [{size}MB, {seeders} seeds]")
        elif "error" in data:
            skip("tool: prowlarr_search", data["error"])
        else:
            fail("tool: prowlarr_search", str(data)[:200])
    except Exception as e:
        fail("tool: prowlarr_search", str(e))

    # Test 5: LangChain tool wrappers
    try:
        from tools.prowlarr import prowlarr_get_indexers
        result = await prowlarr_get_indexers.ainvoke({})
        data = json.loads(result)
        if "indexers" in data:
            ok("tool: prowlarr_get_indexers", f"{data['count']} indexers")
        else:
            fail("tool: prowlarr_get_indexers", str(data)[:200])
    except Exception as e:
        fail("tool: prowlarr_get_indexers", str(e))


# ── Jellyfin ──────────────────────────────────────────────────

async def test_jellyfin():
    print("\n" + "=" * 60)
    print("JELLYFIN")
    print(f"  URL: {config.JELLYFIN_URL}")
    print(f"  API Key: {'set' if config.JELLYFIN_API_KEY else 'MISSING'}")
    print("=" * 60)

    if not config.JELLYFIN_API_KEY:
        skip("all", "JELLYFIN_API_KEY not set")
        return

    headers = {"X-Emby-Token": config.JELLYFIN_API_KEY}

    # Test 1: system info
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{config.JELLYFIN_URL}/System/Info", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    ok("System/Info",
                       f"name={data.get('ServerName')}, version={data.get('Version')}, "
                       f"os={data.get('OperatingSystem')}")
                else:
                    fail("System/Info", f"HTTP {resp.status}")
                    return
    except Exception as e:
        fail("System/Info", str(e))
        return

    # Test 2: libraries
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{config.JELLYFIN_URL}/Library/VirtualFolders", headers=headers) as resp:
                if resp.status == 200:
                    libraries = await resp.json()
                    ok("libraries", f"{len(libraries)} libraries")
                    for lib in libraries:
                        ctype = lib.get("CollectionType", "unknown")
                        paths = lib.get("Locations", [])
                        print(f"    - {lib['Name']} ({ctype}) [{', '.join(paths)}]")
                else:
                    fail("libraries", f"HTTP {resp.status}")
    except Exception as e:
        fail("libraries", str(e))

    # Test 3: search
    try:
        async with aiohttp.ClientSession() as session:
            params = {"searchTerm": "movie", "Recursive": "true", "Limit": "5",
                      "Fields": "Overview,ProductionYear"}
            async with session.get(f"{config.JELLYFIN_URL}/Items", headers=headers, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    items = data.get("Items", [])
                    total = data.get("TotalRecordCount", len(items))
                    ok("search 'movie'", f"{len(items)} shown, {total} total")
                    for it in items[:5]:
                        year = it.get("ProductionYear", "")
                        print(f"    - {it['Name']} ({year}) [{it.get('Type')}]")
                else:
                    fail("search", f"HTTP {resp.status}")
    except Exception as e:
        fail("search", str(e))

    # Test 4: active sessions
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{config.JELLYFIN_URL}/Sessions", headers=headers) as resp:
                if resp.status == 200:
                    sessions = await resp.json()
                    playing = [s for s in sessions if s.get("NowPlayingItem")]
                    ok("sessions", f"{len(sessions)} total, {len(playing)} playing")
                    for s in sessions[:3]:
                        device = s.get("DeviceName", "?")
                        user = s.get("UserName", "?")
                        now = s.get("NowPlayingItem")
                        if now:
                            print(f"    - {user}@{device}: playing {now.get('Name')}")
                        else:
                            print(f"    - {user}@{device}: idle")
                else:
                    fail("sessions", f"HTTP {resp.status}")
    except Exception as e:
        fail("sessions", str(e))

    # Test 5: latest items (requires user ID)
    try:
        from tools.jellyfin import _get_user_id
        user_id = await _get_user_id()
        if not user_id:
            skip("latest items", "could not discover user ID")
        async with aiohttp.ClientSession() as session:
            params = {"Limit": "5", "Fields": "ProductionYear"}
            async with session.get(f"{config.JELLYFIN_URL}/Users/{user_id}/Items/Latest", headers=headers, params=params) as resp:
                if resp.status == 200:
                    items = await resp.json()
                    ok("latest items", f"{len(items)} items")
                    for it in items[:5]:
                        year = it.get("ProductionYear", "")
                        print(f"    - {it['Name']} ({year}) [{it.get('Type')}]")
                else:
                    fail("latest items", f"HTTP {resp.status}")
    except Exception as e:
        fail("latest items", str(e))

    # Test 6: LangChain tool wrappers
    try:
        from tools.jellyfin import jellyfin_system_info
        result = await jellyfin_system_info.ainvoke({})
        data = json.loads(result)
        if "server_name" in data:
            ok("tool: jellyfin_system_info", f"{data['server_name']} v{data['version']}")
        else:
            fail("tool: jellyfin_system_info", str(data)[:200])
    except Exception as e:
        fail("tool: jellyfin_system_info", str(e))

    try:
        from tools.jellyfin import jellyfin_get_libraries
        result = await jellyfin_get_libraries.ainvoke({})
        data = json.loads(result)
        if "libraries" in data:
            ok("tool: jellyfin_get_libraries", f"{data['count']} libraries")
        else:
            fail("tool: jellyfin_get_libraries", str(data)[:200])
    except Exception as e:
        fail("tool: jellyfin_get_libraries", str(e))

    try:
        from tools.jellyfin import jellyfin_get_sessions
        result = await jellyfin_get_sessions.ainvoke({})
        data = json.loads(result)
        if "sessions" in data:
            ok("tool: jellyfin_get_sessions", f"{data['count']} sessions")
        else:
            fail("tool: jellyfin_get_sessions", str(data)[:200])
    except Exception as e:
        fail("tool: jellyfin_get_sessions", str(e))


# ── Runner ────────────────────────────────────────────────────

SERVICE_MAP = {
    "transmission": test_transmission,
    "jellyseerr": test_jellyseerr,
    "prowlarr": test_prowlarr,
    "jellyfin": test_jellyfin,
}


async def main():
    requested = [a.lower() for a in sys.argv[1:]]
    if requested:
        tests = [(name, SERVICE_MAP[name]) for name in requested if name in SERVICE_MAP]
        unknown = [name for name in requested if name not in SERVICE_MAP]
        if unknown:
            print(f"Unknown services: {', '.join(unknown)}")
            print(f"Available: {', '.join(SERVICE_MAP.keys())}")
            sys.exit(1)
    else:
        tests = list(SERVICE_MAP.items())

    print("=" * 60)
    print("HomeBotAI Service Tests")
    print("=" * 60)

    for name, test_fn in tests:
        await test_fn()

    print("\n" + "=" * 60)
    total = PASS + FAIL + SKIP
    print(f"Results: {PASS} passed, {FAIL} failed, {SKIP} skipped (of {total})")
    print("=" * 60)

    sys.exit(1 if FAIL > 0 else 0)


if __name__ == "__main__":
    asyncio.run(main())
