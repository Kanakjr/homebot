"""
Dashboard config persistence.
Stores a single JSON document describing the widget layout,
plus a cached AI-generated dashboard summary.
"""

import json
import logging
from datetime import datetime, timezone

import aiosqlite

log = logging.getLogger("homebot.dashboard_config")

SUMMARY_TTL_SECONDS = 1800  # 30 minutes

DEFAULT_CONFIG = {
    "widgets": [
        {
            "id": "w_weather",
            "type": "weather_card",
            "title": "Weather",
            "config": {"entity_id": "weather.home"},
            "size": "sm",
        },
        {
            "id": "w_room",
            "type": "room_environment",
            "title": "Room",
            "config": {
                "temperature_entity": "sensor.room_temperature",
                "humidity_entity": "sensor.room_humidity",
                "temp_thresholds": {"warn": 32, "critical": 38},
                "humidity_thresholds": {"warn": 60, "critical": 80},
            },
            "size": "sm",
        },
        {
            "id": "w_health",
            "type": "health",
            "title": "Health",
            "config": {
                "heart_rate_entity": "sensor.watch_heart_rate",
                "steps_entity": "sensor.watch_daily_steps",
                "activity_entity": "sensor.watch_activity_state",
                "battery_entity": "sensor.watch_battery_level",
                "daily_distance_entity": "sensor.watch_daily_distance",
                "daily_calories_entity": "sensor.watch_daily_calories",
                "pressure_entity": "sensor.watch_pressure",
                "on_body_entity": "binary_sensor.watch_on_body",
                "daily_floors_entity": "sensor.watch_daily_floors",
            },
            "size": "sm",
        },
        {
            "id": "w_light_ctrl",
            "type": "light_control",
            "title": "Lights",
            "config": {"entities": ["light.bedside", "light.table_lamp"]},
            "size": "sm",
        },
        {
            "id": "w_printer",
            "type": "printer",
            "title": "Printo - Bambu A1",
            "config": {
                "camera_entity": "camera.printer",
                "status_entity": "sensor.printer_status",
                "progress_entity": "sensor.printer_progress",
                "nozzle_temp_entity": "sensor.printer_nozzle_temp",
                "nozzle_target_entity": "sensor.printer_nozzle_target",
                "bed_temp_entity": "sensor.printer_bed_temp",
                "bed_target_entity": "sensor.printer_bed_target",
                "remaining_time_entity": "sensor.printer_remaining_time",
                "current_layer_entity": "sensor.printer_current_layer",
                "total_layers_entity": "sensor.printer_total_layers",
                "weight_entity": "sensor.printer_weight",
                "filament_entity": "sensor.printer_spool",
                "online_entity": "binary_sensor.printer_online",
            },
            "size": "md",
        },
        {
            "id": "w_air_purifier",
            "type": "air_purifier",
            "title": "Air Purifier",
            "config": {
                "fan_entity": "fan.air_purifier",
                "pm25_entity": "sensor.air_purifier_pm2_5",
                "temperature_entity": "sensor.air_purifier_temperature",
                "humidity_entity": "sensor.air_purifier_humidity",
                "filter_life_entity": "sensor.air_purifier_filter_life",
                "motor_speed_entity": "sensor.air_purifier_motor",
            },
            "size": "md",
        },
        {
            "id": "w_plug_desk",
            "type": "smart_plug",
            "title": "Desk",
            "config": {
                "switch_entity": "switch.monitor_plug",
                "power_entity": "sensor.monitor_plug_current_consumption",
                "today_entity": "sensor.monitor_plug_today_s_consumption",
                "month_entity": "sensor.monitor_plug_this_month_s_consumption",
                "voltage_entity": "sensor.monitor_plug_voltage",
                "current_entity": "sensor.monitor_plug_current",
                "overheated_entity": "binary_sensor.monitor_plug_overheated",
                "overloaded_entity": "binary_sensor.desk_overloaded",
            },
            "size": "sm",
        },
        {
            "id": "w_plug_workstation",
            "type": "smart_plug",
            "title": "Workstation",
            "config": {
                "switch_entity": "switch.workstation",
                "power_entity": "sensor.workstation_current_consumption",
                "today_entity": "sensor.workstation_today_s_consumption",
                "month_entity": "sensor.workstation_this_month_s_consumption",
                "voltage_entity": "sensor.workstation_voltage",
                "current_entity": "sensor.workstation_current",
                "overheated_entity": "binary_sensor.workstation_overheated",
                "overloaded_entity": "binary_sensor.workstation_overloaded",
            },
            "size": "sm",
        },
        {
            "id": "w_power_chart",
            "type": "power_chart",
            "title": "Power Usage",
            "config": {"hours": 6, "entity_filter": "power"},
            "size": "md",
        },
        {
            "id": "w_bandwidth_chart",
            "type": "bandwidth_chart",
            "title": "Network Bandwidth",
            "config": {"hours": 6},
            "size": "md",
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
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS dashboard_summary (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                summary_text TEXT NOT NULL,
                generated_at TEXT NOT NULL
            )
        """)
        try:
            await self._db.execute("ALTER TABLE dashboard_summary ADD COLUMN provider TEXT DEFAULT 'gemini'")
            await self._db.commit()
        except Exception:
            pass  # column already exists
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

    async def get_summary(self) -> dict | None:
        """Return cached summary if it exists and is fresh (< SUMMARY_TTL_SECONDS)."""
        cursor = await self._db.execute(
            "SELECT summary_text, generated_at, provider FROM dashboard_summary WHERE id = 1"
        )
        row = await cursor.fetchone()
        if not row:
            return None
        generated_at = datetime.fromisoformat(row[1])
        age = (datetime.now(timezone.utc) - generated_at).total_seconds()
        if age > SUMMARY_TTL_SECONDS:
            return None
        return {"summary": row[0], "generated_at": row[1], "provider": row[2] or "gemini"}

    async def save_summary(self, text: str, provider: str = "gemini"):
        now = datetime.now(timezone.utc).isoformat()
        await self._db.execute(
            "INSERT OR REPLACE INTO dashboard_summary (id, summary_text, generated_at, provider) VALUES (1, ?, ?, ?)",
            (text, now, provider),
        )
        await self._db.commit()
