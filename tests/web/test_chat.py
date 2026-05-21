from datetime import date, datetime
import json
from unittest.mock import MagicMock


def _client(tmp_path, mocker):
    """Build a TestClient with all dependencies stubbed.

    Mirrors the helper in tests/web/test_api.py; adds chat_model="m-chat" so the
    new /api/chat route has a model to pass through to the LLM.
    """
    from fastapi.testclient import TestClient

    from tutor.budget import BudgetTracker
    from tutor.srs_engine import SRSEngine
    from tutor.storage import SessionStorage
    from tutor.web.api import create_app
    from tutor.web.deps import Dependencies

    mocker.patch("tutor.web.deps.WhisperASR")  # don't load real model

    fake_llm = MagicMock()
    fake_asr = MagicMock()

    deps = Dependencies(
        budget=BudgetTracker(
            path=tmp_path / "b.json",
            daily_usd_cap=1.0,
            daily_token_cap=1_000_000,
            now=lambda: datetime(2026, 5, 21, 10, 0),
        ),
        llm=fake_llm,
        asr=fake_asr,
        storage=SessionStorage(
            root=tmp_path / "sessions",
            now=lambda: datetime(2026, 5, 21, 10, 0),
        ),
        srs=SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21)),
        evaluator_model="m1",
        grader_model="m2",
        tts_model="m3",
        tts_voice="v1",
        chat_model="m-chat",
    )
    app = create_app(deps=deps)
    return TestClient(app), deps


def test_post_chat_returns_reply_and_corrections(tmp_path, mocker):
    client, deps = _client(tmp_path, mocker)
    deps.llm.complete.return_value = json.dumps(
        {
            "reply": "That's interesting!",
            "corrections": [
                {
                    "tag": "grammar",
                    "user_utterance": "I readed",
                    "corrected_version": "I read",
                    "explanation": "Past tense of read is irregular.",
                }
            ],
        }
    )
    r = client.post("/api/chat", json={"history": [], "message": "I readed a book"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["reply"] == "That's interesting!"
    assert len(data["corrections"]) == 1
    assert data["corrections"][0]["tag"] == "grammar"


def test_post_chat_passes_history_to_llm(tmp_path, mocker):
    client, deps = _client(tmp_path, mocker)
    deps.llm.complete.return_value = json.dumps({"reply": "ok", "corrections": []})
    history = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi!"},
    ]
    r = client.post(
        "/api/chat", json={"history": history, "message": "How are you?"}
    )
    assert r.status_code == 200, r.text
    call_kwargs = deps.llm.complete.call_args.kwargs
    msgs = call_kwargs["messages"]
    assert any(m["role"] == "user" and m["content"] == "Hello" for m in msgs)
    assert any(m["role"] == "assistant" and m["content"] == "Hi!" for m in msgs)
    assert msgs[-1] == {"role": "user", "content": "How are you?"}


def test_post_chat_rejects_empty_message(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.post("/api/chat", json={"history": [], "message": ""})
    assert r.status_code == 422
