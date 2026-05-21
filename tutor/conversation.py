"""Free-chat LLM turn: reply + per-message corrections in one structured call."""
from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel, ValidationError

from tutor.llm import LLMClient

log = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You are a friendly English conversational partner for a Russian-native intermediate student.

Your job each turn:
1. Reply naturally and conversationally in 2-4 sentences. Match the user's tone. Ask follow-up questions when natural.
2. Identify up to 3 corrections to the user's MOST RECENT message only. Focus on:
   - vocab: word choice that's correct but weak/generic. Suggest a stronger, more precise word.
   - grammar: tense, articles, prepositions, word order errors.
   Skip filler words, typos, idiom/register issues, minor style preferences. If the message is clean, return an empty list.

Return STRICT JSON, no commentary:
{
  "reply": "<your conversational reply>",
  "corrections": [
    {
      "tag": "vocab" | "grammar",
      "user_utterance": "<verbatim what the user wrote>",
      "corrected_version": "<your improved version>",
      "explanation": "<1-2 sentences why the correction is better>"
    }
  ]
}
"""


_FALLBACK_REPLY = "Sorry, I had trouble responding. Could you say that again?"


class ChatCorrection(BaseModel):
    tag: Literal["vocab", "grammar"]
    user_utterance: str
    corrected_version: str
    explanation: str


class ChatResponse(BaseModel):
    reply: str
    corrections: list[ChatCorrection]


class ChatTurn:
    def __init__(self, llm: LLMClient, model: str) -> None:
        self._llm = llm
        self._model = model

    def respond(
        self,
        history: list[dict[str, str]],
        message: str,
    ) -> ChatResponse:
        """One turn: LLM replies AND returns corrections for the latest user message."""
        messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
        for h in history:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": message})

        reminder = {
            "role": "user",
            "content": (
                "Your previous response was not valid JSON. Return STRICT JSON only, "
                "no commentary, no markdown fences. Just the {\"reply\": ..., \"corrections\": [...]} object."
            ),
        }

        last_error: Exception | None = None
        for attempt in range(2):
            call_messages = messages if attempt == 0 else messages + [reminder]
            try:
                raw = self._llm.complete(
                    messages=call_messages,
                    temperature=0.7,
                    model_override=self._model,
                    max_tokens=1024,
                )
            except Exception as e:
                log.warning("Chat LLM call failed: %s", e)
                return ChatResponse(reply=_FALLBACK_REPLY, corrections=[])
            try:
                parsed = ChatResponse.model_validate_json(_strip_code_fences(raw))
                parsed.corrections = parsed.corrections[:3]
                return parsed
            except (ValidationError, ValueError, json.JSONDecodeError) as e:
                last_error = e
                log.warning("Chat returned invalid JSON (attempt %d): %s", attempt + 1, e)
                continue

        log.warning("Chat exhausted retries: %s", last_error)
        return ChatResponse(reply=_FALLBACK_REPLY, corrections=[])


def _strip_code_fences(text: str) -> str:
    """LLMs sometimes wrap JSON in ```json ... ```. Strip if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text
