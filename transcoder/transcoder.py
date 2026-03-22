"""HandBrakeCLI wrapper -- builds commands, runs transcodes, verifies output."""

import asyncio
import logging
import os
import re
import signal
import time
from datetime import datetime

import config
import db
from scanner import get_video_info

log = logging.getLogger("transcoder.transcoder")

_active_processes: dict[int, asyncio.subprocess.Process] = {}


def get_quality_for_height(quality_rules: dict, height: int | None) -> int:
    """Pick the quality value based on video height, matching compress_videos.py logic."""
    if not height or height <= 0:
        return quality_rules.get("1080", 55)
    for threshold in sorted((int(k) for k in quality_rules), reverse=True):
        if height >= threshold:
            return quality_rules[str(threshold)]
    smallest = min(quality_rules, key=lambda k: int(k))
    return quality_rules[smallest]


def build_handbrake_command(
    input_path: str, output_path: str, preset: dict, height: int | None
) -> list[str]:
    quality = get_quality_for_height(preset["quality_rules"], height)
    cmd = [
        config.HANDBRAKE_CLI,
        "-i", input_path,
        "-o", output_path,
        "-f", preset.get("container", "av_mp4"),
        "-e", preset.get("encoder", "vt_h265"),
        "-q", str(quality),
        "-E", preset.get("audio_encoder", "av_aac"),
        "-B", str(preset.get("audio_bitrate", 128)),
        "--mixdown", preset.get("audio_mixdown", "stereo"),
        "--all-audio",
    ]
    ep = preset.get("encoder_preset")
    if ep:
        cmd.extend(["--encoder-preset", ep])
    return cmd


def verify_output(
    input_path: str, output_path: str, input_duration: float | None
) -> tuple[bool, str]:
    if not os.path.exists(output_path):
        return False, "Output file does not exist"
    if os.path.getsize(output_path) == 0:
        return False, "Output file is 0 bytes"
    if input_duration is not None and input_duration > 0:
        _, _, output_duration = get_video_info(output_path)
        if output_duration is not None:
            diff = abs(input_duration - output_duration)
            if diff > config.DURATION_TOLERANCE_SECS:
                return False, (
                    f"Duration mismatch: input={input_duration:.1f}s, "
                    f"output={output_duration:.1f}s (diff={diff:.1f}s)"
                )
    return True, "OK"


async def transcode_file(job_id: int) -> bool:
    """Run a single transcode job. Returns True on success."""
    job = await db.get_job(job_id)
    if not job or job["status"] != "pending":
        return False

    preset = await db.get_preset(job["preset_id"])
    if not preset:
        await db.update_job(job_id, {"status": "failed", "error_message": "Preset not found"})
        return False

    input_path = job["file_path"]
    if not os.path.exists(input_path):
        await db.update_job(job_id, {"status": "failed", "error_message": "File not found"})
        return False

    file_dir, file_name = os.path.split(input_path)
    file_base = os.path.splitext(file_name)[0]
    temp_path = os.path.join(file_dir, f"{file_base}{config.TEMP_SUFFIX}")
    final_path = os.path.join(file_dir, f"{file_base}.mp4")

    codec, height, duration = get_video_info(input_path)
    skip_codecs = preset.get("skip_codecs", [])
    if codec and codec in skip_codecs:
        await db.update_job(job_id, {"status": "skipped"})
        return True

    cmd = build_handbrake_command(input_path, temp_path, preset, height)
    await db.update_job(job_id, {
        "status": "running",
        "started_at": datetime.utcnow().isoformat(),
        "handbrake_command": " ".join(cmd),
    })

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        _active_processes[job_id] = process

        progress_re = re.compile(
            r"Encoding: task \d+ of \d+, (\d+\.\d+) %"
        )
        async for line in process.stdout:
            text = line.decode("utf-8", errors="replace")
            match = progress_re.search(text)
            if match:
                log.debug("Job %d: %.1f%%", job_id, float(match.group(1)))

        return_code = await process.wait()
        _active_processes.pop(job_id, None)

        if return_code != 0:
            raise RuntimeError(f"HandBrakeCLI exited with code {return_code}")

        valid, reason = verify_output(input_path, temp_path, duration)
        if not valid:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            await db.update_job(job_id, {
                "status": "failed",
                "completed_at": datetime.utcnow().isoformat(),
                "error_message": f"Verification failed: {reason}",
            })
            return False

        original_size = os.path.getsize(input_path)
        os.remove(input_path)
        os.rename(temp_path, final_path)
        new_size = os.path.getsize(final_path)

        await db.update_job(job_id, {
            "status": "completed",
            "completed_at": datetime.utcnow().isoformat(),
            "new_size_bytes": new_size,
        })
        if job["file_path"] != final_path:
            database = await db.get_db()
            await database.execute(
                "UPDATE jobs SET file_path = ? WHERE id = ?", (final_path, job_id)
            )
            await database.commit()

        saved_gb = (original_size - new_size) / (1024 ** 3)
        log.info("Job %d completed: %s -> %.2f GB saved", job_id, file_name, saved_gb)
        return True

    except asyncio.CancelledError:
        _active_processes.pop(job_id, None)
        if os.path.exists(temp_path):
            os.remove(temp_path)
        await db.update_job(job_id, {
            "status": "cancelled",
            "completed_at": datetime.utcnow().isoformat(),
        })
        return False

    except Exception as e:
        _active_processes.pop(job_id, None)
        log.exception("Job %d failed: %s", job_id, e)
        if os.path.exists(temp_path):
            os.remove(temp_path)
        await db.update_job(job_id, {
            "status": "failed",
            "completed_at": datetime.utcnow().isoformat(),
            "error_message": str(e),
        })
        return False


async def cancel_job(job_id: int) -> bool:
    proc = _active_processes.get(job_id)
    if proc and proc.returncode is None:
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=10)
        except asyncio.TimeoutError:
            proc.kill()
        return True
    job = await db.get_job(job_id)
    if job and job["status"] == "pending":
        await db.update_job(job_id, {"status": "cancelled"})
        return True
    return False


async def run_library_jobs(library_id: int, preset_id: int | None = None):
    """Process all pending jobs for a library sequentially."""
    database = await db.get_db()
    query = "SELECT id FROM jobs WHERE library_id = ? AND status = 'pending' ORDER BY created_at"
    cur = await database.execute(query, (library_id,))
    pending = [row["id"] for row in await cur.fetchall()]

    if preset_id:
        for jid in pending:
            await database.execute("UPDATE jobs SET preset_id = ? WHERE id = ?", (preset_id, jid))
        await database.commit()

    log.info("Starting %d jobs for library %d", len(pending), library_id)
    for jid in pending:
        await transcode_file(jid)
