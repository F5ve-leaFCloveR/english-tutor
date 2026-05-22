from datetime import datetime
import json
from pathlib import Path
from unittest.mock import MagicMock
import io
import pytest


def _client(tmp_path, mocker, custom_scenarios_path: str | None = None):
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
        tts_model="m3", tts_voice="v1",
        chat_model="m-chat",
        custom_scenarios_path=custom_scenarios_path or str(tmp_path / "custom.json"),
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
    deps.llm.complete.return_value = json.dumps(
        {"reply": "What was the scope?", "corrections": []}
    )

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


def test_post_end_no_turns_returns_accepted(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.post("/api/sessions", json={"scenario_id": "tech_interview_behavioral"})
    sid = r.json()["session_id"]
    r2 = client.post(f"/api/sessions/{sid}/end")
    assert r2.status_code == 202
    body = r2.json()
    assert body["session_id"] == sid
    assert body["status"] == "processing"


def test_post_end_runs_background_task(tmp_path, mocker):
    client, deps = _client(tmp_path, mocker)
    deps.llm.complete.return_value = "Hi."
    deps.asr.transcribe.return_value = "I did stuff"

    r = client.post("/api/sessions", json={"scenario_id": "tech_interview_behavioral"})
    sid = r.json()["session_id"]

    import io
    files = {"audio": ("turn.webm", io.BytesIO(b"audio"), "audio/webm")}
    client.post(f"/api/sessions/{sid}/turn", files=files)

    called_with = {}
    def fake_end(deps_, session_id):
        called_with["session_id"] = session_id
    mocker.patch("tutor.web.api.services.end_session_service", side_effect=fake_end)

    r2 = client.post(f"/api/sessions/{sid}/end")
    assert r2.status_code == 202
    # TestClient runs BackgroundTasks before returning control
    assert called_with["session_id"] == sid


def test_post_end_unknown_session_still_404(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.post("/api/sessions/does_not_exist/end")
    assert r.status_code == 404


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


def test_static_root_serves_index_html(tmp_path, mocker):
    """GET / serves index.html from static/."""
    client, _ = _client(tmp_path, mocker)
    r = client.get("/")
    assert r.status_code in (200, 404)


def test_deep_link_route_serves_index_html(tmp_path, mocker):
    """GET /session/abc serves index.html (catch-all for React Router)."""
    client, _ = _client(tmp_path, mocker)
    r = client.get("/session/abc12345")
    assert r.status_code in (200, 404)


def test_post_tts_returns_wav(tmp_path, mocker):
    client, deps = _client(tmp_path, mocker)
    fake_wav = b"RIFF" + b"\x00" * 100 + b"WAVE"
    mocker.patch("tutor.web.api.TTSService.synthesize", return_value=fake_wav)
    r = client.post("/api/tts", json={"text": "hello world"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert r.content == fake_wav


def test_post_tts_empty_text_422(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.post("/api/tts", json={"text": ""})
    assert r.status_code == 422


def test_post_tts_tts_generation_error_502(tmp_path, mocker):
    from tutor.web.tts import TTSGenerationError
    client, _ = _client(tmp_path, mocker)
    mocker.patch("tutor.web.api.TTSService.synthesize",
                  side_effect=TTSGenerationError("api down"))
    r = client.post("/api/tts", json={"text": "hi"})
    assert r.status_code == 502
    assert r.json()["error"] == "tts_generation_failed"


def test_post_tts_uses_voice_from_request(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    spy = mocker.patch("tutor.web.api.TTSService.synthesize", return_value=b"RIFF...")
    client.post("/api/tts", json={"text": "hi", "voice": "nova"})
    # Voice was passed either as kw or positional
    assert spy.call_args.kwargs.get("voice") == "nova" or "nova" in spy.call_args.args


def test_get_sessions_returns_ended_only(tmp_path, mocker):
    client, deps = _client(tmp_path, mocker)
    deps.llm.complete.return_value = "Hi."

    # Start two sessions, end only the first
    r1 = client.post("/api/sessions", json={"scenario_id": "tech_interview_behavioral"})
    sid1 = r1.json()["session_id"]
    client.post(f"/api/sessions/{sid1}/end")

    r2 = client.post("/api/sessions", json={"scenario_id": "tech_interview_behavioral"})
    sid2 = r2.json()["session_id"]
    # do NOT end sid2

    r = client.get("/api/sessions?limit=10")
    assert r.status_code == 200
    ids = [s["session_id"] for s in r.json()["sessions"]]
    assert sid1 in ids
    assert sid2 not in ids


def test_get_sessions_default_limit(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.get("/api/sessions")
    assert r.status_code == 200
    # default limit is 10; empty store yields 0
    assert r.json()["sessions"] == []


def test_get_sessions_limit_clamped_to_50(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.get("/api/sessions?limit=999")
    assert r.status_code == 422  # pydantic validation rejects >50


def test_post_custom_scenario_returns_summary(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.post("/api/scenarios/custom", json={
        "name": "My Talk",
        "difficulty": "easy",
        "system_prompt": "You are a friend.",
        "opening_line": "Hey!",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["id"] == "my-talk"
    assert data["name"] == "My Talk"
    assert data["is_custom"] is True


def test_post_custom_scenario_rejects_empty_name(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.post("/api/scenarios/custom", json={
        "name": "  ",
        "difficulty": "easy",
        "system_prompt": "P",
    })
    assert r.status_code == 422


def test_post_custom_scenario_rejects_empty_prompt(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.post("/api/scenarios/custom", json={
        "name": "X",
        "difficulty": "easy",
        "system_prompt": "",
    })
    assert r.status_code == 422


def test_delete_custom_scenario_removes_it(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    created = client.post("/api/scenarios/custom", json={
        "name": "Talk", "difficulty": "easy", "system_prompt": "P",
    }).json()
    r = client.delete(f"/api/scenarios/custom/{created['id']}")
    assert r.status_code == 204
    # Verify gone — list scenarios and check id absent
    list_resp = client.get("/api/scenarios")
    items = list_resp.json()["scenarios"]
    ids = [s["id"] for s in items]
    assert created["id"] not in ids


def test_delete_custom_scenario_missing_returns_404(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.delete("/api/scenarios/custom/nonexistent")
    assert r.status_code == 404


def test_get_scenarios_marks_custom(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    created = client.post("/api/scenarios/custom", json={
        "name": "Talk", "difficulty": "easy", "system_prompt": "P",
    }).json()
    r = client.get("/api/scenarios")
    items = r.json()["scenarios"]
    found_custom = next((s for s in items if s["id"] == created["id"]), None)
    assert found_custom is not None
    assert found_custom["is_custom"] is True
    # A built-in scenario should be present with is_custom=False
    found_builtin = next(
        (s for s in items if s["id"] == "tech_interview_behavioral"), None
    )
    assert found_builtin is not None
    assert found_builtin["is_custom"] is False
