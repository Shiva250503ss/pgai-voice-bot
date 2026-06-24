"""Pretty Good AI voice bot package.

A patient-simulating outbound voice bot that calls a clinic line and runs a
single scenario per invocation. Pipeline: Twilio Media Streams (mulaw 8kHz) ->
Deepgram STT -> Claude (patient persona) -> ElevenLabs TTS -> back to Twilio.
"""

__all__ = [
    "caller",
    "stream_handler",
    "stt",
    "llm",
    "tts",
    "recorder",
]
