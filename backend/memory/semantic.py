"""
Semantic memory: persistent knowledge about the home and user preferences.
Key-value store in SQLite. The agent uses remember()/recall() tools to
read and write facts. Also auto-populated from HA state cache on boot.
"""

import logging
import aiosqlite

log = logging.getLogger("homebot.memory.semantic")


class SemanticMemory:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self):
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS semantic (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self._db.commit()
        log.info("Semantic memory initialized")

    async def close(self):
        if self._db:
            await self._db.close()

    async def remember(self, key: str, value: str):
        await self._db.execute(
            "INSERT OR REPLACE INTO semantic (key, value, ts) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (key, value),
        )
        await self._db.commit()

    async def recall(self, query: str) -> dict[str, str]:
        """Search for facts matching the query (substring match on key or value)."""
        cursor = await self._db.execute(
            "SELECT key, value FROM semantic WHERE key LIKE ? OR value LIKE ? LIMIT 20",
            (f"%{query}%", f"%{query}%"),
        )
        rows = await cursor.fetchall()
        return {r[0]: r[1] for r in rows}

    async def get(self, key: str) -> str | None:
        cursor = await self._db.execute(
            "SELECT value FROM semantic WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def all_facts(self) -> dict[str, str]:
        cursor = await self._db.execute("SELECT key, value FROM semantic ORDER BY ts DESC LIMIT 50")
        rows = await cursor.fetchall()
        return {r[0]: r[1] for r in rows}

    async def delete(self, key: str):
        await self._db.execute("DELETE FROM semantic WHERE key = ?", (key,))
        await self._db.commit()
