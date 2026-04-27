"""Audio I/O: microphone capture and speaker playback.

`MicrophoneStream` captures 16-bit PCM at 16 kHz for both openWakeWord
(fixed 80 ms frames) and Gemini Live (variable-length chunks).

`SpeakerStream` plays 16-bit PCM at the sample rate Gemini Live returns
(24 kHz by default). It drains an asyncio queue so the receive loop can
push chunks without blocking on audio playback.

`play_chime()` remains a synchronous helper for the wake / done sounds.
"""

import asyncio
import logging
import queue
import subprocess
import threading

import numpy as np
import sounddevice as sd

import voice.config as cfg

log = logging.getLogger(__name__)


class MicrophoneStream:
    """Continuously capture 16-bit PCM audio from the default microphone.

    Audio frames are placed into an internal queue and consumed via
    :meth:`read_frame` (fixed-size int16 ndarray) or :meth:`read_bytes`
    (raw little-endian PCM bytes, for sending to Gemini Live).

    The stream can be paused/resumed via :meth:`mute` / :meth:`unmute`
    so TTS playback doesn't feed back into the mic when the far-field
    array lacks hardware AEC.
    """

    def __init__(
        self,
        sample_rate: int = cfg.SAMPLE_RATE,
        frame_samples: int = cfg.FRAME_SAMPLES,
        channels: int = cfg.CHANNELS,
        device: int | None = cfg.MIC_DEVICE_INDEX,
    ):
        self.sample_rate = sample_rate
        self.frame_samples = frame_samples
        self.channels = channels
        self.device = device
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=200)
        self._stream: sd.InputStream | None = None
        self._muted = False
        self._lock = threading.Lock()

    def start(self) -> None:
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            blocksize=self.frame_samples,
            device=self.device,
            callback=self._audio_callback,
        )
        self._stream.start()
        log.info(
            "Microphone started  rate=%dHz  frame=%d samples  device=%s",
            self.sample_rate,
            self.frame_samples,
            self.device if self.device is not None else "default",
        )

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
            log.info("Microphone stopped")

    def mute(self) -> None:
        with self._lock:
            self._muted = True
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break

    def unmute(self) -> None:
        with self._lock:
            self._muted = False

    @property
    def is_muted(self) -> bool:
        with self._lock:
            return self._muted

    def read_frame(self, timeout: float = 0.2) -> np.ndarray | None:
        """Return the next audio frame (int16 ndarray) or None on timeout."""
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    async def read_bytes_async(self, timeout: float = 0.2) -> bytes | None:
        """Async variant: return raw little-endian int16 PCM bytes.

        Uses the default executor so we never block the event loop on the
        underlying :class:`queue.Queue.get`. Returns ``None`` on timeout
        (caller typically loops and keeps trying).
        """
        loop = asyncio.get_running_loop()
        frame = await loop.run_in_executor(None, self.read_frame, timeout)
        if frame is None:
            return None
        return frame.tobytes()

    def drain(self) -> None:
        """Discard any queued frames (used when switching modes)."""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        if status:
            log.warning("Mic callback status: %s", status)
        with self._lock:
            if self._muted:
                return
        try:
            self._queue.put_nowait(indata[:, 0].copy())
        except queue.Full:
            pass


class SpeakerStream:
    """Asynchronous 16-bit PCM player backed by sounddevice.

    Gemini Live returns audio as raw PCM chunks at 24 kHz. Instead of
    buffering an entire utterance and shelling out to ``afplay`` (which
    is what the old ``play_audio`` did), we keep an OutputStream open for
    the lifetime of a Live session and feed it chunks from the receive
    loop via :meth:`write`. That gives sub-100 ms playback latency and
    lets us cleanly interrupt when the model is cut off.
    """

    def __init__(
        self,
        sample_rate: int = cfg.OUTPUT_SAMPLE_RATE,
        channels: int = cfg.CHANNELS,
        device: int | None = cfg.SPEAKER_DEVICE_INDEX,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.device = device
        self._stream: sd.RawOutputStream | None = None
        self._queue: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._worker: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def start(self) -> None:
        """Open the output stream and spawn the playback worker."""
        self._loop = asyncio.get_running_loop()
        self._stream = sd.RawOutputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            device=self.device,
        )
        self._stream.start()
        self._worker = asyncio.create_task(self._drain_loop())
        log.info(
            "Speaker started  rate=%dHz  device=%s",
            self.sample_rate,
            self.device if self.device is not None else "default",
        )

    async def write(self, data: bytes) -> None:
        """Queue PCM bytes for playback (non-blocking)."""
        await self._queue.put(data)

    def interrupt(self) -> None:
        """Drop any queued audio. Called when the model is interrupted
        (e.g. user barge-in) so stale TTS doesn't keep playing over new
        speech."""
        dropped = 0
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                dropped += 1
            except asyncio.QueueEmpty:
                break
        if dropped:
            log.debug("Speaker interrupt -- dropped %d queued chunks", dropped)

    async def stop(self) -> None:
        """Flush and tear down the output stream."""
        await self._queue.put(None)
        if self._worker is not None:
            try:
                await asyncio.wait_for(self._worker, timeout=2.0)
            except asyncio.TimeoutError:
                self._worker.cancel()
            self._worker = None
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                log.debug("Speaker stream close failed", exc_info=True)
            self._stream = None
            log.info("Speaker stopped")

    async def _drain_loop(self) -> None:
        """Pull chunks off the queue and push them to the OutputStream.

        ``RawOutputStream.write`` is blocking (it copies into a ring
        buffer and can block briefly if that buffer fills). We push it
        through ``run_in_executor`` so the asyncio loop keeps servicing
        the Gemini receive iterator while audio plays.
        """
        assert self._loop is not None
        while True:
            chunk = await self._queue.get()
            if chunk is None:
                return
            if not self._stream:
                return
            try:
                await self._loop.run_in_executor(None, self._stream.write, chunk)
            except Exception:
                log.exception("Speaker write failed")


def play_chime(name: str) -> None:
    """Play a short chime WAV from the sounds/ directory (synchronous)."""
    path = cfg.SOUNDS_DIR / f"{name}.wav"
    if not path.exists():
        log.debug("Chime file not found: %s", path)
        return
    try:
        subprocess.run(["afplay", str(path)], check=True)
    except Exception:
        log.warning("Failed to play chime %s", name, exc_info=True)
