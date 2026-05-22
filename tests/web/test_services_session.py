from datetime import datetime
import json
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
        chat_model="m-chat",
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


def test_list_sessions_service_returns_ended_only(tmp_path):
    from tutor.web.services import list_sessions_service, start_session_service, end_session_service
    deps = _make_deps(tmp_path)
    deps.llm.complete.return_value = "Hi."

    s1 = start_session_service(deps, scenario_id="tech_interview_behavioral")
    # Note: end_session_service requires evaluator dependency; we just call
    # storage.end_session directly to simulate "ended" without evaluator side-effects
    deps.storage.end_session(s1.session_id)

    # Second session — NOT ended
    s2 = start_session_service(deps, scenario_id="tech_interview_behavioral")

    result = list_sessions_service(deps, limit=10)
    ids = [s["session_id"] for s in result]
    assert s1.session_id in ids
    assert s2.session_id not in ids


def test_list_sessions_service_respects_limit(tmp_path):
    from tutor.web.services import list_sessions_service, start_session_service
    deps = _make_deps(tmp_path)
    deps.llm.complete.return_value = "Hi."

    ids = []
    for _ in range(5):
        s = start_session_service(deps, scenario_id="tech_interview_behavioral")
        deps.storage.end_session(s.session_id)
        ids.append(s.session_id)

    result = list_sessions_service(deps, limit=2)
    assert len(result) == 2


def test_list_sessions_service_empty_when_none(tmp_path):
    from tutor.web.services import list_sessions_service
    deps = _make_deps(tmp_path)
    assert list_sessions_service(deps, limit=10) == []


def test_end_session_persists_empty_growth_points_when_evaluator_returns_empty(tmp_path, mocker):
    """Regression: clean sessions (no corrections) must still mark analysis done.

    Frontend distinguishes "analyzing" from "clean" by presence of `growth_points`
    field. If we never write the field, the page polls forever.
    """
    from tutor.web.services import end_session_service, start_session_service, turn_service
    deps = _make_deps(tmp_path)
    deps.llm.complete.return_value = "Hi."

    s = start_session_service(deps, scenario_id="tech_interview_behavioral")
    # Add one turn so the evaluator path runs
    deps.asr.transcribe.return_value = "I work in IT"
    deps.llm.complete.return_value = json.dumps({"reply": "Great.", "corrections": []})
    turn_service(deps, session_id=s.session_id, audio_bytes=b"...")

    # Patch the Evaluator to return empty growth_points
    mocker.patch("tutor.web.services.Evaluator").return_value.evaluate.return_value = []

    end_session_service(deps, session_id=s.session_id)
    final = deps.storage.load_session(s.session_id)
    assert "growth_points" in final
    assert final["growth_points"] == []
    assert final.get("growth_points_error") in (None, "")


def test_end_session_persists_empty_growth_points_for_zero_turn_session(tmp_path, mocker):
    """0-turn session: skipping the evaluator must still mark analysis done."""
    from tutor.web.services import end_session_service, start_session_service
    deps = _make_deps(tmp_path)
    deps.llm.complete.return_value = "Hi."

    s = start_session_service(deps, scenario_id="tech_interview_behavioral")
    # No turns added — go straight to end_session
    end_session_service(deps, session_id=s.session_id)

    final = deps.storage.load_session(s.session_id)
    assert "growth_points" in final
    assert final["growth_points"] == []


def test_end_session_sets_ended_at_before_evaluator_runs(tmp_path, mocker):
    """Regression: frontend shows just-ended session as 'Analyzing' immediately.

    If `storage.end_session(id)` is called AFTER the evaluator, the session is
    invisible in /review during the evaluator's 5-10s run. We want the session
    to appear as soon as it ends — with growth_points still missing — so /review
    shows the Analyzing state, then transitions to ready.
    """
    from tutor.web.services import end_session_service, start_session_service, turn_service
    deps = _make_deps(tmp_path)

    deps.llm.complete.return_value = "Hi."
    s = start_session_service(deps, scenario_id="tech_interview_behavioral")
    deps.asr.transcribe.return_value = "I work in IT"
    deps.llm.complete.return_value = json.dumps({"reply": "Great.", "corrections": []})
    turn_service(deps, session_id=s.session_id, audio_bytes=b"...")

    # Capture storage state at the moment the evaluator runs
    captured = {}
    def fake_evaluate(transcript):
        snapshot = deps.storage.load_session(s.session_id)
        captured["ended_at"] = snapshot.get("ended_at")
        return []
    mocker.patch("tutor.web.services.Evaluator").return_value.evaluate.side_effect = fake_evaluate

    end_session_service(deps, session_id=s.session_id)

    assert captured["ended_at"], (
        f"ended_at should be set BEFORE the evaluator runs, got {captured['ended_at']!r}"
    )


def test_end_session_writes_error_when_setup_raises(tmp_path, mocker):
    """Regression: if load_scenario or other pre-evaluator setup raises, the session
    must still get growth_points_error written so it doesn't stay Analyzing forever.
    """
    from tutor.web.services import end_session_service, start_session_service, turn_service
    deps = _make_deps(tmp_path)
    deps.llm.complete.return_value = "Hi."

    s = start_session_service(deps, scenario_id="tech_interview_behavioral")
    deps.asr.transcribe.return_value = "I work in IT"
    deps.llm.complete.return_value = json.dumps({"reply": "Great.", "corrections": []})
    turn_service(deps, session_id=s.session_id, audio_bytes=b"...")

    # Simulate a non-evaluator exception (e.g., load_scenario blowing up)
    mocker.patch("tutor.web.services.load_scenario", side_effect=RuntimeError("scenario gone"))

    end_session_service(deps, session_id=s.session_id)
    final = deps.storage.load_session(s.session_id)

    assert final.get("ended_at")
    assert final.get("growth_points_error")
    assert "scenario gone" in final["growth_points_error"]


def test_turn_service_returns_corrections_in_result(tmp_path, mocker):
    """turn_service now uses ChatTurn — TurnResult includes per-turn corrections."""
    from tutor.web.services import turn_service, start_session_service
    deps = _make_deps(tmp_path)
    # start_session_service uses plain LLM (returns string)
    deps.llm.complete.return_value = "Opening."
    s = start_session_service(deps, scenario_id="tech_interview_behavioral")

    # Now configure LLM to return ChatTurn JSON for the turn
    deps.asr.transcribe.return_value = "I goed there"
    deps.llm.complete.return_value = json.dumps({
        "reply": "Where did you go?",
        "corrections": [{
            "tag": "grammar",
            "user_utterance": "I goed",
            "corrected_version": "I went",
            "explanation": "Past tense of 'go' is 'went'.",
        }],
    })
    result = turn_service(deps, session_id=s.session_id, audio_bytes=b"...")
    assert result.user_text == "I goed there"
    assert result.assistant_text == "Where did you go?"
    assert len(result.corrections) == 1
    assert result.corrections[0]["tag"] == "grammar"
    assert result.corrections[0]["corrected_version"] == "I went"


def test_turn_service_persists_corrections_in_storage(tmp_path, mocker):
    """The turn dict in session.json has a corrections field after the turn."""
    from tutor.web.services import turn_service, start_session_service
    deps = _make_deps(tmp_path)
    deps.llm.complete.return_value = "Opening."
    s = start_session_service(deps, scenario_id="tech_interview_behavioral")

    deps.asr.transcribe.return_value = "I goed"
    deps.llm.complete.return_value = json.dumps({
        "reply": "Where?",
        "corrections": [{
            "tag": "grammar",
            "user_utterance": "I goed",
            "corrected_version": "I went",
            "explanation": "Past tense.",
        }],
    })
    turn_service(deps, session_id=s.session_id, audio_bytes=b"...")
    data = deps.storage.load_session(s.session_id)
    assert len(data["turns"]) == 1
    assert data["turns"][0]["corrections"][0]["corrected_version"] == "I went"


def test_turn_service_handles_empty_corrections(tmp_path, mocker):
    """Clean message: LLM returns []. Turn still saves, corrections stored as empty list."""
    from tutor.web.services import turn_service, start_session_service
    deps = _make_deps(tmp_path)
    deps.llm.complete.return_value = "Opening."
    s = start_session_service(deps, scenario_id="tech_interview_behavioral")

    deps.asr.transcribe.return_value = "I went to the store."
    deps.llm.complete.return_value = json.dumps({
        "reply": "What did you buy?",
        "corrections": [],
    })
    result = turn_service(deps, session_id=s.session_id, audio_bytes=b"...")
    assert result.corrections == []
    data = deps.storage.load_session(s.session_id)
    assert data["turns"][0]["corrections"] == []
