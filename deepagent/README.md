# HomeBotAI Deep Agent

A standalone AI-powered smart home assistant built on [LangChain Deep Agents](https://python.langchain.com/docs/concepts/deep_agents/), providing conversational control over Home Assistant devices and a full media management stack (Sonarr, Radarr, Jellyfin, Transmission, Jellyseerr, Prowlarr).

The Deep Agent runs as an independent service with its own API, Docker container, and LLM configuration. It is designed to be used alongside the main HomeBotAI backend -- the dashboard chat interface includes a toggle to switch between the two.

## Architecture

```
Dashboard (Next.js)
    |
    |  POST /api/chat/stream  (SSE)
    v
Deep Agent API  (FastAPI, port 8322)
    |
    |-- agent.py        LangGraph agent with system prompt, skills, tools
    |-- tools/          43 async tool functions across 7 modules
    |-- skills/         4 SKILL.md files (progressive disclosure)
    |-- config.py       Environment-based configuration
    |
    +-- LLM: Gemini (google_genai via langchain-google-genai)
    +-- Backend: LocalShellBackend (filesystem + bash execution)
    +-- Checkpointer: MemorySaver (per-thread conversation memory)
```

The agent uses Server-Sent Events (SSE) to stream responses back to the client, emitting structured events for thinking indicators, tool calls, tool results, and the final natural-language response.

## Tools (43 total)

### Home Assistant (5 tools)

| Tool | Description |
|------|-------------|
| `ha_call_service` | Call any HA service (turn on/off lights, set temperature, activate scenes, etc.) |
| `ha_get_states` | Get current states of all entities, optionally filtered by domain |
| `ha_search_entities` | Search entities by name or entity_id substring |
| `ha_trigger_automation` | Manually trigger a Home Assistant automation |
| `ha_fire_event` | Fire a custom event on the Home Assistant event bus |

### Sonarr -- TV Shows (8 tools)

| Tool | Description |
|------|-------------|
| `sonarr_search` | Search for TV shows by name |
| `sonarr_add_series` | Add a show for monitoring and automatic download |
| `sonarr_get_queue` | Check the current download queue |
| `sonarr_get_series` | List all monitored series with episode counts and disk usage |
| `sonarr_get_calendar` | Get upcoming episodes for the next 7 days |
| `sonarr_delete_series` | Remove a series, optionally deleting files |
| `sonarr_episode_search` | Trigger a re-search for missing episodes |
| `sonarr_get_history` | View recent download/import/delete history |

### Radarr -- Movies (8 tools)

| Tool | Description |
|------|-------------|
| `radarr_search` | Search for movies by name |
| `radarr_add_movie` | Add a movie for monitoring and automatic download |
| `radarr_get_queue` | Check the current download queue |
| `radarr_get_movies` | List all monitored movies with file status |
| `radarr_get_calendar` | Get upcoming movie releases for the next 30 days |
| `radarr_delete_movie` | Remove a movie, optionally deleting files |
| `radarr_movie_search` | Trigger a manual search for a specific movie |
| `radarr_get_history` | View recent download history |

### Jellyfin -- Media Library (9 tools)

| Tool | Description |
|------|-------------|
| `jellyfin_search` | Search the media library (movies, shows, music) |
| `jellyfin_get_libraries` | List all libraries |
| `jellyfin_get_latest` | Get recently added items |
| `jellyfin_get_sessions` | See active playback sessions (who is watching what) |
| `jellyfin_system_info` | Get server version and health info |
| `jellyfin_playback_control` | Play, pause, stop, skip on an active session |
| `jellyfin_mark_played` | Mark an item as watched or unwatched |
| `jellyfin_get_item_details` | Get full details (cast, rating, genres, runtime) for an item |
| `jellyfin_get_resume` | Get the "Continue Watching" list with progress |

### Transmission -- Torrents (8 tools)

| Tool | Description |
|------|-------------|
| `transmission_get_torrents` | List all torrents with progress, speed, and status |
| `transmission_add_torrent` | Add a torrent by magnet link or URL |
| `transmission_pause_resume` | Pause or resume a torrent |
| `transmission_remove_torrent` | Remove a torrent, optionally deleting downloaded files |
| `transmission_set_alt_speed` | Enable/disable bandwidth limiting (turtle mode) |
| `transmission_get_session_stats` | Get session and lifetime transfer statistics |
| `transmission_set_priority` | Set bandwidth priority (low, normal, high) for a torrent |
| `transmission_get_free_space` | Check available disk space |

### Jellyseerr -- Media Requests (5 tools)

| Tool | Description |
|------|-------------|
| `jellyseerr_search` | Search for movies and shows to request |
| `jellyseerr_request` | Submit a media request |
| `jellyseerr_get_requests` | List requests, filtered by status (pending, approved, etc.) |
| `jellyseerr_approve_decline` | Approve or decline a pending request |
| `jellyseerr_get_request_status` | Check the status of a specific request |

### Prowlarr -- Indexers (5 tools)

| Tool | Description |
|------|-------------|
| `prowlarr_search` | Search across all configured torrent/usenet indexers |
| `prowlarr_get_indexers` | List configured indexers |
| `prowlarr_get_indexer_stats` | Get indexer query/grab/failure statistics |
| `prowlarr_grab_release` | Download a specific release from search results |
| `prowlarr_get_health` | Check system health and indexer issues |

### Shell

The agent also has access to a bash shell via `LocalShellBackend` for tasks where no dedicated tool exists (e.g., checking disk usage, running network diagnostics).

## Skills

Skills are `SKILL.md` files that provide domain-specific instructions loaded into the agent's virtual filesystem. The agent reads them on-demand when a user's request matches a skill description.

| Skill | Covers |
|-------|--------|
| **device-control** | Lights, switches, fans, cameras, scenes -- includes known entity IDs |
| **media-management** | Full tool-to-task mapping for all 6 media services with workflows |
| **energy-insights** | Power consumption, energy usage, battery levels, cost estimation |
| **network-diagnostics** | WiFi mesh status, connected devices, bandwidth, presence detection |

## Example Questions

### Device Control
- "Turn off the bedside lamp"
- "Set the bedroom light to 50% brightness"
- "Is the workstation plug on?"
- "Activate movie time"
- "Turn off everything"

### Media -- Search and Download
- "Find the movie Interstellar"
- "Download Invincible season 4"
- "Search for Dune on Radarr and add it"
- "What TV shows am I monitoring?"
- "What movies am I tracking?"

### Media -- Downloads and Torrents
- "What's currently downloading?"
- "Pause all torrents"
- "Remove the Elf torrent but keep the files"
- "How much disk space is left?"
- "Slow down downloads to 500 KB/s, I'm on a video call"
- "Set the Dune torrent to high priority"
- "Show me Transmission lifetime stats"

### Media -- Library and Playback
- "Do I have Breaking Bad in my library?"
- "What was I watching?" (continue watching list)
- "Who's streaming right now?"
- "Pause playback on the Mac mini"
- "Mark Inception as watched"
- "What's new in my Jellyfin library?"
- "Tell me about the movie RRR -- cast, rating, runtime"

### Media -- Calendar and History
- "What episodes are airing this week?"
- "Any upcoming movie releases?"
- "What did Sonarr download recently?"
- "Show me Radarr download history"

### Media -- Requests and Indexers
- "Show me all pending Jellyseerr requests"
- "Approve request #4"
- "Search torrent indexers for One Piece"
- "Are my Prowlarr indexers healthy?"

### Energy
- "How much power is the workstation using?"
- "What's my energy consumption today?"
- "What are the battery levels on my devices?"
- "Estimate my monthly electricity cost"

### Network
- "Are both mesh nodes online?"
- "How many devices are connected to WiFi?"
- "What's my current bandwidth usage?"
- "Is Kanak home?"

### General / Multi-step
- "Give me a full status report -- devices, downloads, network"
- "Find One Punch Man on Sonarr, add it, then show me the download queue"
- "Pause all downloads, turn off the workstation, and activate relax mode"

## Setup

### Prerequisites

- Python 3.12+
- A Google Gemini API key ([get one here](https://aistudio.google.com/apikey))
- Home Assistant with a long-lived access token
- Media services running (Sonarr, Radarr, Jellyfin, Transmission, Jellyseerr, Prowlarr)

### Local Development

```bash
# Clone and navigate
cd deepagent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your actual API keys and service URLs

# Run
python api.py
```

The server starts on `http://localhost:8322`.

### Docker

```bash
docker build -t homebot-deepagent .
docker run -d --name deepagent \
  --env-file .env \
  -p 8322:8322 \
  homebot-deepagent
```

## API

### `GET /api/health`

Returns service status, model name, and skills directory path.

### `POST /api/chat/stream`

Send a message and receive an SSE event stream.

**Request:**
```json
{
  "message": "What episodes are airing this week?",
  "thread_id": "user-session-1"
}
```

**Headers:**
- `X-API-Key` -- required if `API_KEY` is set in config
- `Content-Type: application/json`

**SSE events:**

| Event | Description |
|-------|-------------|
| `thinking` | Agent has started processing |
| `tool_call` | Agent is invoking a tool (includes name and args) |
| `tool_result` | Tool returned a result (includes content and duration) |
| `response` | Final natural-language answer |
| `error` | Something went wrong |
| `done` | Stream complete |

**Example with curl:**
```bash
curl -N http://localhost:8322/api/chat/stream \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is downloading right now?", "thread_id": "test"}'
```

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_API_KEY` | -- | Gemini API key (required) |
| `MODEL` | `google_genai:gemini-3-flash-preview` | LLM model identifier |
| `HA_URL` | `http://localhost:8123` | Home Assistant URL |
| `HA_TOKEN` | -- | HA long-lived access token |
| `SONARR_URL` | `http://localhost:8989` | Sonarr API URL |
| `SONARR_API_KEY` | -- | Sonarr API key |
| `RADARR_URL` | `http://localhost:7878` | Radarr API URL |
| `RADARR_API_KEY` | -- | Radarr API key |
| `TRANSMISSION_URL` | `http://localhost:9091` | Transmission RPC URL |
| `JELLYFIN_URL` | `http://localhost:8096` | Jellyfin API URL |
| `JELLYFIN_API_KEY` | -- | Jellyfin API key |
| `JELLYSEERR_URL` | `http://localhost:5055` | Jellyseerr API URL |
| `JELLYSEERR_API_KEY` | -- | Jellyseerr API key |
| `PROWLARR_URL` | `http://localhost:9696` | Prowlarr API URL |
| `PROWLARR_API_KEY` | -- | Prowlarr API key |
| `PORT` | `8322` | Server port |
| `API_KEY` | -- | API authentication key (empty = no auth) |
| `CORS_ORIGINS` | `http://localhost:3001` | Comma-separated allowed origins |
| `DATA_DIR` | `/tmp/deepagent_data` | Filesystem backend root directory |
| `LANGSMITH_TRACING` | `false` | Enable LangSmith trace logging |
| `LANGSMITH_PROJECT` | `homebot-deepagent` | LangSmith project name |

## Project Structure

```
deepagent/
  api.py              FastAPI server with SSE streaming
  agent.py            Agent builder (system prompt, tools, skills, backend)
  config.py           Environment variable configuration
  requirements.txt    Python dependencies
  Dockerfile          Container build
  .env.example        Configuration template
  tools/
    __init__.py       get_all_tools() aggregator
    homeassistant.py  HA REST API tools (5)
    sonarr.py         Sonarr v3 API tools (8)
    radarr.py         Radarr v3 API tools (8)
    jellyfin.py       Jellyfin API tools (9)
    transmission.py   Transmission RPC tools (8)
    jellyseerr.py     Jellyseerr API tools (5)
    prowlarr.py       Prowlarr API tools (5)
  skills/
    device-control/SKILL.md
    media-management/SKILL.md
    energy-insights/SKILL.md
    network-diagnostics/SKILL.md
```
