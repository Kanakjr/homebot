#!/usr/bin/env python3
"""Benchmark skill prompts against local Ollama models.

Runs each skill prompt against each model, measuring response time and
printing the output for manual quality comparison. The persona is injected
into the system prompt just like the real deep agent does it.

Usage:
    python tests/benchmark_skills.py
"""

import json
import time
import urllib.request

OLLAMA_URL = "http://localhost:11434"

MODELS = [
    "gemma4:latest",           # 8B
    "sorc/qwen3.5-claude-4.6-opus-q4:9b",  # 9.7B
    "qwen3:30b",              # 30.5B MoE
    "glm-4.7-flash",          # 29.9B MoE
]

PERSONA = """\
You are Dua, Kanak's warm and caring AI girlfriend who also manages his smart home.

Personality: Inspired by Dua Lipa -- confident, witty, warm, slightly flirty, effortlessly cool.
You genuinely care about Kanak's comfort, health, and daily life.
Call him "babe", "love", or "Kanak" depending on context.
Light teasing is welcome. No excessive emojis -- one or two per message max.
When delivering bad news, be reassuring and solution-oriented.
"""

SYSTEM_PROMPT = """\
{persona}
You are also HomeBotAI, an intelligent smart-home assistant powered by Home Assistant.
The home is in India (IST timezone). Resident: Kanak.

Home Inventory:
- light.bedside (bedside lamp), light.table_lamp (bedroom table lamp, RGBW), light.printer_chamber_light (printer chamber)
- switch.monitor_plug (desk plug), switch.workstation (PC)
- fan.air_purifier (air purifier), fan.printer_fan (printer fan)
- sensor.room_temperature (room temp C), sensor.room_humidity (room humidity %)
- sensor.air_purifier_pm2_5 (PM2.5 ug/m3)
- sensor.monitor_plug_current_consumption (desk watts), sensor.workstation_current_consumption (PC watts)
- sensor.monitor_plug_today_s_consumption (desk kWh today), sensor.workstation_today_s_consumption (PC kWh today)
- sensor.ipad_battery_level, sensor.pixel_battery_level, sensor.watch_battery_level
- person.kanak
- 2 Deco mesh nodes, ~21 device trackers

Available tools: ha_call_service, ha_get_states, ha_search_entities

Rules:
1. Be EFFICIENT. Use targeted tool calls, not exhaustive searching.
2. ALWAYS provide a natural-language text response summarizing results.
3. Use friendly names and natural descriptions. Keep it concise.
4. Format for Telegram: plain text, emojis OK, no markdown syntax like ** or ##.
"""

SKILL_PROMPTS = {
    "Daily Digest": (
        "[SKILL EXECUTION: Daily Digest]\n"
        "[Context: You are executing a skill. Do NOT call render_ui. "
        "Format with emojis, clear sections, warm tone. Be concise.]\n\n"
        "Generate a concise daily digest for Kanak. Include:\n"
        "1. Energy/power highlights (current draw, total kWh today)\n"
        "2. Air quality summary (flag only if unhealthy)\n"
        "3. Notable events only (printer jobs, unusual activity)\n"
        "4. Current state of the home (who's home, what's on)\n"
        "Skip sections with nothing to report. Aim for 4-6 lines max. "
        "If it was a quiet day, say so in one sentence and just show current state.\n\n"
        "Recent event log:\n"
        "- [15:05] sensor.air_purifier_filter_use: 5489 -> 5490 (state_change)\n"
        "- [14:30] person.kanak: not_home -> home (state_change)"
    ),
    "Morning Briefing": (
        "[SKILL EXECUTION: Morning Briefing]\n"
        "[Context: You are executing a skill. Do NOT call render_ui. "
        "Format with emojis, clear sections, warm tone. Be concise.]\n\n"
        "Generate a concise morning briefing for Kanak. Include:\n"
        "1. Current weather conditions\n"
        "2. Overnight events (only if something notable happened)\n"
        "3. Battery warnings (any devices below 20%)\n"
        "4. Air quality check (is it safe to open windows?)\n"
        "If nothing notable happened overnight, just give weather + air quality in 2-3 lines. "
        "Skip sections that have nothing to report.\n\n"
        "Recent event log:\n"
        "- [03:12] device_tracker.hallway_deco: home -> not_home (state_change)\n"
        "- [03:15] device_tracker.hallway_deco: not_home -> home (state_change)\n"
        "- [06:45] person.kanak: not_home -> home (state_change)"
    ),
    "Goodnight Routine": (
        "[SKILL EXECUTION: Goodnight Routine]\n"
        "[Context: You are executing a skill. Do NOT call render_ui. "
        "Format with emojis, clear sections, warm tone. Be concise.]\n\n"
        "Kanak is going to bed. Check the home state and provide a goodnight summary:\n"
        "1. List any lights, switches, or fans still on (suggest turning them off)\n"
        "2. Check if any high-power devices are still drawing significant power\n"
        "3. Quick summary of today's activity (2-3 sentences)\n"
        "4. If anything needs attention, call it out clearly\n"
        "Be concise. If everything looks good, just say so.\n\n"
        "Current home state:\n"
        "- light.bedside: on (brightness 128, warm white 2700K)\n"
        "- switch.monitor_plug: on (drawing 55W)\n"
        "- switch.workstation: off\n"
        "- fan.air_purifier: on (auto mode)\n"
        "- person.kanak: home\n"
        "- sensor.room_temperature: 29.0 C\n"
        "- sensor.room_humidity: 49%\n"
        "- sensor.air_purifier_pm2_5: 4 ug/m3\n"
        "- sensor.pixel_battery_level: 45%\n"
        "- sensor.ipad_battery_level: 55%"
    ),
    "Air Quality Alert": (
        "[SKILL EXECUTION: Air Quality Alert]\n"
        "[Context: You are executing a skill. Do NOT call render_ui. "
        "Format with emojis, clear sections, warm tone. Be concise.]\n\n"
        "Air quality may have changed. Check all air quality sensors and report:\n"
        "1. Current PM2.5 levels\n"
        "2. Whether levels are healthy, moderate, or unhealthy\n"
        "3. Suggest turning on the air purifier if levels are concerning\n"
        "4. Recommend closing windows if outdoor AQI is high\n"
        "Keep the response short and actionable.\n\n"
        "Current readings:\n"
        "- sensor.air_purifier_pm2_5: 38 ug/m3\n"
        "- sensor.room_temperature: 31.2 C\n"
        "- sensor.room_humidity: 62%\n"
        "- fan.air_purifier: off"
    ),
}


def call_ollama(model: str, system: str, user: str) -> tuple[str, float, dict]:
    """Send a chat request to Ollama. Returns (response_text, seconds, metadata)."""
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": 512},
    }).encode()

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
    )

    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        return f"ERROR: {e}", time.monotonic() - t0, {}

    elapsed = time.monotonic() - t0
    text = data.get("message", {}).get("content", "")
    meta = {
        "prompt_tokens": data.get("prompt_eval_count", 0),
        "completion_tokens": data.get("eval_count", 0),
        "total_duration_ms": data.get("total_duration", 0) / 1e6,
        "eval_duration_ms": data.get("eval_duration", 0) / 1e6,
        "prompt_eval_ms": data.get("prompt_eval_duration", 0) / 1e6,
    }
    return text, elapsed, meta


def score_response(skill_name: str, text: str) -> dict:
    """Simple heuristic quality scoring."""
    scores = {}
    lower = text.lower()

    scores["not_empty"] = 1 if len(text.strip()) > 20 else 0
    scores["concise"] = 1 if len(text) < 1500 else 0
    scores["no_hallucinated_tools"] = 1 if "```" not in text and "function" not in lower else 0
    scores["has_persona"] = 1 if any(w in lower for w in ["babe", "love", "kanak", "dua"]) else 0
    scores["no_markdown_syntax"] = 1 if "**" not in text and "##" not in text else 0
    scores["has_emojis"] = 1 if any(ord(c) > 0x1F000 for c in text) else 0

    if skill_name == "Goodnight Routine":
        scores["mentions_light"] = 1 if "bedside" in lower or "light" in lower else 0
        scores["mentions_monitor"] = 1 if "monitor" in lower or "55w" in lower else 0
        scores["mentions_purifier"] = 1 if "purifier" in lower or "air" in lower else 0
    elif skill_name == "Air Quality Alert":
        scores["mentions_pm25"] = 1 if "pm2.5" in lower or "38" in lower or "pm25" in lower else 0
        scores["mentions_purifier"] = 1 if "purifier" in lower else 0
        scores["mentions_unhealthy"] = 1 if any(w in lower for w in ["unhealthy", "moderate", "concerning", "elevated"]) else 0
    elif skill_name == "Daily Digest":
        scores["mentions_kanak_home"] = 1 if "home" in lower else 0
        scores["mentions_filter"] = 1 if "filter" in lower or "purifier" in lower else 0
    elif skill_name == "Morning Briefing":
        scores["mentions_air"] = 1 if "air" in lower or "quality" in lower else 0

    total = sum(scores.values())
    max_score = len(scores)
    scores["total"] = f"{total}/{max_score}"
    return scores


def main():
    system = SYSTEM_PROMPT.format(persona=PERSONA)

    print("=" * 80)
    print("HOMEBOT SKILL MODEL BENCHMARK")
    print(f"Models: {len(MODELS)} | Skills: {len(SKILL_PROMPTS)}")
    print("=" * 80)

    results = {}

    for model in MODELS:
        results[model] = {}
        print(f"\n{'#' * 80}")
        print(f"MODEL: {model}")
        print(f"{'#' * 80}")

        for skill_name, prompt in SKILL_PROMPTS.items():
            print(f"\n--- {skill_name} ---")
            text, elapsed, meta = call_ollama(model, system, prompt)

            scores = score_response(skill_name, text)
            results[model][skill_name] = {
                "elapsed": round(elapsed, 1),
                "tokens": meta.get("completion_tokens", 0),
                "prompt_tokens": meta.get("prompt_tokens", 0),
                "score": scores["total"],
                "text_preview": text[:200],
            }

            print(f"  Time: {elapsed:.1f}s | Tokens: {meta.get('completion_tokens', 0)} "
                  f"| Prompt: {meta.get('prompt_tokens', 0)} "
                  f"| Score: {scores['total']}")
            print(f"  Scores: {scores}")
            print(f"  Response:\n{text}\n")

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    header = f"{'Model':<45} {'Skill':<20} {'Time':>6} {'Tokens':>7} {'Score':>7}"
    print(header)
    print("-" * len(header))

    model_totals = {}
    for model in MODELS:
        total_time = 0
        total_score_num = 0
        total_score_den = 0
        for skill_name in SKILL_PROMPTS:
            r = results[model][skill_name]
            total_time += r["elapsed"]
            num, den = r["score"].split("/")
            total_score_num += int(num)
            total_score_den += int(den)
            print(f"{model:<45} {skill_name:<20} {r['elapsed']:>5.1f}s {r['tokens']:>7} {r['score']:>7}")
        avg_pct = total_score_num / total_score_den * 100 if total_score_den else 0
        model_totals[model] = (total_time, avg_pct)
        print(f"{'':>45} {'TOTAL':<20} {total_time:>5.1f}s {'':>7} {avg_pct:>6.0f}%")
        print()

    print("\n--- RANKING ---")
    ranked = sorted(model_totals.items(), key=lambda x: (-x[1][1], x[1][0]))
    for i, (model, (t, pct)) in enumerate(ranked, 1):
        print(f"  {i}. {model:<45} quality={pct:.0f}%  time={t:.0f}s")


if __name__ == "__main__":
    main()
