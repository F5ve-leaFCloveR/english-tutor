"""Orchestration layer for the web API. Reuses existing modules."""
from __future__ import annotations

from tutor.scenarios.loader import (
    Scenario,
    ScenarioNotFoundError,
    build_system_prompt,
    list_scenarios,
    load_scenario,
)
from tutor.web.deps import Dependencies
from tutor.web.errors import SessionNotFoundError
from tutor.web.schemas import (
    ScenarioSummary,
    StartSessionResult,
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
