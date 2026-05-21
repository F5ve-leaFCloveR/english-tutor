from datetime import datetime
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
        srs=SRSEngine(path=tmp_path / "cards.json"),
        evaluator_model="m1", grader_model="m2",
        tts_model="m3", tts_voice="v1",
    )


def test_turn_service_happy_path(tmp_path):
    from tutor.web.services import start_session_service, turn_service
    deps = _deps(tmp_path)
    deps.llm.complete.return_value = "What was the project?"
    deps.asr.transcribe.return_value = "I led a backend project"

    started = start_session_service(deps, scenario_id="tech_interview_behavioral")
    deps.llm.complete.reset_mock()
    deps.llm.complete.return_value = "What was the project?"

    result = turn_service(deps, session_id=started.session_id, audio_bytes=b"fake_audio")

    assert result.user_text == "I led a backend project"
    assert result.assistant_text == "What was the project?"

    data = deps.storage.load_session(started.session_id)
    assert len(data["turns"]) == 1
    assert data["turns"][0]["user_text"] == "I led a backend project"
    assert data["turns"][0]["llm_text"] == "What was the project?"


def test_turn_service_raises_on_unknown_session(tmp_path):
    from tutor.web.services import turn_service
    from tutor.web.errors import SessionNotFoundError
    deps = _deps(tmp_path)
    with pytest.raises(SessionNotFoundError):
        turn_service(deps, session_id="does_not_exist", audio_bytes=b"x")


def test_turn_service_raises_on_empty_asr(tmp_path):
    from tutor.web.services import start_session_service, turn_service
    from tutor.web.errors import NoSpeechDetectedError
    deps = _deps(tmp_path)
    deps.llm.complete.return_value = "Hi."
    deps.asr.transcribe.return_value = ""

    started = start_session_service(deps, scenario_id="tech_interview_behavioral")
    with pytest.raises(NoSpeechDetectedError):
        turn_service(deps, session_id=started.session_id, audio_bytes=b"silence")


def test_turn_service_builds_full_history_for_llm(tmp_path):
    from tutor.web.services import start_session_service, turn_service
    deps = _deps(tmp_path)
    deps.llm.complete.return_value = "Opening."
    deps.asr.transcribe.return_value = "First user reply"

    started = start_session_service(deps, scenario_id="tech_interview_behavioral")
    deps.llm.complete.reset_mock()
    deps.llm.complete.return_value = "Reply 1"
    turn_service(deps, session_id=started.session_id, audio_bytes=b"x")

    deps.llm.complete.reset_mock()
    deps.llm.complete.return_value = "Reply 2"
    deps.asr.transcribe.return_value = "Second user reply"
    turn_service(deps, session_id=started.session_id, audio_bytes=b"y")

    call_kwargs = deps.llm.complete.call_args.kwargs
    messages = call_kwargs["messages"]
    # system + assistant(opening) + user(first) + assistant(reply1) + user(second) = 5
    assert len(messages) == 5
    roles = [m["role"] for m in messages]
    assert roles == ["system", "assistant", "user", "assistant", "user"]
