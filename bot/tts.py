"""ElevenLabs text-to-speech.

Produces audio for the patient's spoken lines. We request ElevenLabs' native
``ulaw_8000`` output format, which is exactly what Twilio Media Streams expect
(G.711 mulaw, 8kHz, mono) -- so no ffmpeg/pydub transcoding is needed on the hot
path.

synthesize_stream() is the primary path: it runs the blocking ElevenLabs request
in a daemon thread, buffers chunks into a thread-safe stdlib queue, and yields
them to the caller as they arrive. Audio starts playing in ~300-500ms (first
chunk) rather than waiting for the full synthesis (~2s).
"""

from __future__ import annotations

import asyncio
import os
import queue as stdlib_queue
import threading
from collections.abc import AsyncIterator

from elevenlabs.client import ElevenLabs

DEFAULT_MODEL = "eleven_turbo_v2_5"
TWILIO_OUTPUT_FORMAT = "ulaw_8000"

# How often to poll the chunk queue while waiting for the next chunk from
# ElevenLabs. Short enough to not add perceptible latency; long enough that
# the event loop stays free to handle Deepgram/Twilio websocket traffic.
_POLL_INTERVAL = 0.005  # 5ms


class PatientTTS:
    def __init__(
        self,
        api_key: str | None = None,
        voice_id: str | None = None,
        model_id: str = DEFAULT_MODEL,
    ):
        self.client = ElevenLabs(api_key=api_key or os.environ.get("ELEVENLABS_API_KEY"))
        self.voice_id = voice_id or os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
        self.model_id = model_id

    async def synthesize_stream(self, text: str) -> AsyncIterator[bytes]:
        """Async generator: yields mulaw chunks as ElevenLabs produces them.

        A daemon thread drives the blocking ElevenLabs iterator and pushes
        chunks into a thread-safe stdlib queue. The async side polls that queue
        every 5ms, yielding to the event loop between polls so Deepgram and
        Twilio websockets stay responsive.
        """
        text = (text or "").strip()
        if not text:
            return

        chunk_queue: stdlib_queue.Queue = stdlib_queue.Queue()

        def _produce() -> None:
            try:
                stream = self.client.text_to_speech.convert(
                    voice_id=self.voice_id,
                    model_id=self.model_id,
                    text=text,
                    output_format=TWILIO_OUTPUT_FORMAT,
                )
                for chunk in stream:
                    if chunk:
                        chunk_queue.put(chunk)
            except Exception as exc:
                print(f"⚠️  TTS error: {exc}")
            finally:
                chunk_queue.put(None)  # sentinel: producer is done

        threading.Thread(target=_produce, daemon=True).start()

        while True:
            try:
                chunk = chunk_queue.get_nowait()
            except stdlib_queue.Empty:
                await asyncio.sleep(_POLL_INTERVAL)
                continue

            if chunk is None:
                break
            yield chunk
