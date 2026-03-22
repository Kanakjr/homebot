"""SQLite database layer for the transcoder service."""

import json
import logging
from datetime import datetime
from pathlib import Path

import aiosqlite

import config

log = logging.getLogger("transcoder.db")

_db: aiosqlite.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS libraries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    path        TEXT NOT NULL UNIQUE,
    file_extensions TEXT NOT NULL DEFAULT '.mkv,.mp4,.avi,.mov,.m4v,.webm',
    scan_mode   TEXT NOT NULL DEFAULT 'manual',
    transcode_mode TEXT NOT NULL DEFAULT 'manual',
    scan_cron   TEXT,
    enabled     INTEGER NOT NULL DEFAULT 1,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS presets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    encoder         TEXT NOT NULL DEFAULT 'vt_h265',
    container       TEXT NOT NULL DEFAULT 'av_mp4',
    encoder_preset  TEXT,
    audio_encoder   TEXT NOT NULL DEFAULT 'av_aac',
    audio_bitrate   INTEGER NOT NULL DEFAULT 128,
    audio_mixdown   TEXT NOT NULL DEFAULT 'stereo',
    quality_rules   TEXT NOT NULL DEFAULT '{}',
    skip_codecs     TEXT NOT NULL DEFAULT '["hevc","h265"]',
    is_default      INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS jobs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    library_id          INTEGER REFERENCES libraries(id),
    preset_id           INTEGER REFERENCES presets(id),
    file_path           TEXT NOT NULL,
    status              TEXT NOT NULL DEFAULT 'pending',
    original_codec      TEXT,
    resolution          INTEGER,
    original_size_bytes INTEGER,
    new_size_bytes      INTEGER,
    started_at          TEXT,
    completed_at        TEXT,
    error_message       TEXT,
    handbrake_command   TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scans (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    library_id      INTEGER REFERENCES libraries(id),
    files_found     INTEGER NOT NULL DEFAULT 0,
    files_pending   INTEGER NOT NULL DEFAULT 0,
    files_skipped   INTEGER NOT NULL DEFAULT 0,
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_library ON jobs(library_id);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at);
"""

DEFAULT_PRESETS = [
    {
        "name": "HW Fast",
        "encoder": "vt_h265",
        "container": "av_mp4",
        "encoder_preset": "speed",
        "audio_encoder": "av_aac",
        "audio_bitrate": 128,
        "audio_mixdown": "stereo",
        "quality_rules": json.dumps({"2160": 58, "1080": 48, "720": 40, "480": 35}),
        "skip_codecs": json.dumps(["hevc", "h265"]),
        "is_default": 1,
    },
    {
        "name": "HW Balanced",
        "encoder": "vt_h265",
        "container": "av_mp4",
        "encoder_preset": None,
        "audio_encoder": "av_aac",
        "audio_bitrate": 128,
        "audio_mixdown": "stereo",
        "quality_rules": json.dumps({"2160": 65, "1080": 55, "720": 45, "480": 40}),
        "skip_codecs": json.dumps(["hevc", "h265"]),
        "is_default": 1,
    },
    {
        "name": "HW Max Compression",
        "encoder": "vt_h265",
        "container": "av_mp4",
        "encoder_preset": "quality",
        "audio_encoder": "av_aac",
        "audio_bitrate": 128,
        "audio_mixdown": "stereo",
        "quality_rules": json.dumps({"2160": 50, "1080": 42, "720": 35, "480": 30}),
        "skip_codecs": json.dumps(["hevc", "h265"]),
        "is_default": 1,
    },
]


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)
        _db = await aiosqlite.connect(config.DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA busy_timeout=5000")
        await _db.executescript(SCHEMA)
        await _seed_presets()
        await _db.commit()
    return _db


async def _seed_presets():
    db = _db
    for preset in DEFAULT_PRESETS:
        existing = await db.execute(
            "SELECT id FROM presets WHERE name = ?", (preset["name"],)
        )
        if await existing.fetchone() is None:
            await db.execute(
                """INSERT INTO presets
                   (name, encoder, container, encoder_preset, audio_encoder,
                    audio_bitrate, audio_mixdown, quality_rules, skip_codecs, is_default)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    preset["name"], preset["encoder"], preset["container"],
                    preset["encoder_preset"], preset["audio_encoder"],
                    preset["audio_bitrate"], preset["audio_mixdown"],
                    preset["quality_rules"], preset["skip_codecs"],
                    preset["is_default"],
                ),
            )
    log.info("Default presets seeded")


async def close():
    global _db
    if _db:
        await _db.close()
        _db = None


# -- Library helpers ----------------------------------------------------------

async def list_libraries():
    db = await get_db()
    cur = await db.execute("SELECT * FROM libraries ORDER BY name")
    return [dict(r) for r in await cur.fetchall()]


async def get_library(lib_id: int):
    db = await get_db()
    cur = await db.execute("SELECT * FROM libraries WHERE id = ?", (lib_id,))
    row = await cur.fetchone()
    return dict(row) if row else None


async def create_library(data: dict):
    db = await get_db()
    cur = await db.execute(
        """INSERT INTO libraries (name, path, file_extensions, scan_mode, transcode_mode, scan_cron)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (data["name"], data["path"], data.get("file_extensions", ".mkv,.mp4,.avi,.mov,.m4v,.webm"),
         data.get("scan_mode", "manual"), data.get("transcode_mode", "manual"),
         data.get("scan_cron")),
    )
    await db.commit()
    return await get_library(cur.lastrowid)


async def update_library(lib_id: int, data: dict):
    db = await get_db()
    fields = []
    values = []
    for key in ("name", "path", "file_extensions", "scan_mode", "transcode_mode", "scan_cron", "enabled"):
        if key in data:
            fields.append(f"{key} = ?")
            values.append(data[key])
    if not fields:
        return await get_library(lib_id)
    values.append(lib_id)
    await db.execute(f"UPDATE libraries SET {', '.join(fields)} WHERE id = ?", values)
    await db.commit()
    return await get_library(lib_id)


async def delete_library(lib_id: int):
    db = await get_db()
    await db.execute("DELETE FROM libraries WHERE id = ?", (lib_id,))
    await db.commit()


# -- Preset helpers -----------------------------------------------------------

async def list_presets():
    db = await get_db()
    cur = await db.execute("SELECT * FROM presets ORDER BY is_default DESC, name")
    rows = [dict(r) for r in await cur.fetchall()]
    for r in rows:
        r["quality_rules"] = json.loads(r["quality_rules"])
        r["skip_codecs"] = json.loads(r["skip_codecs"])
    return rows


async def get_preset(preset_id: int):
    db = await get_db()
    cur = await db.execute("SELECT * FROM presets WHERE id = ?", (preset_id,))
    row = await cur.fetchone()
    if row is None:
        return None
    d = dict(row)
    d["quality_rules"] = json.loads(d["quality_rules"])
    d["skip_codecs"] = json.loads(d["skip_codecs"])
    return d


async def create_preset(data: dict):
    db = await get_db()
    cur = await db.execute(
        """INSERT INTO presets
           (name, encoder, container, encoder_preset, audio_encoder,
            audio_bitrate, audio_mixdown, quality_rules, skip_codecs, is_default)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
        (
            data["name"], data.get("encoder", "vt_h265"),
            data.get("container", "av_mp4"), data.get("encoder_preset"),
            data.get("audio_encoder", "av_aac"), data.get("audio_bitrate", 128),
            data.get("audio_mixdown", "stereo"),
            json.dumps(data.get("quality_rules", {})),
            json.dumps(data.get("skip_codecs", ["hevc", "h265"])),
        ),
    )
    await db.commit()
    return await get_preset(cur.lastrowid)


async def update_preset(preset_id: int, data: dict):
    db = await get_db()
    cur = await db.execute("SELECT is_default FROM presets WHERE id = ?", (preset_id,))
    row = await cur.fetchone()
    if row and row["is_default"]:
        return None
    fields, values = [], []
    for key in ("name", "encoder", "container", "encoder_preset", "audio_encoder",
                "audio_bitrate", "audio_mixdown"):
        if key in data:
            fields.append(f"{key} = ?")
            values.append(data[key])
    if "quality_rules" in data:
        fields.append("quality_rules = ?")
        values.append(json.dumps(data["quality_rules"]))
    if "skip_codecs" in data:
        fields.append("skip_codecs = ?")
        values.append(json.dumps(data["skip_codecs"]))
    if not fields:
        return await get_preset(preset_id)
    values.append(preset_id)
    await db.execute(f"UPDATE presets SET {', '.join(fields)} WHERE id = ?", values)
    await db.commit()
    return await get_preset(preset_id)


async def delete_preset(preset_id: int):
    db = await get_db()
    await db.execute("DELETE FROM presets WHERE id = ? AND is_default = 0", (preset_id,))
    await db.commit()


# -- Job helpers --------------------------------------------------------------

async def list_jobs(status=None, library_id=None, limit=50, offset=0):
    db = await get_db()
    where, params = [], []
    if status:
        where.append("j.status = ?")
        params.append(status)
    if library_id:
        where.append("j.library_id = ?")
        params.append(library_id)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    params.extend([limit, offset])
    cur = await db.execute(
        f"""SELECT j.*, l.name as library_name, p.name as preset_name
            FROM jobs j
            LEFT JOIN libraries l ON j.library_id = l.id
            LEFT JOIN presets p ON j.preset_id = p.id
            {clause}
            ORDER BY j.created_at DESC LIMIT ? OFFSET ?""",
        params,
    )
    return [dict(r) for r in await cur.fetchall()]


async def get_job(job_id: int):
    db = await get_db()
    cur = await db.execute(
        """SELECT j.*, l.name as library_name, p.name as preset_name
           FROM jobs j
           LEFT JOIN libraries l ON j.library_id = l.id
           LEFT JOIN presets p ON j.preset_id = p.id
           WHERE j.id = ?""",
        (job_id,),
    )
    row = await cur.fetchone()
    return dict(row) if row else None


async def create_job(data: dict):
    db = await get_db()
    cur = await db.execute(
        """INSERT INTO jobs (library_id, preset_id, file_path, status,
                             original_codec, resolution, original_size_bytes)
           VALUES (?, ?, ?, 'pending', ?, ?, ?)""",
        (data["library_id"], data["preset_id"], data["file_path"],
         data.get("original_codec"), data.get("resolution"),
         data.get("original_size_bytes")),
    )
    await db.commit()
    return cur.lastrowid


async def update_job(job_id: int, data: dict):
    db = await get_db()
    fields, values = [], []
    for key in ("status", "new_size_bytes", "started_at", "completed_at",
                "error_message", "handbrake_command"):
        if key in data:
            fields.append(f"{key} = ?")
            values.append(data[key])
    if not fields:
        return
    values.append(job_id)
    await db.execute(f"UPDATE jobs SET {', '.join(fields)} WHERE id = ?", values)
    await db.commit()


async def count_jobs_by_status():
    db = await get_db()
    cur = await db.execute(
        "SELECT status, COUNT(*) as cnt FROM jobs GROUP BY status"
    )
    return {row["status"]: row["cnt"] for row in await cur.fetchall()}


# -- Scan helpers -------------------------------------------------------------

async def create_scan(library_id: int):
    db = await get_db()
    cur = await db.execute(
        "INSERT INTO scans (library_id) VALUES (?)", (library_id,)
    )
    await db.commit()
    return cur.lastrowid


async def update_scan(scan_id: int, data: dict):
    db = await get_db()
    fields, values = [], []
    for key in ("files_found", "files_pending", "files_skipped", "completed_at"):
        if key in data:
            fields.append(f"{key} = ?")
            values.append(data[key])
    if not fields:
        return
    values.append(scan_id)
    await db.execute(f"UPDATE scans SET {', '.join(fields)} WHERE id = ?", values)
    await db.commit()


async def list_scans(limit=20):
    db = await get_db()
    cur = await db.execute(
        """SELECT s.*, l.name as library_name FROM scans s
           LEFT JOIN libraries l ON s.library_id = l.id
           ORDER BY s.started_at DESC LIMIT ?""",
        (limit,),
    )
    return [dict(r) for r in await cur.fetchall()]


# -- Stats --------------------------------------------------------------------

async def get_stats():
    db = await get_db()
    counts = await count_jobs_by_status()
    cur = await db.execute(
        """SELECT COUNT(*) as total,
                  COALESCE(SUM(original_size_bytes), 0) as total_original,
                  COALESCE(SUM(new_size_bytes), 0) as total_new
           FROM jobs WHERE status = 'completed'"""
    )
    row = await cur.fetchone()
    total_original = row["total_original"]
    total_new = row["total_new"]
    saved = total_original - total_new
    avg_ratio = (saved / total_original * 100) if total_original > 0 else 0
    return {
        "files_processed": row["total"],
        "space_saved_bytes": saved,
        "avg_compression_pct": round(avg_ratio, 1),
        "job_counts": counts,
    }


async def prune_old_jobs(days: int = 90):
    db = await get_db()
    await db.execute(
        "DELETE FROM jobs WHERE status IN ('completed','failed','skipped') "
        "AND created_at < datetime('now', ?)",
        (f"-{days} days",),
    )
    await db.commit()
