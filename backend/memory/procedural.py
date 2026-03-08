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
    ) -> dict:
        trigger = trigger or {"type": "manual"}
        actions = actions or []
        await self._db.execute(
            """INSERT OR REPLACE INTO skills
               (id, name, description, trigger_json, mode, ai_prompt, actions_json, notify, active, ts)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)""",
            (skill_id, name, description, json.dumps(trigger), mode, ai_prompt, json.dumps(actions), int(notify)),
        )
        await self._db.commit()
        log.info("Skill created: %s", skill_id)
        return await self.get_skill(skill_id)

    async def get_skill(self, skill_id: str) -> dict | None:
        cursor = await self._db.execute(
            "SELECT id, name, description, trigger_json, mode, ai_prompt, actions_json, notify, active FROM skills WHERE id = ?",
            (skill_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_skill(row)

    async def list_skills(self) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT id, name, description, trigger_json, mode, ai_prompt, actions_json, notify, active FROM skills ORDER BY ts"
        )
        rows = await cursor.fetchall()
        return [self._row_to_skill(r) for r in rows]

    async def get_triggered_skills(self) -> list[dict]:
        cursor = await self._db.execute(
            """SELECT id, name, description, trigger_json, mode, ai_prompt, actions_json, notify, active
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
        }
