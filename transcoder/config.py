"""Configuration loaded from environment variables."""

import os
import shutil
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PORT = int(os.getenv("PORT", "8323"))
API_KEY = os.getenv("API_KEY", "")
CORS_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:3001").split(",")
    if o.strip()
]

DB_PATH = os.getenv("DB_PATH", "./data/transcoder.db")

HANDBRAKE_CLI = os.getenv("HANDBRAKE_CLI") or shutil.which("HandBrakeCLI") or "HandBrakeCLI"
FFPROBE_PATH = os.getenv("FFPROBE_PATH") or shutil.which("ffprobe") or "ffprobe"

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".webm"}
TEMP_SUFFIX = ".tmp.mp4"
DURATION_TOLERANCE_SECS = 2.0

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
