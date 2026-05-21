"""Review orchestrator: voice-loop through SRS due cards with LLM grading."""
from __future__ import annotations

import logging
import os
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


log = logging.getLogger(__name__)


class _ASR(Protocol):
    def transcribe(self, wav_path: Path) -> str: ...


class _TTS(Protocol):
    def speak(self, text: str) -> None: ...


class _Recorder(Protocol):
    def record_to_wav(self, out_path: Path) -> Path: ...


class _Grader(Protocol):
    def grade(self, target: str, attempt: str) -> int: ...


class _SRSEngine(Protocol):
    def due_today(self, limit: int | None = ..., tag: str | None = ...) -> list: ...
    def record_review(self, card_id: str, quality: int) -> None: ...


_SKIP = "skip"
_QUIT = "quit"


@dataclass
class ReviewSummary:
    cards_reviewed: int = 0
    quality_distribution: dict[int, int] = field(default_factory=dict)


class ReviewOrchestrator:
    def __init__(
        self,
        grader: _Grader,
        asr: _ASR,
        tts: _TTS,
        recorder: _Recorder,
        srs: _SRSEngine,
    ) -> None:
        self._grader = grader
        self._asr = asr
        self._tts = tts
        self._recorder = recorder
        self._srs = srs

    def run(self, limit: int | None = None, tag_filter: str | None = None) -> ReviewSummary:
        cards = self._srs.due_today(limit=limit, tag=tag_filter)
        if not cards:
            print("\nNo cards due today. Run a session first, or come back tomorrow.\n")
            return ReviewSummary()

        print(f"\n=== Review: {len(cards)} cards due ===\n")
        summary = ReviewSummary()
        quality_counter: Counter[int] = Counter()

        for i, card in enumerate(cards, start=1):
            print(f"[card {i}/{len(cards)} — {card.tag}]")
            if card.context:
                print(f"Context: {card.context}")
            print(f"Earlier you said: \"{card.user_utterance}\"")
            print()
            cmd = input("How would you say it more precisely? [Enter to speak, 'skip', 'quit']: ").strip().lower()

            if cmd == _QUIT:
                break

            if cmd == _SKIP:
                quality = 0
                attempt_text = "(skipped)"
            else:
                wav_path = Path(tempfile.gettempdir()) / f"tutor_review_{card.id}.wav"
                try:
                    self._recorder.record_to_wav(wav_path)
                    attempt_text = self._asr.transcribe(wav_path).strip()
                finally:
                    try:
                        if wav_path.exists():
                            os.remove(str(wav_path))
                    except OSError:
                        pass

                if not attempt_text:
                    quality = 0
                    print("[didn't catch that]")
                else:
                    print(f"> you said: \"{attempt_text}\"")
                    print("[grading...]")
                    quality = self._grader.grade(target=card.corrected_version, attempt=attempt_text)

            print(f"\nScore: {quality}/5")
            print(f"Target: \"{card.corrected_version}\"")
            print(f"Why: {card.explanation}\n")
            self._tts.speak(card.corrected_version)

            self._srs.record_review(card.id, quality=quality)
            summary.cards_reviewed += 1
            quality_counter[quality] += 1

        summary.quality_distribution = dict(quality_counter)
        print(f"\n=== Done. {summary.cards_reviewed} cards reviewed. ===\n")
        return summary
