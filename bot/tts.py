"""ElevenLabs text-to-speech.

Produces audio for the patient's spoken lines. We request ElevenLabs' native
``ulaw_8000`` output format, which is exactly what Twilio Media Streams expect
(G.711 mulaw, 8kHz, mono) -- so no ffmpeg/pydub transcoding is needed on the hot
path. The raw mulaw is returned for streaming AND handed to the recorder as a
local fallback recording of the patient's voice.
"""

from __future__ import annotations

import asyncio
import os

from elevenlabs.client import ElevenLabs

# Turbo model keeps TTS latency low, which matters for a live phone call.
DEFAULT_MODEL = "eleven_turbo_v2_5"
# Twilio-compatible: G.711 mulaw, 8kHz, mono.
TWILIO_OUTPUT_FORMAT = "ulaw_8000"


class PatientTTS:
    def __init__(
        self,
        api_key: str | None = None,
        voice_id: str | None = None,
        model_id: str = DEFAULT_MODEL,
    ):
        self.client = ElevenLabs(api_key=api_key or os.environ.get("ELEVENLABS_API_KEY"))
        # Voice is chosen per call from the scenario's voice_id (male/female).
        # ELEVENLABS_VOICE_ID in .env is only a fallback default when the
        # scenario omits voice_id; the final literal is a last-resort default.
        self.voice_id = voice_id or os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
        self.model_id = model_id

    def _synthesize_blocking(self, text: str) -> bytes:
        """Blocking ElevenLabs call -> raw mulaw 8kHz bytes."""
        stream = self.client.text_to_speech.convert(
            voice_id=self.voice_id,
            model_id=self.model_id,
            text=text,
            output_format=TWILIO_OUTPUT_FORMAT,
        )
        # The SDK returns an iterator of byte chunks.
        return b"".join(chunk for chunk in stream if chunk)

    async def synthesize(self, text: str) -> bytes:
        """Async wrapper: returns raw mulaw 8kHz audio for ``text``.

        Runs the blocking SDK call in a thread so it doesn't block the event
        loop that's also pumping the Twilio/Deepgram websockets.
        """
        text = (text or "").strip()
        if not text:
            return b""
        try:
            return await asyncio.to_thread(self._synthesize_blocking, text)
        except Exception as exc:  # noqa: BLE001 - keep the call alive on TTS errors
            print(f"⚠️  TTS error: {exc}")
            return b""
