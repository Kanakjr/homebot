---
name: energy-insights
description: Analyze energy, power, battery, temperature, humidity, and air quality from Home Assistant sensors. Use whenever the user asks about electricity, power draw, energy costs, battery status, room temperature, humidity, air quality, how warm/cold/stuffy the room is, or whether to open a window.
tags: [energy, power, sensors, battery, temperature, humidity, air-quality, environment]
---

# Energy and Environment Insights

## Known Entities (use directly, no search needed)

### Indoor Environment
- `sensor.sensor_temperature` -- Room temperature (C)
- `sensor.sensor_humidity` -- Room humidity (%)
- `sensor.xiaomi_smart_air_purifier_4_temperature` -- Purifier temperature reading (C)
- `sensor.xiaomi_smart_air_purifier_4_humidity` -- Purifier humidity reading (%)
- `sensor.xiaomi_smart_air_purifier_4_pm2_5` -- PM2.5 air quality (ug/m3)

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

- For environment: query the 5 indoor entities above directly. Two standalone sensors + three from the purifier.
- For power + energy: `ha_search_entities(query="consumption")` returns all power and energy sensors in one call.
- For batteries: `ha_search_entities(query="battery")` returns all battery entities in one call.
- IMPORTANT: Do NOT use `ha_get_states(domain="sensor")` for targeted queries -- there are 140+ sensors and results are truncated. Use `ha_search_entities` or query known entity IDs directly.
- If a targeted lookup returns nothing, fall back to `ha_search_entities(query="temperature")` (or "humidity", "pm2", "battery") before telling the user you have no access. These sensors ALWAYS exist.

## Presentation rules (strict)

Sensor data on Telegram often looks noisy because multiple devices report the same quantity. Collapse it:

1. Never quote raw entity_ids or vendor model names ("Xiaomi Smart Air Purifier 4") back to the user. Refer to "the room", "the purifier", or just state the value.
2. If two or more sensors report the same quantity within a small delta, **synthesize one value**, do not list both:
   - Temperature within ~1C -> report the midpoint ("around 28C").
   - Humidity within ~5%RH -> report the midpoint ("humidity mid-50s").
   - Power within ~20% -> report the total or max with context.
3. Good: "Room is around 28C, humidity mid-50s. Air quality is clean (PM2.5 at 3)."
4. Bad: "The Xiaomi Smart Air Purifier reports 28.3C and humidity of 52%. There's also another sensor showing 28.7C and 56% humidity."
5. For "how warm is it" or "can I open the window" style questions, answer the QUESTION, not just the readings. Give a one-word verdict first (cool / comfortable / warm / hot) then the number.

## Cost Estimation

Flat electricity rate: ~8 INR per kWh.
- Daily cost = total kWh * 8
- Monthly estimate = daily average * 30

## Air Quality Reference

- PM2.5 below 12 ug/m3 = clean
- PM2.5 12-35 ug/m3 = moderate
- PM2.5 above 35 ug/m3 = poor; sensitive groups should stay inside

## Tips

- Battery below 20% should be flagged as a warning.
- "What's using the most power?" -- get all power sensors and compare values.
- For historical trends, suggest the Energy page on the dashboard.
