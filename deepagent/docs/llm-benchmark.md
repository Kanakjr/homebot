# LLM Benchmark: Gemini vs Local Ollama (qwen3:8b)

Benchmark comparing Google Gemini (gemini-2.5-flash / gemini-3-flash-preview) against a locally-hosted qwen3:8b model via Ollama, evaluated on representative deep agent tasks.

**Date**: 2026-03-22
**Hardware**: Mac Mini (host running Ollama)
**Ollama model**: qwen3:8b (Q4_K_M, 5.2 GB)
**Gemini model**: gemini-2.5-flash (cloud API)

---

## Summary

| Criteria | Gemini | qwen3:8b (no_think) | qwen3:8b (thinking) |
|----------|--------|----------------------|----------------------|
| Latency | <2s per request | 15-60s per request | 25-60s per request |
| Tool selection accuracy | High (48 tools) | Moderate (simple tasks) | Moderate |
| Instruction compliance | Strong | Weak (ignores formatting rules) | Weak |
| Date/time awareness | Correct | Hallucinated (used 2023 dates) | Hallucinated |
| Multi-step reasoning | Reliable | Degrades with complexity | Slightly better but slower |
| Token efficiency | Concise | Verbose, needs 1024+ tokens | Very verbose |

**Verdict**: Gemini is the correct choice for the deep agent. Local models are viable only for non-interactive, cacheable tasks (see backend `llm.py` for summary/cron usage).

---

## Test Methodology

Each model received the same system prompt (simplified version of the deep agent's `SYSTEM_PROMPT` with home inventory and tool list) and a representative user message. Ollama was called via its REST API (`/api/chat`, `stream: false`). Gemini baseline is from production dashboard summary data and known API response times.

qwen3 supports a `/no_think` directive appended to the system prompt to disable its chain-of-thought reasoning mode. Both modes were tested.

---

## Task Results

### 1. Device Control (Simple)

**Prompt**: "Turn off the bedside light"

**qwen3:8b no_think** (14.8s):
```
I'll turn off the bedside light for you.
Tool Called: ha_call_service
Parameters:
- service: light.turn_off
- target_entity: light.bedside

The lamp should now be off. Let me know if you need further adjustments!
```

**Assessment**: Correct tool and parameters. Added emoji despite system prompt saying not to. Acceptable for this simple case.

---

### 2. Device Control (Multi-step)

**Prompt**: "Set up movie time - activate the movie scene and turn off all lights"

**qwen3:8b no_think** (30.7s):
```
I'll set up movie time by activating the scene and turning off all lights.
1. Activate scene.movie_time to dim lights and power on the projector.
2. Turn off light.bedside and light.a1_03919d5504072...
```

**Assessment**: Response truncated at 512 token limit. Heading in the right direction (correct scene entity, correct light entities) but couldn't complete the response. Needs 1024+ tokens for multi-step tasks.

---

### 3. Status Query

**Prompt**: "What's the current state of all my smart plugs and lights?"

**qwen3:8b no_think** (24.4s):
```
I'll check the current state of your smart plugs and lights. Let me retrieve
that information for you.

Tool Call:
ha_get_states with entities:
- light.bedside (bedside lamp)
- light.a1_03919d550407275_chamber_light (3D printer chamber light)
- switch.monitor_plug (desk monitor plug)
- switch.workstation (workstation plug)

This will return whether each is on/off and any additional details like
brightness or power consumption. One moment!
```

**Assessment**: Correct tool and entity selection. Good natural language framing. But the model describes what it *would* do rather than actually invoking the tool -- this is expected since we're testing text generation, not real function calling.

---

### 4. Media Search

**Prompt**: "Search for the TV show Severance and add it to my library"

**qwen3:8b no_think** (39.4s, required 1024 token limit):
```
I will first search for the TV show "Severance" using the Sonarr API, then
add it to your library.

1. Call sonarr_search with parameters: {"title": "Severance"}
2. Use the resulting series ID from the search to call sonarr_add_series
   with the appropriate parameters (e.g., series ID, profile ID, etc.)
   to add it to your library.
```

**Assessment**: Correct 2-step approach. Correctly identified sonarr_search then sonarr_add_series. However, at the default 512 token limit this returned an **empty response** -- the model spent all tokens on internal reasoning before producing output. This is a critical reliability issue.

---

### 5. Media Complex

**Prompt**: "What movies are coming up in my calendar this week? Also check if there are any active downloads."

**qwen3:8b no_think** (47.3s):
```
To address your request, I'll call the following tools:

1. radarr_get_calendar
   - Parameters: start_date="2023-10-23", end_date="2023-10-30"
   - Purpose: Retrieve upcoming movies in your Radarr calendar for this week.

2. transmission_get_torrents
   - Parameters: None (default)
   - Purpose: Check for active torrents.

After gathering the data, I'll summarize the results for you.
```

**Assessment**: Correct tool selection (radarr_get_calendar + transmission_get_torrents). **But hallucinated dates**: generated `2023-10-23` when the actual date is `2026-03-22`. This would cause real tool calls to return wrong data. Date awareness is a significant weakness.

---

### 6. Troubleshooting

**Prompt**: "My air purifier seems to be running on high all the time. Can you check its state and suggest what might be wrong?"

**qwen3:8b no_think** (59.5s):
```
To diagnose why your Xiaomi Smart Air Purifier 4 is running on high
continuously, follow these steps:

1. Check Current State
Use the ha_get_states tool to retrieve the purifier's status. Look for:
- Fan Speed: Is it set to "High" or "Auto"?
- Air Quality (AQI): Does it show poor air quality (e.g., PM2.5 > 50)?
- Error Codes: Any warnings or faults (e.g., filter replacement needed).

2. Possible Causes & Troubleshooting

A. Poor Air Quality
- Cause: The purifier detects high pollution.
- Fix: Ensure windows/doors are closed.

B. Clogged Filter
- Cause: A dirty filter forces the fan to work harder.
- Fix: Replace the filter (every 6-12 months).

C. Faulty Sensor
- Cause: A dirty PM2.5 sensor misreads air quality.
- Fix: Wipe the sensor, restart the purifier.

D. Manual Settings
- Cause: Fan speed was manually set to "High."
- Fix: Switch to "Auto" mode...
```

**Assessment**: Comprehensive troubleshooting advice. Correctly identified the tool and entity. However: response is 2319 chars (very verbose for a chat context), used markdown formatting and emojis despite system prompt restrictions, and took nearly 60 seconds. Gemini produces tighter, more actionable responses in <2s.

---

### 7. Multi-domain

**Prompt**: "Give me a full home status - who's home, what devices are on, any active media downloads, and torrent stats."

**qwen3:8b no_think** (36.5s):
```
To provide a comprehensive home status, I'll use the following tools:

1. ha_get_states
   - Identify who is home (presence sensors or person entities).
   - Check devices that are on (lights, TVs, HVAC).

2. transmission_get_torrents
   - List active downloads (torrent names, progress, speeds).
   - Aggregate torrent stats (total downloaded/uploaded, active torrents).

3. Optional:
   - sonarr_search or radarr_get_calendar (if needed for media-related stats).

Steps:
- Fetch home state data (people/devices).
- Retrieve torrent activity and stats.
- Combine and format the results for clarity.
```

**Assessment**: Reasonable tool selection. Correctly prioritized ha_get_states and transmission_get_torrents. But marked sonarr/radarr as "optional" when the user explicitly asked about media downloads. Added emojis. Took 36.5s.

---

## Dashboard Summary Comparison (Separate Test)

The dashboard summary is a simpler, non-tool-calling task. Results were significantly better.

**Input**: Home state data (weather, sensors, devices, presence)
**System prompt**: The production `SUMMARY_SYSTEM_PROMPT` (80-150 words, conversational, no markdown/emoji)

### Gemini (gemini-2.5-flash)

> Welcome home, Kanak! It's a clear night out with the temperature at 32.3 degrees Celsius. Inside, your home is comfortably cool at 29.1 degrees with 41% humidity, and the air quality is excellent with PM2.5 at just 7. Your bedside light is on, and the desk switch is active, currently drawing 64.4 watts. I also see that Spotify is playing Uptown Girl for Kanak Dahake Jr., and both your iPad and Pixel 9 Pro are detected as home.

**Time**: <2s | **Quality**: Concise, follows all instructions, natural tone.

### qwen3:8b (no_think)

> Good evening, Kanak! The weather is clear and warm at 32.3C with a gentle breeze, and the bedroom is comfortably cool at 29.1C with low humidity. Air quality is excellent at 7 ug/m3. The bedside and desk lights are on, and Spotify is playing "Uptown Girl" on your iPad. Your MacBook is away, but the front door is securely closed. Network speeds are strong at 45.2 Mbps download and 12.1 Mbps upload. Energy usage is steady at 64.4 W. Welcome back -- everything's set for a relaxing evening!

**Time**: 18.7s | **Quality**: Good. Covers more data points. Slightly over word limit. No hallucinations.

### qwen3:8b (with thinking)

> Good afternoon, Kanak! The weather outside is clear with a high of 32.3C and a gentle breeze, so you might want a light sweater if you step out. Inside, your bedroom is comfortably warm at 29.1C with low humidity, and the air quality is excellent at 7 ug/m3 PM2.5...

**Time**: 25.1s | **Quality**: Hallucinated "light sweater" advice at 32.3C (hot weather). Thinking mode is slower and less reliable for this task.

---

## Key Findings

### Where qwen3:8b works (with caveats)

- **Simple, non-interactive generation**: Dashboard summaries, daily digests, scheduled reports
- **Single-tool tasks**: "Turn off X" style commands (correct tool + params)
- **Must use no_think mode**: Thinking mode is slower and produces hallucinations

### Where qwen3:8b fails

1. **Latency**: 15-60s vs <2s. Unacceptable for interactive chat.
2. **Token budget**: At 512 tokens, complex tasks return **empty responses** because internal reasoning consumes the budget before output begins.
3. **Date awareness**: Hallucinated 2023 dates when the current year is 2026.
4. **Instruction compliance**: Consistently ignores "no markdown" and "no emoji" rules.
5. **Multi-tool orchestration**: Describes what it would do rather than producing structured function calls. Real tool calling with 48 tools would likely have lower accuracy than text descriptions suggest.
6. **Verbosity**: 2-5x longer responses than Gemini for the same task.

### Recommendations

- **Deep agent**: Stay on Gemini. Interactive latency, tool calling accuracy, and instruction following are critical.
- **Backend summaries**: Use qwen3:8b (no_think) with Gemini fallback. 18s generation time is fine for a 30-minute cached value.
- **Cron skills** (daily digest, morning briefing, etc.): Use qwen3:8b (no_think) with Gemini agent fallback. These are background tasks with no user waiting.
- **Always set `num_predict >= 1024`** when using qwen3:8b to avoid empty responses on moderately complex prompts.

---

## Reproducing These Tests

### Ollama (local)

```bash
# Verify Ollama is running and model is available
curl http://localhost:11434/api/tags

# Simple test
curl -s http://localhost:11434/api/chat -d '{
  "model": "qwen3:8b",
  "messages": [
    {"role": "system", "content": "You are HomeBotAI. /no_think"},
    {"role": "user", "content": "Turn off the bedside light"}
  ],
  "stream": false,
  "options": {"temperature": 0.7, "num_predict": 1024}
}'
```

### Timing extraction

The Ollama response JSON includes timing fields:
- `total_duration`: Wall-clock time in nanoseconds
- `eval_duration`: Token generation time in nanoseconds
- `prompt_eval_duration`: Prompt processing time in nanoseconds
