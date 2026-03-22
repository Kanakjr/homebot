---
name: device-control
description: Control Home Assistant devices -- lights, switches, fans, cameras, scenes. Use when the user wants to turn on/off devices, adjust brightness, or check device states.
tags: [homeassistant, devices, control]
---

# Device Control via Home Assistant

## Known Devices

### Lights (only 2 in the home)
| Entity ID | Friendly Name |
|-----------|--------------|
| `light.bedside` | Bedside lamp |
| `light.a1_03919d550407275_chamber_light` | Printo 3D printer chamber light |

### Smart Plugs (main controllable ones)
| Entity ID | Friendly Name |
|-----------|--------------|
| `switch.monitor_plug` | Desk monitor plug |
| `switch.workstation` | Workstation plug |

### Fans (2 total)
| Entity ID | Friendly Name |
|-----------|--------------|
| `fan.xiaomi_smart_air_purifier_4` | Xiaomi Air Purifier 4 |
| `fan.a1_03919d550407275_cooling_fan` | Printo 3D printer cooling fan |

### Cameras
| Entity ID | Friendly Name |
|-----------|--------------|
| `camera.bedroom_camera_live_view` | Bedroom camera (often unavailable) |
| `camera.a1_03919d550407275_camera` | Printo 3D printer camera |

### Scenes
- `scene.movie_time` -- dims lights, sets up media
- `scene.movie_time_paused` -- paused movie scene
- `scene.relax` -- relaxation lighting

There are also ~25 switch entities, but most are config toggles (auto-update, LED indicators, camera settings). The user-controllable switches are the two plugs listed above.

## How to Control Devices

Use `ha_call_service(domain, service, entity_id, data)`:

- **Lights**: `turn_on` / `turn_off`. Optional data: `{"brightness": 128}` (0-255), `{"color_temp_kelvin": 4000}`, `{"rgb_color": [255,0,0]}`
- **Switches**: `turn_on` / `turn_off` / `toggle`
- **Fans**: `turn_on` / `turn_off`. Optional: `{"preset_mode": "auto"}`
- **Scenes**: `scene.turn_on` to activate

## Efficiency

- Since there are only 2 lights, `ha_get_states(domain="light")` gives you everything in one call. No need to search by room.
- For "what's on?" queries, check `ha_get_states` for the relevant domain -- do NOT search room-by-room.
- Use `ha_search_entities(query="...")` only when looking for something by keyword that isn't listed above.

## Tips

- Brightness: 50% = 128, 100% = 255. Color temp: 2700K = warm, 4000K = neutral, 6500K = daylight.
- "Turn off everything" = get lights and switches that are "on", then turn_off each.
- Always confirm actions in your response.
