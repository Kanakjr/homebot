"""Gemini Live WebSocket session manager.

The wake-word loop in :mod:`voice.main` calls :func:`run_session` once the
wake word fires. This module owns everything that happens between that
moment and the moment we go back to listening for the wake word.

Concurrency model
-----------------

Inside ``run_session`` we spawn three long-lived tasks plus a watchdog:

1. **Mic pump** -- reads raw int16 PCM frames from the shared
   :class:`MicrophoneStream` and pushes them to Gemini Live via
   ``send_realtime_input(audio=Blob(..., "audio/pcm;rate=16000"))``.
2. **Receiver** -- iterates ``session.receive()`` in an outer ``while``
   loop, because the SDK iterator *ends at every* ``turn_complete``.
   We re-enter it to keep processing subsequent turns. Each message is
   routed:
     * ``server_content.model_turn`` audio parts -> :class:`SpeakerStream`
     * ``tool_call`` -> tool dispatcher
     * ``interrupted`` -> speaker ``interrupt()`` + unmute mic
     * ``turn_complete`` -> unmute mic + mark activity
     * ``input_transcription`` / ``output_transcription`` -> log + mark
     * ``go_away`` / ``session_resumption_update`` -> log only.
3. **Watchdog** -- checks the last-activity timestamp and the absolute
   start time on a 1 s cadence. Sets ``close_event`` when idle for
   ``SESSION_IDLE_TIMEOUT_S`` seconds (user's "10 second buffer" --
   after that, the wake word is required to resume) or when the session
   exceeds ``SESSION_MAX_S``.

Any task setting ``close_event`` (including the ``end_session`` tool)
triggers graceful teardown: cancel the other tasks, drain the speaker,
close the WebSocket, return control to the wake-word loop.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from contextlib import suppress

from google import genai
from google.genai import types

import voice.config as cfg
import voice.tool_bridge as tb
from voice.audio_io import MicrophoneStream, SpeakerStream
from voice.system_instruction import build_system_instruction

log = logging.getLogger("voice.live")


# Gemini Live chunks we send per batch. 80 ms at 16 kHz = 2560 bytes -- the
# same size the mic produces. Keeping the ratio 1:1 gives sub-100 ms
# end-to-end latency without overwhelming the receive queue.
_MIC_READ_TIMEOUT_S = 0.1


class LiveSession:
    """Owns a single Gemini Live connection and the tasks around it."""

    def __init__(self, mic: MicrophoneStream):
        self.mic = mic
        self.speaker = SpeakerStream()
        self.close_event = asyncio.Event()
        self._last_activity = time.monotonic()
        self._started_at = time.monotonic()
        self._client = genai.Client(api_key=cfg.GEMINI_API_KEY)
        self._tools = tb.get_live_tools()
        self._tool_map = {fn.__name__: fn for fn in self._tools}
        tb.bind_end_session_event(self.close_event)

    # -- lifecycle -----------------------------------------------------

    async def run(self) -> str:
        """Open the session and block until a close condition fires.

        Returns a short reason string for logging.
        """
        if not cfg.GEMINI_API_KEY:
            log.error("GEMINI_API_KEY is not set; cannot open Live session")
            return "no_api_key"

        config = self._build_config()
        log.info(
            "Opening Gemini Live session  model=%s  voice=%s  tools=%d",
            cfg.LIVE_MODEL,
            cfg.LIVE_VOICE,
            len(self._tools),
        )

        await self.speaker.start()

        reason = "closed"
        try:
            async with self._client.aio.live.connect(
                model=cfg.LIVE_MODEL, config=config
            ) as session:
                mic_task = asyncio.create_task(self._mic_pump(session))
                recv_task = asyncio.create_task(self._receiver(session))
                watch_task = asyncio.create_task(self._watchdog())

                try:
                    await self.close_event.wait()
                finally:
                    reason = self._close_reason()
                    log.info("Closing Live session (%s)", reason)
                    for t in (mic_task, recv_task, watch_task):
                        t.cancel()
                    with suppress(asyncio.CancelledError, Exception):
                        await asyncio.gather(mic_task, recv_task, watch_task)
        except Exception:
            log.exception("Gemini Live session failed")
            reason = "error"
        finally:
            await self.speaker.stop()
            self.mic.unmute()
        return reason

    # -- session config ------------------------------------------------

    def _build_config(self) -> types.LiveConnectConfig:
        instruction = build_system_instruction()
        return types.LiveConnectConfig(
            response_modalities=[types.Modality.AUDIO],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=cfg.LIVE_VOICE
                    )
                )
            ),
            system_instruction=types.Content(
                parts=[types.Part(text=instruction)]
            ),
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            tools=self._tools,
            session_resumption=types.SessionResumptionConfig(),
            context_window_compression=types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow(),
            ),
        )

    # -- worker tasks --------------------------------------------------

    async def _mic_pump(self, session) -> None:
        """Stream microphone PCM to Gemini Live as it arrives."""
        log.debug("mic pump starting")
        try:
            while not self.close_event.is_set():
                data = await self.mic.read_bytes_async(timeout=_MIC_READ_TIMEOUT_S)
                if data is None:
                    continue
                await session.send_realtime_input(
                    audio=types.Blob(
                        data=data,
                        mime_type=f"audio/pcm;rate={cfg.SAMPLE_RATE}",
                    )
                )
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("mic pump crashed; closing session")
            self.close_event.set()

    async def _receiver(self, session) -> None:
        """Consume the server->client stream and dispatch events.

        IMPORTANT: ``session.receive()`` returns an async iterator that
        terminates at every ``turn_complete``. To keep the session alive
        across multiple user turns we have to re-enter the iterator in an
        outer ``while`` loop. Without this the receiver task exits after
        the first turn while the mic pump keeps streaming audio into a
        void -- exactly the "worked once, then went silent" bug.

        We also only bump ``_last_activity`` on messages that represent
        real user / model activity (audio chunks, transcription, tool
        calls), not on keepalives like session-resumption pings. That
        way the idle watchdog actually closes the session after
        ``SESSION_IDLE_TIMEOUT_S`` of real silence.
        """
        log.debug("receiver starting")
        turn_idx = 0
        try:
            while not self.close_event.is_set():
                log.debug("receive: entering turn=%d", turn_idx)
                async for message in session.receive():
                    if getattr(message, "go_away", None):
                        log.warning(
                            "Gemini Live requested disconnect: %s",
                            message.go_away,
                        )
                        self.close_event.set()

                    sr = getattr(message, "session_resumption_update", None)
                    if sr and getattr(sr, "new_handle", None):
                        log.debug("receive: session resumption handle issued")

                    sc = getattr(message, "server_content", None)
                    if sc is not None:
                        await self._handle_server_content(sc, turn_idx)

                    tc = getattr(message, "tool_call", None)
                    if tc is not None and tc.function_calls:
                        self._last_activity = time.monotonic()
                        await self._handle_tool_call(session, tc.function_calls)

                log.debug("receive: turn=%d iterator ended", turn_idx)
                turn_idx += 1

        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("receiver crashed; closing session")
            self.close_event.set()

    async def _handle_server_content(self, sc, turn_idx: int) -> None:
        model_turn = getattr(sc, "model_turn", None)
        if model_turn is not None:
            audio_bytes = 0
            for part in model_turn.parts or []:
                inline = getattr(part, "inline_data", None)
                if inline and inline.data:
                    # Mute the mic while the model is speaking so its voice
                    # doesn't loop back into the next turn (when the far-field
                    # mic doesn't have hardware AEC).
                    if not self.mic.is_muted:
                        log.debug("mic: mute (model speaking, turn=%d)", turn_idx)
                        self.mic.mute()
                    await self.speaker.write(inline.data)
                    audio_bytes += len(inline.data)
            if audio_bytes:
                self._last_activity = time.monotonic()
                log.debug(
                    "receive: model audio chunk %d bytes (turn=%d)",
                    audio_bytes,
                    turn_idx,
                )

        if getattr(sc, "interrupted", False):
            log.info("user barge-in: interrupting model")
            self.speaker.interrupt()
            if self.mic.is_muted:
                log.debug("mic: unmute (barge-in)")
            self.mic.unmute()
            self._last_activity = time.monotonic()

        if getattr(sc, "turn_complete", False):
            log.info("turn %d complete -> waiting for user", turn_idx)
            # Small grace period before unmuting -- the speaker queue may
            # still have buffered audio from the final chunk.
            await asyncio.sleep(0.2)
            if self.mic.is_muted:
                log.debug("mic: unmute (turn_complete)")
            self.mic.unmute()
            self._last_activity = time.monotonic()

        it = getattr(sc, "input_transcription", None)
        if it and getattr(it, "text", ""):
            text = it.text.strip()
            if text:
                log.info("You: %s", text)
                self._last_activity = time.monotonic()

        ot = getattr(sc, "output_transcription", None)
        if ot and getattr(ot, "text", ""):
            text = ot.text.strip()
            if text:
                log.info("Jarvis: %s", text)
                self._last_activity = time.monotonic()

    async def _handle_tool_call(self, session, function_calls) -> None:
        responses: list[types.FunctionResponse] = []
        for fc in function_calls:
            fname = fc.name
            args = dict(fc.args or {})
            fn = self._tool_map.get(fname)
            log.info("tool_call %s(%s)", fname, _short(args))

            if fn is None:
                result: object = f"Unknown tool: {fname}"
            else:
                try:
                    if inspect.iscoroutinefunction(fn):
                        result = await fn(**args)
                    else:
                        loop = asyncio.get_running_loop()
                        result = await loop.run_in_executor(
                            None, lambda: fn(**args)
                        )
                except Exception as e:
                    log.exception("tool %s failed", fname)
                    result = f"Tool error: {e}"

            log.debug("tool_result %s -> %s", fname, _short(str(result)))
            responses.append(
                types.FunctionResponse(
                    id=fc.id,
                    name=fname,
                    response={"result": result},
                )
            )

        try:
            await session.send_tool_response(function_responses=responses)
        except Exception:
            log.exception("send_tool_response failed; closing session")
            self.close_event.set()

    async def _watchdog(self) -> None:
        """Close the session after idle / max time."""
        last_heartbeat = 0.0
        try:
            while not self.close_event.is_set():
                await asyncio.sleep(1.0)
                now = time.monotonic()
                elapsed = now - self._started_at
                idle = now - self._last_activity

                if elapsed >= cfg.SESSION_MAX_S:
                    log.info("Session max duration reached (%.0fs)", elapsed)
                    self.close_event.set()
                    return
                if idle >= cfg.SESSION_IDLE_TIMEOUT_S:
                    log.info(
                        "Session idle for %.1fs (>= %ds); closing",
                        idle,
                        cfg.SESSION_IDLE_TIMEOUT_S,
                    )
                    self.close_event.set()
                    return

                # Periodic heartbeat to the log file, throttled so it's
                # useful for debugging without being noisy.
                if now - last_heartbeat >= 2.0:
                    log.debug(
                        "watchdog: elapsed=%.1fs idle=%.1fs mic_muted=%s",
                        elapsed,
                        idle,
                        self.mic.is_muted,
                    )
                    last_heartbeat = now
        except asyncio.CancelledError:
            pass

    def _close_reason(self) -> str:
        elapsed = time.monotonic() - self._started_at
        if elapsed >= cfg.SESSION_MAX_S:
            return f"max_duration:{elapsed:.0f}s"
        idle = time.monotonic() - self._last_activity
        if idle >= cfg.SESSION_IDLE_TIMEOUT_S:
            return f"idle:{idle:.0f}s"
        return "closed"


async def run_session(mic: MicrophoneStream) -> str:
    """Open a new Live session and block until it closes.

    Convenience wrapper so callers don't have to instantiate
    :class:`LiveSession` themselves.
    """
    session = LiveSession(mic)
    return await session.run()


def _short(v: object, n: int = 120) -> str:
    s = str(v)
    return s if len(s) <= n else s[:n] + "..."
