"""APScheduler cron jobs for automated library scans and transcoding."""

import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

import db
from scanner import scan_library
from transcoder import run_library_jobs

log = logging.getLogger("transcoder.scheduler")

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone="UTC")
    return _scheduler


async def _auto_scan_and_transcode(library_id: int):
    """Callback for scheduled scans: scan then auto-transcode if configured."""
    try:
        lib = await db.get_library(library_id)
        if not lib or not lib["enabled"]:
            return
        log.info("Scheduled scan for library '%s'", lib["name"])
        await scan_library(library_id)
        if lib["transcode_mode"] == "auto":
            await run_library_jobs(library_id)
    except Exception:
        log.exception("Scheduled scan failed for library %d", library_id)


async def _prune_old_jobs():
    log.info("Pruning old jobs (>90 days)")
    await db.prune_old_jobs(90)


async def sync_schedules():
    """Rebuild cron jobs from current library configs."""
    sched = get_scheduler()

    for job in sched.get_jobs():
        if job.id.startswith("lib_scan_"):
            sched.remove_job(job.id)

    libraries = await db.list_libraries()
    for lib in libraries:
        if lib["scan_mode"] == "auto" and lib["scan_cron"] and lib["enabled"]:
            try:
                trigger = CronTrigger.from_crontab(lib["scan_cron"])
                sched.add_job(
                    _auto_scan_and_transcode,
                    trigger=trigger,
                    args=[lib["id"]],
                    id=f"lib_scan_{lib['id']}",
                    replace_existing=True,
                )
                log.info("Scheduled scan for '%s': %s", lib["name"], lib["scan_cron"])
            except Exception:
                log.exception("Invalid cron for library '%s': %s", lib["name"], lib["scan_cron"])


def start():
    sched = get_scheduler()
    sched.add_job(_prune_old_jobs, "cron", hour=3, minute=0, id="prune_jobs", replace_existing=True)
    if not sched.running:
        sched.start()
    log.info("Scheduler started")


def stop():
    sched = get_scheduler()
    if sched.running:
        sched.shutdown(wait=False)
    log.info("Scheduler stopped")
