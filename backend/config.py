import os
import platform
import ssl
import subprocess
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")


def _setup_ssl_certs():
    """Merge macOS system keychain CAs with Python's certifi bundle.

    Corporate networks with SSL interception install their CA in the
    system keychain but Python uses its own bundle, causing verification
    failures. This creates a combined bundle and points SSL_CERT_FILE at it.
    """
    if platform.system() != "Darwin" or os.environ.get("SSL_CERT_FILE"):
        return
    try:
        import certifi

        keychain_pem = subprocess.check_output(
            ["security", "find-certificate", "-a", "-p", "/Library/Keychains/System.keychain"],
            timeout=5,
        ).decode()
        if "BEGIN CERTIFICATE" not in keychain_pem:
            return

        combined = Path(certifi.where()).read_text() + "\n" + keychain_pem
        bundle = Path(tempfile.gettempdir()) / "homebot_ca_bundle.pem"
        bundle.write_text(combined)
        os.environ["SSL_CERT_FILE"] = str(bundle)
    except Exception:
        pass


_setup_ssl_certs()


TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_ALLOWED_USERS = [
    int(uid.strip())
    for uid in os.environ.get("TELEGRAM_ALLOWED_USERS", "").split(",")
    if uid.strip()
]

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

HA_URL = os.environ.get("HA_URL", "http://localhost:8123")
HA_TOKEN = os.environ.get("HA_TOKEN", "")
HA_WS_URL = HA_URL.replace("http://", "ws://").replace("https://", "wss://") + "/api/websocket"

N8N_URL = os.environ.get("N8N_URL", "http://localhost:5678")
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")

SONARR_URL = os.environ.get("SONARR_URL", "http://localhost:8989")
SONARR_API_KEY = os.environ.get("SONARR_API_KEY", "")

TRANSMISSION_URL = os.environ.get("TRANSMISSION_URL", "http://localhost:9091")

JELLYSEERR_URL = os.environ.get("JELLYSEERR_URL", "http://localhost:5055")
JELLYSEERR_API_KEY = os.environ.get("JELLYSEERR_API_KEY", "")

PROWLARR_URL = os.environ.get("PROWLARR_URL", "http://localhost:9696")
PROWLARR_API_KEY = os.environ.get("PROWLARR_API_KEY", "")

JELLYFIN_URL = os.environ.get("JELLYFIN_URL", "http://localhost:8096")
JELLYFIN_API_KEY = os.environ.get("JELLYFIN_API_KEY", "")

DB_PATH = os.environ.get("DB_PATH", "/app/data/homebot.db")

TZ = os.environ.get("TZ", "America/New_York")

ENERGY_RATE = float(os.environ.get("ENERGY_RATE", "8"))
ENERGY_CURRENCY = os.environ.get("ENERGY_CURRENCY", "INR")
