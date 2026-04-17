"""
Procedural memory: skills store.
Each skill is a named, reusable procedure with optional triggers,
stored as JSON in SQLite.
"""

import json
import logging
import aiosqlite

log = logging.getLogger("homebot.memory.procedural")


class ProceduralMemory:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self):
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS skills (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                trigger_json TEXT NOT NULL DEFAULT '{"type": "manual"}',
                mode TEXT NOT NULL DEFAULT 'static',
                ai_prompt TEXT NOT NULL DEFAULT '',
                actions_json TEXT NOT NULL DEFAULT '[]',
                notify INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1,
                ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS event_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_id TEXT,
                old_state TEXT,
                new_state TEXT,
                event_type TEXT NOT NULL,
                details TEXT,
                ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_event_log_ts ON event_log(ts)"
        )
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS device_aliases (
                mac TEXT PRIMARY KEY,
                alias TEXT NOT NULL,
                device_type TEXT DEFAULT '',
                icon TEXT DEFAULT '',
                is_presence INTEGER DEFAULT 0
            )
        """)
        for migration in [
            "ALTER TABLE device_aliases ADD COLUMN is_presence INTEGER DEFAULT 0",
            "ALTER TABLE skills ADD COLUMN model TEXT DEFAULT NULL",
        ]:
            try:
                await self._db.execute(migration)
                await self._db.commit()
            except Exception:
                pass
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS notification_rules (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                rule_type TEXT NOT NULL,
                config_json TEXT NOT NULL DEFAULT '{}',
                cooldown_seconds INTEGER NOT NULL DEFAULT 300
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS scenes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                icon TEXT NOT NULL DEFAULT 'scene',
                entities_json TEXT NOT NULL,
                ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS floorplan_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                config_json TEXT NOT NULL,
                ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self._db.commit()
        log.info("Procedural memory initialized")

    async def close(self):
        if self._db:
            await self._db.close()

    async def create_skill(
        self,
        skill_id: str,
        name: str,
        description: str,
        trigger: dict | None = None,
        mode: str = "static",
        ai_prompt: str = "",
        actions: list[dict] | None = None,
        notify: bool = False,
        model: str | None = None,
    ) -> dict:
        trigger = trigger or {"type": "manual"}
        actions = actions or []
        await self._db.execute(
            """INSERT OR REPLACE INTO skills
               (id, name, description, trigger_json, mode, ai_prompt, actions_json, notify, active, model, ts)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, CURRENT_TIMESTAMP)""",
            (skill_id, name, description, json.dumps(trigger), mode, ai_prompt, json.dumps(actions), int(notify), model),
        )
        await self._db.commit()
        log.info("Skill created: %s", skill_id)
        return await self.get_skill(skill_id)

    async def get_skill(self, skill_id: str) -> dict | None:
        cursor = await self._db.execute(
            "SELECT id, name, description, trigger_json, mode, ai_prompt, actions_json, notify, active, model FROM skills WHERE id = ?",
            (skill_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_skill(row)

    async def list_skills(self) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT id, name, description, trigger_json, mode, ai_prompt, actions_json, notify, active, model FROM skills ORDER BY ts"
        )
        rows = await cursor.fetchall()
        return [self._row_to_skill(r) for r in rows]

    async def get_triggered_skills(self) -> list[dict]:
        cursor = await self._db.execute(
            """SELECT id, name, description, trigger_json, mode, ai_prompt, actions_json, notify, active, model
               FROM skills WHERE active = 1 AND trigger_json != '{"type": "manual"}'"""
        )
        rows = await cursor.fetchall()
        return [self._row_to_skill(r) for r in rows]

    async def update_skill(self, skill_id: str, updates: dict) -> dict | None:
        skill = await self.get_skill(skill_id)
        if not skill:
            return None
        if "name" in updates:
            await self._db.execute("UPDATE skills SET name = ? WHERE id = ?", (updates["name"], skill_id))
        if "description" in updates:
            await self._db.execute("UPDATE skills SET description = ? WHERE id = ?", (updates["description"], skill_id))
        if "trigger" in updates:
            await self._db.execute("UPDATE skills SET trigger_json = ? WHERE id = ?", (json.dumps(updates["trigger"]), skill_id))
        if "mode" in updates:
            await self._db.execute("UPDATE skills SET mode = ? WHERE id = ?", (updates["mode"], skill_id))
        if "ai_prompt" in updates:
            await self._db.execute("UPDATE skills SET ai_prompt = ? WHERE id = ?", (updates["ai_prompt"], skill_id))
        if "actions" in updates:
            await self._db.execute("UPDATE skills SET actions_json = ? WHERE id = ?", (json.dumps(updates["actions"]), skill_id))
        if "notify" in updates:
            await self._db.execute("UPDATE skills SET notify = ? WHERE id = ?", (int(updates["notify"]), skill_id))
        if "model" in updates:
            await self._db.execute("UPDATE skills SET model = ? WHERE id = ?", (updates["model"], skill_id))
        await self._db.commit()
        return await self.get_skill(skill_id)

    async def delete_skill(self, skill_id: str) -> bool:
        cursor = await self._db.execute("DELETE FROM skills WHERE id = ?", (skill_id,))
        await self._db.commit()
        return cursor.rowcount > 0

    async def toggle_skill(self, skill_id: str, active: bool) -> dict | None:
        await self._db.execute("UPDATE skills SET active = ? WHERE id = ?", (int(active), skill_id))
        await self._db.commit()
        return await self.get_skill(skill_id)

    async def log_event(self, entity_id: str, old_state: str, new_state: str, event_type: str, details: str = ""):
        await self._db.execute(
            "INSERT INTO event_log (entity_id, old_state, new_state, event_type, details) VALUES (?, ?, ?, ?, ?)",
            (entity_id, old_state, new_state, event_type, details),
        )
        await self._db.commit()

    async def get_event_log(self, hours: int = 24, limit: int = 100) -> list[dict]:
        cursor = await self._db.execute(
            """SELECT entity_id, old_state, new_state, event_type, details, ts
               FROM event_log
               WHERE ts >= datetime('now', ? || ' hours')
               ORDER BY ts DESC LIMIT ?""",
            (f"-{hours}", limit),
        )
        rows = await cursor.fetchall()
        return [
            {"entity_id": r[0], "old_state": r[1], "new_state": r[2],
             "event_type": r[3], "details": r[4], "ts": r[5]}
            for r in reversed(rows)
        ]

    async def prune_event_log(self, keep_hours: int = 72):
        await self._db.execute(
            "DELETE FROM event_log WHERE ts < datetime('now', ? || ' hours')",
            (f"-{keep_hours}",),
        )
        await self._db.commit()

    async def get_energy_history(self, hours: int = 24) -> list[dict]:
        """Return power/energy sensor state changes for the given time window."""
        if not self._db:
            return []
        cursor = await self._db.execute(
            """
            SELECT entity_id, old_state, new_state, ts
            FROM event_log
            WHERE event_type = 'state_change'
              AND ts >= datetime('now', ?)
              AND entity_id LIKE 'sensor.%'
            ORDER BY ts ASC
            """,
            (f"-{hours} hours",),
        )
        rows = await cursor.fetchall()
        results = []
        for entity_id, old_state, new_state, ts in rows:
            try:
                val = float(new_state)
            except (ValueError, TypeError):
                continue
            results.append({
                "entity_id": entity_id,
                "value": round(val, 2),
                "ts": ts,
            })
        return results

    async def get_analytics(self, metric: str, hours: int = 168) -> dict:
        """Return aggregated analytics data for the given metric and time window."""
        if not self._db:
            return {"metric": metric, "data": [], "hours": hours}

        if metric == "energy":
            cursor = await self._db.execute("""
                SELECT date(ts) as day,
                       entity_id,
                       AVG(CAST(new_state AS REAL)) as avg_value,
                       MAX(CAST(new_state AS REAL)) as max_value,
                       COUNT(*) as samples
                FROM event_log
                WHERE event_type = 'state_change'
                  AND ts >= datetime('now', ?)
                  AND entity_id LIKE 'sensor.%'
                  AND CAST(new_state AS REAL) IS NOT NULL
                  AND new_state NOT IN ('unavailable', 'unknown', '')
                GROUP BY day, entity_id
                ORDER BY day ASC
            """, (f"-{hours} hours",))
            rows = await cursor.fetchall()
            data = [{"day": r[0], "entity_id": r[1], "avg": round(r[2], 2),
                     "max": round(r[3], 2), "samples": r[4]} for r in rows]

        elif metric == "presence":
            cursor = await self._db.execute("""
                SELECT date(ts) as day,
                       entity_id,
                       new_state,
                       COUNT(*) as transitions
                FROM event_log
                WHERE event_type = 'state_change'
                  AND ts >= datetime('now', ?)
                  AND (entity_id LIKE 'person.%' OR entity_id LIKE 'device_tracker.%')
                GROUP BY day, entity_id, new_state
                ORDER BY day ASC
            """, (f"-{hours} hours",))
            rows = await cursor.fetchall()
            data = [{"day": r[0], "entity_id": r[1], "state": r[2],
                     "transitions": r[3]} for r in rows]

        elif metric == "network":
            cursor = await self._db.execute("""
                SELECT date(ts) as day,
                       entity_id,
                       AVG(CAST(new_state AS REAL)) as avg_value,
                       MAX(CAST(new_state AS REAL)) as max_value,
                       COUNT(*) as samples
                FROM event_log
                WHERE event_type = 'state_change'
                  AND ts >= datetime('now', ?)
                  AND entity_id LIKE 'sensor.%'
                  AND entity_id IN ('sensor.total_down', 'sensor.total_up',
                                    'sensor.bedroom_down', 'sensor.bedroom_up',
                                    'sensor.hallway_down', 'sensor.hallway_up')
                GROUP BY day, entity_id
                ORDER BY day ASC
            """, (f"-{hours} hours",))
            rows = await cursor.fetchall()
            data = [{"day": r[0], "entity_id": r[1], "avg": round(r[2], 2),
                     "max": round(r[3], 2), "samples": r[4]} for r in rows]

        elif metric == "activity":
            cursor = await self._db.execute("""
                SELECT date(ts) as day,
                       substr(entity_id, 1, instr(entity_id, '.') - 1) as domain,
                       COUNT(*) as events
                FROM event_log
                WHERE event_type = 'state_change'
                  AND ts >= datetime('now', ?)
                GROUP BY day, domain
                ORDER BY day ASC
            """, (f"-{hours} hours",))
            rows = await cursor.fetchall()
            data = [{"day": r[0], "domain": r[1], "events": r[2]} for r in rows]

        else:
            data = []

        return {"metric": metric, "data": data, "hours": hours}

    async def get_device_aliases(self) -> dict[str, dict]:
        cursor = await self._db.execute(
            "SELECT mac, alias, device_type, icon, is_presence FROM device_aliases"
        )
        rows = await cursor.fetchall()
        return {
            r[0]: {"alias": r[1], "device_type": r[2], "icon": r[3], "is_presence": bool(r[4])}
            for r in rows
        }

    async def get_presence_devices(self) -> list[dict]:
        """Return aliases flagged as presence-tracking devices."""
        cursor = await self._db.execute(
            "SELECT mac, alias, device_type FROM device_aliases WHERE is_presence = 1"
        )
        rows = await cursor.fetchall()
        return [{"mac": r[0], "alias": r[1], "device_type": r[2]} for r in rows]

    async def set_device_alias(
        self, mac: str, alias: str, device_type: str = "", icon: str = "", is_presence: bool = False,
    ) -> dict:
        await self._db.execute(
            "INSERT OR REPLACE INTO device_aliases (mac, alias, device_type, icon, is_presence) "
            "VALUES (?, ?, ?, ?, ?)",
            (mac, alias, device_type, icon, int(is_presence)),
        )
        await self._db.commit()
        return {"mac": mac, "alias": alias, "device_type": device_type, "icon": icon, "is_presence": is_presence}

    async def delete_device_alias(self, mac: str) -> bool:
        cursor = await self._db.execute("DELETE FROM device_aliases WHERE mac = ?", (mac,))
        await self._db.commit()
        return cursor.rowcount > 0

    async def get_notification_rules(self) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT id, name, enabled, rule_type, config_json, cooldown_seconds FROM notification_rules"
        )
        rows = await cursor.fetchall()
        return [
            {"id": r[0], "name": r[1], "enabled": bool(r[2]), "rule_type": r[3],
             "config": json.loads(r[4]), "cooldown_seconds": r[5]}
            for r in rows
        ]

    async def update_notification_rule(self, rule_id: str, updates: dict) -> dict | None:
        if "enabled" in updates:
            await self._db.execute(
                "UPDATE notification_rules SET enabled = ? WHERE id = ?",
                (int(updates["enabled"]), rule_id),
            )
        if "config" in updates:
            await self._db.execute(
                "UPDATE notification_rules SET config_json = ? WHERE id = ?",
                (json.dumps(updates["config"]), rule_id),
            )
        if "cooldown_seconds" in updates:
            await self._db.execute(
                "UPDATE notification_rules SET cooldown_seconds = ? WHERE id = ?",
                (updates["cooldown_seconds"], rule_id),
            )
        await self._db.commit()
        rules = await self.get_notification_rules()
        return next((r for r in rules if r["id"] == rule_id), None)

    _DEFAULT_NOTIFICATION_RULES: list[dict] = [
        {"id": "printer_done", "name": "3D Printer Finished", "rule_type": "printer_done",
         "config": {"cooldown": 600}, "cooldown_seconds": 600},
        {"id": "battery_low", "name": "Battery Low", "rule_type": "battery_low",
         "config": {"threshold": 15, "cooldown": 3600}, "cooldown_seconds": 3600},
        {"id": "welcome_home", "name": "Welcome Home", "rule_type": "welcome_home",
         "config": {"cooldown": 1800}, "cooldown_seconds": 1800},
        {"id": "left_home", "name": "Left Home", "rule_type": "left_home",
         "config": {"cooldown": 1800}, "cooldown_seconds": 1800},
        {"id": "deco_offline", "name": "Deco Node Offline", "rule_type": "deco_offline",
         "config": {"cooldown": 1800}, "cooldown_seconds": 1800},
        {"id": "device_disconnect", "name": "Device Disconnected", "rule_type": "device_disconnect",
         "config": {"important_keywords": ["mac mini", "pixel", "ipad", "printer", "server"], "cooldown": 1800},
         "cooldown_seconds": 1800},
    ]

    async def ensure_default_notification_rules(self):
        for rule in self._DEFAULT_NOTIFICATION_RULES:
            cursor = await self._db.execute(
                "SELECT id, cooldown_seconds FROM notification_rules WHERE id = ?", (rule["id"],)
            )
            row = await cursor.fetchone()
            if not row:
                await self._db.execute(
                    "INSERT INTO notification_rules (id, name, enabled, rule_type, config_json, cooldown_seconds) VALUES (?, ?, 1, ?, ?, ?)",
                    (rule["id"], rule["name"], rule["rule_type"], json.dumps(rule["config"]), rule["cooldown_seconds"]),
                )
            elif row[1] != rule["cooldown_seconds"]:
                await self._db.execute(
                    "UPDATE notification_rules SET cooldown_seconds = ?, config_json = ? WHERE id = ?",
                    (rule["cooldown_seconds"], json.dumps(rule["config"]), rule["id"]),
                )
                log.info("Updated notification rule cooldown: %s -> %ds", rule["id"], rule["cooldown_seconds"])
        await self._db.commit()

    _DEFAULT_SKILLS: list[dict] = [
        {
            "id": "daily_digest",
            "name": "Daily Digest",
            "description": "Daily summary of home activity, energy, air quality, network, and notable events (10 PM)",
            "trigger": {"type": "schedule", "cron": "0 22 * * *"},
            "mode": "ai",
            "model": "ollama:sorc/qwen3.5-claude-4.6-opus-q4:9b",
            "ai_prompt": (
                "Generate a concise daily digest for Kanak. Include:\n"
                "1. Energy/power highlights (current draw, total kWh today)\n"
                "2. Air quality summary (flag only if unhealthy)\n"
                "3. Notable events only (printer jobs, unusual activity)\n"
                "4. Current state of the home (who's home, what's on)\n"
                "Skip sections with nothing to report. Aim for 4-6 lines max. "
                "If it was a quiet day, say so in one sentence and just show current state."
            ),
            "notify": True,
        },
        {
            "id": "weekly_energy_report",
            "name": "Weekly Energy Report",
            "description": "Weekly energy trends, costs, and optimization suggestions (Sunday 8 PM)",
            "trigger": {"type": "schedule", "cron": "0 20 * * 0"},
            "mode": "ai",
            "model": "ollama:sorc/qwen3.5-claude-4.6-opus-q4:9b",
            "ai_prompt": (
                "Generate a weekly energy and usage report for Kanak. Include:\n"
                "1. Power consumption patterns from the event log (peak hours, baseline)\n"
                "2. Which devices were most active this week (top power consumers)\n"
                "3. Estimated cost using the configured energy rate and currency\n"
                "4. Trends compared to typical usage (increasing/decreasing)\n"
                "5. Peak usage times and suggestions for shifting load\n"
                "6. Optimization suggestions if any stand out\n"
                "Keep it concise -- a short paragraph + key stats with cost figures."
            ),
            "notify": True,
        },
        {
            "id": "morning_briefing",
            "name": "Morning Briefing",
            "description": "Daily morning summary with weather, overnight events, and device status (7 AM)",
            "trigger": {"type": "schedule", "cron": "0 7 * * *"},
            "mode": "ai",
            "model": "ollama:sorc/qwen3.5-claude-4.6-opus-q4:9b",
            "ai_prompt": (
                "Generate a concise morning briefing for Kanak. Include:\n"
                "1. Current weather conditions\n"
                "2. Overnight events (only if something notable happened)\n"
                "3. Battery warnings (any devices below 20%)\n"
                "4. Air quality check (is it safe to open windows?)\n"
                "If nothing notable happened overnight, just give weather + air quality in 2-3 lines. "
                "Skip sections that have nothing to report."
            ),
            "notify": True,
        },
        {
            "id": "goodnight_routine",
            "name": "Goodnight Routine",
            "description": "Check home state before bed -- lights, doors, devices still on",
            "trigger": {"type": "manual"},
            "mode": "ai",
            "model": "ollama:sorc/qwen3.5-claude-4.6-opus-q4:9b",
            "ai_prompt": (
                "Kanak is going to bed. Check the home state and provide a goodnight summary:\n"
                "1. List any lights, switches, or fans still on (suggest turning them off)\n"
                "2. Check if any doors or windows are open (binary sensors)\n"
                "3. Check if any high-power devices are still drawing significant power\n"
                "4. Quick summary of today's activity (2-3 sentences)\n"
                "5. If anything needs attention, call it out clearly\n"
                "Be concise. If everything looks good, just say so."
            ),
            "notify": True,
        },
        {
            "id": "air_quality_alert",
            "name": "Air Quality Alert",
            "description": "Alert when air quality degrades -- AQI, PM2.5 levels, purifier suggestion",
            "trigger": {"type": "manual"},
            "mode": "ai",
            "model": "ollama:sorc/qwen3.5-claude-4.6-opus-q4:9b",
            "ai_prompt": (
                "Air quality may have changed. Check all air quality sensors and report:\n"
                "1. Current PM2.5, PM10, AQI, and VOC levels from all sensors\n"
                "2. Whether levels are healthy, moderate, or unhealthy\n"
                "3. Suggest turning on the air purifier if levels are concerning\n"
                "4. Recommend closing windows if outdoor AQI is high\n"
                "Keep the response short and actionable."
            ),
            "notify": True,
        },
        {
            "id": "media_weekly_digest",
            "name": "Media Weekly Digest",
            "description": "Weekly summary of new content in Jellyfin and upcoming shows from Sonarr (Friday 7 PM)",
            "trigger": {"type": "schedule", "cron": "0 19 * * 5"},
            "mode": "ai",
            "model": "ollama:sorc/qwen3.5-claude-4.6-opus-q4:9b",
            "ai_prompt": (
                "Generate a weekly media digest for Kanak. Include:\n"
                "1. Check Jellyfin for recently added movies and shows (use jellyfin_get_latest)\n"
                "2. Check Sonarr for upcoming episodes this week (use sonarr_get_queue)\n"
                "3. Summarize what's new and worth watching\n"
                "4. Note any active downloads in the queue\n"
                "Keep it fun and concise -- like a personal watchlist update."
            ),
            "notify": True,
        },
        {
            "id": "network_health_check",
            "name": "Network Health Check",
            "description": "Weekly check of Deco mesh nodes, connectivity, and bandwidth (Sunday noon)",
            "trigger": {"type": "schedule", "cron": "0 12 * * 0"},
            "mode": "ai",
            "model": "ollama:sorc/qwen3.5-claude-4.6-opus-q4:9b",
            "ai_prompt": (
                "Run a weekly network health check. "
                "Check Deco mesh node status and flag any important offline devices. "
                "If everything is healthy, reply with a single sentence confirming that. "
                "Only provide detail if there are actual issues."
            ),
            "notify": True,
        },
        {
            "id": "arrival_lights",
            "name": "Arrival Lights",
            "description": "Turn on hallway lights when a household member arrives home via Deco network detection",
            "trigger": {"type": "state_change", "entity_id": "device_tracker.pixel9pro", "to": "home", "from": "not_home"},
            "mode": "ai",
            "model": "ollama:sorc/qwen3.5-claude-4.6-opus-q4:9b",
            "ai_prompt": (
                "A household member just arrived home (their phone connected to the Deco mesh). "
                "Check the current time -- if it's after 6 PM or before 6 AM (dark hours), "
                "turn on the hallway lights using ha_call_service. "
                "If it's daytime, just acknowledge the arrival without turning on lights. "
                "Keep the response to one sentence."
            ),
            "notify": True,
        },
        {
            "id": "last_person_left",
            "name": "Last Person Left",
            "description": "Check and report devices left on when the last tracked person leaves home",
            "trigger": {"type": "state_change", "entity_id": "device_tracker.pixel9pro", "to": "not_home", "from": "home"},
            "mode": "ai",
            "model": "ollama:sorc/qwen3.5-claude-4.6-opus-q4:9b",
            "ai_prompt": (
                "The last household member just left home (phone disconnected from Deco mesh). "
                "Check for any lights, switches, or fans that are still on. "
                "List what's still running and their power draw if available. "
                "Suggest turning them off but do NOT turn them off automatically. "
                "If everything is already off, just confirm the home is secured. "
                "Keep it concise -- 3-5 bullet points max."
            ),
            "notify": True,
        },
        {
            "id": "goodnight_auto",
            "name": "Goodnight Auto Check",
            "description": "Automatic bedtime check when phone stops network activity late at night",
            "trigger": {"type": "manual"},
            "mode": "ai",
            "model": "ollama:sorc/qwen3.5-claude-4.6-opus-q4:9b",
            "ai_prompt": (
                "It's late and the household seems to be settling down for the night. "
                "Run a quick bedtime check:\n"
                "1. List any lights still on\n"
                "2. Check if any doors/windows are open\n"
                "3. Check air quality for the bedroom (PM2.5, humidity)\n"
                "4. Note the current temperature\n"
                "5. Suggest turning off anything that should be off\n"
                "Be brief. If everything looks good, say so in one line."
            ),
            "notify": True,
        },
    ]

    async def ensure_default_skills(self):
        """Create built-in skills if they don't exist, update prompts if they do."""
        for skill_def in self._DEFAULT_SKILLS:
            existing = await self.get_skill(skill_def["id"])
            if not existing:
                await self.create_skill(
                    skill_id=skill_def["id"],
                    name=skill_def["name"],
                    description=skill_def["description"],
                    trigger=skill_def["trigger"],
                    mode=skill_def["mode"],
                    ai_prompt=skill_def["ai_prompt"],
                    notify=skill_def["notify"],
                    model=skill_def.get("model"),
                )
                log.info("Created default skill: %s", skill_def["name"])
            else:
                updates = {}
                if existing["ai_prompt"] != skill_def["ai_prompt"]:
                    updates["ai_prompt"] = skill_def["ai_prompt"]
                if existing["description"] != skill_def["description"]:
                    updates["description"] = skill_def["description"]
                if existing["trigger"] != skill_def["trigger"]:
                    updates["trigger"] = skill_def["trigger"]
                if skill_def.get("model") and existing.get("model") != skill_def["model"]:
                    updates["model"] = skill_def["model"]
                if updates:
                    await self.update_skill(skill_def["id"], updates)
                    log.info("Updated default skill: %s", skill_def["name"])

    # ---- Scenes ----

    async def create_scene(self, scene_id: str, name: str, entities: list[dict], icon: str = "scene") -> dict:
        await self._db.execute(
            "INSERT OR REPLACE INTO scenes (id, name, icon, entities_json, ts) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (scene_id, name, icon, json.dumps(entities)),
        )
        await self._db.commit()
        log.info("Scene created: %s", scene_id)
        return await self.get_scene(scene_id)

    async def get_scene(self, scene_id: str) -> dict | None:
        cursor = await self._db.execute(
            "SELECT id, name, icon, entities_json, ts FROM scenes WHERE id = ?", (scene_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return {"id": row[0], "name": row[1], "icon": row[2], "entities": json.loads(row[3]), "ts": row[4]}

    async def get_scenes(self) -> list[dict]:
        cursor = await self._db.execute("SELECT id, name, icon, entities_json, ts FROM scenes ORDER BY ts")
        rows = await cursor.fetchall()
        return [{"id": r[0], "name": r[1], "icon": r[2], "entities": json.loads(r[3]), "ts": r[4]} for r in rows]

    async def delete_scene(self, scene_id: str) -> bool:
        cursor = await self._db.execute("DELETE FROM scenes WHERE id = ?", (scene_id,))
        await self._db.commit()
        return cursor.rowcount > 0

    # ---- Floorplan config ----

    async def get_floorplan_config(self) -> dict | None:
        cursor = await self._db.execute("SELECT config_json FROM floorplan_config WHERE id = 1")
        row = await cursor.fetchone()
        return json.loads(row[0]) if row else None

    async def save_floorplan_config(self, cfg: dict):
        await self._db.execute(
            "INSERT OR REPLACE INTO floorplan_config (id, config_json, ts) VALUES (1, ?, CURRENT_TIMESTAMP)",
            (json.dumps(cfg),),
        )
        await self._db.commit()

    @staticmethod
    def _row_to_skill(row) -> dict:
        return {
            "id": row[0],
            "name": row[1],
            "description": row[2],
            "trigger": json.loads(row[3]),
            "mode": row[4],
            "ai_prompt": row[5],
            "actions": json.loads(row[6]),
            "notify": bool(row[7]),
            "active": bool(row[8]),
            "model": row[9] if len(row) > 9 else None,
        }
