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


def test_storage_write_is_atomic(tmp_path, mocker):
    """Regression: crash during _write must leave either old or new content, never partial."""
    from tutor.storage import SessionStorage
    from datetime import datetime

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 10, 0))
    session_id = storage.create_session(scenario_id="tech_interview_behavioral")

    session_path = next(tmp_path.rglob(f"{session_id}.json"))

    import os
    original_replace = os.replace
    rename_was_called = []

    def spy_replace(src, dst):
        rename_was_called.append((str(src), str(dst)))
        return original_replace(src, dst)

    mocker.patch("os.replace", side_effect=spy_replace)
    storage.append_turn(session_id, user_text="hi", llm_text="hello")
    assert len(rename_was_called) >= 1
    src, dst = rename_was_called[-1]
    assert dst == str(session_path)
    assert src.endswith(".json.tmp") or src.endswith(".tmp")


def test_storage_write_cleans_up_tmp_on_failure(tmp_path, mocker):
    """Regression: failed write must not leave an orphan .tmp file."""
    from tutor.storage import SessionStorage
    from datetime import datetime
    import pytest

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 10, 0))
    session_id = storage.create_session(scenario_id="tech_interview_behavioral")
    session_path = next(tmp_path.rglob(f"{session_id}.json"))

    # Force the write to fail by patching os.replace
    mocker.patch("os.replace", side_effect=OSError("simulated rename failure"))

    with pytest.raises(OSError):
        storage.append_turn(session_id, user_text="hi", llm_text="hello")

    # The original session file is still there
    assert session_path.exists()
    # No orphan .tmp file remains
    tmp_files = list(session_path.parent.glob("*.tmp"))
    assert tmp_files == [], f"orphan tmp files: {tmp_files}"


def test_storage_persists_growth_points(tmp_path):
    from tutor.storage import SessionStorage
    from datetime import datetime

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 10, 0))
    session_id = storage.create_session("tech_interview_behavioral")
    storage.set_growth_points(session_id, [
        {"tag": "vocab", "user_utterance": "I made a project", "corrected_version": "I led a project",
         "explanation": "Led signals ownership.", "context": None},
    ])
    data = storage.load_session(session_id)
    assert len(data["growth_points"]) == 1
    assert data["growth_points"][0]["tag"] == "vocab"


def test_storage_persists_growth_points_error(tmp_path):
    from tutor.storage import SessionStorage
    from datetime import datetime

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 10, 0))
    session_id = storage.create_session("tech_interview_behavioral")
    storage.set_growth_points_error(session_id, "parse failed")
    data = storage.load_session(session_id)
    assert data["growth_points_error"] == "parse failed"


def test_storage_persists_cards_created(tmp_path):
    from tutor.storage import SessionStorage
    from datetime import datetime

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 10, 0))
    session_id = storage.create_session("tech_interview_behavioral")
    storage.set_cards_created(session_id, ["card_abc12345", "card_def67890"])
    data = storage.load_session(session_id)
    assert data["cards_created"] == ["card_abc12345", "card_def67890"]
