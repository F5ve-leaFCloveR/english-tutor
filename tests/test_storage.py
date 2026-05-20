import json
from datetime import datetime
from pathlib import Path


def test_storage_creates_session_file(tmp_path):
    from tutor.storage import SessionStorage

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 20, 14, 30, 5))
    session_id = storage.create_session(scenario_id="tech_interview_behavioral")
    assert session_id  # truthy

    sessions = list(tmp_path.rglob("*.json"))
    assert len(sessions) == 1
    data = json.loads(sessions[0].read_text())
    assert data["scenario_id"] == "tech_interview_behavioral"
    assert data["started_at"].startswith("2026-05-20T14:30")
    assert data["turns"] == []


def test_storage_appends_turn(tmp_path):
    from tutor.storage import SessionStorage

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 20, 14, 30, 5))
    session_id = storage.create_session("tech_interview_behavioral")
    storage.append_turn(session_id, user_text="Hi, I'm a candidate.", llm_text="Welcome.")
    storage.append_turn(session_id, user_text="Thanks.", llm_text="Let's begin.")

    data = storage.load_session(session_id)
    assert len(data["turns"]) == 2
    assert data["turns"][0]["user_text"] == "Hi, I'm a candidate."
    assert data["turns"][1]["llm_text"] == "Let's begin."


def test_storage_marks_session_ended(tmp_path):
    from tutor.storage import SessionStorage

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 20, 14, 30, 5))
    session_id = storage.create_session("tech_interview_behavioral")
    storage.end_session(session_id)

    data = storage.load_session(session_id)
    assert data["ended_at"] is not None
