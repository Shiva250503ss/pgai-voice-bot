"""Twilio outbound call initiator.

Places the outbound call to the clinic and attaches a bidirectional Media Stream
pointed at our public websocket URL (via ngrok). Also enables Twilio's built-in
call recording so we get a full-call mp3 of both legs afterward.
"""

from __future__ import annotations

import os

from twilio.rest import Client
from twilio.twiml.voice_response import Connect, VoiceResponse


def build_stream_twiml(public_ws_url: str) -> str:
    """TwiML that connects the call's audio to our websocket, bidirectionally.

    ``<Connect><Stream>`` forks media both ways: we receive the agent's audio
    and can play the patient's synthesized audio back into the call.
    """
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=public_ws_url)
    response.append(connect)
    return str(response)


class TwilioCaller:
    def __init__(
        self,
        account_sid: str | None = None,
        auth_token: str | None = None,
        from_number: str | None = None,
    ):
        self.account_sid = account_sid or os.environ["TWILIO_ACCOUNT_SID"]
        self.auth_token = auth_token or os.environ["TWILIO_AUTH_TOKEN"]
        self.from_number = from_number or os.environ["TWILIO_PHONE_NUMBER"]
        self.client = Client(self.account_sid, self.auth_token)

    def place_call(self, to_number: str, public_ws_url: str) -> str:
        """Start the outbound call. Returns the Twilio Call SID."""
        twiml = build_stream_twiml(public_ws_url)
        call = self.client.calls.create(
            to=to_number,
            from_=self.from_number,
            twiml=twiml,
            record=True,  # full-call recording (both legs) for our outputs/
        )
        return call.sid

    def get_call(self, call_sid: str):
        return self.client.calls(call_sid).fetch()

    def get_recording_url(self, call_sid: str) -> str | None:
        """Return the base recording resource URL for the call, if any.

        Append ``.mp3`` (or ``.wav``) to fetch the media. Returns None if no
        recording is available yet.
        """
        recordings = self.client.recordings.list(call_sid=call_sid, limit=1)
        if not recordings:
            return None
        rec = recordings[0]
        # Public REST media URL for the recording resource.
        return f"https://api.twilio.com{rec.uri.replace('.json', '')}"

    def hang_up(self, call_sid: str) -> None:
        try:
            self.client.calls(call_sid).update(status="completed")
        except Exception:  # noqa: BLE001 - call may already be over
            pass
