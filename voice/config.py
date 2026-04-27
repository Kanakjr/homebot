"""Voice assistant configuration loaded from environment variables.

The pipeline is:

    mic -> openWakeWord (local) -> Gemini Live WebSocket session -> speaker

Gemini Live handles STT, reasoning and TTS server-side, so there are no
separate STT/TTS/VAD knobs here anymore. Function calls from the model
go to `tool_bridge.py`, which talks directly to Home Assistant for the
fast path and falls back to the Deep Agent HTTP API for complex tasks.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

_THIS_DIR = Path(__file__).resolve().parent

# Load voice/.env explicitly so the module works regardless of CWD
# (e.g. `python -m voice` run from Apps/homebot/ wouldn't find a plain
# `load_dotenv()` search that walks up from CWD).
load_dotenv(_THIS_DIR / ".env", override=False)

# --- Audio ------------------------------------------------------------------
# Gemini Live expects 16-bit PCM at 16 kHz on input and returns 16-bit PCM
# at 24 kHz on output. These are fixed by the API contract.
SAMPLE_RATE = 16000              # mic / send
OUTPUT_SAMPLE_RATE = 24000       # speaker / receive
CHANNELS = 1
FRAME_MS = 80                    # openWakeWord frame size (ms)
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)  # 1280 samples at 16 kHz

# Optional: pick a specific capture device (e.g. ReSpeaker XVF3800 USB array).
# `None` means the system default. Use `python -c "import sounddevice as sd;
# print(sd.query_devices())"` to list candidates.
_mic_idx = os.getenv("MIC_DEVICE_INDEX", "").strip()
MIC_DEVICE_INDEX: int | None = int(_mic_idx) if _mic_idx else None

_spk_idx = os.getenv("SPEAKER_DEVICE_INDEX", "").strip()
SPEAKER_DEVICE_INDEX: int | None = int(_spk_idx) if _spk_idx else None

# --- Wake word --------------------------------------------------------------
WAKE_WORD = os.getenv("WAKE_WORD", "hey_jarvis_v0.1")
WAKE_THRESHOLD = float(os.getenv("WAKE_THRESHOLD", "0.5"))

# --- Gemini Live ------------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
# Default: 3.1 flash Live preview (half-cascade). This uses STT -> text model
# -> TTS under the hood, which gives the most reliable function calling --
# what we want for the tool-heavy home-assistant use case.
#
# Alternatives:
#   gemini-2.5-flash-native-audio-latest                 (nicer voice, shakier tools)
#   gemini-2.5-flash-native-audio-preview-12-2025        (pinned Dec 2025 native)
#   gemini-2.5-flash-native-audio-preview-09-2025        (pinned Sep 2025 native)
LIVE_MODEL = os.getenv("LIVE_MODEL", "gemini-3.1-flash-live-preview")
# Prebuilt voices: Puck, Charon, Kore, Fenrir, Aoede, Leda, Orus, Zephyr.
LIVE_VOICE = os.getenv("LIVE_VOICE", "Charon")

# Close a session after this many seconds with no user speech and no model
# audio. Keeps the cloud bill in check and prevents an abandoned session
# hogging the mic. Starts counting from the last message received from
# Gemini (so the model's own reply time doesn't count as idle).
SESSION_IDLE_TIMEOUT_S = int(os.getenv("SESSION_IDLE_TIMEOUT_S", "10"))

# Hard ceiling on session length. Gemini Live caps audio-only sessions at
# ~15 min; close before that so we never get a mid-sentence disconnect.
SESSION_MAX_S = int(os.getenv("SESSION_MAX_S", "780"))  # 13 min

# --- Home Assistant (direct, fast path) ------------------------------------
HA_URL = os.getenv("HA_URL", "http://localhost:8123").rstrip("/")
HA_TOKEN = os.getenv("HA_TOKEN", "")

# --- Deep Agent (delegate path for complex, multi-step asks) ---------------
DEEPAGENT_URL = os.getenv("DEEPAGENT_URL", "http://localhost:8322").rstrip("/")
DEEPAGENT_API_KEY = os.getenv("DEEPAGENT_API_KEY", "") or os.getenv("API_KEY", "")
VOICE_THREAD_ID = os.getenv("VOICE_THREAD_ID", "voice")

# --- Media services (direct, for status queries) ---------------------------
JELLYFIN_URL = os.getenv("JELLYFIN_URL", "").rstrip("/")
JELLYFIN_API_KEY = os.getenv("JELLYFIN_API_KEY", "")
TRANSMISSION_URL = os.getenv("TRANSMISSION_URL", "").rstrip("/")
TRANSMISSION_USERNAME = os.getenv("TRANSMISSION_USERNAME", "")
TRANSMISSION_PASSWORD = os.getenv("TRANSMISSION_PASSWORD", "")

# --- Paths ------------------------------------------------------------------
BASE_DIR = _THIS_DIR
SOUNDS_DIR = BASE_DIR / "sounds"
SKILLS_DIR = BASE_DIR.parent / "deepagent" / "skills"

# --- Logging ---------------------------------------------------------------
LOG_LEVEL = os.getenv("VOICE_LOG_LEVEL", "INFO")
