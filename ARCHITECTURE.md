# Architecture

**How it works (technical).** Each run is a single outbound call driven by one
scenario. `main.py` loads the scenario, starts a FastAPI + uvicorn websocket
server, and opens an `ngrok` tunnel so Twilio can reach that server over a public
`wss://` URL. It then places one outbound Twilio call whose TwiML is
`<Connect><Stream>` pointed at our websocket, which forks the call audio
bidirectionally. Twilio streams the clinic agent's voice to us as base64 mulaw
(G.711, 8 kHz, mono); we forward those bytes straight to Deepgram's real-time
Nova-2 model (which ingests mulaw natively). Deepgram's `endpointing` plus
`UtteranceEnd` events tell us when the agent has finished a turn. That utterance
is appended to the conversation history and sent to Claude Haiku 4.5
(`claude-haiku-4-5-20251001`) under the scenario's patient-persona system prompt, which
returns a short, phone-appropriate line. The line is synthesized by ElevenLabs
directly to `ulaw_8000` and streamed back to Twilio in 20 ms frames. If the agent
starts speaking while the patient is talking, Deepgram's interim results trigger a
barge-in: we stop sending frames and send Twilio a `clear` event to flush the
playback buffer. The reverse direction the patient cutting the agent off
mid-utterance — is opt-in per scenario via `"barge_in": true` in
`scenarios.json` (used by the interruption edge case, Scenario 8): when enabled,
the patient starts its turn off the agent's interim transcript once the agent has
said a few words, instead of waiting for `UtteranceEnd`. Scenarios without the
flag are unaffected and behave exactly as before. Twilio's built-in call
recording captures both legs; after the
call ends we download it as an mp3, and the running transcript is written to a
`.txt` both keyed by scenario number under `outputs/`.

**Why these choices.** Websocket streaming (not request/response polling) is what
keeps end-to-end latency low enough to feel like a real phone conversation, and it
makes natural turn-taking and barge-in possible. Deepgram was chosen for its
accurate conversational STT and, crucially, its built-in endpointing/utterance
events, which give reliable end-of-turn detection without us hand-rolling silence
heuristics and it accepts Twilio's mulaw directly, removing a transcode step on
the inbound path. ElevenLabs provides natural, human-sounding TTS and can emit
`ulaw_8000` natively, so the outbound path also needs no ffmpeg transcoding,
reducing latency and Windows dependency pain. Claude Haiku 4.5 gives fast,
consistent, controllable persona behavior so each scenario stays in character and
steers toward its goal while still reacting naturally; its low latency matters on a
live phone call, where a slow reply turns into dead air. Finally, every persona, goal, and
"what to watch" lives in `scenarios.json`, so calls are reproducible, easy to run
one at a time (`python main.py --scenario N`), and simple to extend the code is
generic and the scenario file is the only thing that changes per test.
