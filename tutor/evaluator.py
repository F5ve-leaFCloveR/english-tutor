"""Post-session transcript evaluator: returns 3-5 GrowthPoint corrections."""
from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel, ValidationError

from tutor.llm import LLMClient

log = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You are an English teacher reviewing a Russian-native intermediate student's
spoken-English practice transcript.

Identify the 3-5 most impactful improvements, focused ONLY on:
  - vocab: word choice that's correct but weak/generic. Suggest a stronger, more precise word.
  - grammar: tense, articles, prepositions, word order errors.

Explicitly skip: filler words, ASR mistranscriptions, idiom/register issues, minor style preferences.

Return STRICT JSON, no commentary:
{
  "growth_points": [
    {
      "tag": "vocab" | "grammar",
      "user_utterance": "<verbatim what the student said>",
      "corrected_version": "<your improved version>",
      "explanation": "<1-2 sentences why the correction is better>",
      "context": "<one line of dialog before the utterance, or null>"
    }
  ]
}
"""


class GrowthPoint(BaseModel):
    tag: Literal["vocab", "grammar"]
    user_utterance: str
    corrected_version: str
    explanation: str
    context: str | None = None


class _GrowthPointsResponse(BaseModel):
    growth_points: list[GrowthPoint]


class Evaluator:
    def __init__(self, llm: LLMClient, model: str) -> None:
        self._llm = llm
        self._model = model

    def evaluate(self, transcript: list[dict[str, str]]) -> list[GrowthPoint]:
        """Run the evaluator LLM once (with one retry on parse failure)."""
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": "Here is the transcript to review:\n\n" + self._format_transcript(transcript)},
        ]

        last_error: Exception | None = None
        reminder = {
            "role": "user",
            "content": (
                "Your previous response was not valid JSON. Return STRICT JSON only, "
                "no commentary, no markdown fences. Just the {\"growth_points\": [...]} object."
            ),
        }
        for attempt in range(2):
            call_messages = messages if attempt == 0 else messages + [reminder]
            try:
                raw = self._llm.complete(
                    messages=call_messages,
                    temperature=0.2,
                    model_override=self._model,
                    max_tokens=8192,
                )
            except Exception as e:
                log.warning("Evaluator LLM call failed: %s", e)
                return []
            try:
                parsed = _GrowthPointsResponse.model_validate_json(_strip_code_fences(raw))
                return parsed.growth_points[:5]
            except (ValidationError, ValueError, json.JSONDecodeError) as e:
                last_error = e
                log.warning("Evaluator returned invalid JSON (attempt %d): %s", attempt + 1, e)
                continue

        log.warning("Evaluator exhausted retries: %s", last_error)
        return []

    @staticmethod
    def _format_transcript(transcript: list[dict[str, str]]) -> str:
        lines = []
        for msg in transcript:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if role == "system":
                continue
            lines.append(f"[{role}] {content}")
        return "\n".join(lines)


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
