from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock
import pytest


def _make_deps(tmp_path):
    from tutor.web.deps import Dependencies
    from tutor.budget import BudgetTracker
    from tutor.storage import SessionStorage
    from tutor.srs_engine import SRSEngine

    budget = BudgetTracker(
        path=tmp_path / "budget.json",
        daily_usd_cap=1.0, daily_token_cap=1_000_000,
        now=lambda: datetime(2026, 5, 21, 10, 0),
    )
    llm = MagicMock()
    asr = MagicMock()
    storage = SessionStorage(root=tmp_path / "sessions",
                              now=lambda: datetime(2026, 5, 21, 10, 0))
    srs = SRSEngine(path=tmp_path / "cards.json")
    return Dependencies(
        budget=budget, llm=llm, asr=asr, storage=storage, srs=srs,
        evaluator_model="m1", grader_model="m2",
        tts_model="m3", tts_voice="v1",
    )


def test_list_scenarios_service_returns_summaries(tmp_path):
    from tutor.web.services import list_scenarios_service
    deps = _make_deps(tmp_path)
    result = list_scenarios_service(deps)
    ids = [s.id for s in result]
    assert "tech_interview_behavioral" in ids
    assert "daily_standup" in ids
    assert "apartment_rental_abroad" in ids


def test_start_session_service_persists_opening(tmp_path):
    from tutor.web.services import start_session_service
    deps = _make_deps(tmp_path)
    deps.llm.complete.return_value = "Hi there, tell me about yourself."

    result = start_session_service(deps, scenario_id="tech_interview_behavioral")
    assert result.session_id
    assert result.opening_text == "Hi there, tell me about yourself."

    data = deps.storage.load_session(result.session_id)
    assert data["scenario_id"] == "tech_interview_behavioral"
    assert data["opening_text"] == "Hi there, tell me about yourself."


def test_start_session_service_raises_on_unknown_scenario(tmp_path):
    from tutor.web.services import start_session_service
    from tutor.scenarios.loader import ScenarioNotFoundError
    deps = _make_deps(tmp_path)
    with pytest.raises(ScenarioNotFoundError):
        start_session_service(deps, scenario_id="does_not_exist")


def test_get_session_service_returns_full_dict(tmp_path):
    from tutor.web.services import get_session_service, start_session_service
    deps = _make_deps(tmp_path)
    deps.llm.complete.return_value = "Hi."

    started = start_session_service(deps, scenario_id="tech_interview_behavioral")
    full = get_session_service(deps, started.session_id)
    assert full["session_id"] == started.session_id
    assert full["opening_text"] == "Hi."
    assert full["turns"] == []


def test_get_session_service_raises_on_unknown(tmp_path):
    from tutor.web.services import get_session_service
    from tutor.web.errors import SessionNotFoundError
    deps = _make_deps(tmp_path)
    with pytest.raises(SessionNotFoundError):
        get_session_service(deps, "does_not_exist")
