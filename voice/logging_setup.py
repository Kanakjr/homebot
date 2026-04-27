"""Logging setup for the voice assistant.

Writes two streams:

* **Console** (stderr) at ``VOICE_LOG_LEVEL`` (default ``INFO``) -- what you
  see in the terminal you ran ``python -m voice`` from.
* **File** at ``DEBUG`` -- a fresh file per run under
  ``voice/logs/voice-YYYYMMDD-HHMMSS.log`` (or wherever ``VOICE_LOG_DIR``
  points). Rotated implicitly by the per-run timestamp in the filename,
  so nothing is ever overwritten.

The file handler always logs at DEBUG so that when something misbehaves
you can hand over the log and we can see low-level receive-loop events,
tool-call args/results, and mic-mute transitions even if the console
was set to INFO at the time.

Also routes noisy third-party loggers to the file but not the console
(google.genai.live, websockets, asyncio, openwakeword) so the console
stays readable.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

import voice.config as cfg

_NOISY = (
    "google.genai",
    "google_genai",
    "websockets",
    "websockets.client",
    "asyncio",
    "httpx",
    "httpcore",
    "openwakeword",
    "urllib3",
)

_FILE_FMT = (
    "%(asctime)s.%(msecs)03d %(levelname)-5s %(name)-26s "
    "[%(threadName)s] %(message)s"
)
_CONSOLE_FMT = "%(asctime)s %(name)-22s %(levelname)-5s %(message)s"


def setup_logging() -> Path:
    """Configure root logger. Returns the log file path for info-printing.

    Safe to call more than once -- handlers are cleared and reinstalled so
    re-imports during tests don't spawn duplicates.
    """
    log_dir = Path(os.getenv("VOICE_LOG_DIR", cfg.BASE_DIR / "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = log_dir / f"voice-{stamp}.log"

    # Also keep a stable "latest" pointer so it's easy to tail.
    latest = log_dir / "voice-latest.log"
    try:
        if latest.is_symlink() or latest.exists():
            latest.unlink()
        latest.symlink_to(log_path.name)
    except OSError:
        pass

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.setLevel(logging.DEBUG)

    console = logging.StreamHandler(stream=sys.stderr)
    console.setLevel(getattr(logging, cfg.LOG_LEVEL, logging.INFO))
    console.setFormatter(logging.Formatter(_CONSOLE_FMT, datefmt="%H:%M:%S"))
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=20 * 1024 * 1024,  # 20 MB safety cap per-run
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter(_FILE_FMT, datefmt="%Y-%m-%d %H:%M:%S")
    )
    root.addHandler(file_handler)

    # Silence noisy libs on the console but keep their DEBUG in the file.
    for name in _NOISY:
        lg = logging.getLogger(name)
        lg.setLevel(logging.DEBUG)
        lg.propagate = True
    # A hard WARNING floor on the console for the noisiest of them:
    class _ConsoleFloor(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            for noisy in _NOISY:
                if record.name.startswith(noisy):
                    return record.levelno >= logging.WARNING
            return True

    console.addFilter(_ConsoleFloor())

    logging.getLogger("voice.boot").info("Logging to %s", log_path)
    return log_path
