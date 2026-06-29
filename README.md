# pgai-voice-bot

An outbound **voice bot** for the Pretty Good AI AI Engineering Challenge. It
phones a clinic line (`+1-805-439-8008`) and plays a realistic **patient** :
scheduling, refills, insurance questions, and deliberately tricky edge cases
to probe how the clinic's AI agent behaves. Audio runs over Twilio Media Streams
with **Deepgram** for real-time speech-to-text, **Claude Haiku 4.5** for the patient
persona, and **ElevenLabs** for natural text-to-speech. Every call is recorded and
transcribed automatically. You run **one scenario at a time**, manually.

## How it works

```
Twilio call  ──mulaw 8k──▶  Deepgram STT  ──▶  Claude (patient persona)
   ▲                                                     │
   └──────────  ElevenLabs TTS (ulaw 8k)  ◀──────────────┘
```

`<Connect><Stream>` forks the call audio to a local FastAPI websocket (exposed via
ngrok). The agent's speech is transcribed, Claude replies in character, and the
reply is spoken back into the call. See [ARCHITECTURE.md](ARCHITECTURE.md).

## Prerequisites

- **Python 3.11+** (3.13 works; `audioop-lts` is pulled in automatically there)
- Accounts/keys for **Twilio** (a voice-capable number), **Deepgram**,
  **Anthropic**, **ElevenLabs**, and a free **ngrok** account
- `ffmpeg` is **not** required — audio stays in mulaw end to end

## Setup

```bash
git clone <repo>
cd pgai-voice-bot
python -m venv venv && source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                # Windows: copy .env.example .env
# Fill in .env with your keys
```

### Verify dependencies installed correctly

```bash
python -c "import twilio, deepgram, anthropic, elevenlabs, pyngrok, fastapi, uvicorn; print('All imports OK')"
```

## Running a single call

```bash
python main.py --scenario 1    # Simple new-patient scheduling
python main.py --scenario 5    # Weekend appointment edge case
python main.py --scenario 8    # Barge-in / interruption test
```

The bot places the call, runs the conversation, then saves outputs and prints a
transcript summary. Press `Ctrl+C` to abort early.

## Outputs

Saved automatically per call, keyed by scenario number:

- Transcripts → `outputs/transcripts/call_NN.txt`
- Recordings  → `outputs/recordings/call_NN.mp3` (full call, both sides, from
  Twilio; falls back to `call_NN_patient.wav` if Twilio's recording isn't ready)

## The 12 scenarios

| #  | Name | What it tests |
|----|------|---------------|
| 1  | Simple new patient scheduling | Baseline: book a first weekday-morning appointment |
| 2  | Reschedule existing appointment | Move a Thu 2pm appointment to Friday |
| 3  | Cancel appointment | Cancel cleanly, no rebooking (resist upsell) |
| 4  | Medication refill request | Refill Lisinopril, pharmacy + timeline |
| 5  | Weekend appointment *(edge)* | Should **reject** Saturday 10am, no hallucinated slot |
| 6  | After-hours scheduling *(edge)* | Should **reject** a 9pm request, state real hours |
| 7  | Insurance question | Aetna, then Blue Cross, then Cigna — one at a time |
| 8  | Barge-in / interruption *(edge)* | Patient cuts agent off; agent should yield gracefully |
| 9  | Angry / frustrated patient *(edge)* | Agent should de-escalate and still complete the task |
| 10 | Mumbled multi-part request *(edge)* | Three asks in one breath: refill + appt + directions |
| 11 | Completely off-topic *(edge)* | Agent should redirect, not follow off-topic / hallucinate |
| 12 | New-patient info stress test *(edge)* | Wrong DOB first, then corrected — does the record update? |

Edge-case scenarios print a **"watch for"** reminder after the call.

## Notes & limits

- One call at a time, always triggered with `--scenario N`; nothing auto-runs.
- A safety cap (`MAX_CALL_SECONDS` in `main.py`, default 360s) ends stuck calls.
- If Deepgram/Twilio drops, the handler logs the error and ends the call cleanly,
  still saving whatever transcript was captured.
