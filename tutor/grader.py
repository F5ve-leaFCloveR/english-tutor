"""LLM grader: scores a student's recall attempt against the target on 0-5."""
from __future__ import annotations

import logging
import re

from tutor.llm import LLMClient

log = logging.getLogger(__name__)

_GRADER_PROMPT = """You are grading an English recall practice.

TARGET (the correct version the student should say): "{target}"
STUDENT ATTEMPT (transcribed from speech): "{attempt}"

Grade on 0-5:
0 = wrong/silence/totally unrelated
1 = vague hint, missing key vocabulary or structure
2 = partial, missed important element
3 = essentially correct meaning, minor wording differences
4 = correct with small variation
5 = essentially identical

Be lenient about word order. Focus on whether the student demonstrated the key
improvement (vocab word or grammar pattern) from the target, not on exact wording.

Return ONLY the integer 0-5. No explanation."""


_DEFAULT_QUALITY = 3


class LLMGrader:
    def __init__(self, llm: LLMClient, model: str) -> None:
        self._llm = llm
        self._model = model

    def grade(self, target: str, attempt: str) -> int:
        prompt = _GRADER_PROMPT.format(target=target, attempt=attempt or "(no audio)")
        response = self._llm.complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            model_override=self._model,
            max_tokens=16,
        )
        return self._parse_score(response)

    @staticmethod
    def _parse_score(response: str) -> int:
        match = re.search(r"\b([0-5])\b", response)
        if match is None:
            log.warning("Grader returned no parseable score: %r — defaulting to 3", response[:60])
            return _DEFAULT_QUALITY
        try:
            score = int(match.group(1))
        except ValueError:
            return _DEFAULT_QUALITY
        if not 0 <= score <= 5:
            log.warning("Grader score %d out of range — defaulting to 3", score)
            return _DEFAULT_QUALITY
        return score
