from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock
import io
import pytest


def _client(tmp_path, mocker):
    from tutor.web.api import create_app
    from tutor.web.deps import Dependencies
    from tutor.budget import BudgetTracker
    from tutor.storage import SessionStorage
    from tutor.srs_engine import SRSEngine
    from datetime import date

    mocker.patch("tutor.web.deps.WhisperASR")  # don't load real model

    fake_llm = MagicMock()
    fake_llm.complete.return_value = "Opening line."
    fake_asr = MagicMock()
    fake_asr.transcribe.return_value = "I led a backend project"

    deps = Dependencies(
        budget=BudgetTracker(
            path=tmp_path / "b.json", daily_usd_cap=1.0,
            daily_token_cap=1_000_000,
            now=lambda: datetime(2026, 5, 21, 10, 0),
        ),
        llm=fake_llm, asr=fake_asr,
        storage=SessionStorage(root=tmp_path / "sessions",
                                now=lambda: datetime(2026, 5, 21, 10, 0)),
        srs=SRSEngine(path=tmp_path / "cards.json",
                      now=lambda: date(2026, 5, 21)),
        evaluator_model="m1", grader_model="m2",
    )
    app = create_app(deps=deps)
    from fastapi.testclient import TestClient
    return TestClient(app), deps


def test_get_scenarios_returns_three(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.get("/api/scenarios")
    assert r.status_code == 200
    ids = [s["id"] for s in r.json()["scenarios"]]
    assert "tech_interview_behavioral" in ids
    assert "daily_standup" in ids
    assert "apartment_rental_abroad" in ids


def test_post_session_creates_and_returns_opening(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.post("/api/sessions", json={"scenario_id": "tech_interview_behavioral"})
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"]
    assert body["opening_text"] == "Opening line."


def test_post_session_unknown_scenario_404(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.post("/api/sessions", json={"scenario_id": "bogus"})
    assert r.status_code == 404
    assert r.json()["error"] == "scenario_not_found"


def test_get_session_returns_full_dict(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.post("/api/sessions", json={"scenario_id": "tech_interview_behavioral"})
    sid = r.json()["session_id"]
    r2 = client.get(f"/api/sessions/{sid}")
    assert r2.status_code == 200
    assert r2.json()["session_id"] == sid
    assert r2.json()["opening_text"] == "Opening line."


def test_get_session_unknown_404(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.get("/api/sessions/does_not_exist")
    assert r.status_code == 404
    assert r.json()["error"] == "session_not_found"


def test_post_turn_uploads_audio_and_returns_reply(tmp_path, mocker):
    client, deps = _client(tmp_path, mocker)
    r = client.post("/api/sessions", json={"scenario_id": "tech_interview_behavioral"})
    sid = r.json()["session_id"]
    deps.llm.complete.return_value = "What was the scope?"

    files = {"audio": ("turn.webm", io.BytesIO(b"fake_audio_bytes"), "audio/webm")}
    r2 = client.post(f"/api/sessions/{sid}/turn", files=files)
    assert r2.status_code == 200
    body = r2.json()
    assert body["user_text"] == "I led a backend project"
    assert body["assistant_text"] == "What was the scope?"


def test_post_turn_unknown_session_404(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    files = {"audio": ("turn.webm", io.BytesIO(b"x"), "audio/webm")}
    r = client.post("/api/sessions/does_not_exist/turn", files=files)
    assert r.status_code == 404


def test_post_turn_empty_asr_422(tmp_path, mocker):
    client, deps = _client(tmp_path, mocker)
    r = client.post("/api/sessions", json={"scenario_id": "tech_interview_behavioral"})
    sid = r.json()["session_id"]
    deps.asr.transcribe.return_value = ""
    files = {"audio": ("turn.webm", io.BytesIO(b"x"), "audio/webm")}
    r2 = client.post(f"/api/sessions/{sid}/turn", files=files)
    assert r2.status_code == 422
    assert r2.json()["error"] == "no_speech_detected"


def test_post_end_no_turns_skips_evaluator(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.post("/api/sessions", json={"scenario_id": "tech_interview_behavioral"})
    sid = r.json()["session_id"]
    r2 = client.post(f"/api/sessions/{sid}/end")
    assert r2.status_code == 200
    body = r2.json()
    assert body["session_id"] == sid
    assert body["growth_points"] == []
    assert body["cards_created"] == []


def test_get_review_due_returns_empty_initially(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.get("/api/review/due")
    assert r.status_code == 200
    assert r.json()["total_due"] == 0
    assert r.json()["cards"] == []


def test_get_stats_returns_summary(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.get("/api/stats")
    assert r.status_code == 200
    body = r.json()
    assert "streak_days" in body
    assert "sessions_total" in body


def test_get_budget_returns_caps(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.get("/api/budget")
    assert r.status_code == 200
    body = r.json()
    assert body["daily_usd_cap"] == 1.0
    assert body["daily_token_cap"] == 1_000_000
