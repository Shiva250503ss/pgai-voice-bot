"""Claude-backed patient persona LLM.

Wraps the Anthropic async SDK. Given a scenario's system prompt and the running
conversation history (agent vs. patient turns), it returns the patient's next
spoken line -- short, natural, phone-appropriate.
"""

from __future__ import annotations

import os

from anthropic import AsyncAnthropic

# Keep replies short: this is a live phone call, not a chat window.
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 160

PHONE_STYLE_RULES = (
    "\n\nIMPORTANT CALL RULES:\n"
    "- You are on a phone call. Reply in 1-2 sentences maximum.\n"
    "- Never use lists or bullet points.\n"
    "- Use natural speech -- contractions, filler words like 'um' or 'yeah' occasionally.\n"
    "- Pause naturally between thoughts.\n"
    "- CRITICAL: You have reached the correct clinic. No matter what name or specialty the clinic "
    "announces, NEVER say you called the wrong number, NEVER apologize for a wrong number, and "
    "NEVER end the call early because of the clinic name. Always stay in character and pursue your goal.\n"
)


class PatientLLM:
    """Stateful patient persona. Holds conversation history for one call."""

    def __init__(self, system_prompt: str, api_key: str | None = None):
        self.client = AsyncAnthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.system_prompt = system_prompt.strip() + PHONE_STYLE_RULES
        # Anthropic message history: roles alternate user/assistant.
        # The clinic AGENT is the "user"; the PATIENT (us) is the "assistant".
        self.history: list[dict] = []

    def record_agent(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self.history.append({"role": "user", "content": text})

    def record_patient(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        self.history.append({"role": "assistant", "content": text})

    async def respond_to(self, agent_text: str) -> str:
        """Record the agent's latest line and produce the patient's reply."""
        self.record_agent(agent_text)
        reply = await self._generate()
        self.record_patient(reply)
        return reply

    async def _generate(self) -> str:
        # Anthropic requires the first message to have role "user". If the agent
        # hasn't said anything yet, seed a neutral opener so the patient can talk.
        messages = self.history
        if not messages or messages[0]["role"] != "user":
            messages = [{"role": "user", "content": "(The call has just connected.)"}] + messages

        try:
            msg = await self.client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=self.system_prompt,
                messages=messages,
            )
            parts = [block.text for block in msg.content if getattr(block, "type", None) == "text"]
            return " ".join(p.strip() for p in parts if p).strip()
        except Exception as exc:  # noqa: BLE001 - surface but keep the call alive
            print(f"⚠️  LLM error: {exc}")
            return "Sorry, could you repeat that?"

    def is_goodbye(self, text: str) -> bool:
        """Heuristic: did the patient just sign off? Used to end the call."""
        if not text:
            return False
        lowered = text.lower()
        farewells = ("bye", "goodbye", "good bye", "take care", "have a good", "have a great")
        return any(f in lowered for f in farewells)
