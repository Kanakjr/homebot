# API reference

HomeBotAI exposes a REST API on **port 8321** (default). The tables below list **65+** HTTP routes grouped by domain. Interactive OpenAPI documentation is available at [http://localhost:8321/docs](http://localhost:8321/docs).

## Authentication

When the backend is started with `API_KEY` set, protected routes require the header:

| Header | Description |
|--------|-------------|
| `X-API-Key` | Must match the configured API key |

If `API_KEY` is not set, requests are accepted without this header.

## SSE stream events (`/api/chat/stream`)

Server-Sent Events carry JSON payloads. Common event types:

| Event type | Description |
|------------|-------------|
| `thinking` | Model reasoning or intermediate status |
| `tool_call` | A tool invocation was requested |
| `tool_result` | Result returned from a tool |
| `response` | Partial or final assistant text |
| `error` | An error occurred |
| `done` | Stream completed |

## Examples

Blocking chat:

```bash
curl -s -X POST http://localhost:8321/api/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"message": "What is the weather?"}'
```

Streaming chat (SSE):

```bash
curl -sN -X POST http://localhost:8321/api/chat/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"message": "List my lights"}'
```

Omit `-H "X-API-Key: ..."` when no API key is configured.

---

## Endpoints by domain

??? "Chat"

    | Method | Path | Description |
    |--------|------|-------------|
    | POST | `/api/chat` | Blocking chat; returns full response and tool calls |
    | POST | `/api/chat/stream` | SSE stream of real-time events |
    | GET | `/api/chat/threads` | List conversation threads |
    | GET | `/api/chat/{id}/history` | Get message history for a thread |
    | DELETE | `/api/chat/{id}/history` | Clear a thread's history |

??? "System"

    | Method | Path | Description |
    |--------|------|-------------|
    | GET | `/api/health` | System status (tools, entities, model) |
    | GET | `/api/health/data` | Health metrics time series |
    | GET | `/api/models` | Available LLM models |
    | GET | `/api/tools` | List all registered tools |

??? "Skills"

    | Method | Path | Description |
    |--------|------|-------------|
    | GET | `/api/skills` | List learned skills |
    | POST | `/api/skills` | Create a new skill |
    | GET | `/api/skills/{id}` | Get one skill by ID |
    | PUT | `/api/skills/{id}` | Update a skill |
    | DELETE | `/api/skills/{id}` | Delete a skill |
    | POST | `/api/skills/{id}/toggle` | Enable or disable a skill |
    | POST | `/api/skills/{id}/execute` | Execute a skill on demand |

??? "Entities"

    | Method | Path | Description |
    |--------|------|-------------|
    | GET | `/api/entities` | Home Assistant entities grouped by domain |
    | POST | `/api/entities/{id}/toggle` | Toggle a switch, light, fan, or scene |
    | POST | `/api/entities/{id}/light` | Set light brightness, color, and color temperature |
    | POST | `/api/entities/{id}/climate` | Set climate preset, fan mode, and temperature |

??? "Events"

    | Method | Path | Description |
    |--------|------|-------------|
    | GET | `/api/events` | Event log with time filtering |

??? "Memory"

    | Method | Path | Description |
    |--------|------|-------------|
    | GET | `/api/memory` | Semantic memory facts |
    | POST | `/api/memory` | Store a memory fact |
    | DELETE | `/api/memory/{key}` | Delete a memory fact |

??? "Cameras"

    | Method | Path | Description |
    |--------|------|-------------|
    | POST | `/api/cameras/{id}/snapshot` | Request a camera snapshot |
    | GET | `/api/snapshots/{filename}` | Serve a saved snapshot image |

??? "Dashboard"

    | Method | Path | Description |
    |--------|------|-------------|
    | GET | `/api/dashboard` | Dashboard widget configuration |
    | PUT | `/api/dashboard` | Save dashboard configuration |
    | POST | `/api/dashboard/edit` | AI-assisted layout edits from natural language |
    | GET | `/api/dashboard/summary` | AI-generated home summary |
    | POST | `/api/dashboard/generate-widget` | Generate widget JSON from entities |
    | POST | `/api/dashboard/suggest-widget` | Suggest widget title and description |

??? "Network"

    | Method | Path | Description |
    |--------|------|-------------|
    | GET | `/api/network` | Network status: mesh nodes, clients, bandwidth |

??? "Energy"

    | Method | Path | Description |
    |--------|------|-------------|
    | GET | `/api/energy` | Energy sensors and historical power data |

??? "Analytics"

    | Method | Path | Description |
    |--------|------|-------------|
    | GET | `/api/analytics` | Historical analytics (energy, presence, network) |

??? "Reports"

    | Method | Path | Description |
    |--------|------|-------------|
    | GET | `/api/reports/summary` | Long-term report summaries |

??? "Scenes"

    | Method | Path | Description |
    |--------|------|-------------|
    | GET | `/api/scenes` | List saved scenes |
    | POST | `/api/scenes` | Create a scene (snapshot entity states) |
    | POST | `/api/scenes/{id}/activate` | Restore a scene's saved states |
    | DELETE | `/api/scenes/{id}` | Delete a scene |

??? "Floorplan"

    | Method | Path | Description |
    |--------|------|-------------|
    | GET | `/api/floorplan/config` | Floorplan device-to-SVG mapping |
    | PUT | `/api/floorplan/config` | Update floorplan configuration |

??? "Device aliases"

    | Method | Path | Description |
    |--------|------|-------------|
    | GET | `/api/devices/aliases` | Device name aliases |
    | PUT | `/api/devices/aliases/{mac}` | Set a device alias |
    | DELETE | `/api/devices/aliases/{mac}` | Delete a device alias |

??? "Notifications"

    | Method | Path | Description |
    |--------|------|-------------|
    | GET | `/api/notifications/rules` | Notification rule configurations |
    | PUT | `/api/notifications/rules/{id}` | Update a notification rule |

??? "Media"

    | Method | Path | Description |
    |--------|------|-------------|
    | GET | `/api/media/overview` | Media overview: now playing, downloads, queues |
    | GET | `/api/media/search` | Search across media services |
    | GET | `/api/media/downloads` | Active downloads from Transmission |
    | POST | `/api/media/downloads` | Add a torrent by URL or magnet link |
    | POST | `/api/media/downloads/{torrent_id}/action` | Pause or resume a torrent |
    | GET | `/api/media/tv` | Sonarr: series, queue, and upcoming calendar |
    | POST | `/api/media/tv` | Add a TV series to Sonarr |
    | GET | `/api/media/movies` | Radarr: movies and download queue |
    | POST | `/api/media/movies` | Add a movie to Radarr |
    | GET | `/api/media/library` | Jellyfin: libraries, sessions, and latest items |
    | GET | `/api/media/requests` | Jellyseerr: pending and recent requests |
    | POST | `/api/media/requests` | Submit a Jellyseerr media request |
    | GET | `/api/media/discover` | AI-powered media discovery |

??? "Server"

    | Method | Path | Description |
    |--------|------|-------------|
    | GET | `/api/server/containers` | Docker container listing |
    | GET | `/api/server/tunnel` | Cloudflare Tunnel routes |
    | POST | `/api/server/tunnel` | Add a tunnel route |
    | DELETE | `/api/server/tunnel/{subdomain}` | Remove a tunnel route |
    | GET | `/api/server/backups` | Backup status |

For request and response schemas, use the Swagger UI at [http://localhost:8321/docs](http://localhost:8321/docs).
