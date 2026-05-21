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


def test_storage_list_sessions_returns_all_sorted(tmp_path):
    from tutor.storage import SessionStorage
    from datetime import datetime

    times = [
        datetime(2026, 5, 19, 9, 0),
        datetime(2026, 5, 21, 14, 0),
        datetime(2026, 5, 20, 11, 0),
    ]
    for t in times:
        s = SessionStorage(root=tmp_path, now=lambda t=t: t)
        s.create_session("tech_interview_behavioral")

    reader = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 15, 0))
    sessions = reader.list_sessions()
    assert len(sessions) == 3
    started_dates = [s["started_at"][:10] for s in sessions]
    assert started_dates == ["2026-05-21", "2026-05-20", "2026-05-19"]


def test_storage_list_sessions_skips_corrupt_files(tmp_path, caplog):
    from tutor.storage import SessionStorage
    from datetime import datetime
    import logging

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 10, 0))
    storage.create_session("tech_interview_behavioral")

    corrupt = tmp_path / "2026-05-21" / "corrupt_id.json"
    corrupt.write_text("{ not json")

    with caplog.at_level(logging.WARNING):
        sessions = storage.list_sessions()
    assert len(sessions) == 1
    assert any("corrupt_id" in r.message or "corrupt" in r.message.lower()
               for r in caplog.records)


def test_storage_list_sessions_empty_when_no_sessions(tmp_path):
    from tutor.storage import SessionStorage
    from datetime import datetime

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 10, 0))
    assert storage.list_sessions() == []


def test_storage_create_session_no_opening_text_by_default(tmp_path):
    from tutor.storage import SessionStorage
    from datetime import datetime

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 10, 0))
    session_id = storage.create_session("tech_interview_behavioral")
    data = storage.load_session(session_id)
    assert data.get("opening_text") is None


def test_storage_set_opening_text_persists(tmp_path):
    from tutor.storage import SessionStorage
    from datetime import datetime

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 10, 0))
    session_id = storage.create_session("tech_interview_behavioral")
    storage.set_opening_text(session_id, "Hi, tell me about a project.")
    data = storage.load_session(session_id)
    assert data["opening_text"] == "Hi, tell me about a project."
