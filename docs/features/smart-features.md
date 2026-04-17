# Smart Features

Advanced context, scheduling, and agent behavior that keep HomeBotAI aware of your home and your conversation.

## Presence tracking

Device trackers and **person** entities are included in every conversation context, so the agent can answer questions such as whether anyone is home, where phones or wearables last reported, and how that relates to automations.

Typical queries:

- Is anyone home?
- Where am I?
- Which tracked devices are at home?

Presence data is summarized for the model on each turn so answers stay aligned with live Home Assistant state.

## Context-aware state summary

The home state summary is filtered by **keywords** in your message. Mentioning a topic pulls in related entities that might otherwise be omitted for brevity.

| Keyword or topic | What gets emphasized |
|------------------|------------------------|
| printer, 3D, print job | 3D printer telemetry and related sensors |
| battery, watch, phone | Battery levels across devices |
| Xbox, TV, media, Spotify | Media players and playback context |
| energy, power | Power and energy sensors |
| camera | Camera entities and details |
| purifier | Air purifier / climate entities even when idle |

This keeps responses focused when you ask narrowly, and expansive when you ask about a specific subsystem.

## Recent changes

State changes are kept in a **rolling ten-minute buffer**. The summary can include a **Recent Changes** section so short-lived events (toggles, brief sensor spikes) remain visible in context.

Example:

```text
Recent Changes: light.bedside: off->on | switch.monitor_plug: on->off
```

## Anomaly detection

Unusual conditions are surfaced in the summary (for example under an alerts-style section):

| Signal | Typical rule |
|--------|----------------|
| Battery critically low | Below 15% |
| High power draw | Above 500 W |
| Doors / windows | Binary sensors indicating open |

## Daily and weekly AI digests

Scheduled **Telegram** summaries run in AI mode:

| Digest | Schedule | Role |
|--------|----------|------|
| Daily | 10:00 PM every day | Activity, energy highlights, notable events, home snapshot |
| Weekly | 8:00 PM every Sunday | Broader trends, usage patterns, suggestions |

You can manage these skills from the dashboard (toggle, cron, prompts). They are created at bootstrap and remain idempotent (existing definitions are not overwritten).

## Proactive notifications

The reactor can send **Telegram** notifications without a dedicated skill when rules match—for example printer finished, battery low, welcome home, or left home. Each rule uses a **five-minute cooldown** per entity to limit duplicate alerts when states fluctuate.

Notification behavior is **configurable** (rules and thresholds in the database and settings), so you can tune or disable categories without editing code.

## Multi-turn tool planning

The agent is guided to **chain tools** for multi-step workflows—for example media search, indexer checks, and download clients—and to use **confirmation flows** before destructive actions (bulk deletes, clearing history, disabling automations). After a confirmation prompt, short affirmations such as “yes” or “go ahead” continue the planned sequence.

This balances automation with safety for irreversible or wide-impact operations.
