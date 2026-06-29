# Bug Report — Clinic Agent (target: +1-805-439-8008)

Findings from running the patient-simulation scenarios. Add one entry per issue
as you review each call's transcript and recording.

## Template

### [Scenario N] Short title
- **Severity:** low / medium / high
- **Call:** `outputs/transcripts/call_NN.txt` · `outputs/recordings/call_NN.mp3`
- **Expected:** what a correct agent should have done
- **Actual:** what the agent actually did
- **Repro / quote:** the exact line(s) from the transcript showing the bug
- **Notes:** latency, talk-over, hallucination, data handling, etc.

---

## Findings

### [All scenarios] Agent talks over the patient — does not wait for the patient to finish speaking
- **Severity:** high
- **Call:** Observed across calls; clearest in `outputs/transcripts/call_01.txt` and `outputs/transcripts/call_06.txt` (and audible in the matching `.mp3` recordings).
- **Expected:** The agent should wait for the patient to finish their utterance (proper end-of-speech / endpoint detection) before responding, and should not start its own turn while the patient is still talking.
- **Actual:** The agent repeatedly begins its response before the patient has finished, cutting off the end of the patient's sentence. During live runs the harness logged `Barge-in: cleared patient playback` multiple times per call — that event only fires when the clinic agent starts speaking while the patient is still mid-utterance, so the agent is interrupting, not the other way around.
- **Repro / quote:** In Scenario 6, the patient's turns and the agent's replies are timestamped ~1 second apart on long patient turns (e.g., PATIENT 20:59:43 → AGENT 20:59:55 "Great, Kev." while the patient was still mid-thought, with the patient continuing at 20:59:56). Scenario 1's re-run logged several `Barge-in: cleared patient playback` events at the same overlap points.
- **Notes:** Likely premature endpointing / no wait for end-of-speech. Impact is systemic: it truncates patient information (names, dates, callback numbers, the actual request), forces repetition, and makes the conversation feel like it is being talked over. Affects every scenario, not just the two cited.

---

### [All scenarios] Pre-seeded demo appointment blocks new bookings and dead-ends into a transfer/hang-up
- **Severity:** high
- **Call:** Reproduced in `call_01.txt`, `call_06.txt`, `call_08.txt`, `call_10.txt`, and `call_12.txt` (and their `.mp3` recordings).
- **Expected:** A new-patient or new-appointment request should end in a booked, confirmed slot. If a matching appointment already exists, the agent should be able to read back its date/time or reschedule it in-line.
- **Actual:** Every demo profile already contains an appointment of the exact type the patient is trying to book. The agent then (a) refuses to create a "duplicate," (b) says it "can't access" or "can't update" the existing appointment, and (c) offers to transfer to a "team member" — which routes to a recording that says "You've reached the Pretty Good AI test line. Goodbye." and drops the call with nothing accomplished.
- **Repro / quote:** AGENT (call_10, 21:49:29): "I can't reschedule appointments directly, but I can connect you with a team member..." → AGENT (21:50:19): "Hello. You've reached the Pretty Good AI test line. Goodbye."
- **Notes:** Highest-impact issue found — it prevents the core task (booking) from completing in most scheduling scenarios and ends the call abruptly. Scenarios 2, 3, and 9 avoid it only because they act on the pre-existing appointment (reschedule/cancel/keep) instead of creating a new one.

---

### [Scenario 1] Wrong specialty not flagged
- **Severity:** high
- **Call:** `outputs/transcripts/call_01.txt` · `outputs/recordings/call_01.mp3`
- **Expected:** Agent should clarify it is an orthopedic clinic (not primary care) and ask if the patient still wants to proceed.
- **Actual:** Athena (Pivot Point Orthopedics) never clarified the practice specialty and scheduled the appointment anyway.
- **Repro / quote:** Patient: "I'm hoping to get set up as a new patient with a primary care doctor — is this something y'all can help me with?" — Agent proceeds without correction.
- **Notes:** Occurs at ~0:10 into the call.

---

### [Scenario 1] Fake date of birth assigned without asking
- **Severity:** low
- **Call:** `outputs/transcripts/call_01.txt` · `outputs/recordings/call_01.mp3`
- **Expected:** Agent should ask the patient for their date of birth before creating a profile.
- **Actual:** Athena assigned DOB 07/04/2000 automatically without ever asking the patient.
- **Repro / quote:** No DOB question appears anywhere in the transcript; profile created with fabricated value.
- **Notes:** Occurs at ~1:48. Data integrity risk — patient record contains hallucinated PII.

---

### [Scenario 1] Re-asked for booking confirmation after patient already confirmed
- **Severity:** low
- **Call:** `outputs/transcripts/call_01.txt` · `outputs/recordings/call_01.mp3`
- **Expected:** After the first "yes" from the patient, agent should proceed to booking without asking again.
- **Actual:** Patient confirmed twice, then Athena asked "Would you like to book one of these?" a third time.
- **Repro / quote:** Patient says yes → Agent re-asks "Would you like to book one of these?" at ~1:44.
- **Notes:** Minor UX friction; creates unnecessary conversational loops.

---

### [Scenario 2] Demo profile created for self-identified existing patient
- **Severity:** high
- **Call:** `outputs/transcripts/call_02.txt` · `outputs/recordings/call_02.mp3`
- **Expected:** Agent should look up the existing patient by name rather than creating a new demo profile.
- **Actual:** Agent offered to create a demo profile; patient declined and said they were an existing patient; agent created the profile anyway.
- **Repro / quote:** Patient: "no thanks, I'm actually an existing patient" → Agent: "Your patient profile is set up and your date of birth is 07/04/2000 for demo purposes."
- **Notes:** Same fake-DOB issue as Scenario 1. Creates a duplicate/phantom record for a real patient.

---

### [Scenario 2] Fake date of birth assigned without asking
- **Severity:** low
- **Call:** `outputs/transcripts/call_02.txt` · `outputs/recordings/call_02.mp3`
- **Expected:** Agent should ask the patient for their date of birth (or look it up from the existing record) before creating or confirming a profile.
- **Actual:** Agent assigned DOB 07/04/2000 automatically without asking — same hallucinated value as Scenario 1.
- **Repro / quote:** AGENT: "Your patient profile is set up and your date of birth is 07/04/2000 for demo purposes."
- **Notes:** Recurring data integrity risk; the agent appears to hardcode this demo value regardless of who is calling.

---

### [Scenario 2] Re-asked "How may I help you today?" mid-call
- **Severity:** low
- **Call:** `outputs/transcripts/call_02.txt` · `outputs/recordings/call_02.mp3`
- **Expected:** After completing profile setup, agent should return to the patient's original stated purpose (reschedule an appointment) without re-prompting.
- **Actual:** Agent asked "How may I help you today?" after profile creation, losing the context of the patient's opening request.
- **Repro / quote:** Patient states they need to reschedule at 21:28:58 → Agent: "How may I help you today?" at 21:29:21, forcing the patient to repeat themselves.
- **Notes:** Causes unnecessary friction and adds a conversational loop.

---

### [Scenario 2] Wrong appointment shown when looking up by date/time
- **Severity:** high
- **Call:** `outputs/transcripts/call_02.txt` · `outputs/recordings/call_02.mp3`
- **Expected:** Agent should surface the appointment matching the patient's stated date/time (Thursday 2 PM) or clearly state it cannot be found.
- **Actual:** Agent returned a Wednesday 9 AM appointment when the patient said Thursday 2 PM, with no clear explanation for the mismatch.
- **Repro / quote:** Patient: "I need to move my Thursday 2 PM appointment" → AGENT: "I see you have an appointment scheduled for Wednesday, July 8 at 9AM. I hope to see a Thursday 2PM appointment on file."
- **Notes:** Patient was confused and ultimately deferred to whatever the system showed. Agent should fail gracefully and ask for clarification rather than presenting a mismatched record.

---

### [Scenario 3] Demo profile created for existing patient who declined (recurring)
- **Severity:** high
- **Call:** `outputs/transcripts/call_03.txt` · `outputs/recordings/call_03.mp3`
- **Expected:** Agent should look up the existing patient and proceed to cancellation without creating a profile.
- **Actual:** Patient declined the demo profile offer and said they just needed to cancel; agent created the profile anyway.
- **Repro / quote:** Patient: "No thanks, I just need to cancel my appointment." → AGENT: "Your patient profile is set up, and your date of birth is 07/04/2000."
- **Notes:** Same behavior as Scenario 2. Indicates this is a systemic flow problem — the demo-profile creation path is not being bypassed correctly when the patient declines.

---

### [Scenario 3] Fake date of birth assigned without asking (recurring)
- **Severity:** low
- **Call:** `outputs/transcripts/call_03.txt` · `outputs/recordings/call_03.mp3`
- **Expected:** Agent should ask for or look up the patient's actual date of birth.
- **Actual:** Agent assigned DOB 07/04/2000 automatically — same hardcoded demo value seen in Scenarios 1 and 2.
- **Repro / quote:** AGENT: "Your patient profile is set up, and your date of birth is 07/04/2000." Patient: "Um, that's not my date of birth."
- **Notes:** Third consecutive scenario with this issue; confirms the value is hardcoded and not patient-specific.

---

### [Scenario 3] Re-asked "How can I help you today?" after patient stated purpose (recurring)
- **Severity:** low
- **Call:** `outputs/transcripts/call_03.txt` · `outputs/recordings/call_03.mp3`
- **Expected:** After profile setup, agent should resume the patient's stated goal (cancel an appointment) without re-prompting.
- **Actual:** Patient stated cancellation intent twice before profile creation; agent still asked "How can I help you today?" afterward.
- **Repro / quote:** Patient states cancellation intent at 10:00:05 and 10:00:09 → AGENT: "How can I help you today?" at 10:00:44.
- **Notes:** Same pattern as Scenario 2. Profile creation appears to clear conversational context.


---

### [Scenario 4] Fake date of birth assigned without asking (recurring)
- **Severity:** low
- **Call:** `outputs/transcripts/call_04.txt` · `outputs/recordings/call_04.mp3`
- **Expected:** Agent should ask the patient for their date of birth before creating a profile.
- **Actual:** Agent assigned DOB 07/04/2000 automatically — same hardcoded demo value seen in Scenarios 1–3.
- **Repro / quote:** AGENT: "Your patient profile is set up, and your date of birth is 07/04/2000 for demo purposes." PATIENT: "Well actually my real date of birth is December 3rd, 1958."
- **Notes:** Fourth consecutive scenario with this issue. Agent did not update the record with the patient's corrected DOB.

---

### [Scenario 4] Re-asked "Can I help you today?" after patient already stated purpose (recurring)
- **Severity:** low
- **Call:** `outputs/transcripts/call_04.txt` · `outputs/recordings/call_04.mp3`
- **Expected:** After profile setup, agent should resume the patient's already-stated goal without re-prompting.
- **Actual:** Patient stated the refill need twice before profile creation; agent still asked "Can I help you today?" immediately after, making the patient repeat themselves a third time.
- **Repro / quote:** Patient states refill need at 14:00:20 and 14:00:24 → AGENT (14:01:01): "Can I help you today?"
- **Notes:** Same context-reset pattern seen in Scenarios 2 and 3.

---

### [Scenario 4] Out-of-scope refill processed without flagging
- **Severity:** medium
- **Call:** `outputs/transcripts/call_04.txt` · `outputs/recordings/call_04.mp3`
- **Expected:** PivotPoint Orthopedics is an orthopedic clinic. A blood pressure medication (Lisinopril) refill is outside its scope; the agent should redirect the patient to their primary care provider or pharmacy.
- **Actual:** Agent processed the Lisinopril refill in full — collecting medication name, days remaining, callback number, and pharmacy — without ever noting the request falls outside orthopedic care.
- **Repro / quote:** PATIENT: "I need a refill on my Lisinopril" — Agent proceeds with no out-of-scope warning.
- **Notes:** Risk of patient assuming their refill is being handled when it may not be routable to an orthopedic clinic's support team.

---

### [Scenario 4] Asked for medication name the patient had already provided
- **Severity:** medium
- **Call:** `outputs/transcripts/call_04.txt` · `outputs/recordings/call_04.mp3`
- **Expected:** Agent should carry forward the medication name already stated in the same turn.
- **Actual:** Patient said "I need a refill on my Lisinopril" and agent immediately asked "Which blood pressure medication do you need refilled today? Please tell me the name as it appears on the bottle."
- **Repro / quote:** PATIENT (14:01:02): "I need a refill on my Lisinopril." → AGENT (14:01:16): "Which blood pressure medication do you need refilled today?"
- **Notes:** Patient had to spell out the name letter by letter as a result.

---

### [Scenario 4] Days-remaining question looped three times after patient answered
- **Severity:** medium
- **Call:** `outputs/transcripts/call_04.txt` · `outputs/recordings/call_04.mp3`
- **Expected:** After patient says "two or three days," agent should acknowledge and move on.
- **Actual:** Agent responded as if the patient hadn't answered ("Take your time. Let me know when you find out"), then asked the same question a third time before finally accepting the answer.
- **Repro / quote:** PATIENT (14:01:36): "I'd say I've got maybe two or three days left." → AGENT (14:01:44): "Take your time. Let me know when you find out how many days you have left." → PATIENT repeats → AGENT (14:01:55): "How many days of lisinopril do you have left?"
- **Notes:** Three exchanges required for one piece of information; likely an NLU response-recognition failure.

---

### [Scenario 4] Phone number read back incorrectly four times before getting it right
- **Severity:** high
- **Call:** `outputs/transcripts/call_04.txt` · `outputs/recordings/call_04.mp3`
- **Expected:** Agent should accurately capture and confirm the phone number in one or at most two exchanges.
- **Actual:** Patient provided (833) 725-2475 once. Agent read it back as (833) 725-2200, then (833) 720-2475 twice, requiring the patient to correct it four times before it was captured correctly.
- **Repro / quote:** PATIENT: "(833) 725-2475" → AGENT: "(833) 725-2200" → AGENT: "(833) 720-2475" → AGENT (14:03:07): "(833) 720-2475" (still wrong) → AGENT (14:03:25): "(833) 725-2475" ✓
- **Notes:** Critical data-capture failure. If the wrong number had been saved, the clinic could not follow up on the refill.

---

### [Scenario 4] Pharmacy info re-asked after patient had already provided it
- **Severity:** medium
- **Call:** `outputs/transcripts/call_04.txt` · `outputs/recordings/call_04.mp3`
- **Expected:** Agent should carry forward the pharmacy details ("CVS on Main Street in Nashville, Tennessee") given in the same turn.
- **Actual:** After the patient stated the pharmacy, agent asked "Could you please provide the name of the pharmacy you want to use?" as if nothing had been said.
- **Repro / quote:** PATIENT (14:03:38): "I'd like to get it filled at the CVS on Main Street in Nashville, Tennessee." → AGENT (14:04:03): "Could you please provide the name of the pharmacy you want to use for your medication?"
- **Notes:** Same information-retention failure as the medication name issue above.

---

### [Scenario 4] No estimated pickup timeline given
- **Severity:** low
- **Call:** `outputs/transcripts/call_04.txt` · `outputs/recordings/call_04.mp3`
- **Expected:** Agent should provide a rough timeline for when the refill will be ready (e.g., "within 24–48 hours" or "the team will call you back today").
- **Actual:** Agent only said "The clinic support team will review your request and contact you as soon as possible" — no estimate given.
- **Repro / quote:** PATIENT: "Do you have any idea when it might be ready for pickup?" → AGENT: "They'll let you know when your prescription is ready for pickup at CVS."
- **Notes:** Patient's explicit goal was to find out when it would be ready; that goal went unmet.

---

---

### [Scenario 5] Fake date of birth assigned without asking (recurring)
- **Severity:** low
- **Call:** `outputs/transcripts/call_05.txt` · `outputs/recordings/call_05.mp3`
- **Expected:** Agent should ask the patient for their date of birth before creating a profile.
- **Actual:** Agent assigned DOB 07/04/2000 automatically — same hardcoded demo value seen in all prior scenarios.
- **Repro / quote:** AGENT: "Your patient profile is set up, and your date of birth is 07/04/2000 for demo purposes." PATIENT: "Actually, um, I think there might be a mistake with that date of birth — mine is July 22, 1980."
- **Notes:** Fifth consecutive scenario with this issue. When patient corrected it, agent did acknowledge and repeat the corrected DOB (07/22/1980).

---

### [Scenario 5] Offered to reschedule to Saturday before checking Saturday availability
- **Severity:** medium
- **Call:** `outputs/transcripts/call_05.txt` · `outputs/recordings/call_05.mp3`
- **Expected:** Agent should immediately inform the patient that Saturday appointments are not available when first asked.
- **Actual:** Agent said "I can help with that. Before we check Saturday availability..." — implying Saturday might be available — before later revealing the clinic is closed on weekends.
- **Repro / quote:** AGENT: "I can help with that. Before we check Saturday availability, would you like to create a demo patient profile?" — then after profile setup, proceeded to offer "I can help you reschedule it to a Saturday at 10AM."
- **Notes:** Agent both raised false hope and then offered to reschedule to Saturday before eventually refusing. Should decline Saturday in the first exchange.

---

### [Scenario 5] Offered to reschedule existing appointment to Saturday before stating Saturday unavailability
- **Severity:** high
- **Call:** `outputs/transcripts/call_05.txt` · `outputs/recordings/call_05.mp3`
- **Expected:** Agent should not offer Saturday as a rescheduling option when the clinic is closed on weekends.
- **Actual:** After finding the patient had an existing appointment, agent said "If you want, I can help you reschedule it to a Saturday at 10AM" — directly offering a slot that does not exist.
- **Repro / quote:** AGENT: "It looks like you already have a Root checkup appointment booked. If you want, I can help you reschedule it to a Saturday at 10AM or cancel the current one."
- **Notes:** This is a hallucinated availability; the agent confirmed one minute later that no Saturday slots exist.

---

### [Scenario 5] Re-asked "How can I help you today?" after patient stated purpose (recurring)
- **Severity:** low
- **Call:** `outputs/transcripts/call_05.txt` · `outputs/recordings/call_05.mp3`
- **Expected:** After profile setup, agent should resume the patient's already-stated goal (Saturday appointment) without re-prompting.
- **Actual:** Agent asked "How can I help you today?" immediately after creating the profile, despite the patient having clearly stated their need twice already.
- **Repro / quote:** AGENT: "Your patient profile is set up... How can I help you today?" — patient had already stated Saturday 10 AM twice before profile creation.
- **Notes:** Same context-reset pattern seen in Scenarios 2, 3, and 4.

---

### [Scenario 6] After-hours 9 PM request never declined and clinic hours never stated (edge-case failure)
- **Severity:** high
- **Call:** `outputs/transcripts/call_06.txt` · `outputs/recordings/call_06.mp3`
- **Expected:** This is an after-hours edge case. When the patient repeatedly asks for a 9:00 PM appointment, the agent should state real clinic hours and decline the after-hours slot (or offer the latest valid time) — never imply an evening slot is fine.
- **Actual:** The patient asked for ~9 PM at least four times across the call. The agent never stated clinic hours, never said whether 9 PM is possible, and never declined it. It closed with a vague "Great. ... Have a good evening" that neither confirms nor rejects the after-hours time.
- **Repro / quote:** PATIENT (21:00:41): "I'm really hoping for something around 9 PM if you have that available?" / PATIENT (21:01:08): "I just really need that evening time slot around 9 PM." → AGENT (21:01:50): "Great. If you need to reschedule or have any other questions, just let me know. Have a good evening." (no hours stated, no decline)
- **Notes:** The core purpose of this scenario — does the agent reject after-hours scheduling? — is effectively failed: the agent neither rejects 9 PM nor states hours, leaving an invalid request unaddressed.

---

### [Scenario 6] Ambiguous close — reschedule to 9 PM left unconfirmed, no date/time given
- **Severity:** high
- **Call:** `outputs/transcripts/call_06.txt` · `outputs/recordings/call_06.mp3`
- **Expected:** When the patient asks to reschedule the existing appointment to 9 PM, the agent should either confirm a concrete new date/time or decline 9 PM — not respond with a non-committal acknowledgement.
- **Actual:** In response to "can we just reschedule that to 9 PM," the agent said only "Great. ... Have a good evening," implying agreement while never confirming a date/time, and appeared to wrap up the call. The patient was left asking what time was actually booked.
- **Repro / quote:** PATIENT (21:01:38): "can we just reschedule that to 9 PM instead?" → AGENT (21:01:50): "Great. ... Have a good evening." → PATIENT (21:01:52): "so just to confirm — you're gonna set that appointment for 9 PM, right? And ... what's the exact date and time I should expect?"
- **Notes:** Re-run no longer dead-ends into a transfer/hang-up (the earlier demo-profile collision is handled), but the outcome is now ambiguous: a "Great" that reads as accepting an out-of-hours slot, with no confirmed booking.

---

### [Scenario 6] Fake date of birth assigned without asking (recurring)
- **Severity:** low
- **Call:** `outputs/transcripts/call_06.txt` · `outputs/recordings/call_06.mp3`
- **Expected:** Agent should ask the patient for their date of birth before creating a profile.
- **Actual:** Agent assigned DOB 07/04/2000 automatically — same hardcoded demo value seen in all prior scenarios.
- **Repro / quote:** AGENT (21:00:40): "your date of birth is 07/04/2000 for demo purposes." PATIENT (21:00:41): "my date of birth is March 8th, 1987 — not that date."
- **Notes:** Sixth consecutive scenario with this issue. Agent did acknowledge and repeat the corrected DOB (03/08/1987).

---

### [Scenario 6] Re-asked "How can I help you today?" after patient stated purpose (recurring)
- **Severity:** low
- **Call:** `outputs/transcripts/call_06.txt` · `outputs/recordings/call_06.mp3`
- **Expected:** After profile setup, agent should resume the patient's already-stated goal (an evening appointment) without re-prompting.
- **Actual:** Agent asked "How can I help you today?" right after creating the profile, despite the patient having already asked for a 9 PM appointment twice.
- **Repro / quote:** PATIENT (20:59:43 / 20:59:56) asks for an evening / 9 PM appointment → AGENT (21:00:40): "How can I help you today?"
- **Notes:** Same context-reset pattern seen in Scenarios 2–5.

---

### [Scenario 7] Blanket "we accept most major insurance plans" — affirms every plan without verification
- **Severity:** medium
- **Call:** `outputs/transcripts/call_07.txt` · `outputs/recordings/call_07.mp3`
- **Expected:** Agent should confirm coverage only for plans it can actually verify, or clearly state it cannot confirm and tell the patient how to verify.
- **Actual:** Agent affirmed all three plans (Aetna, Blue Cross Blue Shield, Cigna) with a blanket "we accept most major insurance plans," never indicating it had checked anything specific — possible hallucinated coverage.
- **Repro / quote:** AGENT (21:13:41): "Do accept most insurance plans, including AETA." → AGENT (21:14:05): "we accept most major insurance plans, including Blue Cross Blue Shield." → AGENT (21:14:25): "Yes. We accept Cigna as well."
- **Notes:** This is the scenario's watch-point. Risk: the patient may rely on coverage that isn't actually in-network.

---

### [Scenario 7] Fake date of birth assigned without asking (recurring) — left uncorrected
- **Severity:** low
- **Call:** `outputs/transcripts/call_07.txt` · `outputs/recordings/call_07.mp3`
- **Expected:** Agent should ask the patient for their date of birth before creating a profile.
- **Actual:** Agent assigned DOB 07/04/2000 automatically. The patient was focused on insurance and never corrected it, so the fabricated value persists on the record.
- **Repro / quote:** AGENT (21:13:41): "Your patient profile is set up. And your date of birth is 07/04/2000 for demo purposes."
- **Notes:** Seventh consecutive scenario with this issue; here the wrong value goes entirely uncorrected. The profile was also created even though the patient only asked an insurance question and never requested one.

---

> **Harness note (Scenario 8):** Patient-initiated barge-in is now enabled for
> this scenario only, via `"barge_in": true` in `scenarios/scenarios.json`. The
> patient simulator cuts the agent off mid-utterance (after the agent has said a
> few words) instead of waiting for end-of-speech. This is opt-in per scenario,
> so all other calls are unchanged. Before this, the simulator could only reply
> after the agent finished, so the interruption edge case was never exercised.

### [Scenario 8] Agent does not yield on barge-in — keeps talking over the patient
- **Severity:** high
- **Call:** `outputs/transcripts/call_08.txt` · `outputs/recordings/call_08.mp3`
- **Expected:** When the patient interrupts, the agent should stop speaking, listen, and respond to what the patient just said.
- **Actual:** The agent ignored the interruptions and kept pushing its own script. Nearly every agent turn was cut off mid-sentence by the patient, yet the agent continued its previous line on the next turn rather than adapting, repeatedly restarting the same "you already have a routine checkup" statement.
- **Repro / quote:** AGENT (21:32:22): "I can help with that. First," → PATIENT cuts in → AGENT (21:32:33): "I'll check the schedule for you." → PATIENT gives name/DOB/callback → AGENT (21:32:40): "What is your first name and last name?" (ignores what the patient just said).
- **Notes:** The agent shows no barge-in handling; it talks over the patient and never acknowledges being interrupted.

---

### [Scenario 8] Agent loops on the "already have an appointment" message without progressing
- **Severity:** high
- **Call:** `outputs/transcripts/call_08.txt` · `outputs/recordings/call_08.mp3`
- **Expected:** After stating an appointment exists, the agent should answer the patient's repeated, direct question ("when is it / book a new one") or hand off cleanly.
- **Actual:** The agent restated "you already have a routine checkup appointment" four-plus times in slightly different wording, never gave the date/time, and never booked a new slot — the patient asked "when is it?" repeatedly and never got an answer.
- **Repro / quote:** AGENT: "It looks like you already have a routine check..." → "You already have a routine checkup..." → "You already have a checkup appointment on file." → "I can't book another checkup since you already have one..." — all in response to the patient asking when the existing appointment is.
- **Notes:** Same pre-seeded-demo-appointment collision seen in Scenarios 1 and 6; under rapid interruption it degrades into a repeating loop with no resolution.

---

### [Scenario 8] Re-asked for the patient's name after it was already given (context loss)
- **Severity:** medium
- **Call:** `outputs/transcripts/call_08.txt` · `outputs/recordings/call_08.mp3`
- **Expected:** Agent should retain the name the patient already provided and not re-ask.
- **Actual:** Patient gave "Alex Turner" (and DOB + callback) up front, but the agent asked "What is your first name and last name?" afterward.
- **Repro / quote:** PATIENT (21:32:34): "I'm Alex Turner, by the way. August 25th, '96..." → AGENT (21:32:40): "What is your first name and last name?"
- **Notes:** Likely a side effect of the agent talking over the patient and not capturing the interjected details. Same information-retention pattern seen in Scenario 4.

---

### [Scenario 8] Fake date of birth assigned without asking (recurring)
- **Severity:** low
- **Call:** `outputs/transcripts/call_08.txt` · `outputs/recordings/call_08.mp3`
- **Expected:** Agent should ask the patient for their date of birth before creating a profile.
- **Actual:** Agent assigned DOB 07/04/2000 automatically — same hardcoded demo value seen in all prior scenarios.
- **Repro / quote:** AGENT: "Your patient profile is set up, and your date of birth is 07/04/2000. For demo purposes."
- **Notes:** Recurring across every scenario reviewed so far.

---

### [Scenario 9] Refused to correct date of birth; fabricated DOB left on record
- **Severity:** high
- **Call:** `outputs/transcripts/call_09.txt` · `outputs/recordings/call_09.mp3`
- **Expected:** When the patient corrects their DOB, the agent should update the record (as it did in Scenarios 4–6, where it repeated the corrected value back).
- **Actual:** Agent said it "can't update your date of birth directly" and deferred to the support team, leaving the fabricated 07/04/2000 in place instead of the patient's stated June 30, 1970.
- **Repro / quote:** PATIENT (21:42:11): "My date of birth is June 30, 1970, not July 4th, 2000." → AGENT (21:42:35): "I can't update your date of birth directly, but I'll let our clinic support team know about the correction."
- **Notes:** Inconsistent with other scenarios where the agent did update/repeat the corrected DOB; data-integrity risk — incorrect PII persists on the record.

---

### [Scenario 9] Fake date of birth assigned without asking (recurring)
- **Severity:** low
- **Call:** `outputs/transcripts/call_09.txt` · `outputs/recordings/call_09.mp3`
- **Expected:** Agent should ask the patient for their date of birth before creating a profile.
- **Actual:** Agent assigned DOB 07/04/2000 automatically — same hardcoded demo value seen in all prior scenarios.
- **Repro / quote:** AGENT (21:42:10): "Your patient profile is set up, and your date of birth is 07/04/2000 for demo purposes."
- **Notes:** Ninth scenario with this issue; compounded here by the refusal-to-correct bug above.

---

### [Scenario 9] Thin empathy — past hour-long wait only "noted," never apologized for (edge-case partial)
- **Severity:** low
- **Call:** `outputs/transcripts/call_09.txt` · `outputs/recordings/call_09.mp3`
- **Expected:** For an angry patient venting about a previous hour-long wait, the agent should acknowledge and apologize to de-escalate, not just log it.
- **Actual:** Agent stayed calm and completed the booking, but never apologized for the prior wait; it only offered to "note your request about the wait time."
- **Repro / quote:** PATIENT (21:43:49): "try to make sure I don't wait an hour like last time, okay?" → AGENT (21:44:12): "I'll note your request about the wait time for the clinic team."
- **Notes:** Positive overall — unlike Scenarios 1, 6, and 8, the booking actually completed (follow-up booked for Tuesday, June 30 at 2PM), so de-escalation was good enough to finish the task; empathy was thin but never hostile.

---

### [Scenario 10] Multi-part request parsed but none of the three tasks completed
- **Severity:** medium
- **Call:** `outputs/transcripts/call_10.txt` · `outputs/recordings/call_10.mp3`
- **Expected:** The agent should work through all three asks — prescription refill, appointment next week, and directions — and resolve each or clearly hand off.
- **Actual:** The agent correctly identified all three requests up front (good), but resolved none: the refill stalled (no medication name and no access to history), the booking hit the pre-seeded "already have an appointment" block, and the call ended in the transfer → "Goodbye" dead-end. The patient hung up with nothing done.
- **Repro / quote:** AGENT (21:45:51): "I'll get your demo patient profile set up first, then help with your prescription refill and appointment. I could also give you the full address" → later AGENT (21:50:19): "Hello. You've reached the Pretty Good AI test line. Goodbye."
- **Notes:** Credit for catching the three-part request; the failure is in completion, driven mainly by the systemic demo-appointment dead-end above.

---

### [Scenario 10] "Directions" request only partially met — address given, directions declined
- **Severity:** low
- **Call:** `outputs/transcripts/call_10.txt` · `outputs/recordings/call_10.mp3`
- **Expected:** When the patient asks how to get to the office, give directions or at least a complete address with a brief orientation.
- **Actual:** Agent provided the address but explicitly said it could not provide directions.
- **Repro / quote:** AGENT (21:47:57): "I can give you the office address, but I can't provide detailed directions." → AGENT (21:48:32): "The office is Pivot Point Orthopedics, 123 Main Street, Suite 400, Seattle."
- **Notes:** Reasonable boundary, but the patient's explicit ask (directions) was only partly satisfied.

---

### [Scenario 11] Off-topic handling — agent stayed on task and did not hallucinate (mostly a pass)
- **Severity:** low
- **Call:** `outputs/transcripts/call_11.txt` · `outputs/recordings/call_11.mp3`
- **Expected:** Politely redirect off-topic chatter (restaurants, weather, sports, parking, coffee) back to clinic business without inventing answers.
- **Actual:** The agent handled this well: it declined every off-topic question and steered back to scheduling, and even corrected the premise ("I'm actually a virtual assistant, so I don't experience the weather"). No hallucinated recommendations.
- **Repro / quote:** AGENT (21:56:21): "I don't have recommendations for pizza places. But I could help with anything related to the clinic" → AGENT (21:58:12): "I don't have weather updates."
- **Notes:** Logged as a positive result — strong redirection and no fabrication. This scenario largely passes.

---

### [Scenario 11] Declared "your appointment is all set" without ever giving its date/time
- **Severity:** low
- **Call:** `outputs/transcripts/call_11.txt` · `outputs/recordings/call_11.mp3`
- **Expected:** When closing, the agent should confirm the actual appointment date/time the patient is keeping.
- **Actual:** The patient chose to keep the pre-existing appointment; the agent closed with "Your appointment is all set" but never stated what day/time that appointment is.
- **Repro / quote:** PATIENT (21:57:42): "maybe I should just keep it as is then" → AGENT (21:58:32): "Your appointment is all set. Have a great day."
- **Notes:** Mildly misleading closure — "all set" implies certainty about an appointment whose details were never surfaced.

---

### [Scenario 12] "Can't update date of birth directly," but the correction WAS captured (stress test passes)
- **Severity:** medium
- **Call:** `outputs/transcripts/call_12.txt` · `outputs/recordings/call_12.mp3`
- **Expected:** When the patient gives a wrong DOB then corrects it, the agent should register the corrected value.
- **Actual:** The agent claimed it "can't update your date of birth directly" and deferred to support (same messaging as Scenario 9), yet it then correctly documented the corrected value — registering March 4th, 1998, not the erroneous March 14th. So the core stress-test passed even though the capability messaging is inconsistent.
- **Repro / quote:** PATIENT (22:01:35): "It's March 4th, 1998, not the 14th." → AGENT (22:02:16): "I've documented that your correct date of birth is 03/04/1998."
- **Notes:** Good outcome on the actual data (right date captured); the "I can't update directly / I'll let the support team know" framing is confusing and contradicts the fact that it did record the corrected DOB.

---

### [Scenario 12] New-patient booking not completed — demo-appointment dead-end again
- **Severity:** high
- **Call:** `outputs/transcripts/call_12.txt` · `outputs/recordings/call_12.mp3`
- **Expected:** A first-time patient establishing care should leave with a booked new-patient consult.
- **Actual:** The agent found a pre-existing "new patient consult" on file, couldn't provide its details, and routed to the transfer → "Goodbye" dead-end without booking anything.
- **Repro / quote:** AGENT (22:03:38): "I don't have access to the exact date and time of your appointment, but our live support team can provide those details" → AGENT (22:04:15): "Connecting you to a representative. Please wait. Hello. You've reached the Pretty Good AI test line. Goodbye."
- **Notes:** Same systemic demo-appointment dead-end documented at the top of this report; here it blocks new-patient registration end-to-end.
