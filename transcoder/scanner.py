"""Library scanner -- walks directories and probes video files with ffprobe."""

import json
import logging
import os
import subprocess
from datetime import datetime

import config
import db

log = logging.getLogger("transcoder.scanner")


def run_ffprobe(filepath: str, *args) -> dict | None:
    command = [
        config.FFPROBE_PATH, "-v", "quiet", "-print_format", "json",
        *args, filepath,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        pass
    return None


def get_video_info(filepath: str) -> tuple[str | None, int | None, float | None]:
    """Return (codec_name, height, duration_secs) for the first video stream."""
    data = run_ffprobe(filepath, "-show_streams", "-select_streams", "v:0")
    if not data or "streams" not in data or not data["streams"]:
        return None, None, None

    stream = data["streams"][0]
    codec = stream.get("codec_name", "").lower()
    height = int(stream.get("height", 0))

    duration = None
    dur_str = stream.get("duration")
    if dur_str:
        try:
            duration = float(dur_str)
        except ValueError:
            pass

    if duration is None:
        fmt_data = run_ffprobe(filepath, "-show_format")
        if fmt_data and "format" in fmt_data:
            try:
                duration = float(fmt_data["format"].get("duration", 0))
            except (ValueError, TypeError):
                pass

    return codec, height, duration


def find_videos(directory: str, extensions: set[str]) -> list[str]:
    """Recursively find all video files in a directory."""
    videos = []
    for root, _, files in os.walk(directory):
        for f in sorted(files):
            if f.endswith(config.TEMP_SUFFIX):
                continue
            ext = os.path.splitext(f)[1].lower()
            if ext in extensions:
                videos.append(os.path.join(root, f))
    return videos


async def scan_library(library_id: int) -> dict:
    """Scan a library, probe files, create pending jobs for un-processed files."""
    lib = await db.get_library(library_id)
    if not lib:
        raise ValueError(f"Library {library_id} not found")

    scan_id = await db.create_scan(library_id)
    extensions = {e.strip() for e in lib["file_extensions"].split(",") if e.strip()}

    if not os.path.isdir(lib["path"]):
        await db.update_scan(scan_id, {
            "files_found": 0, "files_pending": 0, "files_skipped": 0,
            "completed_at": datetime.utcnow().isoformat(),
        })
        log.warning("Library path does not exist: %s", lib["path"])
        return {"files_found": 0, "files_pending": 0, "files_skipped": 0}

    video_files = find_videos(lib["path"], extensions)
    files_found = len(video_files)
    files_pending = 0
    files_skipped = 0

    database = await db.get_db()
    existing = await database.execute(
        "SELECT file_path FROM jobs WHERE library_id = ? AND status IN ('pending','running','completed')",
        (library_id,),
    )
    existing_paths = {row["file_path"] for row in await existing.fetchall()}

    presets = await db.list_presets()
    default_preset = next((p for p in presets if p["name"] == "HW Balanced"), presets[0] if presets else None)
    if not default_preset:
        log.error("No presets available")
        return {"files_found": files_found, "files_pending": 0, "files_skipped": 0}

    for vf in video_files:
        if vf in existing_paths:
            continue

        codec, height, _ = get_video_info(vf)
        skip_codecs = default_preset.get("skip_codecs", [])
        if codec and codec in skip_codecs:
            files_skipped += 1
            await db.create_job({
                "library_id": library_id,
                "preset_id": default_preset["id"],
                "file_path": vf,
                "original_codec": codec,
                "resolution": height,
                "original_size_bytes": os.path.getsize(vf),
            })
            await db.update_job(
                (await db.get_db()).execute("SELECT last_insert_rowid()"),
                {"status": "skipped"},
            )
            continue

        files_pending += 1
        await db.create_job({
            "library_id": library_id,
            "preset_id": default_preset["id"],
            "file_path": vf,
            "original_codec": codec,
            "resolution": height,
            "original_size_bytes": os.path.getsize(vf),
        })

    await db.update_scan(scan_id, {
        "files_found": files_found,
        "files_pending": files_pending,
        "files_skipped": files_skipped,
        "completed_at": datetime.utcnow().isoformat(),
    })

    log.info("Scan complete for '%s': found=%d pending=%d skipped=%d",
             lib["name"], files_found, files_pending, files_skipped)
    return {"files_found": files_found, "files_pending": files_pending, "files_skipped": files_skipped}
