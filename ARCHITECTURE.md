# HomeBotAI Architecture

## System Overview

```
                        +------------------+
                        |    Telegram Bot   |
                        |    (main.py)      |
                        +--------+---------+
                                 |
                                 v
+------------------+    +--------+---------+    +------------------+
|   Dashboard UI   +--->|   FastAPI / API   |<---+   CLI (Rich)     |
|   (Next.js)      |    |   (api.py)        |    |   (cli.py)       |
|   :3001          |    |   :8321           |    |                  |
+------------------+    +--------+---------+    +------------------+
                                 |
                        +--------+---------+
                        |    LangGraph      |
                        |    ReAct Agent    |
                        |    (agent.py)     |
                        +--------+---------+
                                 |
              +------------------+------------------+
              |                  |                  |
     +--------+------+  +-------+-------+  +-------+-------+
     |   Memory      |  |   Tools       |  |   Reactor     |
     |   (3-layer)   |  |   (35 tools)  |  |   (auto-act)  |
     +---------------+  +-------+-------+  +---------------+
                                |
     +--------+---------+-------+-------+---------+--------+
     |        |         |       |       |         |        |
  +--+--+ +--+--+ +----+--+ +--+--+ +--+---+ +---+--+ +---+--+
  | HA  | | n8n | | Sonarr| |Trans| |Jelly- | |Prow- | |Jelly-|
  |     | |     | |       | |miss.| |seerr  | |larr  | |fin   |
  +-----+ +-----+ +-------+ +-----+ +------+ +------+ +------+
```

## Backend

### Entry Points

All three entry points share initialization via `bootstrap.py`:

| Entry Point | File | Purpose | Transport |
|-------------|------|---------|-----------|
| Telegram | `main.py` | Production chat via Telegram | Long polling |
| API | `api.py` | REST + SSE for dashboard/testing | HTTP (:8321) |
| CLI | `cli.py` | Developer interactive REPL | stdin/stdout |

`bootstrap.py` provides `create_app()` which initializes memory stores, registers all 35 tools, builds the LangGraph agent, and optionally connects the HA WebSocket state cache.

### Agent (agent.py)

- Model: `gemini-2.5-flash` via `langchain-google-genai`
- Orchestration: `langgraph.prebuilt.create_react_agent` (ReAct loop)
- System prompt: dynamically built per request with live HA state, learned skills, and semantic memory
- State summary: relevance-filtered (only notable entities -- active lights, climate, useful sensors, playing media)
- History: last 10 conversation turns from episodic memory
- Streaming: `run_stream()` async generator yields typed events (`thinking`, `tool_call`, `tool_result`, `response`, `error`)

### Memory (3-Layer)

```
memory/
  episodic.py    Conversation history per chat_id (SQLite, max 50 turns)
  semantic.py    Facts and preferences (key-value store in SQLite)
  procedural.py  Learned skills, event log (SQLite)
```

| Layer | Purpose | Storage | Lifecycle |
|-------|---------|---------|-----------|
| Episodic | Chat history | SQLite, per chat_id | Auto-trimmed to 50 |
| Semantic | User prefs, facts | SQLite key-value | Persistent |
| Procedural | Skills, routines | SQLite + event log | User-managed |

### Tools (35 registered)

| Category | Count | Tools | Source |
|----------|-------|-------|--------|
| Home Assistant | 4 | `ha_call_service`, `ha_get_camera_snapshot`, `ha_trigger_automation`, `ha_fire_event` | `tools/homeassistant.py` |
| Skills | 7 | `create_skill`, `execute_skill`, `list_skills`, `update_skill`, `delete_skill`, `toggle_skill`, `get_event_log` | `tools/skills.py` |
| Memory | 2 | `remember`, `recall` | `tools/memory_tools.py` |
| n8n | 5 | `n8n_list_workflows`, `n8n_get_workflow`, `n8n_create_workflow`, `n8n_execute_workflow`, `n8n_toggle_workflow` | `tools/n8n.py` |
| Sonarr | 4 | `sonarr_search`, `sonarr_add_series`, `sonarr_list_series`, `sonarr_upcoming` | `tools/sonarr.py` |
| Transmission | 4 | `transmission_get_torrents`, `transmission_add_torrent`, `transmission_remove_torrent`, `transmission_pause_resume` | `tools/transmission.py` |
| Jellyseerr | 3 | `jellyseerr_search`, `jellyseerr_request`, `jellyseerr_get_requests` | `tools/jellyseerr.py` |
| Prowlarr | 3 | `prowlarr_search`, `prowlarr_get_indexers`, `prowlarr_get_indexer_stats` | `tools/prowlarr.py` |
| Jellyfin | 5 | `jellyfin_search`, `jellyfin_get_libraries`, `jellyfin_get_latest`, `jellyfin_get_sessions`, `jellyfin_system_info` | `tools/jellyfin.py` |

### State Cache (state.py)

Maintains a live in-memory mirror of all Home Assistant entities via WebSocket subscription. The agent never needs an API call to read state -- it gets a relevance-filtered summary injected into the system prompt.

Filtering strategy:
- Always: persons, weather, lights (on), active climate/fans, playing media
- Sensors: only temperature, humidity, PM2.5, AQI, power, energy, battery (< 30%)
- Skips: internal HA entities, 3D printer internals (unless printing), config entities

### Reactor (reactor.py)

Proactive automation engine with two trigger types:
- **Schedule**: cron-based jobs via APScheduler
- **State change**: HA entity state transitions (e.g., motion detected, door opened)

Skills can define triggers that the reactor monitors. When triggered, skills execute either static tool sequences or AI-driven responses.

### API Endpoints (api.py)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/chat` | Blocking chat, returns full response + tool calls |
| POST | `/api/chat/stream` | SSE stream of real-time events |
| GET | `/api/health` | System status (tools, entities, model) |
| GET | `/api/tools` | List all registered tools |
| GET | `/api/skills` | List learned skills |
| GET | `/api/entities` | Entity summary grouped by domain |

### Configuration (config.py)

Loads environment variables from `.env` via `python-dotenv`. Handles SSL certificate merging for macOS (combines keychain CAs with `certifi` bundle) to work behind corporate proxies.

### Testing

```
tests/
  test_agent.py      Agent integration tests (requires Gemini API key)
  test_services.py   Service connectivity tests (Transmission, Jellyseerr, Prowlarr, Jellyfin)
```

## Dashboard

### Tech Stack

| Technology | Version | Purpose |
|------------|---------|---------|
| Next.js | 15 | App Router, React 19 |
| TypeScript | 5 | Type safety |
| Tailwind CSS | 3.4 | Styling |
| Framer Motion | 11 | Animations |
| Magic UI | -- | Bento grid, cards, effects |
| next-themes | 0.4 | Dark mode |

### Design System

Shared with the portfolio site (kanakjr_website_26):

- **Background**: `#0a0a0a`
- **Primary**: `#FFD700` (cyber-yellow)
- **Secondary**: `#FF4500` (retro-red)
- **Fonts**: Geist Sans (body), Geist Mono (headings/code)
- **Theme**: Dark-only, HSL CSS variables for semantic tokens

### Pages

| Route | Purpose | Backend Endpoint |
|-------|---------|-----------------|
| `/` | Dashboard home -- bento grid with stats, sensors, quick chat | `/api/health`, `/api/entities` |
| `/chat` | Full-page AI chat with SSE streaming | `/api/chat/stream` |
| `/devices` | Entity browser -- 280 entities, domain filters, search | `/api/entities` |
| `/skills` | Skill manager -- list, view triggers, teach via chat | `/api/skills` |
| `/tools` | Tool reference -- 35 tools grouped by category | `/api/tools` |

### Frontend Architecture

```
dashboard/
  app/
    layout.tsx       Root layout (ThemeProvider, Sidebar, Geist fonts)
    page.tsx         Dashboard home (stats, sensors, quick chat)
    chat/page.tsx    Full AI chat page
    devices/page.tsx Entity browser
    skills/page.tsx  Skills manager
    tools/page.tsx   Tools reference
  components/
    Sidebar.tsx      Navigation sidebar with backend status
    ChatWidget.tsx   Reusable chat interface (used on / and /chat)
    EntityCard.tsx   Individual entity display card
    StatusBadge.tsx  Status indicator component
    magicui/         Copied subset of Magic UI components
  lib/
    api.ts           API client (fetchJSON, SSE streaming)
    types.ts         TypeScript interfaces for API responses
    utils.ts         cn() class merge utility
    hooks/
      useChat.ts     Chat state + SSE streaming hook
      useEntities.ts Entity fetching + polling hook
```

### Data Flow: Chat Request

```
User types message in Dashboard
  |
  v
useChat hook opens SSE connection to POST /api/chat/stream
  |
  v
Backend: agent.run_stream() starts LangGraph ReAct loop
  |
  +---> Yields "thinking" event --> Dashboard shows spinner
  |
  +---> Yields "tool_call" event --> Dashboard shows tool name + args
  |       |
  |       v
  |     Tool executes (e.g., ha_call_service)
  |       |
  |       v
  +---> Yields "tool_result" event --> Dashboard shows result + duration
  |
  +---> Yields "response" event --> Dashboard renders final answer
  |
  v
SSE stream closes, chat turn complete
```

### State Management

- **Server state** (entities, health, tools, skills): fetched via API, polled or refreshed on page focus
- **Chat state**: client-side only (messages array in React state), streamed via SSE
- **No client-side database**: all persistence lives in the backend SQLite

## Docker Deployment

```yaml
homebot:
  build: ./backend
  env_file: ./backend/.env
  volumes:
    - ./backend/data:/app/data
  ports:
    - "8321:8321"

homebot-dashboard:
  build: ./dashboard
  environment:
    - NEXT_PUBLIC_API_URL=http://homebot:8321
  ports:
    - "3001:3000"
  depends_on:
    - homebot
```

Both services run on the same Docker network. The dashboard resolves `homebot` by container name for server-side requests, while client-side JavaScript uses `NEXT_PUBLIC_API_URL` (set to the externally reachable backend URL in production).

## Phase 2 (Future)

- Activity timeline / event log visualization
- AI summary reports (daily/weekly digests)
- Visual automation builder (drag-and-drop skill creation)
- Camera feeds (snapshots from HA cameras)
- Media controls (Jellyfin playback widgets, Transmission torrent management)
- Push notifications via service worker
- Mobile-responsive adaptive layout
