"""Voice assistant entry point.

Pipeline:

    mic -> openWakeWord ("hey jarvis")
        -> wake chime
        -> Gemini Live WebSocket session (STT + reasoning + TTS + tools)
        -> done chime
        -> reset wake word
        -> back to listening

Run from the repo root with either::

    python -m voice
    python -m voice.main
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

import voice.config as cfg
from voice.audio_io import MicrophoneStream, play_chime
from voice.live_session import run_session
from voice.logging_setup import setup_logging
from voice.wake_word import WakeWordDetector

_LOG_PATH = setup_logging()
log = logging.getLogger("voice")

_running = True


def _handle_signal(sig, _frame) -> None:
    global _running
    log.info("Shutdown requested (signal %s)", sig)
    _running = False


async def _wait_for_wake(mic: MicrophoneStream, ww: WakeWordDetector) -> bool:
    """Block until the wake word fires or shutdown is requested.

    Returns True on wake, False if asked to shut down first.
    """
    ww.reset()
    while _running:
        frame = await asyncio.get_running_loop().run_in_executor(
            None, mic.read_frame, 0.2
        )
        if frame is None:
            continue
        if ww.process(frame):
            return True
    return False


async def _voice_loop(mic: MicrophoneStream, ww: WakeWordDetector) -> None:
    mic.start()
    log.info(
        "Voice assistant active  wake_word=%s  model=%s",
        cfg.WAKE_WORD,
        cfg.LIVE_MODEL,
    )
    wake_phrase = cfg.WAKE_WORD.replace("_v0.1", "").replace("_", " ")
    print(f'\nJarvis is listening -- say "{wake_phrase}" to wake.\n')

    try:
        while _running:
            triggered = await _wait_for_wake(mic, ww)
            if not triggered:
                break
            log.info("Wake word triggered")
            play_chime("wake")

            mic.drain()
            reason = await run_session(mic)
            log.info("Session ended: %s", reason)
            play_chime("done")

            if not _running:
                break
            print(f'Listening again -- say "{wake_phrase}" to wake.')
    finally:
        mic.stop()


def main() -> int:
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    if not cfg.GEMINI_API_KEY:
        print(
            "ERROR: GEMINI_API_KEY (or GOOGLE_API_KEY) is not set. "
            "Copy .env.example to .env and fill it in.",
            file=sys.stderr,
        )
        return 2
    if not cfg.HA_TOKEN:
        log.warning(
            "HA_TOKEN is not set -- device control tools will fail until "
            "you add HA_URL + HA_TOKEN to .env."
        )

    log.info("--- Loading voice pipeline components ---")
    log.info("Log file: %s", _LOG_PATH)
    log.info(
        "Config  model=%s voice=%s idle=%ds max=%ds mic=%s spk=%s",
        cfg.LIVE_MODEL,
        cfg.LIVE_VOICE,
        cfg.SESSION_IDLE_TIMEOUT_S,
        cfg.SESSION_MAX_S,
        cfg.MIC_DEVICE_INDEX if cfg.MIC_DEVICE_INDEX is not None else "default",
        cfg.SPEAKER_DEVICE_INDEX if cfg.SPEAKER_DEVICE_INDEX is not None else "default",
    )
    mic = MicrophoneStream()
    ww = WakeWordDetector()
    ww.load()
    log.info("--- Components ready ---")

    try:
        asyncio.run(_voice_loop(mic, ww))
    except KeyboardInterrupt:
        pass

    log.info("Voice assistant stopped.")
    print("Goodbye.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
