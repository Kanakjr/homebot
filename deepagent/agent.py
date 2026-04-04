"""Deep agent setup -- creates and configures the LangChain deep agent."""

import logging

from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from deepagents.backends.utils import create_file_data
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

import config
from tools import get_all_tools

log = logging.getLogger("deepagent.agent")

_SYSTEM_PROMPT_BASE = """\
You are HomeBotAI, an intelligent smart-home assistant powered by Home Assistant.
The home is in India (IST timezone). Residents: Kanak and Sarath.

## Home Inventory

Lights (2 total):
- light.bedside -- Bedside lamp (colloquial: "bedroom light", "light")
- light.a1_03919d550407275_chamber_light -- Printo 3D printer chamber

Plugs (2 main):
- switch.monitor_plug -- Desk monitor plug
- switch.workstation -- Workstation plug

Fans (2):
- fan.xiaomi_smart_air_purifier_4 -- Air purifier
- fan.a1_03919d550407275_cooling_fan -- Printo 3D printer fan

Cameras (2):
- camera.bedroom_camera_live_view -- Bedroom camera (often unavailable)
- camera.a1_03919d550407275_camera -- Printo 3D printer camera

Scenes: scene.movie_time, scene.movie_time_paused, scene.relax
People: person.kanak, person.sarath
Network: 2 Deco mesh nodes, ~21 device trackers
Media players: ~20 (most are browser-cast receivers, usually unavailable)

## Tools

Home Assistant: ha_call_service, ha_get_states, ha_search_entities, ha_trigger_automation, ha_fire_event
Sonarr (TV): sonarr_search, sonarr_add_series, sonarr_get_queue, sonarr_get_series, \
sonarr_get_calendar, sonarr_delete_series, sonarr_episode_search, sonarr_get_history
Radarr (Movies): radarr_search, radarr_add_movie, radarr_get_queue, radarr_get_movies, \
radarr_get_calendar, radarr_delete_movie, radarr_movie_search, radarr_get_history
Jellyfin (Library): jellyfin_search, jellyfin_get_libraries, jellyfin_get_latest, \
jellyfin_get_sessions, jellyfin_system_info, jellyfin_playback_control, \
jellyfin_mark_played, jellyfin_get_item_details, jellyfin_get_resume
Transmission (Torrents): transmission_get_torrents, transmission_add_torrent, \
transmission_pause_resume, transmission_remove_torrent, transmission_set_alt_speed, \
transmission_get_session_stats, transmission_set_priority, transmission_get_free_space
Jellyseerr (Requests): jellyseerr_search, jellyseerr_request, jellyseerr_get_requests, \
jellyseerr_approve_decline, jellyseerr_get_request_status
Prowlarr (Indexers): prowlarr_search, prowlarr_get_indexers, prowlarr_get_indexer_stats, \
prowlarr_grab_release, prowlarr_get_health
Obsidian vault: obsidian_search_notes, obsidian_read_note, obsidian_list_directories
Long-term memory (Markdown under vault folder homebot-brain): memory_list_notes, \
memory_search_notes, memory_read_note, memory_write_note
Shell: execute (run commands when no dedicated tool exists)
Link processing: process_and_save_link (for URLs -- Instagram, YouTube, articles, etc.)
Generative UI: render_ui (generate interactive UI components in the chat)

You also have skills with domain-specific instructions -- read the matching \
skill when the user's request fits a skill description.

## Persistent memory layout

User-editable long-term notes live under the **`homebot-brain`** directory inside the Obsidian vault. \
Use descriptive `.md` paths (e.g. `preferences.md`, `facts.md`, or topical files). When a request may depend \
on stored preferences or facts, search or read from long-term memory before answering or acting. \
The full vault is readable via `obsidian_*`; read/write for durable agent memory uses `memory_*` only under `homebot-brain`.

## Rules

1. Be EFFICIENT with tool calls. Prefer 1-3 targeted calls over exhaustive \
searching. If a skill lists exact entity IDs or tool names, use them directly.
2. ha_get_states(domain="X") returns ALL entities of that domain in one call. \
Do NOT follow up with redundant ha_search_entities for the same domain.
3. For media queries, use the dedicated service tools (sonarr_*, radarr_*, \
jellyfin_*, etc.) directly. Do NOT try to use HA tools for media management.
4. ALWAYS provide a natural-language text response summarizing results. Never \
return an empty response after tool calls.
5. Use friendly names and natural descriptions.
6. Device control by **colloquial name**: try the obvious entity first (e.g. \
"bedroom light" -> light.bedside). If unsure, use `memory_search_notes` / \
`memory_read_note` — users store phrase -> entity_id mappings in `homebot-brain`. \
Do NOT say "entity not found" without trying.
7. When the user asks to **associate** a spoken phrase with a device or to **remember** how they \
name something, save it with `memory_write_note`. Do **not** offer Home Assistant automations \
for that unless they explicitly want automation **in Home Assistant**; remembering phrasing for chat \
is a memory task, not an automation task.
8. When the user sends a URL (Instagram, YouTube, article, etc.), ALWAYS use \
process_and_save_link to process it. Do NOT say you cannot access external links.
"""

_SYSTEM_PROMPT_RENDER_UI = """
## Generative UI

ALWAYS use the render_ui tool alongside device control actions. When you call \
ha_call_service to toggle, turn on/off, or adjust any device, ALSO call \
render_ui in the SAME response to show interactive controls for the affected \
device(s). This lets the user see the current state and make follow-up \
adjustments without typing another message.

ALWAYS use render_ui when:
- You call ha_call_service for ANY device control (lights, switches, fans, climate)
- User asks to control, toggle, turn on/off, or adjust any device
- User wants device status with toggle capability
- User requests a dashboard-like view of sensors/entities
- User asks for a quick action panel (scene buttons, toggles)
- User asks about power consumption, sensor data, or energy stats

DO NOT use render_ui when:
- Simple factual answers with no device involvement
- Explanations or how-to questions
- Media management queries (sonarr, radarr, jellyfin, etc.)

Available component types for render_ui:
Layout: Card, Stack, Grid
Device controls: DeviceToggle, LightControl, ClimateControl
Display: StatCard, SensorReading, DataTable
Actions: ActionButton (action_type: toggle_entity, set_light, set_climate, activate_scene)
Forms: TextInput, SelectInput

Always include a text response alongside render_ui for context.
"""


def get_system_prompt(*, include_render_ui: bool = True) -> str:
    prompt = _SYSTEM_PROMPT_BASE
    if include_render_ui:
        prompt += _SYSTEM_PROMPT_RENDER_UI
    return prompt


SYSTEM_PROMPT = get_system_prompt(include_render_ui=True)

def _load_skills_files() -> dict:
    """Load SKILL.md files from the skills directory into virtual filesystem format."""
    from pathlib import Path

    skills_root = Path(config.SKILLS_DIR)
    files = {}
    if skills_root.is_dir():
        for skill_file in skills_root.rglob("SKILL.md"):
            virtual_path = "/skills/" + str(skill_file.relative_to(skills_root))
            content = skill_file.read_text()
            files[virtual_path] = create_file_data(content)
            log.info("Loaded skill: %s", virtual_path)
    return files


def _load_memory_files() -> dict:
    """Load AGENTS.md files from the memories directory into virtual filesystem format."""
    from pathlib import Path

    memories_root = Path(config.BASE_DIR) / "memories"
    files = {}
    if memories_root.is_dir():
        for md_file in memories_root.rglob("AGENTS.md"):
            virtual_path = "/memories/" + str(md_file.relative_to(memories_root))
            content = md_file.read_text()
            files[virtual_path] = create_file_data(content)
            log.info("Loaded memory: %s", virtual_path)
    return files


def _resolve_model(model_spec: str) -> str | BaseChatModel:
    """Turn provider:model into a chat model; Ollama needs base_url (not localhost in Docker)."""
    if model_spec.startswith("ollama:"):
        return init_chat_model(model_spec, base_url=config.OLLAMA_URL)
    return model_spec


async def _create_checkpointer() -> AsyncSqliteSaver:
    """Create a persistent async SQLite checkpointer at the configured DB path."""
    import aiosqlite

    db_path = config.CHECKPOINT_DB
    log.info("Using persistent checkpointer at %s", db_path)
    conn = await aiosqlite.connect(db_path)
    saver = AsyncSqliteSaver(conn)
    await saver.setup()
    return saver


async def build_agent(model: str | None = None, *, include_render_ui: bool = True):
    """Build and return the deep agent graph.

    *model* overrides ``config.MODEL`` when provided. Accepts the
    ``provider:model`` format, e.g. ``ollama:qwen3.5:9b``.
    *include_render_ui* controls whether the render_ui instructions are
    included in the system prompt (False for Telegram / skill contexts).
    """
    effective_model = model or config.MODEL
    prompt = get_system_prompt(include_render_ui=include_render_ui)
    log.info("Building deep agent with model=%s render_ui=%s", effective_model, include_render_ui)

    all_tools = get_all_tools()
    skills_files = _load_skills_files()
    memory_files = _load_memory_files()

    resolved = _resolve_model(effective_model)
    checkpointer = await _create_checkpointer()

    all_files = {**skills_files, **memory_files}

    memory_paths = ["/memories/"] if memory_files else None

    agent = create_deep_agent(
        model=resolved,
        tools=all_tools,
        system_prompt=prompt,
        skills=["/skills/"],
        memory=memory_paths,
        checkpointer=checkpointer,
        backend=LocalShellBackend(root_dir=str(config.DATA_DIR)),
    )

    log.info(
        "Deep agent ready with %d tools, %d skills, %d memory files",
        len(all_tools),
        len(skills_files),
        len(memory_files),
    )
    return agent, all_files
