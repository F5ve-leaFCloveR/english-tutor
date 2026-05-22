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


def test_end_session_sets_ended_at_first(tmp_path, mocker):
    """Regression: ended_at must be set before SRS card creation."""
    import json
    from tutor.web.services import end_session_service, start_session_service, turn_service
    deps = _make_deps(tmp_path)
    deps.srs = MagicMock()
    deps.llm.complete.return_value = "Opening."
    s = start_session_service(deps, scenario_id="tech_interview_behavioral")

    captured = {}
    def fake_create_cards(growth_points, session_id):
        snapshot = deps.storage.load_session(session_id)
        captured["ended_at"] = snapshot.get("ended_at")
        return []
    deps.srs.create_cards.side_effect = fake_create_cards

    deps.asr.transcribe.return_value = "I goed"
    deps.llm.complete.return_value = json.dumps({
        "reply": "ok",
        "corrections": [{"tag": "grammar", "user_utterance": "I goed",
                         "corrected_version": "I went", "explanation": "Past tense."}],
    })
    turn_service(deps, session_id=s.session_id, audio_bytes=b"...")
    end_session_service(deps, session_id=s.session_id)
    assert captured["ended_at"], "ended_at must be set before create_cards runs"


def test_end_session_aggregates_per_turn_corrections(tmp_path, mocker):
    """End simply unions per-turn corrections into growth_points (no Evaluator call)."""
    import json
    from tutor.web.services import end_session_service, start_session_service, turn_service
    deps = _make_deps(tmp_path)
    deps.llm.complete.return_value = "Opening."
    s = start_session_service(deps, scenario_id="tech_interview_behavioral")

    # Turn 1: 1 correction
    deps.asr.transcribe.return_value = "I goed"
    deps.llm.complete.return_value = json.dumps({
        "reply": "Where?",
        "corrections": [{
            "tag": "grammar", "user_utterance": "I goed",
            "corrected_version": "I went", "explanation": "Past tense.",
        }],
    })
    turn_service(deps, session_id=s.session_id, audio_bytes=b"...")

    # Turn 2: 1 different correction
    deps.asr.transcribe.return_value = "more better"
    deps.llm.complete.return_value = json.dumps({
        "reply": "Interesting.",
        "corrections": [{
            "tag": "grammar", "user_utterance": "more better",
            "corrected_version": "better", "explanation": "'More' redundant with comparative.",
        }],
    })
    turn_service(deps, session_id=s.session_id, audio_bytes=b"...")

    result = end_session_service(deps, session_id=s.session_id)
    assert len(result.growth_points) == 2
    user_utts = [gp["user_utterance"] for gp in result.growth_points]
    assert "I goed" in user_utts
    assert "more better" in user_utts


def test_end_session_dedupes_corrections_by_user_utterance(tmp_path, mocker):
    """Same user_utterance across turns dedupes to one growth_point."""
    import json
    from tutor.web.services import end_session_service, start_session_service, turn_service
    deps = _make_deps(tmp_path)
    deps.llm.complete.return_value = "Opening."
    s = start_session_service(deps, scenario_id="tech_interview_behavioral")

    correction = {
        "tag": "grammar", "user_utterance": "I goed",
        "corrected_version": "I went", "explanation": "Past tense.",
    }
    deps.asr.transcribe.return_value = "I goed there"
    deps.llm.complete.return_value = json.dumps({"reply": "ok", "corrections": [correction]})
    turn_service(deps, session_id=s.session_id, audio_bytes=b"...")

    deps.asr.transcribe.return_value = "I goed home"
    deps.llm.complete.return_value = json.dumps({"reply": "ok", "corrections": [correction]})
    turn_service(deps, session_id=s.session_id, audio_bytes=b"...")

    result = end_session_service(deps, session_id=s.session_id)
    assert len(result.growth_points) == 1


def test_end_session_does_not_call_evaluator(tmp_path, mocker):
    """Regression: Stage 2e drops the separate Evaluator pass."""
    import json
    from tutor.web.services import end_session_service, start_session_service, turn_service
    deps = _make_deps(tmp_path)
    deps.llm.complete.return_value = "Opening."
    s = start_session_service(deps, scenario_id="tech_interview_behavioral")
    deps.asr.transcribe.return_value = "I goed"
    deps.llm.complete.return_value = json.dumps({"reply": "ok", "corrections": []})
    turn_service(deps, session_id=s.session_id, audio_bytes=b"...")

    evaluator_mock = mocker.patch("tutor.web.services.Evaluator")
    end_session_service(deps, session_id=s.session_id)
    evaluator_mock.return_value.evaluate.assert_not_called()


def test_end_session_creates_srs_cards_from_aggregated(tmp_path, mocker):
    """SRS cards created from aggregated per-turn corrections."""
    import json
    from tutor.web.services import end_session_service, start_session_service, turn_service
    deps = _make_deps(tmp_path)
    deps.srs = MagicMock()
    deps.srs.create_cards.return_value = []
    deps.llm.complete.return_value = "Opening."
    s = start_session_service(deps, scenario_id="tech_interview_behavioral")
    deps.asr.transcribe.return_value = "I goed"
    deps.llm.complete.return_value = json.dumps({
        "reply": "ok",
        "corrections": [{
            "tag": "grammar", "user_utterance": "I goed",
            "corrected_version": "I went", "explanation": "Past tense.",
        }],
    })
    turn_service(deps, session_id=s.session_id, audio_bytes=b"...")

    end_session_service(deps, session_id=s.session_id)
    deps.srs.create_cards.assert_called_once()
    args, kwargs = deps.srs.create_cards.call_args
    growth_points_passed = args[0] if args else kwargs.get("growth_points")
    # Argument is a list of GrowthPoint instances
    assert len(growth_points_passed) == 1
    gp = growth_points_passed[0]
    assert gp.user_utterance == "I goed"


def test_end_session_no_cards_when_no_corrections(tmp_path, mocker):
    """Clean session (no per-turn corrections) → no SRS card creation."""
    import json
    from tutor.web.services import end_session_service, start_session_service, turn_service
    deps = _make_deps(tmp_path)
    deps.srs = MagicMock()
    deps.llm.complete.return_value = "Opening."
    s = start_session_service(deps, scenario_id="tech_interview_behavioral")
    deps.asr.transcribe.return_value = "I went to the store."
    deps.llm.complete.return_value = json.dumps({"reply": "Nice.", "corrections": []})
    turn_service(deps, session_id=s.session_id, audio_bytes=b"...")

    end_session_service(deps, session_id=s.session_id)
    deps.srs.create_cards.assert_not_called()


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
