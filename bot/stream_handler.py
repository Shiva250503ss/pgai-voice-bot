"""FastAPI websocket server for Twilio Media Streams + the real-time loop.

One Twilio call == one websocket connection == one StreamHandler. The handler:
  1. Receives Twilio Media Stream events (connected/start/media/stop).
  2. Forwards inbound mulaw audio (the clinic agent's voice) to Deepgram.
  3. On end-of-utterance, asks Claude (patient persona) for the next line.
  4. Synthesizes that line with ElevenLabs and streams it back to Twilio.
  5. Handles barge-in: if the agent starts talking while the patient is
     speaking, playback is stopped and Twilio's buffer is cleared.

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
# If the agent hasn't said anything this long after connect, the patient opens.
OPENING_SILENCE_TIMEOUT = 4.0


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
        self._interrupt = False
        self._turn_lock = asyncio.Lock()
        self._current_turn_task: asyncio.Task | None = None
        self._opening_task: asyncio.Task | None = None

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
        # If the agent stays silent, the patient kicks off the conversation.
        self._opening_task = asyncio.create_task(self._maybe_open())

    async def _on_media(self, msg: dict) -> None:
        payload = msg.get("media", {}).get("payload")
        if not payload:
            return
        audio = base64.b64decode(payload)
        await self.stt.send(audio)

    # ----- conversation logic --------------------------------------------
    async def _maybe_open(self) -> None:
        """Patient speaks first if the agent hasn't greeted in time."""
        try:
            await asyncio.sleep(OPENING_SILENCE_TIMEOUT)
        except asyncio.CancelledError:
            return
        if not self._conversation_started:
            print("🤖 Agent silent; patient opening the conversation.")
            await self._take_turn(agent_text="")

    async def _on_interim(self, _text: str) -> None:
        # Agent is talking. If the patient is mid-sentence, stop and listen.
        if self._speaking:
            await self._barge_in()

    async def _on_utterance(self, text: str) -> None:
        self._conversation_started = True
        if self._opening_task and not self._opening_task.done():
            self._opening_task.cancel()
        print(f"🎤 Agent said: {text}")
        self.session.recorder.add_turn("agent", text)
        await self._take_turn(agent_text=text)

    async def _take_turn(self, agent_text: str) -> None:
        # Cancel any in-flight turn (covers barge-in / overlapping utterances).
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

                audio = await self.session.tts.synthesize(reply)
                if audio:
                    await self._speak(audio)

                # End the call if the patient just said goodbye.
                if self.session.llm.is_goodbye(reply):
                    print("👋 Patient said goodbye; ending call.")
                    await asyncio.sleep(0.5)
                    self.session.completed.set()
        except asyncio.CancelledError:
            pass

    # ----- audio playback (patient -> Twilio) ----------------------------
    async def _speak(self, mulaw_audio: bytes) -> None:
        """Stream mulaw audio back to Twilio in 20ms frames, interruptible."""
        if not self._stream_sid:
            return
        self._speaking = True
        self._interrupt = False
        self.session.recorder.add_patient_audio(mulaw_audio)
        try:
            for i in range(0, len(mulaw_audio), FRAME_BYTES):
                if self._interrupt:
                    break
                frame = mulaw_audio[i : i + FRAME_BYTES]
                await self.ws.send_text(
                    json.dumps(
                        {
                            "event": "media",
                            "streamSid": self._stream_sid,
                            "media": {"payload": base64.b64encode(frame).decode("ascii")},
                        }
                    )
                )
                # Pace slightly under real time so Twilio's buffer stays shallow,
                # which keeps barge-in latency low.
                await asyncio.sleep(FRAME_SECONDS * 0.9)
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
