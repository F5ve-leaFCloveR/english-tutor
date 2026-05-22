def test_scenario_summary_schema():
    from tutor.web.schemas import ScenarioSummary
    s = ScenarioSummary(id="x", name="X", difficulty="intermediate")
    assert s.model_dump() == {
        "id": "x",
        "name": "X",
        "difficulty": "intermediate",
        "is_custom": False,
    }


def test_start_session_request_validates():
    from tutor.web.schemas import StartSessionRequest
    import pytest as _p
    StartSessionRequest(scenario_id="x")
    with _p.raises(Exception):
        StartSessionRequest()


def test_turn_result_schema():
    from tutor.web.schemas import TurnResult
    r = TurnResult(user_text="hi", assistant_text="hello")
    assert r.user_text == "hi"
    assert r.assistant_text == "hello"


def test_budget_summary_schema():
    from tutor.web.schemas import BudgetSummary
    b = BudgetSummary(usd_today=0.01, tokens_today=100,
                      daily_usd_cap=0.5, daily_token_cap=200_000)
    assert b.usd_today == 0.01


def test_grade_result_schema():
    from tutor.web.schemas import GradeResult
    g = GradeResult(card_id="c1", user_attempt_text="x", quality=4,
                    target="y", explanation="z", next_due="2026-05-22")
    assert g.quality == 4


def test_tts_request_schema():
    from tutor.web.schemas import TTSRequest
    import pytest as _p
    TTSRequest(text="hello")
    TTSRequest(text="hello", voice="alloy")
    with _p.raises(Exception):
        TTSRequest(text="")  # min_length=1


def test_end_session_accepted_schema():
    from tutor.web.schemas import EndSessionAccepted
    r = EndSessionAccepted(session_id="abc12345")
    assert r.status == "processing"
    assert r.session_id == "abc12345"
