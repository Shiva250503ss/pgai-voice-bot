"""Pretty Good AI voice bot - single-call entry point.

Usage:
    python main.py --scenario 1

Loads one scenario, spins up the websocket server + ngrok tunnel, places a single
outbound Twilio call that simulates that patient, waits for the call to finish,
then saves the transcript and recording to outputs/.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from bot.caller import TwilioCaller
from bot.llm import PatientLLM
from bot.recorder import CallRecorder
from bot.stream_handler import CallSession, create_app
from bot.tts import PatientTTS

ROOT = Path(__file__).resolve().parent
SCENARIOS_PATH = ROOT / "scenarios" / "scenarios.json"
TRANSCRIPTS_DIR = ROOT / "outputs" / "transcripts"
RECORDINGS_DIR = ROOT / "outputs" / "recordings"

# Safety cap so a stuck call can't run forever.
MAX_CALL_SECONDS = 360
# How long to keep polling Twilio for the finalized recording after hang-up.
RECORDING_POLL_ATTEMPTS = 10
RECORDING_POLL_INTERVAL = 3.0

REQUIRED_ENV = [
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_PHONE_NUMBER",
    "DEEPGRAM_API_KEY",
    "ANTHROPIC_API_KEY",
    "ELEVENLABS_API_KEY",
    "TARGET_PHONE_NUMBER",
]


def load_scenario(scenario_id: int) -> dict:
    with open(SCENARIOS_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    # The scenarios file stores the list under the "scenarios" key (not
    # "scenario_list"). Using the correct key avoids a KeyError at load time.
    for scenario in data["scenarios"]:
        if scenario["id"] == scenario_id:
            return scenario
    raise SystemExit(f"❌ Scenario {scenario_id} not found in {SCENARIOS_PATH}")


def check_env() -> None:
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        raise SystemExit(
            "❌ Missing required environment variables: "
            + ", ".join(missing)
            + "\n   Copy .env.example to .env and fill in your keys."
        )


def start_ngrok(port: int) -> str:
    """Open an ngrok tunnel to the local port; return the public https URL."""
    from pyngrok import conf, ngrok

    authtoken = os.environ.get("NGROK_AUTHTOKEN")
    if authtoken:
        conf.get_default().auth_token = authtoken
    tunnel = ngrok.connect(port, "http")
    return tunnel.public_url  # e.g. https://abcd-1234.ngrok-free.app


async def wait_for_recording(caller: TwilioCaller, call_sid: str):
    for _ in range(RECORDING_POLL_ATTEMPTS):
        url = await asyncio.to_thread(caller.get_recording_url, call_sid)
        if url:
            return url
        await asyncio.sleep(RECORDING_POLL_INTERVAL)
    return None


async def run_call(scenario: dict) -> None:
    port = int(os.environ.get("PORT", "8000"))
    target = os.environ["TARGET_PHONE_NUMBER"]

    # --- assemble the per-call session -----------------------------------
    recorder = CallRecorder(
        scenario_id=scenario["id"],
        scenario_name=scenario["name"],
        transcripts_dir=str(TRANSCRIPTS_DIR),
        recordings_dir=str(RECORDINGS_DIR),
    )
    session = CallSession(
        scenario=scenario,
        recorder=recorder,
        llm=PatientLLM(system_prompt=scenario["system_prompt"]),
        # Per-scenario voice (male/female). Falls back to ELEVENLABS_VOICE_ID
        # inside PatientTTS if the scenario omits voice_id.
        tts=PatientTTS(voice_id=scenario.get("voice_id")),
    )

    app = create_app(lambda: session)

    import uvicorn

    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)
    server_task = asyncio.create_task(server.serve())

    # Wait until uvicorn is actually listening.
    while not server.started:
        await asyncio.sleep(0.1)

    caller = TwilioCaller()
    public_url = None
    try:
        public_url = await asyncio.to_thread(start_ngrok, port)
        ws_url = public_url.replace("https://", "wss://").replace("http://", "ws://") + "/ws"
        print(f"🌐 Public tunnel: {public_url}")
        print(f"🔗 Stream URL:    {ws_url}")

        print(
            f"\n📞 Calling {target} with Scenario {scenario['id']}: {scenario['name']}"
        )
        print(f"   Persona: {scenario['persona']}")
        print(f"   Goal:    {scenario['goal']}\n")

        call_sid = await asyncio.to_thread(caller.place_call, target, ws_url)
        session.call_sid = call_sid
        print(f"☎️  Call placed (SID={call_sid}). Waiting for conversation...\n")

        try:
            await asyncio.wait_for(session.completed.wait(), timeout=MAX_CALL_SECONDS)
        except asyncio.TimeoutError:
            print(f"⏰ Reached max call duration ({MAX_CALL_SECONDS}s); ending call.")

        await asyncio.to_thread(caller.hang_up, call_sid)

        # --- persist outputs ---------------------------------------------
        transcript_path = recorder.save_transcript()
        print(f"\n📝 Transcript saved: {transcript_path}")

        print("⏳ Fetching call recording from Twilio...")
        rec_url = await wait_for_recording(caller, call_sid)
        if rec_url:
            path = await asyncio.to_thread(
                recorder.save_twilio_recording,
                rec_url,
                caller.account_sid,
                caller.auth_token,
            )
            if path:
                print(f"🎧 Recording saved:  {path}")
        else:
            fallback = recorder.save_patient_wav_fallback()
            if fallback:
                print(f"🎧 Twilio recording unavailable; saved patient audio: {fallback}")
            else:
                print("⚠️  No recording available for this call.")

        print_summary(recorder, scenario)
        print(f"\n✅ Call complete. Saved to outputs/{recorder.call_tag}.*")

    finally:
        if public_url is not None:
            try:
                from pyngrok import ngrok

                ngrok.disconnect(public_url)
                ngrok.kill()
            except Exception:  # noqa: BLE001
                pass
        server.should_exit = True
        await server_task


def print_summary(recorder: CallRecorder, scenario: dict) -> None:
    print("\n" + "=" * 60)
    print(f"CONVERSATION SUMMARY - Scenario {scenario['id']}: {scenario['name']}")
    print("=" * 60)
    for turn in recorder.turns:
        label = "AGENT  " if turn.speaker == "agent" else "PATIENT"
        print(f"{label}: {turn.text}")
    print("=" * 60)
    if scenario.get("edge_case"):
        print(f"🔍 EDGE CASE - watch for: {scenario['what_to_watch']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Pretty Good AI patient voice bot")
    parser.add_argument(
        "--scenario",
        type=int,
        required=True,
        help="Scenario id to run (1-12). See scenarios/scenarios.json.",
    )
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    check_env()

    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)

    scenario = load_scenario(args.scenario)

    try:
        asyncio.run(run_call(scenario))
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user.")
        sys.exit(130)


if __name__ == "__main__":
    main()
