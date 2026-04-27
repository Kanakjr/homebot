"""Verify the LiveSession receiver keeps consuming turns after the first one.

This is the regression test for the bug the user reported: first
Gemini Live turn worked, then the session went silent. Root cause was
``session.receive()`` returning a fresh async iterator per turn, which
ends at each ``turn_complete`` -- the old receiver ran it *once* and
exited silently. We now wrap it in a ``while not close_event.is_set()``
loop.

We don't hit the real Gemini API here. We stub the SDK session with a
fake that yields two turns worth of server messages (each ending in
``turn_complete``) and check that the receiver processed both turns and
stayed alive.

Run from Apps/homebot::

    .venv/bin/python -u -m voice._smoke_multi_turn
"""

from __future__ import annotations

import asyncio
import logging
import sys
from types import SimpleNamespace

from voice.logging_setup import setup_logging

log_path = setup_logging()
log = logging.getLogger("voice.smoke")


class FakeAudioPart:
    def __init__(self, data: bytes):
        self.inline_data = SimpleNamespace(data=data)


def mk_msg(
    audio: bytes | None = None,
    in_text: str | None = None,
    out_text: str | None = None,
    turn_complete: bool = False,
):
    sc = SimpleNamespace(
        model_turn=None,
        interrupted=False,
        turn_complete=turn_complete,
        input_transcription=SimpleNamespace(text=in_text) if in_text else None,
        output_transcription=SimpleNamespace(text=out_text) if out_text else None,
    )
    if audio:
        sc.model_turn = SimpleNamespace(parts=[FakeAudioPart(audio)])
    return SimpleNamespace(
        server_content=sc,
        tool_call=None,
        go_away=None,
        session_resumption_update=None,
    )


class FakeSession:
    """Mimics google.genai Live session's per-turn async iterator."""

    def __init__(self, turns: list[list]):
        self._turns = list(turns)
        self._recv_calls = 0
        self.tool_responses: list = []

    def receive(self):
        self._recv_calls += 1
        if not self._turns:
            async def _empty():
                # Simulate a long-lived empty wait (the real SDK would
                # block until the server has something). We just end
                # immediately so the outer loop can break.
                await asyncio.sleep(0.01)
                return
                yield
            return _empty()
        current = self._turns.pop(0)

        async def _gen():
            for msg in current:
                await asyncio.sleep(0.005)
                yield msg
        return _gen()

    async def send_tool_response(self, function_responses):
        self.tool_responses.append(function_responses)


class FakeMic:
    is_muted = False

    def mute(self):
        self.is_muted = True

    def unmute(self):
        self.is_muted = False


class FakeSpeaker:
    def __init__(self):
        self.written = 0

    async def write(self, data: bytes):
        self.written += len(data)

    def interrupt(self):
        pass


async def main() -> int:
    # Import here so setup_logging() runs before any voice.* logger gets
    # configured to its default handler.
    from voice.live_session import LiveSession

    turns = [
        [
            mk_msg(audio=b"\x00" * 100),
            mk_msg(in_text="turn on bedroom light"),
            mk_msg(out_text="Okay"),
            mk_msg(audio=b"\x00" * 200, turn_complete=True),
        ],
        [
            mk_msg(audio=b"\x00" * 100),
            mk_msg(in_text="and the kitchen"),
            mk_msg(out_text="Done"),
            mk_msg(audio=b"\x00" * 200, turn_complete=True),
        ],
    ]

    session = FakeSession(turns)
    mic = FakeMic()

    ls = LiveSession.__new__(LiveSession)
    ls.mic = mic
    ls.speaker = FakeSpeaker()
    ls.close_event = asyncio.Event()
    ls._last_activity = asyncio.get_event_loop().time()
    ls._started_at = ls._last_activity
    ls._tool_map = {}

    recv = asyncio.create_task(ls._receiver(session))

    # Give the receiver enough time to process both turns.
    for _ in range(50):
        await asyncio.sleep(0.05)
        if session._recv_calls >= 3:
            break

    ls.close_event.set()
    recv.cancel()
    try:
        await recv
    except asyncio.CancelledError:
        pass

    log.info("receive() was called %d times", session._recv_calls)
    log.info("speaker got %d bytes of audio", ls.speaker.written)
    log.info("mic muted at end: %s", mic.is_muted)

    if session._recv_calls >= 2 and ls.speaker.written == 600:
        log.info("PASSED: receiver re-entered session.receive() between turns")
        print("log file:", log_path)
        return 0

    log.error(
        "FAILED: expected >= 2 recv calls and 600 audio bytes, "
        "got recv=%d audio=%d",
        session._recv_calls,
        ls.speaker.written,
    )
    print("log file:", log_path)
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
