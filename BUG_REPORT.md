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

<!-- Example:
### [Scenario 5] Agent booked a Saturday appointment
- **Severity:** high
- **Call:** outputs/transcripts/call_05.txt
- **Expected:** decline weekend; offer a weekday slot
- **Actual:** confirmed "Saturday at 10am"
- **Repro / quote:** AGENT: "Great, you're booked for Saturday at 10."
- **Notes:** hallucinated availability outside clinic hours
-->
