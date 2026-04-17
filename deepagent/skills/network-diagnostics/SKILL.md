---
name: network-diagnostics
description: Diagnose network issues, check connected devices, mesh node status, and bandwidth usage from the TP-Link Deco mesh system via Home Assistant. Use when the user asks about WiFi, network, connected devices, or bandwidth.
tags: [network, deco, wifi, bandwidth, mesh]
---

# Network Diagnostics

The home network runs on a TP-Link Deco mesh system with 2 nodes.

## Known Network Entities

### Mesh Nodes (use these entity IDs directly)
- `device_tracker.hallway_deco` -- Hallway Deco node. State: "home" = online, "not_home" = offline.
- `device_tracker.bedroom_deco` -- Bedroom Deco node. State: "home" = online, "not_home" = offline.

### Bandwidth Sensors (use these entity IDs directly)
- `sensor.total_down` / `sensor.total_up` -- Total bandwidth (kB/s)
- `sensor.bedroom_down` / `sensor.bedroom_up` -- Bedroom Deco node (kB/s)
- `sensor.hallway_down` / `sensor.hallway_up` -- Hallway Deco node (kB/s)
- `sensor.transmission_download_speed` / `sensor.transmission_upload_speed` -- Transmission client (MB/s)

### Connected Devices
All network clients are `device_tracker.*` entities (~21 total). To get the full list in one call:
`ha_get_states(domain="device_tracker")`

Count those with state "home" for connected device count.

### Presence
- `person.kanak` -- state "home" or "not_home"

## Efficiency

- For mesh node status: use `ha_search_entities(query="deco", domain="device_tracker")` -- returns both nodes.
- For bandwidth: use `ha_search_entities(query="down")` or query the known sensor IDs directly.
  Do NOT search for "bandwidth" or "kbps" -- those terms don't appear in entity names.
- For connected devices: one `ha_get_states(domain="device_tracker")` call is enough.
- For presence: `ha_search_entities(query="", domain="person")`

## Conversions

- Bandwidth sensors report kB/s. Convert: 1000 kB/s ~ 8 Mbps.
- If a mesh node is "not_home", flag it as potentially powered off or disconnected.

## Tips

- For detailed network analytics, suggest the Network page on the dashboard.
