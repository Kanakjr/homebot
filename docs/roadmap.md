# Roadmap

A prioritized list of features and improvements planned for HomeBotAI, organized by status and category.

---

## Current Baseline

What exists today:

- **AI Agent**: LangChain/LangGraph ReAct agent with Gemini 2.5 Flash, 59 backend tools, three-layer memory (episodic, semantic, procedural)
- **Deep Agent**: Standalone LangChain Deep Agent service with 49 tools across 8 modules, SKILL.md skills, model policy routing
- **Home Assistant**: WebSocket mirror of 300+ entities, real-time state cache, context-aware summaries, anomaly detection
- **Integrations**: Sonarr, Radarr, Transmission, Jellyseerr, Prowlarr, Jellyfin, Ollama
- **Skills**: Manual, scheduled (cron), and state-change triggered routines in static or AI mode
- **Scenes**: Snapshot and restore device states (lights, fans, climate) with attribute preservation
- **Notifications**: Proactive Telegram alerts with configurable rules (printer done, battery low, welcome/left home, Deco node offline, network device disconnect)
- **Dashboard**: 18 pages -- Home (AI-customizable widget grid with drag-and-drop), Chat, Devices, Cameras, Activity, Energy, Network, Media, Health, Analytics, Reports, Skills and Scenes, Memory, Tools, Home Map, Settings, Server, Transcoder
- **Widget System**: 19 widget types, AI-powered widget builder, generative UI, react-grid-layout
- **Home Map**: Interactive SVG floorplan with live device state overlays and click-to-control
- **Network**: TP-Link Deco mesh integration with mesh nodes, connected clients, live bandwidth
- **Transcoder**: HandBrake-based media transcoding with library browsing, job management, presets
- **Media Discovery**: Ollama-powered content recommendations with category filtering
- **Local LLM**: Ollama integration for skill execution, summaries, and media discovery
- **Server Management**: Docker container listing, Cloudflare Tunnel routes, backup status
- **65+ API endpoints** with Swagger docs
- **LLM Benchmarks**: Automated test suites for task quality and tool calling across 7 models

---

## Completed

Features that have been implemented.

| Feature | Status | Description |
|---------|--------|-------------|
| Device Naming / Aliasing | DONE | MAC-to-name mapping for friendly network device names |
| Notification Preferences | DONE | Database-backed notification rules with per-rule toggles and cooldowns |
| Radarr Integration | DONE | 8 movie management tools following the Sonarr pattern |
| Floorplan / Home Map (Phase 2) | DONE | Interactive SVG floor plan with live device overlays and click-to-control |
| AI-Customizable Dashboard | DONE | Widget-based homepage with AI editor and drag-and-drop layout |
| Widget Builder | DONE | AI-powered widget generation via generative UI system |
| Media Discovery | DONE | Ollama-powered content recommendations |
| Server Management | DONE | Docker containers, Cloudflare tunnels, backup status |
| Transcoder | DONE | HandBrake-based library transcoding with job management |
| Local LLM Support | DONE | Ollama integration for local model execution |
| Reports | DONE | Long-term energy and network data aggregation |
| Deep Agent | DONE | Standalone 49-tool LangChain Deep Agent service |

---

## Planned

### Dashboard Real-Time Updates

**Priority**: High | **Effort**: Medium | **Status**: PLANNED

Add WebSocket or SSE connection from dashboard to backend for instant entity state updates. The backend already maintains HA WebSocket subscription -- the plumbing is in `state.py`. Eliminates the current 15-30 second polling delay for lights, switches, sensors, and presence changes.

### Presence-Based Automations

**Priority**: High | **Effort**: Medium | **Status**: PLANNED

Build presence-based skill templates using Deco device_tracker state changes as triggers. Scenarios: auto-lights on arrival (after sunset), last-person-left lockdown, sleep detection (network inactivity after midnight), work mode (suppress notifications when laptop connects).

### Energy Cost Optimization

**Priority**: High | **Effort**: Medium | **Status**: PLANNED

Phase 1: Time-of-use rate structures (peak/off-peak). Phase 2: Monthly budget tracking with projected cost alerts. Phase 3: AI-powered cost optimization suggestions in weekly energy reports.

### Spotify / Music Control

**Priority**: High | **Effort**: Medium | **Status**: PLANNED

Spotify-specific tools (search, play, queue, now playing, transfer playback) via HA Spotify integration and Spotify Web API. "Now Playing" widget type for the dashboard.

### Speed Test Integration

**Priority**: Medium | **Effort**: Low | **Status**: PLANNED

Pull HA Speedtest integration sensors (download, upload, ping) into the Network page. Trend chart overlaying ISP speed vs Deco throughput. Alert when ISP speed drops below threshold.

### Guest Mode / New Device Detection

**Priority**: Medium | **Effort**: Low | **Status**: PLANNED

Track known device MACs, alert when unknown devices connect to WiFi. Telegram notification with option to trust. Guest visit history tracking.

### Camera Motion Detection Feed

**Priority**: Medium | **Effort**: Medium | **Status**: PLANNED

Subscribe to motion sensor state changes, auto-capture snapshots, build a security timeline. Cross-reference with presence for "motion detected, nobody home" alerts.

### Voice Interface

**Priority**: High | **Effort**: High | **Status**: PLANNED

Voice input for Telegram (Whisper/Gemini STT) and dashboard (Web Speech API). Optional TTS responses. Stretch goal: wake word detection for always-listening wall tablet mode.

### Multi-Room Audio Visualization

**Priority**: Medium | **Effort**: Medium | **Status**: PLANNED

Unified "Now Playing" view across all speakers. Per-room play/pause/skip/volume controls. "Play everywhere" grouping. Spotify URI transfer between devices.

### Floorplan Enhancements

**Priority**: Medium | **Effort**: Medium | **Status**: PLANNED

Phase 1: Room cards (grouped device views per room). Phase 3: Deco mesh coverage overlay on floorplan. Drag-and-drop device placement editor. Multi-floor support.

### AdGuard Home / DNS Stats

**Priority**: Low | **Effort**: Low | **Status**: PLANNED

Pull DNS-level ad blocking stats into the Network page. Total queries, blocked queries, block rate, top clients, top blocked domains.

---

## Suggested Implementation Order

### Phase 1 -- Quick Wins (1-2 days each)

1. Speed test integration
2. Guest mode / new device detection

### Phase 2 -- Core Improvements (3-5 days each)

1. Dashboard real-time updates (WebSocket)
2. Presence-based automations
3. Energy cost optimization
4. Spotify / music control

### Phase 3 -- Major Features (1-2 weeks each)

1. Camera motion detection feed
2. Multi-room audio visualization
3. Floorplan enhancements

### Phase 4 -- Ambitious Projects (2-4 weeks each)

1. Voice interface
2. AdGuard Home integration
