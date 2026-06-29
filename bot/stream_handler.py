"""FastAPI websocket server for Twilio Media Streams + the real-time loop.

One Twilio call == one websocket connection == one StreamHandler. The handler:
  1. Receives Twilio Media Stream events (connected/start/media/stop).
  2. Forwards inbound mulaw audio (the clinic agent's voice) to Deepgram.
  3. On end-of-utterance, asks Claude (patient persona) for the next line.
  4. Streams that line through ElevenLabs and plays it back to Twilio in
     real-time as chunks arrive, so audio starts ~300-500ms after the LLM
     responds instead of waiting for the full synthesis.
  5. Handles barge-in: if the agent starts talking while the patient is
     speaking (and the patient has been speaking for at least
     BARGE_IN_MIN_SPEAK_SECONDS), playback is stopped and Twilio's buffer
     is cleared.

main.py creates a CallSession, registers it on app.state, then places the call.
The handler picks up that session when Twilio connects.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from dataclasses import dataclass, field

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from .llm import PatientLLM
from .recorder import CallRecorder
from .stt import DeepgramSTT
from .tts import PatientTTS

# 20ms of mulaw 8kHz audio = 160 bytes. We stream back in these frames.
FRAME_BYTES = 160
FRAME_SECONDS = 0.02

# How long to wait for the clinic agent to speak before the patient opens.
# Long enough to clear IVR connection delay without making the call feel dead.
OPENING_SILENCE_TIMEOUT = 20.0

# Minimum time the patient must have been speaking before the clinic agent
# can trigger a barge-in. Prevents the agent's first word from cutting off
# the patient mid-sentence.
BARGE_IN_MIN_SPEAK_SECONDS = 2.0

# Patient-initiated barge-in: how many words the clinic agent must have spoken
# in its current utterance before an impatient patient cuts in. Only used when a
# scenario opts in via scenario["barge_in"] (e.g. the interruption edge case);
# all other scenarios leave patient barge-in disabled and are unaffected.
INTERRUPT_MIN_AGENT_WORDS = 6


@dataclass
class CallSession:
    """Shared state for a single call, created by main.py."""

    scenario: dict
    recorder: CallRecorder
    llm: PatientLLM
    tts: PatientTTS

    call_sid: str | None = None
    stream_sid: str | None = None
    completed: asyncio.Event = field(default_factory=asyncio.Event)
    turn_count: int = 0


class StreamHandler:
    def __init__(self, websocket: WebSocket, session: CallSession):
        self.ws = websocket
        self.session = session
        self.scenario = session.scenario

        self.stt = DeepgramSTT(on_interim=self._on_interim, on_utterance=self._on_utterance)

        self._stream_sid: str | None = None
        self._conversation_started = False
        self._speaking = False
        self._speaking_since: float = 0.0
        self._interrupt = False
        self._turn_lock = asyncio.Lock()
        self._current_turn_task: asyncio.Task | None = None
        self._opening_task: asyncio.Task | None = None

        # Patient-initiated barge-in is opt-in per scenario so it cannot affect
        # any other call. When enabled, the patient cuts the agent off mid-turn
        # instead of waiting for the agent to finish speaking.
        self._interrupt_mode = bool(self.scenario.get("barge_in"))
        # True once the patient has already barged in over the agent's current
        # utterance, so we don't reply twice for the same agent turn.
        self._interrupted_current = False

    # ----- main receive loop ---------------------------------------------
    async def run(self) -> None:
        await self.ws.accept()
        await self.stt.start()
        print("🔌 Twilio media stream connected.")

        try:
            async for raw in self.ws.iter_text():
                msg = json.loads(raw)
                event = msg.get("event")
                if event == "start":
                    await self._on_start(msg)
                elif event == "media":
                    await self._on_media(msg)
                elif event == "stop":
                    print("⏹️  Twilio sent stop event.")
                    break
        except WebSocketDisconnect:
            print("🔌 Twilio websocket disconnected.")
        except Exception as exc:  # noqa: BLE001 - end the call cleanly on any error
            print(f"⚠️  Stream handler error: {exc}")
        finally:
            await self._shutdown()

    async def _on_start(self, msg: dict) -> None:
        start = msg.get("start", {})
        self._stream_sid = start.get("streamSid") or msg.get("streamSid")
        self.session.stream_sid = self._stream_sid
        self.session.call_sid = start.get("callSid", self.session.call_sid)
        print(f"📞 Stream started (streamSid={self._stream_sid}).")
        self._opening_task = asyncio.create_task(self._maybe_open())

    async def _on_media(self, msg: dict) -> None:
        payload = msg.get("media", {}).get("payload")
        if not payload:
            return
        audio = base64.b64decode(payload)
        await self.stt.send(audio)

    # ----- conversation logic --------------------------------------------
    async def _maybe_open(self) -> None:
        """Patient speaks first if the clinic agent hasn't greeted in time."""
        try:
            await asyncio.sleep(OPENING_SILENCE_TIMEOUT)
        except asyncio.CancelledError:
            return
        if not self._conversation_started:
            print("🤖 Agent silent; patient opening the conversation.")
            await self._take_turn(agent_text="")

    async def _on_interim(self, text: str) -> None:
        # Agent interrupts patient (all scenarios): if the agent starts talking
        # while the patient is mid-sentence, stop the patient -- but only after
        # the patient has been speaking long enough that the agent's first word
        # doesn't cut them off.
        if self._speaking:
            if (time.time() - self._speaking_since) >= BARGE_IN_MIN_SPEAK_SECONDS:
                await self._barge_in()
            return

        # Patient interrupts agent (opt-in scenarios only): an impatient patient
        # cuts in once the agent has said enough words, instead of waiting for
        # the agent to finish. Gated on self._interrupt_mode so no other call is
        # affected.
        await self._maybe_patient_interrupt(text)

    async def _maybe_patient_interrupt(self, text: str) -> None:
        if not self._interrupt_mode or self._interrupted_current:
            return
        # Don't interrupt before the call is underway, during the legal
        # disclaimer, or while a patient turn is already in flight.
        if not self._conversation_started or self._is_disclaimer(text):
            return
        if self._current_turn_task and not self._current_turn_task.done():
            return
        if len((text or "").split()) < INTERRUPT_MIN_AGENT_WORDS:
            return
        self._interrupted_current = True
        print(f"🗣️  Patient barging in over agent: {text}")
        self.session.recorder.add_turn("agent", text)
        await self._take_turn(agent_text=text)

    # Phrases that indicate a system/legal disclaimer, not a conversational turn.
    _DISCLAIMER_PHRASES = (
        "may be recorded",
        "recorded for quality",
        "recorded for training",
        "quality and training",
        "quality assurance",
        "monitoring purposes",
    )

    def _is_disclaimer(self, text: str) -> bool:
        lowered = text.lower()
        return any(phrase in lowered for phrase in self._DISCLAIMER_PHRASES)

    async def _on_utterance(self, text: str) -> None:
        if self._is_disclaimer(text):
            print(f"🔇 Disclaimer (no reply): {text}")
            self.session.recorder.add_turn("agent", text)
            # Clinic is live — cancel self-open timer, but don't reply yet.
            self._conversation_started = True
            if self._opening_task and not self._opening_task.done():
                self._opening_task.cancel()
            return
        self._conversation_started = True
        if self._opening_task and not self._opening_task.done():
            self._opening_task.cancel()
        # If the patient already barged in over this agent utterance, the patient
        # has effectively replied already. Note that the agent's turn finished
        # and reset for the next one instead of generating a second reply.
        if self._interrupted_current:
            print(f"🎤 Agent finished (already interrupted): {text}")
            self._interrupted_current = False
            return
        print(f"🎤 Agent said: {text}")
        self.session.recorder.add_turn("agent", text)
        await self._take_turn(agent_text=text)

    async def _take_turn(self, agent_text: str) -> None:
        # Cancel any in-flight turn (barge-in / overlapping utterances).
        if self._current_turn_task and not self._current_turn_task.done():
            self._current_turn_task.cancel()
        self._conversation_started = True
        self._current_turn_task = asyncio.create_task(self._handle_turn(agent_text))

    async def _handle_turn(self, agent_text: str) -> None:
        try:
            async with self._turn_lock:
                self.session.turn_count += 1
                reply = await self.session.llm.respond_to(agent_text)
                if not reply:
                    return
                print(f"🤖 Patient responding: {reply}")
                self.session.recorder.add_turn("patient", reply)

                # Stream TTS: audio starts playing as first chunk arrives (~300ms)
                # rather than waiting for the full synthesis to complete (~2s).
                await self._speak_stream(self.session.tts.synthesize_stream(reply))

                if self.session.llm.is_goodbye(reply):
                    print("👋 Patient said goodbye; ending call.")
                    await asyncio.sleep(0.5)
                    self.session.completed.set()
        except asyncio.CancelledError:
            pass

    # ----- audio playback (patient -> Twilio) ----------------------------
    async def _speak_stream(self, audio_stream) -> None:
        """Play mulaw audio from an async generator, interruptible, frame-by-frame.

        Chunks from ElevenLabs are buffered and emitted as 160-byte Twilio
        media frames paced at real-time (18ms sleep per frame to keep Twilio's
        buffer shallow for low barge-in latency).
        """
        if not self._stream_sid:
            # Drain the generator so the producer thread can exit cleanly.
            async for _ in audio_stream:
                pass
            return

        self._speaking = True
        self._speaking_since = time.time()
        self._interrupt = False
        buf = bytearray()

        try:
            async for chunk in audio_stream:
                if self._interrupt:
                    break
                self.session.recorder.add_patient_audio(chunk)
                buf.extend(chunk)

                # Emit all complete 160-byte frames from the buffer.
                while len(buf) >= FRAME_BYTES:
                    if self._interrupt:
                        break
                    frame = bytes(buf[:FRAME_BYTES])
                    del buf[:FRAME_BYTES]
                    try:
                        await self.ws.send_text(
                            json.dumps(
                                {
                                    "event": "media",
                                    "streamSid": self._stream_sid,
                                    "media": {"payload": base64.b64encode(frame).decode("ascii")},
                                }
                            )
                        )
                    except Exception:
                        self._interrupt = True
                        return
                    await asyncio.sleep(FRAME_SECONDS * 0.9)

            # Flush any remaining bytes as a zero-padded final frame.
            if buf and not self._interrupt:
                frame = bytes(buf) + b"\x7f" * (FRAME_BYTES - len(buf))
                try:
                    await self.ws.send_text(
                        json.dumps(
                            {
                                "event": "media",
                                "streamSid": self._stream_sid,
                                "media": {"payload": base64.b64encode(frame).decode("ascii")},
                            }
                        )
                    )
                except Exception:
                    self._interrupt = True
        finally:
            self._speaking = False

    async def _barge_in(self) -> None:
        """Stop the patient mid-sentence and flush Twilio's playback buffer."""
        self._interrupt = True
        if self._stream_sid:
            try:
                await self.ws.send_text(
                    json.dumps({"event": "clear", "streamSid": self._stream_sid})
                )
                print("✋ Barge-in: cleared patient playback.")
            except Exception:  # noqa: BLE001
                pass

    # ----- shutdown -------------------------------------------------------
    async def _shutdown(self) -> None:
        self._interrupt = True
        if self._opening_task and not self._opening_task.done():
            self._opening_task.cancel()
        if self._current_turn_task and not self._current_turn_task.done():
            self._current_turn_task.cancel()
        await self.stt.finish()
        self.session.completed.set()


def create_app(get_session) -> FastAPI:
    """Build the FastAPI app. ``get_session`` returns the active CallSession."""
    app = FastAPI()

    @app.get("/health")
    async def health():  # noqa: D401 - simple healthcheck
        return {"status": "ok", "time": time.time()}

    @app.websocket("/ws")
    async def media_stream(websocket: WebSocket):
        session = get_session()
        if session is None:
            await websocket.close(code=1011)
            return
        handler = StreamHandler(websocket, session)
        await handler.run()

    return app
