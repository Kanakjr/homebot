# Deep Agent

The **Deep Agent** is a standalone [LangChain Deep Agent](https://python.langchain.com/docs/concepts/deep_agents/) service for smart-home and media control. It exposes its own HTTP API (default port **8322**) and can be selected from the dashboard chat instead of the main HomeBotAI backend agent.

!!! abstract "At a glance"
    - **Port:** 8322 (configurable via `PORT`)
    - **Stack:** LangGraph agent with a fixed system prompt, tool surface, and on-demand `SKILL.md` skills
    - **Integration:** Dashboard chat can switch between the main backend agent and the Deep Agent

---

## Architecture

The service is a **FastAPI** application (`deepagent/api.py`) that builds a LangGraph deep agent (`deepagent/agent.py`) using `create_deep_agent` with:

- A **system prompt** describing home inventory, tool names, generative UI rules, and behavior constraints
- **Tools** registered from `deepagent/tools/` (see [Tools](#tools-49-across-8-modules) below)
- **Skills** as a virtual filesystem: `SKILL.md` files under `deepagent/skills/` are exposed under `/skills/` for progressive disclosure
- **Memory:** `MemorySaver` checkpointer for per-thread conversation state
- **Backend:** `LocalShellBackend` rooted at `DATA_DIR` for shell execution when no dedicated tool fits

The dashboard’s chat UI can **toggle** between posting to the main backend agent and the Deep Agent endpoint, so operators can choose the richer Deep Agent toolset when needed.

---

## Tools (49 across 8 modules)

| Module | Count | Tools |
|--------|------:|-------|
| Home Assistant | 5 | `ha_call_service`, `ha_get_states`, `ha_search_entities`, `ha_trigger_automation`, `ha_fire_event` |
| Sonarr | 8 | `sonarr_search`, `sonarr_add_series`, `sonarr_get_queue`, `sonarr_get_series`, `sonarr_get_calendar`, `sonarr_delete_series`, `sonarr_episode_search`, `sonarr_get_history` |
| Radarr | 8 | `radarr_search`, `radarr_add_movie`, `radarr_get_queue`, `radarr_get_movies`, `radarr_get_calendar`, `radarr_delete_movie`, `radarr_movie_search`, `radarr_get_history` |
| Jellyfin | 9 | `jellyfin_search`, `jellyfin_get_libraries`, `jellyfin_get_latest`, `jellyfin_get_sessions`, `jellyfin_system_info`, `jellyfin_playback_control`, `jellyfin_mark_played`, `jellyfin_get_item_details`, `jellyfin_get_resume` |
| Transmission | 8 | `transmission_get_torrents`, `transmission_add_torrent`, `transmission_pause_resume`, `transmission_remove_torrent`, `transmission_set_alt_speed`, `transmission_get_session_stats`, `transmission_set_priority`, `transmission_get_free_space` |
| Jellyseerr | 5 | `jellyseerr_search`, `jellyseerr_request`, `jellyseerr_get_requests`, `jellyseerr_approve_decline`, `jellyseerr_get_request_status` |
| Prowlarr | 5 | `prowlarr_search`, `prowlarr_get_indexers`, `prowlarr_get_indexer_stats`, `prowlarr_grab_release`, `prowlarr_get_health` |
| Render UI | 1 | `render_ui` -- emits JSON UI specs for dashboard widget rendering in chat |

The agent may also use the deep agent **shell** (`execute`) provided by `LocalShellBackend` when appropriate.

---

## SKILL.md skills

Four skills ship under `deepagent/skills/`, each with a `SKILL.md` loaded into the virtual filesystem and read **on demand** when the user’s request matches the skill’s domain:

| Skill | Purpose |
|-------|---------|
| `device-control` | Home Assistant device and automation patterns |
| `media-management` | Sonarr, Radarr, Jellyfin, and related workflows |
| `energy-insights` | Power and sensor / energy-focused queries |
| `network-diagnostics` | Network and connectivity troubleshooting |

Paths appear to the model as `/skills/.../SKILL.md` relative to the skills root.

---

## Model policy (`model_policy.py`)

- **Chat model resolution** (`agent.py`): The `MODEL` environment variable uses a **`provider:model-name`** form. Values starting with `ollama:` are passed to `init_chat_model` with `OLLAMA_URL` as the Ollama HTTP base. Other values (typically `google_genai:...`) resolve through LangChain’s Google GenAI integration when `GOOGLE_API_KEY` is set.
- **Ollama model picker** (`/api/models`): `model_policy.py` filters **Qwen-family** Ollama tags whose name encodes a parameter size **above** `DEEPAGENT_MAX_QWEN_B` (default 4). Non-Qwen models and Qwen tags without a parseable `:Nb` suffix are not excluded by this rule.

---

## HTTP API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Liveness: status, service id, configured model, skills directory |
| `GET` | `/api/models` | Lists the default model plus eligible Ollama models (after policy filtering) |
| `POST` | `/api/chat/stream` | Chat; **Server-Sent Events** stream of structured events |

### Authentication

If `API_KEY` is set in the environment, requests under `/api/` must send the key in the **`X-API-Key`** header. If `API_KEY` is empty, no key is required.

### SSE event types

Streams use named SSE events with JSON payloads. Documented types:

| Event | Role |
|-------|------|
| `thinking` | Indicates the agent is processing |
| `tool_call` | Tool invocation (name, args, id) |
| `tool_result` | Tool output and timing |
| `response` | Natural-language assistant content |
| `error` | Failure message |
| `done` | Stream finished (empty data payload) |

When `render_ui` runs, the server may also emit a **`ui_spec`** event for widget payloads before related `tool_result` lines.

---

## Environment variables

| Variable | Purpose |
|----------|---------|
| `GOOGLE_API_KEY` | API key for Google Gemini (when using `google_genai:...`) |
| `MODEL` | Default model spec, e.g. `google_genai:gemini-2.5-flash` or `ollama:qwen3.5:9b` |
| `OLLAMA_URL` | Ollama HTTP API base (e.g. `http://127.0.0.1:11434`; use `host.docker.internal` from Docker on macOS/Windows) |
| `DEEPAGENT_MAX_QWEN_B` | Max Qwen parameter size (from `:Nb` in tag) allowed in `/api/models` list (default `4`) |
| `HA_URL` | Home Assistant base URL |
| `HA_TOKEN` | Home Assistant long-lived access token |
| `SONARR_URL` | Sonarr base URL |
| `SONARR_API_KEY` | Sonarr API key |
| `RADARR_URL` | Radarr base URL |
| `RADARR_API_KEY` | Radarr API key |
| `TRANSMISSION_URL` | Transmission RPC/web URL |
| `JELLYSEERR_URL` | Jellyseerr base URL |
| `JELLYSEERR_API_KEY` | Jellyseerr API key |
| `PROWLARR_URL` | Prowlarr base URL |
| `PROWLARR_API_KEY` | Prowlarr API key |
| `JELLYFIN_URL` | Jellyfin base URL |
| `JELLYFIN_API_KEY` | Jellyfin API key |
| `PORT` | HTTP listen port (default `8322`) |
| `API_KEY` | Optional shared secret for `/api/*` (header `X-API-Key`) |
| `CORS_ORIGINS` | Comma-separated allowed browser origins |
| `DATA_DIR` | Writable directory for `LocalShellBackend` and agent scratch data |
| `LANGSMITH_TRACING` | Enable LangSmith tracing (`true` / `false`) |
| `LANGSMITH_PROJECT` | LangSmith project name |
| `LANGSMITH_API_KEY` | LangSmith API key (if tracing) |
| `LANGSMITH_ENDPOINT` | LangSmith API endpoint (optional; standard default in `.env.example`) |

---

## Docker

From the repository root (or `Apps/homebot/deepagent` depending on your layout), build and run:

```bash
cd deepagent
docker build -t homebot-deep-agent .
docker run --rm -p 8322:8322 --env-file .env homebot-deep-agent
```

The image exposes port **8322** and runs `python -u api.py`. Ensure `.env` sets `OLLAMA_URL` to a host reachable from the container if you use Ollama on the machine.

---

## Project structure

```text
deepagent/
├── api.py              # FastAPI app, SSE streaming, auth middleware
├── agent.py            # Deep agent graph, system prompt, skills FS load
├── config.py           # Environment configuration
├── model_policy.py     # Ollama eligibility for /api/models
├── requirements.txt
├── Dockerfile
├── tools/
│   ├── __init__.py
│   ├── homeassistant.py
│   ├── sonarr.py
│   ├── radarr.py
│   ├── jellyfin.py
│   ├── transmission.py
│   ├── jellyseerr.py
│   ├── prowlarr.py
│   └── render_ui.py
└── skills/
    ├── device-control/SKILL.md
    ├── media-management/SKILL.md
    ├── energy-insights/SKILL.md
    └── network-diagnostics/SKILL.md
```

---

## See also

- [Architecture](architecture.md) -- full stack including Deep Agent placement
- [LLM Benchmarks](benchmarks.md) -- model quality and latency comparisons
