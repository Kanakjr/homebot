---
name: media-management
description: Manage media -- search/add/delete movies and TV shows, check downloads and history, browse Jellyfin library, control playback, manage requests, check disk space. Use when the user asks about movies, TV shows, downloads, torrents, media playback, or requests.
tags: [media, sonarr, radarr, jellyfin, transmission, jellyseerr, prowlarr]
---

# Media Management

You have direct API tools for all media services. Use them instead of HA tools for media tasks.

## Tool-to-Task Mapping

### Sonarr (TV Shows)
| User wants to... | Tool |
|---|---|
| Search for a TV show | `sonarr_search(query="...")` |
| Add/download a show | `sonarr_add_series(tvdb_id=...)` (use tvdbId from search) |
| List all monitored shows | `sonarr_get_series()` |
| Check TV download queue | `sonarr_get_queue()` |
| See upcoming episodes this week | `sonarr_get_calendar()` |
| Delete a show | `sonarr_delete_series(series_id, delete_files=False)` |
| Re-search for missing episodes | `sonarr_episode_search(series_id)` |
| See recent TV download history | `sonarr_get_history()` |

### Radarr (Movies)
| User wants to... | Tool |
|---|---|
| Search for a movie | `radarr_search(query="...")` |
| Add/download a movie | `radarr_add_movie(tmdb_id=...)` (use tmdbId from search) |
| List all monitored movies | `radarr_get_movies()` |
| Check movie download queue | `radarr_get_queue()` |
| See upcoming movie releases | `radarr_get_calendar()` |
| Delete a movie | `radarr_delete_movie(movie_id, delete_files=False)` |
| Re-search for a movie | `radarr_movie_search(movie_id)` |
| See recent movie download history | `radarr_get_history()` |

### Transmission (Torrents)
| User wants to... | Tool |
|---|---|
| List active torrents | `transmission_get_torrents()` |
| Add a torrent | `transmission_add_torrent(url="magnet:...")` |
| Pause/resume a torrent | `transmission_pause_resume(torrent_id, "pause"/"resume")` |
| Remove a torrent | `transmission_remove_torrent(torrent_id, delete_data=False)` |
| Limit download speed | `transmission_set_alt_speed(enabled=True, down_kbps=500)` |
| Remove speed limits | `transmission_set_alt_speed(enabled=False)` |
| Get transfer stats | `transmission_get_session_stats()` |
| Set torrent priority | `transmission_set_priority(torrent_id, "high"/"normal"/"low")` |
| Check disk space | `transmission_get_free_space(path="/data")` |

### Jellyfin (Media Library)
| User wants to... | Tool |
|---|---|
| Search library | `jellyfin_search(query="...", media_type="Movie"/"Series")` |
| Recently added | `jellyfin_get_latest()` |
| Continue watching list | `jellyfin_get_resume()` |
| Who's watching? | `jellyfin_get_sessions()` |
| Pause/play on a device | `jellyfin_playback_control(session_id, "PlayPause"/"Stop")` |
| Mark as watched | `jellyfin_mark_played(item_id, played=True)` |
| Get movie/show details | `jellyfin_get_item_details(item_id)` |
| List libraries | `jellyfin_get_libraries()` |
| Server health | `jellyfin_system_info()` |

### Jellyseerr (Requests)
| User wants to... | Tool |
|---|---|
| Search for media to request | `jellyseerr_search(query="...")` |
| Submit a request | `jellyseerr_request(media_id, "movie"/"tv")` |
| List pending requests | `jellyseerr_get_requests(status="pending")` |
| Approve/decline a request | `jellyseerr_approve_decline(request_id, "approve"/"decline")` |
| Check a request's status | `jellyseerr_get_request_status(request_id)` |

### Prowlarr (Indexers)
| User wants to... | Tool |
|---|---|
| Search torrent indexers | `prowlarr_search(query="...")` |
| Grab a release | `prowlarr_grab_release(guid, indexer_id)` |
| List indexers | `prowlarr_get_indexers()` |
| Indexer stats | `prowlarr_get_indexer_stats()` |
| System health check | `prowlarr_get_health()` |

### HA Media Players
| User wants to... | Tool |
|---|---|
| Control HA media players | `ha_call_service(domain="media_player", ...)` |

## Common Workflows

**"Download this movie/show":**
1. `radarr_search("name")` or `sonarr_search("name")`
2. Confirm with user (show title, year, overview)
3. `radarr_add_movie(tmdb_id)` or `sonarr_add_series(tvdb_id)`

**"What's downloading?":**
`transmission_get_torrents()` -- one call gives all active torrents with progress and speed.

**"What's airing this week?":**
`sonarr_get_calendar()` -- returns upcoming episodes for the next 7 days.

**"Slow down downloads, I'm on a call":**
`transmission_set_alt_speed(enabled=True, down_kbps=200, up_kbps=50)`

**"What was I watching?":**
`jellyfin_get_resume()` -- returns partially-watched items with progress.

## Key Media Players (HA)

| Entity ID | Name |
|---|---|
| `media_player.kanaks_mac_mini_2` | Kanak's Mac mini |
| `media_player.spotify_kanak_dahake_jr` | Spotify |
| `media_player.kanak_xbox` | Kanak Xbox |

## Efficiency

- Use dedicated tools directly. Do NOT use ha_search_entities for media tasks.
- For "what's downloading?" one `transmission_get_torrents()` call is enough.
- Always present results with title, year, and a brief overview.
