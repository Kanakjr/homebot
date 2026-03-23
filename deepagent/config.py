"""Configuration loaded from environment variables."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# --- LLM ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
MODEL = os.getenv("MODEL", "ollama:sorc/qwen3.5-claude-4.6-opus-q4:2b")
# Ollama HTTP API base (used by ChatOllama and /api/models). In Docker use host.docker.internal; on host use 127.0.0.1.
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")

# --- Home Assistant ---
HA_URL = os.getenv("HA_URL", "http://localhost:8123")
HA_TOKEN = os.getenv("HA_TOKEN", "")

# --- Media Services ---
SONARR_URL = os.getenv("SONARR_URL", "http://localhost:8989")
SONARR_API_KEY = os.getenv("SONARR_API_KEY", "")
RADARR_URL = os.getenv("RADARR_URL", "http://localhost:7878")
RADARR_API_KEY = os.getenv("RADARR_API_KEY", "")
TRANSMISSION_URL = os.getenv("TRANSMISSION_URL", "http://localhost:9091")
JELLYSEERR_URL = os.getenv("JELLYSEERR_URL", "http://localhost:5055")
JELLYSEERR_API_KEY = os.getenv("JELLYSEERR_API_KEY", "")
PROWLARR_URL = os.getenv("PROWLARR_URL", "http://localhost:9696")
PROWLARR_API_KEY = os.getenv("PROWLARR_API_KEY", "")
JELLYFIN_URL = os.getenv("JELLYFIN_URL", "http://localhost:8096")
JELLYFIN_API_KEY = os.getenv("JELLYFIN_API_KEY", "")

# --- Server ---
PORT = int(os.getenv("PORT", "8322"))
API_KEY = os.getenv("API_KEY", "")
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3001").split(",") if o.strip()]

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent
SKILLS_DIR = str(BASE_DIR / "skills")
DATA_DIR = Path(os.getenv("DATA_DIR", "/tmp/deepagent_data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# --- LangSmith ---
DEEPAGENT_MAX_QWEN_B = int(os.getenv("DEEPAGENT_MAX_QWEN_B", "4"))

# --- LangSmith ---
LANGSMITH_TRACING = os.getenv("LANGSMITH_TRACING", "false")
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "homebot-deepagent")
