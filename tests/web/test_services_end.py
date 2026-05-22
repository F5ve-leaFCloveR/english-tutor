from datetime import datetime, date
from unittest.mock import MagicMock
import pytest


def _deps(tmp_path):
    from tutor.web.deps import Dependencies
    from tutor.budget import BudgetTracker
    from tutor.storage import SessionStorage
    from tutor.srs_engine import SRSEngine

    return Dependencies(
        budget=BudgetTracker(
            path=tmp_path / "b.json", daily_usd_cap=1.0,
            daily_token_cap=1_000_000,
            now=lambda: datetime(2026, 5, 21, 10, 0),
        ),
        llm=MagicMock(), asr=MagicMock(),
        storage=SessionStorage(root=tmp_path / "sessions",
                                now=lambda: datetime(2026, 5, 21, 10, 0)),
        srs=SRSEngine(path=tmp_path / "cards.json",
                      now=lambda: date(2026, 5, 21)),
        evaluator_model="m1", grader_model="m2",
        tts_model="m3", tts_voice="v1",
    )


def test_end_session_service_happy_path(tmp_path, mocker):
    import json
    from tutor.web.services import start_session_service, turn_service, end_session_service

    deps = _deps(tmp_path)
    deps.llm.complete.return_value = "Hi."
    deps.asr.transcribe.return_value = "I made a project"

    started = start_session_service(deps, scenario_id="tech_interview_behavioral")
    deps.llm.complete.return_value = json.dumps({
        "reply": "Tell me more.",
        "corrections": [{
            "tag": "vocab", "user_utterance": "I made a project",
            "corrected_version": "I led a project",
            "explanation": "led signals ownership",
        }],
    })
    turn_service(deps, started.session_id, audio_bytes=b"x")

    result = end_session_service(deps, session_id=started.session_id)

    assert result.session_id == started.session_id
    assert result.ended_at is not None
    assert len(result.growth_points) == 1
    assert result.growth_points[0]["tag"] == "vocab"
    assert len(result.cards_created) == 1
    assert result.growth_points_error is None


def test_end_session_service_create_cards_raises(tmp_path, mocker):
    """If srs.create_cards fails, growth_points_error is set."""
    import json
    from tutor.web.services import start_session_service, turn_service, end_session_service
    deps = _deps(tmp_path)
    deps.llm.complete.return_value = "Hi."
    deps.asr.transcribe.return_value = "I goed"

    started = start_session_service(deps, scenario_id="tech_interview_behavioral")
    deps.llm.complete.return_value = json.dumps({
        "reply": "ok",
        "corrections": [{
            "tag": "grammar", "user_utterance": "I goed",
            "corrected_version": "I went", "explanation": "past tense",
        }],
    })
    turn_service(deps, started.session_id, audio_bytes=b"x")

    mocker.patch.object(deps.srs, "create_cards", side_effect=RuntimeError("disk full"))
    result = end_session_service(deps, session_id=started.session_id)
    assert result.cards_created == []
    assert "disk full" in (result.growth_points_error or "")


def test_end_session_service_no_turns_skips_card_creation(tmp_path, mocker):
    from tutor.web.services import start_session_service, end_session_service
    deps = _deps(tmp_path)
    deps.llm.complete.return_value = "Hi."

    started = start_session_service(deps, scenario_id="tech_interview_behavioral")

    mocked_create = mocker.patch.object(deps.srs, "create_cards")
    result = end_session_service(deps, session_id=started.session_id)
    assert result.growth_points == []
    assert result.cards_created == []
    mocked_create.assert_not_called()


def test_end_session_service_raises_on_unknown_session(tmp_path):
    from tutor.web.services import end_session_service
    from tutor.web.errors import SessionNotFoundError
    deps = _deps(tmp_path)
    with pytest.raises(SessionNotFoundError):
        end_session_service(deps, session_id="does_not_exist")
