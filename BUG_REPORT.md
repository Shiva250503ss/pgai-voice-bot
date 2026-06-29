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

### [Scenario 2] Provider name inconsistent between offer and confirmation
- **Severity:** medium
- **Call:** `outputs/transcripts/call_02.txt` · `outputs/recordings/call_02.mp3`
- **Expected:** The provider name should be the same throughout the call.
- **Actual:** Agent named the provider "Aperker" when offering the slot, then "Abrekar" when reading back the confirmation — two different spellings of what appears to be the same provider.
- **Repro / quote:** AGENT (21:30:23): "Friday, July 10 at 09:45AM in Nashville with Aperker" → AGENT (21:31:00): "Friday, July 10 at 09:45AM in Nashville with Abrekar."
- **Notes:** Likely a hallucinated or corrupted provider name; patient cannot reliably know which doctor they are seeing.

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

### [Scenario 5] Provider name inconsistent across the same call (recurring)
- **Severity:** medium
- **Call:** `outputs/transcripts/call_05.txt` · `outputs/recordings/call_05.mp3`
- **Expected:** The provider name should be consistent throughout the call.
- **Actual:** Provider referred to as "Z Bigniew Lukovsky" when reading existing appointment, then "Zee Bigniew Lucoska" when confirming the new slot — two different spellings/pronunciations of the same provider.
- **Repro / quote:** AGENT: "appointment scheduled for Tuesday, July 7 at 10AM with doctor Z Bigniew Lukovsky" → AGENT: "appointment is July 20 at 9AM with doctor Zee Bigniew Lucoska."
- **Notes:** Same pattern as Scenario 2. Likely hallucinated phonetic rendering of a database name.

---

### [Scenario 5] Re-asked "How can I help you today?" after patient stated purpose (recurring)
- **Severity:** low
- **Call:** `outputs/transcripts/call_05.txt` · `outputs/recordings/call_05.mp3`
- **Expected:** After profile setup, agent should resume the patient's already-stated goal (Saturday appointment) without re-prompting.
- **Actual:** Agent asked "How can I help you today?" immediately after creating the profile, despite the patient having clearly stated their need twice already.
- **Repro / quote:** AGENT: "Your patient profile is set up... How can I help you today?" — patient had already stated Saturday 10 AM twice before profile creation.
- **Notes:** Same context-reset pattern seen in Scenarios 2, 3, and 4.

<!-- Example:
### [Scenario 5] Agent booked a Saturday appointment
- **Severity:** high
- **Call:** outputs/transcripts/call_05.txt
- **Expected:** decline weekend; offer a weekday slot
- **Actual:** confirmed "Saturday at 10am"
- **Repro / quote:** AGENT: "Great, you're booked for Saturday at 10."
- **Notes:** hallucinated availability outside clinic hours
-->
