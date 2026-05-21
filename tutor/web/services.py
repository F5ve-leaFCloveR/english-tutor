"""Orchestration layer for the web API. Reuses existing modules."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from tutor.scenarios.loader import (
    Scenario,
    ScenarioNotFoundError,
    build_system_prompt,
    list_scenarios,
    load_scenario,
)
from tutor.web.deps import Dependencies
from tutor.web.errors import NoSpeechDetectedError, SessionNotFoundError
from tutor.web.schemas import (
    ScenarioSummary,
    StartSessionResult,
    TurnResult,
)


def list_scenarios_service(deps: Dependencies) -> list[ScenarioSummary]:
    summaries: list[ScenarioSummary] = []
    for sid in list_scenarios():
        sc = load_scenario(sid)
        summaries.append(ScenarioSummary(id=sc.id, name=sc.name, difficulty=sc.difficulty))
    return summaries


def start_session_service(deps: Dependencies, scenario_id: str) -> StartSessionResult:
    scenario = load_scenario(scenario_id)  # raises ScenarioNotFoundError
    session_id = deps.storage.create_session(scenario_id=scenario.id)

    system_prompt = build_system_prompt(scenario, user_native_language="Russian")
    opening = deps.llm.complete(
        messages=[{"role": "system", "content": system_prompt}],
    )
    deps.storage.set_opening_text(session_id, opening)
    return StartSessionResult(session_id=session_id, opening_text=opening)


def get_session_service(deps: Dependencies, session_id: str) -> dict:
    try:
        return deps.storage.load_session(session_id)
    except FileNotFoundError as e:
        raise SessionNotFoundError(session_id) from e


def turn_service(deps: Dependencies, session_id: str, audio_bytes: bytes) -> TurnResult:
    # 1. Load session first (cheap, fails fast on bad id)
    try:
        session_data = deps.storage.load_session(session_id)
    except FileNotFoundError as e:
        raise SessionNotFoundError(session_id) from e

    # 2. Save audio + ASR
    tmp = Path(tempfile.gettempdir()) / f"web_turn_{session_id}_{os.getpid()}.bin"
    tmp.write_bytes(audio_bytes)
    try:
        user_text = deps.asr.transcribe(tmp).strip()
        if not user_text:
            raise NoSpeechDetectedError(f"empty transcript for session {session_id}")

        # 3. Build messages
        scenario = load_scenario(session_data["scenario_id"])
        system_prompt = build_system_prompt(scenario, user_native_language="Russian")
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if session_data.get("opening_text"):
            messages.append({"role": "assistant", "content": session_data["opening_text"]})
        for turn in session_data.get("turns", []):
            messages.append({"role": "user", "content": turn["user_text"]})
            messages.append({"role": "assistant", "content": turn["llm_text"]})
        messages.append({"role": "user", "content": user_text})

        # 4. LLM call
        assistant_text = deps.llm.complete(messages=messages)

        # 5. Persist
        deps.storage.append_turn(session_id, user_text=user_text, llm_text=assistant_text)
        return TurnResult(user_text=user_text, assistant_text=assistant_text)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
