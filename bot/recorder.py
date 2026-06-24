"""Per-call recording: transcript accumulation + audio file persistence.

A CallRecorder holds the running transcript for one call (a list of turns) and
knows how to write a human-readable .txt transcript at the end of the call.

Full-call audio (both the clinic agent and our synthesized patient) is captured
via Twilio's built-in call recording and downloaded by main.py after the call
completes -- see ``save_twilio_recording``. As a fallback (e.g. if the Twilio
recording is unavailable), we also keep the raw mulaw bytes of the patient's
own speech that we streamed out, and can write those to a WAV file.
"""

from __future__ import annotations

import audioop
import os
import time
import wave
from dataclasses import dataclass, field
from datetime import datetime

import httpx


@dataclass
class TranscriptTurn:
    speaker: str  # "agent" or "patient"
    text: str
    timestamp: float  # epoch seconds


@dataclass
class CallRecorder:
    scenario_id: int
    scenario_name: str
    transcripts_dir: str
    recordings_dir: str

    turns: list[TranscriptTurn] = field(default_factory=list)
    # Raw outbound patient audio (mulaw 8kHz) kept as a local fallback recording.
    _patient_mulaw: bytearray = field(default_factory=bytearray)
    started_at: float = field(default_factory=time.time)

    # ----- transcript -----------------------------------------------------
    def add_turn(self, speaker: str, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self.turns.append(TranscriptTurn(speaker=speaker, text=text, timestamp=time.time()))

    def add_patient_audio(self, mulaw_bytes: bytes) -> None:
        """Accumulate outbound patient audio for the fallback WAV recording."""
        self._patient_mulaw.extend(mulaw_bytes)

    @property
    def call_tag(self) -> str:
        return f"call_{self.scenario_id:02d}"

    # ----- persistence ----------------------------------------------------
    def save_transcript(self) -> str:
        os.makedirs(self.transcripts_dir, exist_ok=True)
        path = os.path.join(self.transcripts_dir, f"{self.call_tag}.txt")

        started = datetime.fromtimestamp(self.started_at)
        ended = datetime.now()
        duration = max(0.0, ended.timestamp() - self.started_at)

        lines = [
            "=" * 70,
            f"CALL TRANSCRIPT - Scenario {self.scenario_id}: {self.scenario_name}",
            "=" * 70,
            f"Started:  {started:%Y-%m-%d %H:%M:%S}",
            f"Ended:    {ended:%Y-%m-%d %H:%M:%S}",
            f"Duration: {duration:0.1f}s",
            f"Turns:    {len(self.turns)}",
            "=" * 70,
            "",
        ]

        for turn in self.turns:
            ts = datetime.fromtimestamp(turn.timestamp)
            label = "AGENT (clinic)" if turn.speaker == "agent" else "PATIENT (bot)"
            lines.append(f"[{ts:%H:%M:%S}] {label}:")
            lines.append(f"    {turn.text}")
            lines.append("")

        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines))

        return path

    def save_patient_wav_fallback(self) -> str | None:
        """Write the patient's outbound audio to a WAV file (no ffmpeg needed).

        Used only when the Twilio call recording isn't available. Returns the
        path written, or None if there was no audio.
        """
        if not self._patient_mulaw:
            return None
        os.makedirs(self.recordings_dir, exist_ok=True)
        path = os.path.join(self.recordings_dir, f"{self.call_tag}_patient.wav")

        # mulaw (G.711) -> 16-bit linear PCM, 8kHz mono.
        pcm16 = audioop.ulaw2lin(bytes(self._patient_mulaw), 2)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            wf.writeframes(pcm16)
        return path

    def save_twilio_recording(
        self,
        recording_url: str,
        account_sid: str,
        auth_token: str,
        suffix: str = "mp3",
    ) -> str | None:
        """Download Twilio's full-call recording (both legs) as mp3.

        ``recording_url`` is the Twilio recording resource URL (without the file
        extension). Returns the local path written, or None on failure.
        """
        os.makedirs(self.recordings_dir, exist_ok=True)
        path = os.path.join(self.recordings_dir, f"{self.call_tag}.{suffix}")
        media_url = f"{recording_url}.{suffix}"
        try:
            with httpx.Client(timeout=60.0) as client:
                resp = client.get(media_url, auth=(account_sid, auth_token))
                resp.raise_for_status()
                with open(path, "wb") as fh:
                    fh.write(resp.content)
            return path
        except Exception as exc:  # noqa: BLE001 - best-effort download
            print(f"⚠️  Could not download Twilio recording: {exc}")
            return None
