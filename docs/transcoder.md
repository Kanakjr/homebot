# Transcoder service

The Transcoder is a **standalone HandBrake-based** service for batch and on-demand **video transcoding**. It runs separately from the main HomeBotAI API and exposes its own FastAPI surface (default port **8323**).

## Architecture

| Module | Responsibility |
|--------|----------------|
| `transcoder/transcoder.py` | Core **HandBrakeCLI** wrapper: start jobs, progress, cancellation, file output |
| `transcoder/api.py` | **FastAPI** HTTP API, request validation, CORS, optional API key middleware |
| `transcoder/db.py` | **SQLite** persistence for libraries, presets, jobs, and scan metadata |
| `transcoder/scanner.py` | **Library scanner**: discover videos, probe with ffprobe, browse paths |
| `transcoder/scheduler.py` | **Scheduled scans and job orchestration** after service startup |
| `transcoder/config.py` | Environment-driven settings (port, paths, keys) |

## API overview

All routes below are relative to the transcoder base URL (for example `http://localhost:8323`). When `API_KEY` is set, send `X-API-Key` on `/api/*` routes except `/api/health`.

### Libraries

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/libraries` | List transcoding libraries |
| POST | `/api/libraries` | Create a library (name, path, extensions, scan/transcode modes, cron) |
| PUT | `/api/libraries/{lib_id}` | Update a library |
| DELETE | `/api/libraries/{lib_id}` | Delete a library |
| POST | `/api/libraries/{lib_id}/scan` | Trigger a scan of a library |
| GET | `/api/libraries/{lib_id}/browse` | Browse files under a library |

### Jobs

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/jobs` | List jobs |
| GET | `/api/jobs/progress` | Aggregate progress for active work |
| GET | `/api/jobs/{job_id}` | Job detail |
| POST | `/api/jobs/start` | Start a job (library + optional preset) |
| POST | `/api/jobs/start-path` | Start transcoding from a specific file path |
| POST | `/api/jobs/{job_id}/cancel` | Cancel a job |

### Presets

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/presets` | List HandBrake presets (encoder, container, audio, quality rules) |
| POST | `/api/presets` | Create a preset |
| PUT | `/api/presets/{preset_id}` | Update a preset |
| DELETE | `/api/presets/{preset_id}` | Delete a preset |

### Scans and stats

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/scans` | List recorded scans |
| POST | `/api/scans/{library_id}` | Start a background scan (same behavior as `POST /api/libraries/{lib_id}/scan`) |
| GET | `/api/stats` | Aggregate statistics |

### Health

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Liveness and service info |

Interactive docs are typically at `http://localhost:8323/docs` when the service is running.

## Dashboard integration

The main app includes a **`/transcoder`** page with a **library browser**, **job management**, and controls wired to the transcoder API.

![Transcoder](assets/screenshots/transcoder.png)

## Configuration

Environment variables are read in `transcoder/config.py`:

| Variable | Default / notes |
|----------|-----------------|
| `PORT` | `8323` |
| `API_KEY` | Empty disables auth; when set, use `X-API-Key` |
| `CORS_ORIGINS` | Comma-separated origins (default includes `http://localhost:3001`) |
| `DB_PATH` | SQLite file path (default `./data/transcoder.db`) |
| `HANDBRAKE_CLI` | Path to **HandBrakeCLI**; falls back to `which HandBrakeCLI` |
| `FFPROBE_PATH` | Path to **ffprobe** for media inspection |

**Library paths** are not a single global env var: each **library** record stores its own filesystem `path` via the libraries API. Ensure the process user can read those directories and write output next to sources or wherever your preset dictates.
