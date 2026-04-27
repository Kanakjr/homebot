"""One-off script to generate simple chime WAV files for the voice assistant."""

import numpy as np
import soundfile as sf
from pathlib import Path

SOUNDS_DIR = Path(__file__).resolve().parent / "sounds"
SR = 24000


def _sine(freq: float, duration: float, sr: int = SR) -> np.ndarray:
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    return np.sin(2 * np.pi * freq * t).astype(np.float32)


def _fade(audio: np.ndarray, fade_ms: int = 10, sr: int = SR) -> np.ndarray:
    n = int(sr * fade_ms / 1000)
    audio[:n] *= np.linspace(0, 1, n).astype(np.float32)
    audio[-n:] *= np.linspace(1, 0, n).astype(np.float32)
    return audio


def generate_wake_chime() -> None:
    """Two ascending tones: 'listening' indicator."""
    t1 = _fade(_sine(880, 0.08) * 0.4)
    gap = np.zeros(int(SR * 0.03), dtype=np.float32)
    t2 = _fade(_sine(1174, 0.10) * 0.4)
    audio = np.concatenate([t1, gap, t2])
    sf.write(str(SOUNDS_DIR / "wake.wav"), audio, SR)


def generate_done_chime() -> None:
    """Single descending tone: 'done' indicator."""
    t1 = _fade(_sine(1174, 0.06) * 0.3)
    gap = np.zeros(int(SR * 0.02), dtype=np.float32)
    t2 = _fade(_sine(880, 0.08) * 0.3)
    audio = np.concatenate([t1, gap, t2])
    sf.write(str(SOUNDS_DIR / "done.wav"), audio, SR)


if __name__ == "__main__":
    SOUNDS_DIR.mkdir(parents=True, exist_ok=True)
    generate_wake_chime()
    generate_done_chime()
    print(f"Chimes written to {SOUNDS_DIR}")
