"""Deepgram real-time speech-to-text (the clinic agent's voice).

Wraps Deepgram SDK v3's async websocket client. Twilio gives us mulaw 8kHz
audio, which Deepgram can ingest natively (encoding=mulaw, sample_rate=8000) --
no decoding required.

Two callbacks are exposed to the stream handler:
  * on_interim(text): an interim (non-final) transcript arrived. Used to detect
    that the agent has started talking again (barge-in).
  * on_utterance(text): the agent finished a complete utterance. This is the
    cue to generate the patient's reply.

Turn-boundary detection strategy
---------------------------------
We wait until Deepgram fires UtteranceEnd — meaning the agent's audio has been
*completely silent* for UTTERANCE_END_SILENCE_MS milliseconds — before
triggering the patient's reply. This avoids any mid-sentence interruptions:
no matter how many natural pauses the agent takes within a sentence, we
never respond until their voice is gone for the configured silence window.

speech_final events are used only to accumulate transcript text; they never
trigger a flush on their own. Interim results cancel any pending flush so that
even a race between speech_final and the agent resuming speech is handled
correctly.
"""

from __future__ import annotations

import asyncio
import os
from typing import Awaitable, Callable

from deepgram import (
    DeepgramClient,
    DeepgramClientOptions,
    LiveOptions,
    LiveTranscriptionEvents,
)

InterimCb = Callable[[str], Awaitable[None]]
UtteranceCb = Callable[[str], Awaitable[None]]

# How long the agent must be silent (ms) before we treat their turn as done.
# Deepgram measures this from the last detected word, so it's a true voice-gap
# check — not a wall-clock timer.
UTTERANCE_END_SILENCE_MS = 1500


class DeepgramSTT:
    def __init__(
        self,
        on_interim: InterimCb,
        on_utterance: UtteranceCb,
        api_key: str | None = None,
    ):
        api_key = api_key or os.environ.get("DEEPGRAM_API_KEY")
        config = DeepgramClientOptions(options={"keepalive": "true"})
        self._client = DeepgramClient(api_key, config)
        self._conn = None

        self._on_interim = on_interim
        self._on_utterance = on_utterance

        # Accumulates final transcript fragments within one utterance.
        self._final_parts: list[str] = []
        # Task used to defer the flush until we're sure no new audio is coming.
        self._flush_task: asyncio.Task | None = None

    async def start(self) -> None:
        self._conn = self._client.listen.asyncwebsocket.v("1")

        self._conn.on(LiveTranscriptionEvents.Transcript, self._handle_transcript)
        self._conn.on(LiveTranscriptionEvents.UtteranceEnd, self._handle_utterance_end)
        self._conn.on(LiveTranscriptionEvents.Error, self._handle_error)

        options = LiveOptions(
            model="nova-2",
            language="en-US",
            encoding="mulaw",
            sample_rate=8000,
            channels=1,
            interim_results=True,
            smart_format=True,
            punctuate=True,
            # endpointing: ms of silence before Deepgram marks a result as
            # speech_final. We only use speech_final to accumulate text, not to
            # trigger a reply, so a moderate value is fine.
            endpointing=500,
            # utterance_end_ms: ms of silence (after the last word) before
            # Deepgram fires UtteranceEnd. THIS is what triggers our reply.
            utterance_end_ms=UTTERANCE_END_SILENCE_MS,
            vad_events=True,
        )

        if not await self._conn.start(options):
            raise RuntimeError("Failed to start Deepgram connection")

    async def send(self, mulaw_audio: bytes) -> None:
        if self._conn is not None:
            await self._conn.send(mulaw_audio)

    async def finish(self) -> None:
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
        if self._conn is not None:
            try:
                await self._conn.finish()
            except Exception:
                pass
            self._conn = None

    # ----- Deepgram event handlers ---------------------------------------

    async def _handle_transcript(self, _client, result, **_kwargs) -> None:
        try:
            alt = result.channel.alternatives[0]
        except (AttributeError, IndexError):
            return
        text = (alt.transcript or "").strip()
        if not text:
            return

        if result.is_final:
            # Accumulate text. We do NOT flush here — we wait for UtteranceEnd.
            self._final_parts.append(text)
        else:
            # Interim result: agent is still actively speaking.
            # Cancel any pending flush so we never respond mid-sentence.
            if self._flush_task and not self._flush_task.done():
                self._flush_task.cancel()
                self._flush_task = None
            await self._on_interim(text)

    async def _handle_utterance_end(self, _client, *_args, **_kwargs) -> None:
        # Agent has been silent for UTTERANCE_END_SILENCE_MS — their turn is done.
        # Flush immediately; Deepgram already waited the silence window for us.
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
        self._flush_task = asyncio.create_task(self._do_flush())

    async def _handle_error(self, _client, error, **_kwargs) -> None:
        print(f"⚠️  Deepgram error: {error}")

    async def _do_flush(self) -> None:
        if not self._final_parts:
            return
        utterance = " ".join(self._final_parts).strip()
        self._final_parts = []
        if utterance:
            await self._on_utterance(utterance)
