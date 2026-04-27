---
name: device-control
description: Control Home Assistant devices -- lights, switches, fans, cameras, scenes. Use when the user wants to turn on/off devices, adjust brightness, or check device states.
tags: [homeassistant, devices, control]
---

# Device Control via Home Assistant

## Known Devices

### Lights (2 in the home)
| Entity ID | Friendly Name |
|-----------|--------------|
| `light.bedside` | Bedside lamp (TP-Link, HS color + tunable white 2500-6500K, accepts any `rgb_color`) |
| `light.table_lamp` | Table lamp (WiZ RGBW + tunable white 2200-6500K, bedroom) |

### Alexa-proxy scripts (RGB LED strip)
The Homemate RGB LED strip has no local API, so we control it by having HA speak
commands at an Echo. These scripts are in the **`script`** domain, not `light`.

| Script | Does | Example call |
|--------|------|--------------|
| `script.rgb_strip_on` | Tells Alexa: "turn on smart rgb led strip" | `ha_call_service(domain="script", service="rgb_strip_on")` |
| `script.rgb_strip_off` | Tells Alexa: "turn off smart rgb led strip" | `ha_call_service(domain="script", service="rgb_strip_off")` |
| `script.rgb_strip_brightness` | Needs `level` field (0-100) | `ha_call_service(domain="script", service="rgb_strip_brightness", data={"level": 50})` |
| `script.rgb_strip_color` | Needs `color` field | `ha_call_service(domain="script", service="rgb_strip_color", data={"color": "red"})` |

Known color names the strip responds to: red, green, blue, yellow, orange, purple,
pink, warm white, cool white, daylight. Anything else Alexa may refuse.

The trip produces a ~1-2 sec delay plus a verbal "okay" from `media_player.kanak_s_echo_dot`.
When the user says "turn on the strip / led strip / rgb strip", call
`script.rgb_strip_on`; do not search `light.*` for it — there's no light entity
for this device.

### Smart Plugs (main controllable ones)
| Entity ID | Friendly Name |
|-----------|--------------|
| `switch.monitor_plug` | Desk plug |
| `switch.workstation` | Workstation plug |

### Fans (2 total)
| Entity ID | Friendly Name |
|-----------|--------------|
| `fan.air_purifier` | Air purifier |
| `fan.printer_fan` | 3D printer cooling fan |

### Cameras
| Entity ID | Friendly Name |
|-----------|--------------|
| `camera.bedroom_camera_live_view` | Bedroom camera (often unavailable) |
| `camera.printer` | 3D printer camera (state is only `streaming` / `idle` — it does NOT tell you whether a print is running) |

### 3D Printer (Bambu Lab A1, exposed via `ha-bambulab`)
The printer is named `Printo`. To answer "what is the printer doing"
or "what's the status of my 3D print", read these entities (NOT the
`camera.printer` state -- that only reports the video stream):

| Entity ID | What it tells you |
|-----------|-------------------|
| `binary_sensor.printer_online` | `on` if connected via MQTT |
| `binary_sensor.printer_error` | `on` if the printer reports a fault |
| `sensor.printer_current_stage` | Machine stage: `idle`, `printing`, `heatbed_preheating`, `auto_bed_leveling`, etc. |
| `sensor.printer_status` | High-level status string (`running`, `idle`, ...) |
| `sensor.printer_progress` | Print progress percentage (0-100) |
| `sensor.printer_current_layer` / `sensor.printer_total_layers` | Layer progress |
| `sensor.printer_remaining_time` | Minutes/hours left (unit varies; default hours) |
| `sensor.printer_end_time`, `sensor.printer_start_time` | ISO timestamps |
| `sensor.printer_task_name`, `sensor.printer_gcode` | Current job name |
| `sensor.printer_bed_temp`, `sensor.printer_bed_target` | Bed temperature / target (°C) |
| `sensor.printer_nozzle_temp`, `sensor.printer_nozzle_target` | Nozzle / hotend temperature / target (°C) |
| `sensor.printer_spool` | Loaded filament (e.g. "Generic PLA") |

Pause/resume/stop the printer via `button.printer_pause`,
`button.printer_resume`, `button.printer_stop` (domain `button`,
service `press`).

There are also ~25 switch entities, but most are config toggles (auto-update, LED indicators, camera settings). The user-controllable switches are the two plugs listed above.

## How to Control Devices

Use `ha_call_service(domain, service, entity_id, data)`:

- **Lights**: `turn_on` / `turn_off`. Optional data: `{"brightness": 128}` (0-255), `{"color_temp_kelvin": 4000}`, `{"rgb_color": [255,0,0]}`
- **Switches**: `turn_on` / `turn_off` / `toggle`
- **Fans**: `turn_on` / `turn_off`. Optional: `{"preset_mode": "auto"}`

## Room scopes (fan out, don't ask)

The bedroom is the only room with lights, and it contains exactly three
controllable "lights": `light.bedside`, `light.table_lamp`, and the
Alexa-proxied RGB strip (via `script.rgb_strip_*`). When the user speaks
about the room as a whole rather than a specific device, act on all three in
the SAME turn. Do NOT use `offer_choices` to ask which one.

Trigger phrases that mean "bedroom scope, fan out to all three":

- `"bedroom"`, `"the room"`, `"the bedroom"`
- `"bedroom lights"` (plural), `"all the lights"`, `"all lights"`
- `"set bedroom to X"`, `"turn bedroom on/off"`, `"bedroom warm white"`
- `"dim the room"`, `"brighten the bedroom"`

Worked examples:

| User says | Tool calls (all in one turn) |
|-----------|------------------------------|
| `"Set bedroom to full brightness"` | `ha_call_service("light","turn_on","light.bedside",{"brightness":255})` + `ha_call_service("light","turn_on","light.table_lamp",{"brightness":255})` + `ha_call_service("script","rgb_strip_brightness",data={"level":100})` |
| `"Turn off the bedroom"` | `turn_off` on `light.bedside`, `light.table_lamp`, and `script.rgb_strip_off` |
| `"Bedroom warm white"` | `turn_on` with `color_temp_kelvin=2700` on both lights + `script.rgb_strip_color` with `color="warm white"` |
| `"Dim the room to 30%"` | `brightness=77` on both lights + `script.rgb_strip_brightness` with `level=30` |

Only use `offer_choices` if the user is clearly singular+indefinite
("turn on *a* bedroom light", "which light is the reading one?"). A plain
"bedroom light" still counts as the scope above.

After fanning out, confirm in one sentence ("Bedroom is at full brightness")
— do not re-list the three devices and do not second-guess.

## Colloquial names and long-term memory

Friendly names in HA may not match how the user speaks (e.g. they say “bedroom light” but the entity is `light.bedside`).

1. **Before** you say you could not find a device for a natural-language name, use **`memory_search_notes`** (and `memory_read_note` if needed) on keywords from their phrase — the user may have stored a phrase → `entity_id` mapping under `homebot-brain`.
2. If memory lists a mapping, use that **`entity_id`** with `ha_call_service` (and `render_ui` as usual).
3. If the user **teaches** a mapping in chat, persist it with **`memory_write_note`** (see long-term-memory skill); do **not** default to Home Assistant automations unless they ask for automation inside HA.

## Efficiency

- Since there are only 2 lights, `ha_get_states(domain="light")` gives you everything in one call. No need to search by room.
- For "what's on?" queries, check `ha_get_states` for the relevant domain -- do NOT search room-by-room.
- Use `ha_search_entities(query="...")` only when looking for something by keyword that isn't listed above and memory did not already resolve the name.

## Tips

- Brightness: 50% = 128, 100% = 255. Color temp: 2700K = warm, 4000K = neutral, 6500K = daylight.
- "Turn off everything" = get lights and switches that are "on", then turn_off each.
- Always confirm actions in your response.
