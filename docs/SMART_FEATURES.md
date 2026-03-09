# Smart Features

Advanced AI intelligence features that make HomeBotAI context-aware, proactive, and capable of multi-step reasoning.

## Presence Tracking (2C.1)

Device trackers and person entities are included in every agent conversation.

**What's tracked:**
- `person.kanak` -- home/not_home based on HA presence detection
- `device_tracker.ipad` -- iPad location
- `device_tracker.pixel_9_pro` -- Pixel phone location
- `device_tracker.galaxy_watch` -- Galaxy Watch location

**Example queries:**
- "where am I?" / "is anyone home?"
- "which devices are at home?"

**How it works:** The `device_tracker` domain was removed from `_SKIP_DOMAINS` in `state.py`. A new "Presence" section in `summarize()` shows each tracker's location and source type. This data is injected into the agent's system prompt on every call.

**Files:** `backend/state.py`

---

## Smarter State Summary (2E.1)

The agent's home awareness is context-sensitive, time-aware, and anomaly-detecting.

### Context-Aware Filtering

When you mention a topic, the agent automatically includes more related entities that are normally filtered out for brevity.

| Keyword in your message | Extra entities included |
|-------------------------|----------------------|
| "printer", "3d", "printo" | All printer sensors (bed temp, nozzle, WiFi, gcode, etc.) |
| "battery", "watch", "phone" | All battery levels (normally only shown if <30%) |
| "xbox", "tv", "media", "spotify" | All media players (normally only playing/paused) |
| "energy", "power" | All power/energy sensors |
| "camera" | Camera entities with details |
| "purifier" | Purifier climate/fan even if off |

### Recent Changes

State changes from the last 10 minutes are tracked in a rolling buffer and shown as a "Recent Changes" section in the summary. Example:

```
Recent Changes: light.bedside: off->on | switch.desk: on->off
```

### Anomaly Detection

Unusual states are flagged in an "Alerts" section:

| Anomaly | Threshold |
|---------|-----------|
| Battery critically low | < 15% |
| High power consumption | > 500W |
| Door/window open | binary_sensor state = "on" |

**Files:** `backend/state.py` (`summarize()`, `_detect_anomalies()`)

---

## Daily/Weekly AI Digests (2E.2)

Two scheduled AI-mode skills are auto-created on first boot.

### Daily Digest

- **Schedule:** 10 PM every day (`0 22 * * *`)
- **Content:** Activity summary, energy highlights, notable events, current home state
- **Delivery:** Telegram notification
- **Skill ID:** `daily_digest`

### Weekly Energy Report

- **Schedule:** 8 PM every Sunday (`0 20 * * 0`)
- **Content:** Power consumption patterns, most active devices, usage trends, optimization suggestions
- **Delivery:** Telegram notification
- **Skill ID:** `weekly_energy_report`

### Management

Both skills are visible on the `/skills` dashboard page where you can:
- Toggle them on/off
- Edit the cron schedule
- Change the AI prompt
- Delete them (they won't be recreated if deleted)

Skills are created by `ensure_default_skills()` in `ProceduralMemory`, called during bootstrap. Idempotent -- existing skills are never overwritten.

**Files:** `backend/memory/procedural.py`, `backend/bootstrap.py`

---

## Multi-Turn Tool Planning (2E.3)

The agent plans multi-step tool chains and handles confirmations for destructive actions.

### Chain Awareness

The system prompt includes explicit planning instructions:

- **Media download:** Search Sonarr -> check Prowlarr for releases -> add to Transmission
- **Media requests:** Search library (Jellyfin/Sonarr) -> search downloads (Prowlarr) -> add to Transmission
- **Failure recovery:** Explain what went wrong, suggest alternatives

### Confirmation Flows

Destructive actions require user confirmation:
- Deleting torrents
- Clearing chat history
- Disabling automations
- Bulk device changes

When the user says "yes", "go ahead", or "do it" after a confirmation prompt, the agent proceeds.

**Files:** `backend/agent.py` (`_build_system_prompt()`)

---

## Proactive Notifications (2E.4)

Automatic Telegram notifications triggered by state changes, without needing explicit skills.

### Notification Rules

| Rule | Trigger | Message |
|------|---------|---------|
| Printer finished | `printing`/`preparing` -> `idle`/`complete`/`standby` | "Your 3D printer finished! Printo is now idle." |
| Battery low | Any battery drops below 15% | "Low battery: Galaxy Watch is at 12%" |
| Welcome home | Person/device_tracker -> `home` | "Welcome home, Kanak! Lights on: Bedside." |
| Left home | Person/device_tracker -> `not_home` | "Kanak left home. Still on: Desk, Workstation" |

### Cooldown

Each rule has a 5-minute cooldown per entity to prevent notification spam. For example, if the printer state flickers between idle and standby, you'll only get one notification per 5-minute window.

### How It Works

The `_check_proactive_notifications()` method in the Reactor is called on every state change event. It evaluates each built-in rule, checks cooldowns, and sends Telegram messages to all allowed users.

These rules are hardcoded in the reactor -- they can't be accidentally deleted and don't depend on the skills system.

**Files:** `backend/reactor.py` (`_check_proactive_notifications()`, `_can_notify()`, `_send_notification()`)
