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


def test_session_runs_evaluator_and_creates_cards(tmp_path, mocker):
    from tutor.session import SessionOrchestrator
    from tutor.storage import SessionStorage
    from tutor.scenarios.loader import load_scenario
    from tutor.evaluator import GrowthPoint

    mocker.patch("builtins.input", side_effect=["go", "end"])
    llm, asr, tts, recorder = _stub_adapters(
        turn_user_texts=["I made a project."],
        turn_llm_replies=["Opening line.", "What project?"],
    )

    fake_evaluator = MagicMock()
    fake_evaluator.evaluate.return_value = [
        GrowthPoint(tag="vocab", user_utterance="I made a project.",
                    corrected_version="I led a project.",
                    explanation="Led signals ownership.", context=None),
    ]
    fake_srs = MagicMock()
    fake_card = MagicMock()
    fake_card.id = "card_xyz"
    fake_srs.create_cards.return_value = [fake_card]

    storage = SessionStorage(root=tmp_path)
    orch = SessionOrchestrator(
        llm=llm, asr=asr, tts=tts, recorder=recorder, storage=storage,
        scenario=load_scenario("tech_interview_behavioral"),
        per_session_turn_limit=25,
        evaluator=fake_evaluator,
        srs_engine=fake_srs,
    )
    session_id = orch.run()

    fake_evaluator.evaluate.assert_called_once()
    fake_srs.create_cards.assert_called_once()
    data = storage.load_session(session_id)
    assert data["growth_points"] == [
        {"tag": "vocab", "user_utterance": "I made a project.",
         "corrected_version": "I led a project.", "explanation": "Led signals ownership.",
         "context": None}
    ]
    assert data["cards_created"] == ["card_xyz"]


def test_session_evaluator_returns_empty_no_cards_created(tmp_path, mocker):
    """If evaluator returns empty list (parse fail / API error), session ends cleanly without cards."""
    from tutor.session import SessionOrchestrator
    from tutor.storage import SessionStorage
    from tutor.scenarios.loader import load_scenario

    # One turn happens, then end
    mocker.patch("builtins.input", side_effect=["", "end"])
    llm, asr, tts, recorder = _stub_adapters(
        turn_user_texts=["hi"],
        turn_llm_replies=["Opening.", "Reply."],
    )

    fake_evaluator = MagicMock()
    fake_evaluator.evaluate.return_value = []  # eval failed silently
    fake_srs = MagicMock()

    storage = SessionStorage(root=tmp_path)
    orch = SessionOrchestrator(
        llm=llm, asr=asr, tts=tts, recorder=recorder, storage=storage,
        scenario=load_scenario("tech_interview_behavioral"),
        per_session_turn_limit=25,
        evaluator=fake_evaluator,
        srs_engine=fake_srs,
    )
    session_id = orch.run()
    data = storage.load_session(session_id)
    assert data["ended_at"] is not None
    fake_evaluator.evaluate.assert_called_once()
    fake_srs.create_cards.assert_not_called()


def test_session_works_without_evaluator(tmp_path, mocker):
    """Backwards compatible: evaluator and srs_engine are optional."""
    from tutor.session import SessionOrchestrator
    from tutor.storage import SessionStorage
    from tutor.scenarios.loader import load_scenario

    mocker.patch("builtins.input", side_effect=["end"])
    llm, asr, tts, recorder = _stub_adapters(
        turn_user_texts=[],
        turn_llm_replies=["Hi."],
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
    assert "growth_points" not in data


def test_session_opening_budget_exhausted_exits_cleanly(tmp_path, mocker, capsys):
    """Regression (polish): opening LLM call BudgetExceededError must not produce a traceback."""
    from tutor.session import SessionOrchestrator
    from tutor.storage import SessionStorage
    from tutor.scenarios.loader import load_scenario
    from tutor.budget import BudgetExceededError

    mocker.patch("builtins.input", side_effect=[])  # input never called
    llm, asr, tts, recorder = _stub_adapters(
        turn_user_texts=[],
        turn_llm_replies=[BudgetExceededError("daily cap already hit before opening")],
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
    captured = capsys.readouterr()
    assert "budget" in captured.out.lower()
    assert "Traceback" not in captured.out


def test_session_cleans_up_temp_wavs(tmp_path, mocker):
    """Regression (polish): temp WAV files created during session must be removed in finally."""
    from tutor.session import SessionOrchestrator
    from tutor.storage import SessionStorage
    from tutor.scenarios.loader import load_scenario
    import os, tempfile, glob

    # Snapshot of existing tutor_turn_* files before the test
    pattern = os.path.join(tempfile.gettempdir(), "tutor_turn_*.wav")
    before = set(glob.glob(pattern))

    mocker.patch("builtins.input", side_effect=["", "", "end"])
    llm, asr, tts, recorder = _stub_adapters(
        turn_user_texts=["hi", "hello"],
        turn_llm_replies=["Opening.", "R1.", "R2."],
    )

    # Make recorder actually create the file so cleanup has something to remove
    def real_create(path):
        from pathlib import Path
        Path(path).write_bytes(b"")
        return path
    recorder.record_to_wav.side_effect = real_create

    storage = SessionStorage(root=tmp_path)
    orch = SessionOrchestrator(
        llm=llm, asr=asr, tts=tts, recorder=recorder, storage=storage,
        scenario=load_scenario("tech_interview_behavioral"),
        per_session_turn_limit=25,
    )
    orch.run()

    after = set(glob.glob(pattern))
    new_files = after - before
    assert new_files == set(), f"orphan temp WAVs left: {new_files}"
