def test_no_speech_detected_error_is_exception():
    from tutor.web.errors import NoSpeechDetectedError
    e = NoSpeechDetectedError("empty")
    assert isinstance(e, Exception)


def test_session_not_found_error_carries_id():
    from tutor.web.errors import SessionNotFoundError
    e = SessionNotFoundError("abc12345")
    assert e.session_id == "abc12345"


def test_handler_returns_404_for_scenario_not_found():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from tutor.web.errors import register_exception_handlers
    from tutor.scenarios.loader import ScenarioNotFoundError

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/raise-scenario")
    def _r():
        raise ScenarioNotFoundError("does_not_exist")

    client = TestClient(app)
    r = client.get("/raise-scenario")
    assert r.status_code == 404
    body = r.json()
    assert body["error"] == "scenario_not_found"


def test_handler_returns_429_for_budget():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from tutor.web.errors import register_exception_handlers
    from tutor.budget import BudgetExceededError

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/raise-budget")
    def _r():
        raise BudgetExceededError("cap hit")

    client = TestClient(app)
    r = client.get("/raise-budget")
    assert r.status_code == 429
    body = r.json()
    assert body["error"] == "budget_exhausted"
    assert "cap hit" in body["message"]
