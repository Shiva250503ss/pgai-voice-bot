"""Deepgram real-time speech-to-text (the clinic agent's voice).

Wraps Deepgram SDK v3's async websocket client. Twilio gives us mulaw 8kHz
audio, which Deepgram can ingest natively (encoding=mulaw, sample_rate=8000) --
no decoding required.

Two callbacks are exposed to the stream handler:
  * on_interim(text): an interim (non-final) transcript arrived. Used to detect
    that the agent has started talking again (barge-in).
  * on_utterance(text): the agent finished an utterance (end of turn). This is
    the cue to generate the patient's reply.
"""

from __future__ import annotations

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


class DeepgramSTT:
    def __init__(
        self,
        on_interim: InterimCb,
        on_utterance: UtteranceCb,
        api_key: str | None = None,
    ):
        api_key = api_key or os.environ.get("DEEPGRAM_API_KEY")
        # keepalive avoids Deepgram closing the socket during silent stretches.
        config = DeepgramClientOptions(options={"keepalive": "true"})
        self._client = DeepgramClient(api_key, config)
        self._conn = None

        self._on_interim = on_interim
        self._on_utterance = on_utterance

        # Buffer of finalized fragments not yet flushed as a full utterance.
        self._final_parts: list[str] = []

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
            # endpointing: ms of silence before a result is marked speech_final.
            endpointing=300,
            # utterance_end fires after this much silence -> hard end-of-turn.
            utterance_end_ms=1000,
            vad_events=True,
        )

        if not await self._conn.start(options):
            raise RuntimeError("Failed to start Deepgram connection")

    async def send(self, mulaw_audio: bytes) -> None:
        if self._conn is not None:
            await self._conn.send(mulaw_audio)

    async def finish(self) -> None:
        if self._conn is not None:
            try:
                await self._conn.finish()
            except Exception:  # noqa: BLE001 - shutdown best-effort
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
            self._final_parts.append(text)
            # speech_final: Deepgram is confident the speaker paused/finished.
            if getattr(result, "speech_final", False):
                await self._flush()
        else:
            # Interim words -> the agent is currently speaking (barge-in signal).
            await self._on_interim(text)

    async def _handle_utterance_end(self, _client, *_args, **_kwargs) -> None:
        # The Deepgram SDK delivers the UtteranceEnd payload as a keyword arg
        # (named `utterance_end`, NOT `result`), so we must not declare a
        # required positional `_result` -- doing so raised "missing 1 required
        # positional argument: '_result'". We accept *_args/**_kwargs and ignore
        # the payload, since all we need to do is flush the buffered finals when
        # the silence threshold (utterance_end_ms) is crossed.
        await self._flush()

    async def _handle_error(self, _client, error, **_kwargs) -> None:
        print(f"⚠️  Deepgram error: {error}")

    async def _flush(self) -> None:
        if not self._final_parts:
            return
        utterance = " ".join(self._final_parts).strip()
        self._final_parts = []
        if utterance:
            await self._on_utterance(utterance)
