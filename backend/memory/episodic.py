"""
Episodic memory: conversation history per chat_id.
Stored in SQLite, auto-trimmed to keep only the most recent messages.
"""

import logging
import aiosqlite

log = logging.getLogger("homebot.memory.episodic")

MAX_HISTORY = 50


class EpisodicMemory:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def init(self):
        self._db = await aiosqlite.connect(self._db_path)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS episodic (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                text TEXT NOT NULL,
                ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await self._db.execute(
            "CREATE INDEX IF NOT EXISTS idx_episodic_chat ON episodic(chat_id, id)"
        )
        await self._db.commit()
        log.info("Episodic memory initialized")

    async def close(self):
        if self._db:
            await self._db.close()

    async def add(self, chat_id: int, role: str, text: str):
        await self._db.execute(
            "INSERT INTO episodic (chat_id, role, text) VALUES (?, ?, ?)",
            (chat_id, role, text),
        )
        await self._db.commit()
        await self._trim(chat_id)

    async def get_history(self, chat_id: int, limit: int = 20) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT role, text, ts FROM episodic WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (chat_id, limit),
        )
        rows = await cursor.fetchall()
        return [{"role": r[0], "text": r[1], "ts": r[2]} for r in reversed(rows)]

    async def list_threads(self) -> list[dict]:
        cursor = await self._db.execute("""
            SELECT chat_id,
                   COUNT(*) as message_count,
                   MAX(ts) as last_ts,
                   (SELECT text FROM episodic e2
                    WHERE e2.chat_id = e1.chat_id
                    ORDER BY e2.id DESC LIMIT 1) as last_message
            FROM episodic e1
            GROUP BY chat_id
            ORDER BY MAX(ts) DESC
        """)
        rows = await cursor.fetchall()
        return [
            {
                "chat_id": r[0],
                "message_count": r[1],
                "last_ts": r[2],
                "last_message": r[3],
            }
            for r in rows
        ]

    async def _trim(self, chat_id: int):
        cursor = await self._db.execute(
            "SELECT COUNT(*) FROM episodic WHERE chat_id = ?", (chat_id,)
        )
        (count,) = await cursor.fetchone()
        if count > MAX_HISTORY:
            await self._db.execute(
                """DELETE FROM episodic WHERE chat_id = ? AND id NOT IN
                   (SELECT id FROM episodic WHERE chat_id = ? ORDER BY id DESC LIMIT ?)""",
                (chat_id, chat_id, MAX_HISTORY),
            )
            await self._db.commit()

    async def clear(self, chat_id: int):
        await self._db.execute("DELETE FROM episodic WHERE chat_id = ?", (chat_id,))
        await self._db.commit()
