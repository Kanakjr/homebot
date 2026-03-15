# HomeBotAI -- Future Roadmap

A prioritized list of features and improvements planned for HomeBotAI, organized by category. Each item includes context on why it matters, what it involves, and how it fits with the existing architecture.

---

## Current Baseline

Before diving into what's next, here's what exists today:

- **AI Agent**: LangChain/LangGraph ReAct agent with Gemini 2.5 Flash, 39 tools, three-layer memory (episodic, semantic, procedural)
- **Home Assistant**: WebSocket mirror of 290 entities, real-time state cache, context-aware summaries, anomaly detection
- **Integrations**: Sonarr, Transmission, Jellyseerr, Prowlarr, Jellyfin, n8n
- **Skills**: Manual, scheduled (cron), and state-change triggered routines in static or AI mode
- **Scenes**: Snapshot and restore device states (lights, fans, climate) with attribute preservation
- **Notifications**: Proactive Telegram alerts with configurable rules (printer done, battery low, welcome/left home, Deco node offline, network device disconnect)
- **Dashboard**: 14 pages -- Home (AI-customizable widgets), Chat, Devices, Cameras, Activity, Energy, Network, Skills & Scenes, Memory, Tools, Analytics, Health, Settings, Home Map
- **Home Map**: Interactive SVG floorplan with live device state overlays and click-to-control
- **Network**: TP-Link Deco mesh integration with mesh nodes, connected clients, live bandwidth, bandwidth history charts
- **Device Aliases**: MAC-to-name mapping for friendly device names on the Network page
- **43 API endpoints** with Swagger docs

---

## 1. Dashboard Real-Time Updates

**Priority**: High | **Effort**: Medium

### Problem

The dashboard polls the backend every 15-30 seconds. State changes (light toggled, sensor updated, device connected) take up to 30 seconds to appear. This creates a sluggish feel, especially when toggling devices from the dashboard itself.

### Solution

Add a WebSocket or SSE connection from the dashboard to the backend that pushes entity state changes in real-time. The backend already maintains a WebSocket connection to HA and fires callbacks on every state change -- the plumbing is in `state.py`. The new flow:

1. Add a `GET /api/ws` or `GET /api/events/stream` endpoint that upgrades to WebSocket or opens an SSE stream.
2. When `StateCache` receives a state change, broadcast it to all connected dashboard clients.
3. Dashboard components subscribe to the stream and update local state immediately.

### Impact

- Lights, switches, and fans toggle instantly in the UI
- Sensor values, bandwidth, and energy data update in real-time
- Presence changes (someone arrives/leaves) appear immediately
- Reduces polling load on the backend

### Implementation Notes

- FastAPI supports WebSocket natively (`@app.websocket("/api/ws")`)
- Use a broadcast pattern: maintain a set of connected clients, fan out events
- Dashboard side: a `useWebSocket` hook that merges incoming state into React state
- Fallback: keep polling as a fallback if WebSocket disconnects
- Filter events on the server to only send domains the client cares about

---

## 2. Device Naming and Aliasing [DONE]

**Priority**: High | **Effort**: Low | **Status**: Implemented

### Problem

Network devices from the Deco integration show raw names: `zhimi-airp-mb5_mibt1697`, `lwip0`, `SM-L500`, `H100`. These are meaningless to a human. The same issue affects some HA entities where friendly names are auto-generated from model numbers.

### Solution

A MAC-to-name mapping stored in the backend (either in semantic memory or a dedicated config). When the network API or state summary references a device, it resolves the MAC or entity_id to a human-friendly name.

### Implementation

1. Add a `device_aliases` table in SQLite: `mac TEXT PRIMARY KEY, alias TEXT, device_type TEXT, icon TEXT`.
2. Add `GET/PUT /api/devices/aliases` endpoints for CRUD.
3. In `state.py` `get_network_data()`, resolve `friendly_name` through the alias map before returning.
4. Add a settings section on the Network page to manage aliases.
5. Seed with known devices on first run (detect from HA device registry).

### Example Aliases


| MAC               | Raw Name                | Alias               |
| ----------------- | ----------------------- | ------------------- |
| 84-46-93-DF-16-97 | zhimi-airp-mb5_mibt1697 | Xiaomi Air Purifier |
| FC-67-1F-F1-EA-90 | lwip0                   | Bambu Lab P1S       |
| 98-25-4A-D4-11-26 | H100                    | TP-Link Tapo Hub    |
| 56-4A-C0-79-2D-EE | SM-L500                 | Samsung Printer     |


---

## 3. Presence-Based Automations

**Priority**: High | **Effort**: Medium

### Problem

The Deco integration provides reliable LAN-level presence detection -- a phone connecting to or disconnecting from the mesh is a strong signal for arrival/departure. Currently, this data is only displayed; it isn't used to trigger actions.

### Solution

Build a set of presence-based skill templates and reactor rules that use Deco device_tracker state changes as triggers.

### Scenarios

**Auto-lights on arrival**: When Pixel9Pro connects (state changes to `home`), turn on hallway lights if it's after sunset. Use the existing `ha_call_service` tool with a condition check.

**Last person left**: When all tracked phones (`pixel9pro`, `sarath_s_s25`) are `not_home`, run a "lockdown" routine -- turn off all lights, set fan to off, send a summary of what was turned off.

**Sleep detection**: If a phone's `down_kilobytes_per_s` drops to 0 after midnight and stays there for 10 minutes, trigger a "goodnight" routine (dim lights, set fan to auto).

**Work mode**: When the work laptop (`apac_ind_lap392`) connects during work hours, suppress non-critical notifications and set a "do not disturb" state.

### Implementation

1. Create skill templates in `_DEFAULT_SKILLS` with `state_change` triggers on Deco device_tracker entities.
2. Add a "Presence Automations" section on the Skills page with toggle cards for each scenario.
3. The reactor already supports `state_change` triggers with `to`/`from`/`above`/`below` conditions -- just wire up the right entity IDs.
4. Add a `get_sun_state()` helper to condition on daylight.

---

## 4. Notification Preferences [DONE]

**Priority**: Medium | **Effort**: Low | **Status**: Implemented

### Problem

Notification rules are hardcoded in `reactor.py`. Changing which alerts fire, adjusting thresholds (battery at 15% vs 20%), or disabling welcome-home notifications requires editing Python code and restarting.

### Solution

Move notification rules to the database and expose them via the API and dashboard.

### Implementation

1. Add a `notification_rules` table: `id TEXT PK, name TEXT, enabled BOOLEAN, rule_type TEXT, config_json TEXT, cooldown_seconds INT`.
2. Seed with the current hardcoded rules on first run.
3. Add `GET/PUT /api/notifications/rules` endpoints.
4. Add a "Notifications" section to the dashboard Settings page (or a new Settings page) with toggle switches and threshold sliders.
5. Refactor `_check_proactive_notifications()` to load rules from DB instead of hardcoded logic.

### Configurable Rules


| Rule                      | Settings                                      |
| ------------------------- | --------------------------------------------- |
| Printer finished          | Enable/disable                                |
| Battery low               | Enable/disable, threshold (default 15%)       |
| Welcome home              | Enable/disable, which persons trigger it      |
| Left home                 | Enable/disable, include device-on summary     |
| Deco node offline         | Enable/disable                                |
| Network device disconnect | Enable/disable, which devices are "important" |
| Bandwidth spike           | Enable/disable, threshold (default 50 MB/s)   |


---

## 5. Radarr Integration

**Priority**: Medium | **Effort**: Low

### Problem

Sonarr handles TV series but movies go through a different pipeline. Currently, movie requests go through Jellyseerr, but there's no way to monitor download progress, manage quality profiles, or browse the movie library through the agent.

### Solution

Add Radarr tools following the same pattern as the Sonarr integration (they share the same API structure since both are *arr stack).

### Tools to Add


| Tool                  | Description                                   |
| --------------------- | --------------------------------------------- |
| `radarr_search`       | Search for movies by title                    |
| `radarr_add_movie`    | Add a movie to Radarr for monitoring/download |
| `radarr_get_queue`    | Get the download queue                        |
| `radarr_get_calendar` | Get upcoming movie releases                   |


### Implementation

1. Create `tools/radarr.py` following the `tools/sonarr.py` pattern.
2. Add `RADARR_URL` and `RADARR_API_KEY` to `config.py`.
3. Register tools in `bootstrap.py`.
4. The agent prompt already handles multi-step media workflows; Radarr slots in naturally.

---

## 6. Speed Test Integration

**Priority**: Medium | **Effort**: Low

### Problem

The Deco bandwidth sensors show real-time per-node throughput, but there's no measure of actual internet speed (what your ISP delivers). You can't tell if slowness is the Deco mesh or the ISP.

### Solution

Integrate with the HA Speedtest integration or run periodic speed tests via a scheduled skill. Store results in the event log for historical trending.

### Implementation

**Option A -- HA Speedtest integration**: If the Speedtest integration is enabled in HA, the sensors (`sensor.speedtest_download`, `sensor.speedtest_upload`, `sensor.speedtest_ping`) are already in the state cache. Add them to the Network page alongside Deco bandwidth.

**Option B -- Scheduled skill**: Create a skill that calls a speed test API (e.g., fast.com CLI, speedtest-cli) on a schedule, stores results, and trends them. This is more work but doesn't depend on HA.

### Network Page Additions

- "Internet Speed" card showing last test results (download, upload, ping)
- Trend chart overlaying ISP speed vs Deco throughput
- Alert when ISP speed drops below a threshold

---

## 7. Energy Cost Optimization

**Priority**: High | **Effort**: Medium

### Problem

The energy page shows consumption and a flat-rate cost estimate. Real electricity billing is more complex -- time-of-use rates, tiered pricing, monthly budgets. The agent doesn't proactively suggest ways to reduce costs.

### Solution

Enhance the energy system with rate structures, budget tracking, and AI-powered cost insights.

### Implementation

**Phase 1 -- Rate structures**:

- Add `ENERGY_RATES` config supporting time-of-use: `{"peak": {"rate": 10, "hours": "6-22"}, "off_peak": {"rate": 5, "hours": "22-6"}}`.
- Update cost calculation to use the appropriate rate based on timestamp.
- Show peak vs off-peak breakdown on the Energy page.

**Phase 2 -- Budget tracking**:

- Add monthly budget config (`ENERGY_BUDGET_MONTHLY`).
- Track cumulative cost and show progress bar on Energy page.
- Proactive alert when projected monthly cost exceeds budget.

**Phase 3 -- AI insights**:

- Weekly energy report skill includes cost optimization suggestions.
- "Your workstation was on all night (8 hours idle), costing ~40 rupees. Consider a sleep schedule."
- "Peak-hour AC usage is 60% of your bill. Shifting to off-peak could save 15%."

---

## 8. Spotify / Music Control

**Priority**: High | **Effort**: Medium

### Problem

HA exposes media_player entities for connected speakers and Spotify, but the agent can only do basic play/pause/volume via `ha_call_service`. There's no way to search for music, manage playlists, or do "play Bohemian Rhapsody on the bedroom speaker."

### Solution

Add Spotify-specific tools that use the Spotify Web API (via HA's Spotify integration or direct API) for rich music control.

### Tools to Add


| Tool                  | Description                                      |
| --------------------- | ------------------------------------------------ |
| `spotify_search`      | Search tracks, albums, artists, playlists        |
| `spotify_play`        | Play a track/album/playlist on a specific device |
| `spotify_queue`       | Add tracks to the play queue                     |
| `spotify_now_playing` | Get current playback state across all devices    |
| `spotify_transfer`    | Transfer playback between speakers               |


### Implementation

1. Use the HA Spotify integration's `media_player.play_media` service with Spotify URIs.
2. For search, use the Spotify Web API (needs OAuth token, refresh via HA integration).
3. Add a "Now Playing" widget type for the dashboard.
4. The agent prompt already handles media player entities -- extend with music-specific instructions.

---

## 9. Guest Mode / New Device Detection

**Priority**: Medium | **Effort**: Low

### Problem

When a guest connects to the WiFi, their device appears as a Deco client with a cryptic name. There's no alert, and no way to differentiate guests from household devices.

### Solution

Track known device MACs and alert when an unknown device connects. Optionally offer guest-specific actions.

### Implementation

1. Maintain a `known_devices` set in the DB (seeded from current Deco clients + manual additions).
2. In the reactor, when a Deco client entity changes to `home`, check if its MAC is in `known_devices`.
3. If unknown: send a Telegram notification -- "New device connected: [name] ([MAC]) on [node]. Reply 'trust' to add to known devices."
4. Add a "Known Devices" management section on the Network page.
5. Optional: track guest visit history (first seen, last seen, total visits).

---

## 10. Historical Analytics Page

**Priority**: Medium | **Effort**: Medium

### Problem

The event log stores 72 hours of state changes, and the energy/bandwidth pages show real-time data with short-term history. There's no long-term trend analysis -- weekly patterns, month-over-month energy comparisons, device reliability metrics.

### Solution

A dedicated Analytics page that aggregates data over longer periods with comparative views.

### Sections

**Energy Trends**: Weekly/monthly energy consumption with comparison bars (this week vs last week). Peak usage hours heatmap. Cost trend line.

**Presence Patterns**: Who's home when. Time-at-home per person per day. Arrival/departure heatmap (e.g., "you usually leave at 9:15 AM").

**Network Usage**: Bandwidth trends per device over time. Peak hours heatmap. Data usage per device per day.

**Device Reliability**: Uptime percentage per device. Entities that frequently go `unavailable`. Network devices that disconnect often.

### Implementation

1. Extend the event log retention to 30 days (currently 72h).
2. Add aggregation queries to `procedural.py` (daily/weekly rollups).
3. Create `app/analytics/page.tsx` with Recharts bar/line/heatmap charts.
4. Add `GET /api/analytics?metric=energy&period=weekly` endpoint.

---

## 11. Camera Motion Detection Feed

**Priority**: Medium | **Effort**: Medium

### Problem

Cameras are snapshot-on-demand only. There's no event timeline showing when motion was detected, and no way to correlate motion events with presence data.

### Solution

Build a security timeline that combines motion sensor events with camera snapshots and presence context.

### Implementation

1. Subscribe to `binary_sensor.motion_`* state changes in the reactor.
2. When motion is detected (`off` -> `on`), auto-capture a snapshot from the nearest camera.
3. Log the event with the snapshot filename.
4. Add a "Motion" tab to the Cameras page showing a chronological feed of motion events with snapshots.
5. Cross-reference with presence: flag "motion detected, nobody home" events as alerts.

### Agent Integration

- "Was there any motion last night?" -> agent queries the motion event log and returns a summary with snapshots.
- "Alert me if there's motion while I'm away" -> create a state-change skill that fires when motion is detected and all persons are `not_home`.

---

## 12. Floorplan / Home Map View [PARTIAL]

**Priority**: High | **Effort**: High | **Status**: Phase 2 implemented

### Problem

The Devices page is a flat list. There's no spatial context -- you can't see which room a device is in, where motion was detected, or how the Deco mesh covers your space.

### Solution

An interactive floorplan page where devices are placed on a room layout. Shows live state (lights on/off, temperatures, motion indicators, Deco node coverage zones).

### Implementation

**Phase 1 -- Room cards**: A simpler version -- cards for each room (Bedroom, Hallway, Living Room) showing all devices in that room, their states, and controls. Room assignment stored in the DB.

**Phase 2 -- SVG floorplan** [DONE]: Interactive SVG floor plan at `/home-map`. Device icons overlaid at configured coordinates with live state (color, glow, text). Click to toggle lights/switches/fans or capture camera snapshots. Device mapping stored in `floorplan_config` table with `GET/PUT /api/floorplan/config` endpoints.

**Phase 3 -- Mesh overlay**: Show Deco node coverage areas and which clients are connected to which node, overlaid on the floorplan.

### Remaining Work

- Phase 1 room cards (could complement the SVG view)
- Phase 3 mesh overlay
- Drag-and-drop device placement editor
- Multi-floor support

---

## 13. Voice Interface

**Priority**: High | **Effort**: High

### Problem

All interaction is text-based (Telegram messages or dashboard chat). For hands-free control -- cooking, in bed, walking around -- voice would be far more natural.

### Solution

Add voice input/output to both the Telegram bot and the dashboard.

### Implementation

**Telegram voice**:

1. Handle `voice` message type in `main.py`.
2. Use Gemini's audio capabilities or Whisper API for speech-to-text.
3. Process the transcribed text through the normal agent pipeline.
4. Optionally generate a voice response using TTS (Google Cloud TTS or Gemini).

**Dashboard voice**:

1. Add a microphone button to the chat page.
2. Use the Web Speech API (browser-native) for speech-to-text.
3. Send transcribed text to `/api/chat/stream`.
4. Optionally use Web Speech API synthesis for spoken responses.

**Wake word** (stretch goal):

- A browser-based wake word detector ("Hey HomeBot") that activates the mic.
- Enables always-listening mode on a wall-mounted tablet.

---

## 14. Multi-Room Audio Visualization

**Priority**: Medium | **Effort**: Medium

### Problem

If multiple speakers are active (bedroom, living room, etc.), there's no unified view of what's playing where or controls to manage them together.

### Solution

A "Now Playing" dashboard section or widget showing all active media players, with per-room controls.

### Features

- Grid of speaker cards showing: room name, current track/artist, album art, play/pause/skip controls, volume slider.
- "Play everywhere" button to group all speakers.
- "Transfer" to move playback from one room to another.
- Part of the dashboard home page as a widget, and expanded on a dedicated page.

### Implementation

1. Filter `media_player` entities in state cache for active sessions.
2. Add a `media_player` widget type to the dashboard.
3. Use `ha_call_service` with `media_player.media_play`, `media_player.volume_set`, etc.
4. For Spotify: use `media_player.play_media` with the spotify URI on the target device.

---

## 15. AdGuard Home / Pi-hole DNS Stats

**Priority**: Low | **Effort**: Low

### Problem

If a DNS-level ad blocker (AdGuard Home or Pi-hole) is running on the network, its stats are invisible to HomeBotAI.

### Solution

Pull DNS stats into the Network page as an additional section.

### Implementation

1. Add `ADGUARD_URL` and `ADGUARD_API_KEY` to config.
2. Create `tools/adguard.py` with a `get_stats` function (queries `/control/stats`).
3. Add a "DNS" section to the Network page: total queries, blocked queries, block rate, top clients, top blocked domains.
4. Optional: agent tool `adguard_stats` for "how many ads were blocked today?"

---

## Implementation Order

A suggested phased approach (items marked [DONE] are completed):

### Phase 1 -- Quick Wins (1-2 days each)

1. ~~Device naming/aliasing~~ [DONE]
2. ~~Notification preferences in dashboard~~ [DONE]
3. Radarr integration
4. Guest mode / new device detection
5. Speed test integration

### Phase 2 -- Core Improvements (3-5 days each)

1. Dashboard real-time updates (WebSocket)
2. Presence-based automations
3. Energy cost optimization
4. Spotify/music control

### Phase 3 -- Major Features (1-2 weeks each)

1. Historical analytics page
2. Camera motion detection feed
3. Multi-room audio visualization

### Phase 4 -- Ambitious Projects (2-4 weeks each)

1. ~~Floorplan / home map view~~ [DONE -- Phase 2 SVG floorplan; Phases 1 & 3 remaining]
2. Voice interface
3. AdGuard Home integration

