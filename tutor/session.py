"""Session orchestrator: ties LLM + ASR + TTS + recorder + storage into the voice loop."""
from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Protocol

from tutor.budget import BudgetExceededError
from tutor.scenarios.loader import Scenario, build_system_prompt
from tutor.storage import SessionStorage

log = logging.getLogger(__name__)


class _LLM(Protocol):
    def complete(self, messages: list[dict[str, str]], temperature: float = ...) -> str: ...


class _ASR(Protocol):
    def transcribe(self, wav_path: Path) -> str: ...


class _TTS(Protocol):
    def speak(self, text: str) -> None: ...


class _Recorder(Protocol):
    def record_to_wav(self, out_path: Path) -> Path: ...


class _Evaluator(Protocol):
    def evaluate(self, transcript: list[dict[str, str]]) -> list: ...


class _SRSEngine(Protocol):
    def create_cards(self, growth_points: list, session_id: str) -> list: ...


_END_SENTINEL = "end"


class SessionOrchestrator:
    def __init__(
        self,
        llm: _LLM,
        asr: _ASR,
        tts: _TTS,
        recorder: _Recorder,
        storage: SessionStorage,
        scenario: Scenario,
        per_session_turn_limit: int = 25,
        user_native_language: str = "Russian",
        evaluator: _Evaluator | None = None,
        srs_engine: _SRSEngine | None = None,
    ) -> None:
        self._llm = llm
        self._asr = asr
        self._tts = tts
        self._recorder = recorder
        self._storage = storage
        self._scenario = scenario
        self._limit = per_session_turn_limit
        self._system_prompt = build_system_prompt(scenario, user_native_language=user_native_language)
        self._evaluator = evaluator
        self._srs_engine = srs_engine

    def run(self) -> str:
        session_id = self._storage.create_session(scenario_id=self._scenario.id)
        history: list[dict[str, str]] = [{"role": "system", "content": self._system_prompt}]
        temp_wavs: list[Path] = []

        try:
            try:
                opening = self._llm.complete(messages=history)
            except BudgetExceededError as e:
                print(f"\n[budget exhausted before session start: {e}]\n[session ending]")
                return session_id
            history.append({"role": "assistant", "content": opening})
            print(f"\n[interviewer] {opening}\n")
            self._tts.speak(opening)

            turn_count = 0
            while turn_count < self._limit:
                cmd = input(f"[turn {turn_count + 1}/{self._limit}] press Enter to speak, or type 'end' to finish: ").strip().lower()
                if cmd == _END_SENTINEL:
                    break

                wav_path = Path(tempfile.gettempdir()) / f"tutor_turn_{session_id}_{turn_count}.wav"
                temp_wavs.append(wav_path)
                self._recorder.record_to_wav(wav_path)
                user_text = self._asr.transcribe(wav_path).strip()
                if not user_text:
                    print("[didn't catch that — try again]")
                    continue
                print(f"[you] {user_text}\n")
                history.append({"role": "user", "content": user_text})

                try:
                    reply = self._llm.complete(messages=history)
                except BudgetExceededError as e:
                    print(f"\n[budget exhausted: {e}]\n[session ending]")
                    break

                history.append({"role": "assistant", "content": reply})
                print(f"[interviewer] {reply}\n")
                self._tts.speak(reply)

                self._storage.append_turn(session_id, user_text=user_text, llm_text=reply)
                turn_count += 1

            # After loop: run evaluator if provided and there were turns
            if self._evaluator is not None and self._srs_engine is not None and turn_count > 0:
                try:
                    growth_points = self._evaluator.evaluate(transcript=history)
                except Exception as e:
                    log.warning("Evaluator raised unexpectedly: %s", e)
                    growth_points = []

                if growth_points:
                    gp_dicts = [
                        gp.model_dump() if hasattr(gp, "model_dump") else asdict(gp)
                        for gp in growth_points
                    ]
                    self._storage.set_growth_points(session_id, gp_dicts)
                    try:
                        cards = self._srs_engine.create_cards(growth_points, session_id=session_id)
                        self._storage.set_cards_created(session_id, [c.id for c in cards])
                        print(f"\n[saved {len(cards)} cards for review tomorrow]")
                    except Exception as e:
                        log.warning("SRS create_cards failed: %s", e)
                else:
                    log.info("Evaluator returned no growth points; no cards created.")
        finally:
            # Clean up temp WAVs
            for wav in temp_wavs:
                try:
                    if wav.exists():
                        os.remove(str(wav))
                except OSError:
                    pass
            self._storage.end_session(session_id)

        return session_id
