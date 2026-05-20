from unittest.mock import MagicMock
from pathlib import Path
import pytest


def _stub_adapters(turn_user_texts, turn_llm_replies):
    """Build mock LLM/ASR/TTS/recorder that replay the given turns."""
    llm = MagicMock()
    llm.complete.side_effect = turn_llm_replies

    asr = MagicMock()
    asr.transcribe.side_effect = turn_user_texts

    tts = MagicMock()

    recorder = MagicMock()
    recorder.record_to_wav.side_effect = [Path(f"/tmp/fake_{i}.wav") for i in range(50)]

    return llm, asr, tts, recorder


def test_session_runs_three_turns_then_user_ends(tmp_path, mocker):
    from tutor.session import SessionOrchestrator
    from tutor.storage import SessionStorage
    from tutor.scenarios.loader import load_scenario

    user_inputs = iter(["go", "go", "go", "end"])
    mocker.patch("builtins.input", side_effect=lambda *_a, **_kw: next(user_inputs))

    llm, asr, tts, recorder = _stub_adapters(
        turn_user_texts=["I led a project.", "It was hard.", "I learned a lot."],
        turn_llm_replies=[
            "Hi, tell me about yourself.",
            "What was the project?",
            "What made it hard?",
            "What did you learn?",
        ],
    )

    storage = SessionStorage(root=tmp_path)
    orch = SessionOrchestrator(
        llm=llm,
        asr=asr,
        tts=tts,
        recorder=recorder,
        storage=storage,
        scenario=load_scenario("tech_interview_behavioral"),
        per_session_turn_limit=25,
    )
    session_id = orch.run()

    data = storage.load_session(session_id)
    assert len(data["turns"]) == 3
    assert data["ended_at"] is not None
    assert tts.speak.call_count == 4


def test_session_stops_at_turn_limit(tmp_path, mocker):
    from tutor.session import SessionOrchestrator
    from tutor.storage import SessionStorage
    from tutor.scenarios.loader import load_scenario

    mocker.patch("builtins.input", side_effect=lambda *_a, **_kw: "go")

    llm, asr, tts, recorder = _stub_adapters(
        turn_user_texts=["hi"] * 100,
        turn_llm_replies=["opening"] + ["reply"] * 100,
    )

    storage = SessionStorage(root=tmp_path)
    orch = SessionOrchestrator(
        llm=llm, asr=asr, tts=tts, recorder=recorder, storage=storage,
        scenario=load_scenario("tech_interview_behavioral"),
        per_session_turn_limit=2,
    )
    session_id = orch.run()

    data = storage.load_session(session_id)
    assert len(data["turns"]) == 2


def test_session_stops_on_budget_exceeded(tmp_path, mocker):
    from tutor.session import SessionOrchestrator
    from tutor.storage import SessionStorage
    from tutor.scenarios.loader import load_scenario
    from tutor.budget import BudgetExceededError

    mocker.patch("builtins.input", side_effect=lambda *_a, **_kw: "go")

    llm, asr, tts, recorder = _stub_adapters(
        turn_user_texts=["hi", "hi"],
        turn_llm_replies=[
            "opening",
            BudgetExceededError("daily cap hit"),
        ],
    )

    storage = SessionStorage(root=tmp_path)
    orch = SessionOrchestrator(
        llm=llm, asr=asr, tts=tts, recorder=recorder, storage=storage,
        scenario=load_scenario("tech_interview_behavioral"),
        per_session_turn_limit=25,
    )
    session_id = orch.run()

    data = storage.load_session(session_id)
    assert data["ended_at"] is not None
    assert len(data["turns"]) <= 1


def test_session_builds_system_prompt_once(tmp_path, mocker):
    from tutor.session import SessionOrchestrator
    from tutor.storage import SessionStorage
    from tutor.scenarios.loader import load_scenario

    mocker.patch("builtins.input", side_effect=lambda *_a, **_kw: "end")

    llm, asr, tts, recorder = _stub_adapters(
        turn_user_texts=[],
        turn_llm_replies=["Hi, tell me about yourself."],
    )

    storage = SessionStorage(root=tmp_path)
    orch = SessionOrchestrator(
        llm=llm, asr=asr, tts=tts, recorder=recorder, storage=storage,
        scenario=load_scenario("tech_interview_behavioral"),
        per_session_turn_limit=25,
    )
    orch.run()

    first_call = llm.complete.call_args_list[0]
    messages = first_call.kwargs.get("messages") or first_call.args[0]
    assert messages[0]["role"] == "system"
    assert "Russian" in messages[0]["content"]
