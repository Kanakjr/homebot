---
name: energy-insights
description: Analyze energy consumption, power usage, and battery levels from Home Assistant sensors. Use when the user asks about electricity, power draw, energy costs, or battery status.
tags: [energy, power, sensors, battery]
---

# Energy Insights

## Known Energy Entities (use directly, no search needed)

### Power (real-time watts)
- `sensor.monitor_plug_current_consumption` -- Desk monitor plug (W)
- `sensor.workstation_current_consumption` -- Workstation plug (W)

### Energy (cumulative kWh)
- `sensor.monitor_plug_today_s_consumption` -- Desk today (kWh)
- `sensor.monitor_plug_this_month_s_consumption` -- Desk this month (kWh)
- `sensor.workstation_today_s_consumption` -- Workstation today (kWh)
- `sensor.workstation_this_month_s_consumption` -- Workstation this month (kWh)

### Battery Levels
- `sensor.ipad_battery_level` -- iPad (%)
- `sensor.pixel_9_pro_battery_level` -- Pixel 9 Pro (%)
- `sensor.galaxy_watch8_classic_krbx_battery_level` -- Galaxy Watch (%)

## Efficient Queries

- For power + energy: `ha_search_entities(query="consumption")` returns all power and energy sensors in one call.
- For batteries: `ha_search_entities(query="battery")` returns all battery entities in one call.
- Two calls total cover everything. Do NOT search sensor-by-sensor or room-by-room.

## Cost Estimation

Flat electricity rate: ~8 INR per kWh.
- Daily cost = total kWh * 8
- Monthly estimate = daily average * 30

## Tips

- Battery below 20% should be flagged as a warning.
- "What's using the most power?" -- get all power sensors and compare values.
- For historical trends, suggest the Energy page on the dashboard.
