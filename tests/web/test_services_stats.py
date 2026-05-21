from datetime import datetime, date
from unittest.mock import MagicMock


def _deps(tmp_path):
    from tutor.web.deps import Dependencies
    from tutor.budget import BudgetTracker
    from tutor.storage import SessionStorage
    from tutor.srs_engine import SRSEngine

    return Dependencies(
        budget=BudgetTracker(
            path=tmp_path / "b.json", daily_usd_cap=0.5,
            daily_token_cap=200_000,
            now=lambda: datetime(2026, 5, 21, 10, 0),
        ),
        llm=MagicMock(), asr=MagicMock(),
        storage=SessionStorage(root=tmp_path / "sessions",
                                now=lambda: datetime(2026, 5, 21, 10, 0)),
        srs=SRSEngine(path=tmp_path / "cards.json",
                      now=lambda: date(2026, 5, 21)),
        evaluator_model="m1", grader_model="m2",
        tts_model="m3", tts_voice="v1",
    )


def test_stats_service_returns_summary(tmp_path):
    from tutor.web.services import stats_service
    deps = _deps(tmp_path)
    s = stats_service(deps, days=None)
    assert s.sessions_total == 0
    assert s.cards_total == 0
    assert s.streak_days == 0


def test_stats_service_with_days_filter(tmp_path):
    from tutor.web.services import stats_service
    deps = _deps(tmp_path)
    s = stats_service(deps, days=7)
    assert s.sessions_total == 0


def test_budget_service(tmp_path):
    from tutor.web.services import budget_service
    deps = _deps(tmp_path)
    deps.budget.record(tokens_in=10, tokens_out=5, usd_cost=0.001)
    b = budget_service(deps)
    assert b.usd_today > 0
    assert b.tokens_today == 15
    assert b.daily_usd_cap == 0.5
    assert b.daily_token_cap == 200_000
