"""
Dashboard config persistence.
Stores a single JSON document describing the widget layout.
"""

import json
import logging
import aiosqlite

log = logging.getLogger("homebot.dashboard_config")

DEFAULT_CONFIG = {
    "widgets": [
        {
            "id": "w_temp",
            "type": "stat",
            "title": "Temperature",
            "config": {"entity_id": "sensor.sensor_temperature", "unit": "C"},
            "size": "sm",
        },
        {
            "id": "w_humidity",
            "type": "stat",
            "title": "Humidity",
            "config": {"entity_id": "sensor.sensor_humidity", "unit": "%"},
            "size": "sm",
        },
        {
            "id": "w_pm25",
            "type": "stat",
            "title": "PM2.5",
            "config": {"entity_id": "sensor.xiaomi_smart_air_purifier_4_pm2_5", "unit": "ug/m3"},
            "size": "sm",
        },
        {
            "id": "w_weather",
            "type": "weather",
            "title": "Weather",
            "config": {"entity_id": "weather.forecast_home"},
            "size": "sm",
        },
        {
            "id": "w_lights",
            "type": "toggle_group",
            "title": "Lights",
            "config": {"entities": ["light.bedside", "light.printo_chamber_light"]},
            "size": "md",
        },
        {
            "id": "w_switches",
            "type": "toggle_group",
            "title": "Switches",
            "config": {"entities": ["switch.desk", "switch.workstation", "switch.transmission_switch"]},
            "size": "md",
        },
        {
            "id": "w_sensors",
            "type": "sensor_grid",
            "title": "Environment",
            "config": {
                "entities": [
                    "sensor.sensor_temperature",
                    "sensor.sensor_humidity",
                    "sensor.xiaomi_smart_air_purifier_4_temperature",
                    "sensor.xiaomi_smart_air_purifier_4_humidity",
                    "sensor.xiaomi_smart_air_purifier_4_pm2_5",
                    "sensor.desk_current_consumption",
                    "sensor.workstation_current_consumption",
                ]
            },
            "size": "full",
        },
        {
            "id": "w_camera",
            "type": "camera",
            "title": "Printo Camera",
            "config": {"entity_id": "camera.a1_03919d550407275_camera"},
            "size": "md",
        },
        {
            "id": "w_scenes",
            "type": "scene_buttons",
            "title": "Scenes",
            "config": {
                "scenes": [
                    {"entity_id": "scene.movie_time", "label": "Movie Time"},
                    {"entity_id": "scene.movie_time_paused", "label": "Movie Paused"},
                    {"entity_id": "scene.relax", "label": "Relax"},
                ]
            },
            "size": "sm",
        },
        {
            "id": "w_quick",
            "type": "quick_actions",
            "title": "Quick Actions",
            "config": {
                "actions": [
                    {"label": "Purifier Auto", "entity_id": "climate.xiaomi_smart_air_purifier_4", "domain": "climate", "service": "turn_on"},
                    {"label": "Purifier Off", "entity_id": "climate.xiaomi_smart_air_purifier_4", "domain": "climate", "service": "turn_off"},
                ]
            },
            "size": "sm",
        },
    ]
}


class DashboardConfig:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self):
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS dashboard_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                config_json TEXT NOT NULL,
                ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self._db.commit()
        log.info("Dashboard config initialized")

    async def close(self):
        if self._db:
            await self._db.close()

    async def get(self) -> dict:
        cursor = await self._db.execute(
            "SELECT config_json FROM dashboard_config WHERE id = 1"
        )
        row = await cursor.fetchone()
        if row:
            return json.loads(row[0])
        return DEFAULT_CONFIG

    async def save(self, config: dict):
        config_json = json.dumps(config)
        await self._db.execute(
            "INSERT OR REPLACE INTO dashboard_config (id, config_json, ts) VALUES (1, ?, CURRENT_TIMESTAMP)",
            (config_json,),
        )
        await self._db.commit()
