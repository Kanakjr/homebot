"""HomeBotAI Transcoder Service -- native video transcoding via HandBrakeCLI."""

import asyncio
import logging
import subprocess

import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import config
import db
import scheduler
from scanner import scan_library
from transcoder import transcode_file, cancel_job, run_library_jobs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-28s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("transcoder.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.get_db()
    scheduler.start()
    await scheduler.sync_schedules()
    log.info("Transcoder service started on port %d", config.PORT)
    yield
    scheduler.stop()
    await db.close()


app = FastAPI(title="HomeBotAI Transcoder", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)
    if config.API_KEY and request.url.path.startswith("/api/"):
        if request.url.path == "/api/health":
            return await call_next(request)
        key = request.headers.get("X-API-Key", "")
        if key != config.API_KEY:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


# -- Models -------------------------------------------------------------------

class LibraryCreate(BaseModel):
    name: str
    path: str
    file_extensions: str = ".mkv,.mp4,.avi,.mov,.m4v,.webm"
    scan_mode: str = "manual"
    transcode_mode: str = "manual"
    scan_cron: str | None = None

class LibraryUpdate(BaseModel):
    name: str | None = None
    path: str | None = None
    file_extensions: str | None = None
    scan_mode: str | None = None
    transcode_mode: str | None = None
    scan_cron: str | None = None
    enabled: int | None = None

class PresetCreate(BaseModel):
    name: str
    encoder: str = "vt_h265"
    container: str = "av_mp4"
    encoder_preset: str | None = None
    audio_encoder: str = "av_aac"
    audio_bitrate: int = 128
    audio_mixdown: str = "stereo"
    quality_rules: dict = Field(default_factory=dict)
    skip_codecs: list[str] = Field(default_factory=lambda: ["hevc", "h265"])

class PresetUpdate(BaseModel):
    name: str | None = None
    encoder: str | None = None
    container: str | None = None
    encoder_preset: str | None = None
    audio_encoder: str | None = None
    audio_bitrate: int | None = None
    audio_mixdown: str | None = None
    quality_rules: dict | None = None
    skip_codecs: list[str] | None = None

class JobStart(BaseModel):
    library_id: int
    preset_id: int | None = None


# -- Health -------------------------------------------------------------------

@app.get("/api/health")
async def health():
    counts = await db.count_jobs_by_status()
    hb_version = "unknown"
    try:
        result = subprocess.run(
            [config.HANDBRAKE_CLI, "--version"],
            capture_output=True, text=True, timeout=5,
        )
        for line in (result.stdout + result.stderr).splitlines():
            if "HandBrake" in line:
                hb_version = line.strip()
                break
    except Exception:
        hb_version = "not found"
    return {
        "status": "ok",
        "service": "transcoder",
        "port": config.PORT,
        "handbrake_cli": hb_version,
        "active_jobs": counts.get("running", 0),
    }


# -- Libraries ----------------------------------------------------------------

@app.get("/api/libraries")
async def list_libraries():
    return await db.list_libraries()

@app.post("/api/libraries", status_code=201)
async def create_library(body: LibraryCreate):
    return await db.create_library(body.model_dump())

@app.put("/api/libraries/{lib_id}")
async def update_library(lib_id: int, body: LibraryUpdate):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    result = await db.update_library(lib_id, data)
    if result is None:
        raise HTTPException(404, "Library not found")
    await scheduler.sync_schedules()
    return result

@app.delete("/api/libraries/{lib_id}", status_code=204)
async def delete_library(lib_id: int):
    await db.delete_library(lib_id)
    await scheduler.sync_schedules()

@app.post("/api/libraries/{lib_id}/scan")
async def trigger_scan(lib_id: int, background_tasks: BackgroundTasks):
    lib = await db.get_library(lib_id)
    if not lib:
        raise HTTPException(404, "Library not found")
    background_tasks.add_task(scan_library, lib_id)
    return {"message": f"Scan started for '{lib['name']}'"}


# -- Presets ------------------------------------------------------------------

@app.get("/api/presets")
async def list_presets():
    return await db.list_presets()

@app.post("/api/presets", status_code=201)
async def create_preset(body: PresetCreate):
    return await db.create_preset(body.model_dump())

@app.put("/api/presets/{preset_id}")
async def update_preset(preset_id: int, body: PresetUpdate):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    result = await db.update_preset(preset_id, data)
    if result is None:
        raise HTTPException(400, "Cannot edit default presets")
    return result

@app.delete("/api/presets/{preset_id}", status_code=204)
async def delete_preset(preset_id: int):
    await db.delete_preset(preset_id)


# -- Jobs ---------------------------------------------------------------------

@app.get("/api/jobs")
async def list_jobs(
    status: str | None = None,
    library_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
):
    return await db.list_jobs(status=status, library_id=library_id, limit=limit, offset=offset)

@app.get("/api/jobs/{job_id}")
async def get_job(job_id: int):
    job = await db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job

@app.post("/api/jobs/start")
async def start_jobs(body: JobStart, background_tasks: BackgroundTasks):
    lib = await db.get_library(body.library_id)
    if not lib:
        raise HTTPException(404, "Library not found")
    background_tasks.add_task(run_library_jobs, body.library_id, body.preset_id)
    return {"message": f"Transcoding started for '{lib['name']}'"}

@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job_endpoint(job_id: int):
    success = await cancel_job(job_id)
    if not success:
        raise HTTPException(400, "Job cannot be cancelled")
    return {"message": "Job cancelled"}


# -- Stats --------------------------------------------------------------------

@app.get("/api/stats")
async def get_stats():
    return await db.get_stats()


# -- Scans --------------------------------------------------------------------

@app.get("/api/scans")
async def list_scans():
    return await db.list_scans()

@app.post("/api/scans/{library_id}")
async def trigger_scan_alt(library_id: int, background_tasks: BackgroundTasks):
    lib = await db.get_library(library_id)
    if not lib:
        raise HTTPException(404, "Library not found")
    background_tasks.add_task(scan_library, library_id)
    return {"message": f"Scan started for '{lib['name']}'"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=config.PORT, log_level="info")
