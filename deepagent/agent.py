"""Deep agent setup -- creates and configures the LangChain deep agent."""

import logging
import os

from deepagents import create_deep_agent
from deepagents.backends import LocalShellBackend
from deepagents.backends.utils import create_file_data
from langchain.agents.middleware.types import AgentMiddleware
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, RemoveMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

import config
from tools import get_all_tools

log = logging.getLogger("deepagent.agent")

MAX_HUMAN_TURNS = int(os.getenv("MAX_HUMAN_TURNS", "5"))


class MessageWindowMiddleware(AgentMiddleware):
    """Keep conversation state bounded to the last N human turns.

    Two complementary trims, same window:

    1. ``awrap_model_call`` -- trims messages in-flight to the LLM so the
       model never sees more than the window, regardless of what's in state.
    2. ``aafter_agent`` -- emits ``RemoveMessage`` updates so the persisted
       graph state (SQLite checkpoint) itself never grows past the window.

    The second step is the critical one: without it, ``checkpoints.db`` keeps
    a full snapshot of every historical message at every step. On the live
    Telegram thread we ended up with 192+ messages replicated across 500+
    checkpoint rows (~1.6 GB). SQLite under disk pressure then slowed commits
    enough that python-telegram-bot retried its send, producing duplicate
    replies on the user's phone (the "messages repeat" bug).

    Keeping the window narrow at the STATE level means each checkpoint row
    stays kilobytes, not megabytes, no matter how long the conversation runs.
    """

    def __init__(self, max_human_turns: int = MAX_HUMAN_TURNS):
        self._max_human_turns = max_human_turns

    async def awrap_model_call(self, request, handler):
        trimmed = _trim_to_last_n_human(request.messages, self._max_human_turns)
        if len(trimmed) < len(request.messages):
            log.debug(
                "MessageWindow: trimmed %d -> %d messages for LLM (last %d human turns)",
                len(request.messages), len(trimmed), self._max_human_turns,
            )
        return await handler(request.override(messages=trimmed))

    async def aafter_agent(self, state, runtime):
        """Drop out-of-window messages from the persisted graph state.

        Returns a state-update dict containing ``RemoveMessage`` entries; the
        ``add_messages`` reducer on the ``messages`` channel interprets those
        as "remove by id", shrinking the state before the next checkpoint is
        written.  Messages without a stable ``id`` cannot be referenced this
        way and are left alone (they will be trimmed again on the next turn
        once LangGraph assigns them ids).
        """
        messages = state.get("messages") if isinstance(state, dict) else getattr(state, "messages", None)
        if not messages:
            return None

        cutoff = _window_cutoff_index(messages, self._max_human_turns)
        if cutoff <= 0:
            return None

        to_remove = []
        for msg in messages[:cutoff]:
            msg_id = getattr(msg, "id", None)
            if msg_id:
                to_remove.append(RemoveMessage(id=msg_id))
        if not to_remove:
            return None

        log.info(
            "MessageWindow: pruning %d old messages from state (keeping last ~%d human turns, %d remain)",
            len(to_remove), self._max_human_turns, len(messages) - cutoff,
        )
        return {"messages": to_remove}


def _trim_to_last_n_human(messages: list, n: int) -> list:
    """Return the tail of *messages* starting from the n-th-last HumanMessage."""
    cutoff = _window_cutoff_index(messages, n)
    return messages[cutoff:] if cutoff > 0 else messages


def _window_cutoff_index(messages: list, n: int) -> int:
    """Index of the first message inside the last ``n`` human turns.

    Returns 0 when there are fewer than ``n`` human turns so the caller
    treats the message list as already in-window.
    """
    human_indices = [
        i for i, m in enumerate(messages) if isinstance(m, HumanMessage)
    ]
    if len(human_indices) <= n:
        return 0
    return human_indices[-n]


_SYSTEM_PROMPT_BASE = """\
You are HomeBotAI, an intelligent smart-home assistant powered by Home Assistant.
The home is in India (IST timezone). Resident: Kanak.

## Home Inventory

Lights (2 total):
- light.bedside -- Bedside lamp, white only (colloquial: "bedside", "bedside light", "bedside lamp")
- light.table_lamp -- Bedroom table lamp, WiZ RGBW + tunable white \
(colloquial: "table lamp", "desk lamp", "reading lamp"). Supports colour, \
brightness, temperature, and WiZ scenes via the standard light service.

Bedroom is the only room with lights. When the user's phrase is a SCOPE \
rather than a specific lamp -- "bedroom", "bedroom lights" (plural), "the \
room", "all the lights", or any brightness/colour/on/off verb applied to the \
room as a whole -- treat it as "fan out to ALL THREE bedroom devices in the \
same turn": `light.bedside` + `light.table_lamp` + the `script.rgb_strip_*` \
bridge. Issue the tool calls together; do NOT ask which one.

Only use `offer_choices` when the user has explicitly signalled they want to \
pick ONE (singular + indefinite: "turn on a bedroom light", "which light \
should I...?", or a direct "pick one"). A bare "bedroom light" still counts \
as the scope above; when in doubt, fan out and confirm in one sentence.

Alexa-proxied RGB LED strip (NOT Home Assistant-native; no `light.*` entity):
The phrases "strip", "led strip", "rgb strip", "light strip", "rgb light", \
"the strip" ALWAYS refer to this Homemate strip.

Control surface (always use `domain="script"`):
- `script.rgb_strip_on` — on, no data
- `script.rgb_strip_off` — off, no data
- `script.rgb_strip_brightness` — data: `{"level": 0-100}` (percent)
- `script.rgb_strip_color` — data: `{"color": "red"}`. Valid colours: red, \
green, blue, yellow, orange, purple, pink, warm white, cool white, daylight.

Call via `ha_call_service(domain="script", service="rgb_strip_on", data={...})`. \
Do NOT pass an `entity_id`. Do NOT look for a `light.*` entity for the strip — \
there isn't one. Expect ~1-2s delay and a faint verbal "okay" from the Echo; \
this is normal and not a failure.

Plugs (2 main):
- switch.monitor_plug -- Desk monitor plug (colloquial: "desk", "desk plug")
- switch.workstation -- Workstation plug (colloquial: "workstation", "PC", "PC plug")

Fans (2):
- fan.air_purifier -- Air purifier
- fan.printer_fan -- 3D printer cooling fan

Cameras (2):
- camera.bedroom_camera_live_view -- Bedroom camera (often unavailable)
- camera.printer -- 3D printer camera

People: person.kanak
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
Choices: offer_choices (present 2-8 tap-able options instead of a text list; end your turn after calling it)

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
5. Use friendly, colloquial names in replies (e.g. "the purifier", "the room"). \
Never quote raw entity_ids or vendor model names like "Xiaomi Smart Air Purifier 4" \
back to the user.
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
9. **Ordinal / short replies resolve against your last message.** If you just \
offered a numbered or bulleted list of items and the user replies with a bare \
digit ("3"), letter ("a"), or ordinal ("the second one", "last one"), interpret \
it as selecting that item and act on it — do not ask "what do you mean by 3?".
10. **Synthesize redundant sensor data.** If two or more sensors report the same \
quantity within a small delta (about 1°C or 5%RH or 20% on wattage), report a \
single synthesized value ("around 28°C, humidity mid-50s"), not a list of raw \
readings.
11. **Environmental queries never fail for 'no access'.** Temperature, humidity, \
PM2.5, and battery sensors are always reachable via the Home Assistant sensor \
domain. If a targeted lookup returns nothing, fall back to \
`ha_search_entities(query="temperature")` (or "humidity"/"battery"/"pm2") before \
saying you cannot find the data.
12. **Confirm actions in one line, without second-guessing.** After a successful \
ha_call_service, state what changed in a single short sentence. Do not \
immediately ask "did you mean another light?" unless the action clearly did \
nothing useful.
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


_SYSTEM_PROMPT_TELEGRAM = """
## Telegram channel rules

You are replying over Telegram. Keep every response tight and scannable:

- 2-6 lines, plain text. No markdown headers, no bullet symbols like `*` or `#`, \
  no HTML. Short sentences are fine; use line breaks for rhythm.
- At most ONE emoji per message, and only when it adds information (warnings, \
  celebrations). Never decorate replies with emojis.
- Answer first, flourish last. For status/control queries (temperature, lights, \
  power, recaps) give the answer in the first sentence with no preamble.
- Do NOT tack on "Let me know if you need anything else!", "Enjoy!", \
  "Pretty cool, right?", or similar filler tails. The conversation stays open \
  by default.
- Confirm an action in a single sentence ("Bedside lamp is on.") and stop — \
  don't immediately second-guess yourself with "did you mean another light?".
- For URLs, always call process_and_save_link.
- For device control, try the obvious entity first; use stored phrase -> \
  entity_id mappings from `homebot-brain` before saying "not found".
- Do NOT emit render_ui on Telegram (there is no UI surface).

## Offering choices

When you need the user to pick from a list, prefer the `offer_choices` tool over \
a numbered text list — it renders as tap-able buttons in Telegram. Reserve plain \
text lists for cases where the user is likely scanning, not selecting.
"""



def _load_persona() -> str | None:
    """Read persona.md from the data directory. Returns None if missing."""
    from pathlib import Path

    persona_path = config.DATA_DIR / "persona.md"
    if persona_path.is_file():
        text = persona_path.read_text().strip()
        if text:
            log.info("Loaded persona from %s", persona_path)
            return text
    return None


def get_system_prompt(
    *,
    include_render_ui: bool = True,
    include_persona: bool = False,
    include_telegram: bool = False,
) -> str:
    prompt = _SYSTEM_PROMPT_BASE

    if include_persona:
        persona = _load_persona()
        if persona:
            identity_end = prompt.index("\n\n## Home Inventory")
            prompt = persona + "\n\n" + prompt[identity_end + 2:]

    if include_render_ui:
        prompt += _SYSTEM_PROMPT_RENDER_UI
    if include_telegram:
        prompt += _SYSTEM_PROMPT_TELEGRAM
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
    """Turn provider:model into a chat model.

    - Ollama fine-tunes (``ollama:homebot-*``) go through ChatOllamaRaw,
      which calls /api/generate with a hand-rolled ChatML prompt and parses
      ``<tool_call>`` blocks client-side. Ollama 0.21's built-in qwen3.5
      renderer rewrites the system prompt in a Qwen3-Coder style that our
      fine-tunes were not trained on, producing XML parse errors under the
      full DeepAgent context (persona + telegram + 62 tools).
    - Other Ollama models keep the standard ChatOllama -- their renderer
      and parser work fine with an explicit base_url (not localhost inside
      Docker).
    - Gemini 2.5 models default to "thinking mode" which consumes the
      entire output budget on chain-of-thought before producing tool calls
      or text, leading to empty streamed responses. We disable it with
      ``thinking_budget=0`` unless the caller overrides via env.
    """
    if model_spec.startswith("ollama:"):
        model_name = model_spec.split(":", 1)[1]
        if model_name.startswith("homebot-"):
            from ollama_raw_chat import ChatOllamaRaw

            log.info("Using ChatOllamaRaw for %s (bypasses Ollama renderer/parser)", model_spec)
            return ChatOllamaRaw(base_url=config.OLLAMA_URL, model=model_name)
        return init_chat_model(model_spec, base_url=config.OLLAMA_URL)

    if model_spec.startswith("google_genai:") or model_spec.startswith("gemini:"):
        try:
            budget = int(os.getenv("GEMINI_THINKING_BUDGET", "0"))
        except ValueError:
            budget = 0
        return init_chat_model(model_spec, thinking_budget=budget)

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


async def build_agent(
    model: str | None = None,
    *,
    include_render_ui: bool = True,
    include_persona: bool = False,
    include_telegram: bool = False,
):
    """Build and return the deep agent graph.

    *model* overrides ``config.MODEL`` when provided. Accepts the
    ``provider:model`` format, e.g. ``ollama:qwen3.5:9b``.
    *include_render_ui* controls whether the render_ui instructions are
    included in the system prompt (False for Telegram / skill contexts).
    *include_persona* loads persona.md and replaces the default identity.
    *include_telegram* appends the Telegram channel rules block.
    """
    effective_model = model or config.MODEL
    prompt = get_system_prompt(
        include_render_ui=include_render_ui,
        include_persona=include_persona,
        include_telegram=include_telegram,
    )
    log.info(
        "Building deep agent with model=%s render_ui=%s persona=%s telegram=%s",
        effective_model, include_render_ui, include_persona, include_telegram,
    )

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
        middleware=[MessageWindowMiddleware()],
    )

    log.info(
        "Deep agent ready with %d tools, %d skills, %d memory files",
        len(all_tools),
        len(skills_files),
        len(memory_files),
    )
    return agent, all_files
