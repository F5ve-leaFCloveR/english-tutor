from datetime import datetime, timedelta
from pathlib import Path
import json
import pytest


def test_budget_records_usage(tmp_path):
    from tutor.budget import BudgetTracker
    bt = BudgetTracker(
        path=tmp_path / "budget.json",
        daily_usd_cap=0.5,
        daily_token_cap=200_000,
        now=lambda: datetime(2026, 5, 20, 12, 0),
    )
    bt.record(tokens_in=1000, tokens_out=500, usd_cost=0.002)
    assert bt.tokens_today == 1500
    assert bt.usd_today == pytest.approx(0.002)


def test_budget_blocks_when_usd_exceeded(tmp_path):
    from tutor.budget import BudgetTracker, BudgetExceededError
    bt = BudgetTracker(
        path=tmp_path / "budget.json",
        daily_usd_cap=0.01,
        daily_token_cap=200_000,
        now=lambda: datetime(2026, 5, 20, 12, 0),
    )
    bt.record(tokens_in=1000, tokens_out=500, usd_cost=0.02)
    with pytest.raises(BudgetExceededError, match="USD"):
        bt.check_can_spend()


def test_budget_blocks_when_tokens_exceeded(tmp_path):
    from tutor.budget import BudgetTracker, BudgetExceededError
    bt = BudgetTracker(
        path=tmp_path / "budget.json",
        daily_usd_cap=0.5,
        daily_token_cap=1000,
        now=lambda: datetime(2026, 5, 20, 12, 0),
    )
    bt.record(tokens_in=600, tokens_out=500, usd_cost=0.001)
    with pytest.raises(BudgetExceededError, match="token"):
        bt.check_can_spend()


def test_budget_resets_on_new_day(tmp_path):
    from tutor.budget import BudgetTracker
    path = tmp_path / "budget.json"
    bt = BudgetTracker(
        path=path,
        daily_usd_cap=0.5,
        daily_token_cap=200_000,
        now=lambda: datetime(2026, 5, 20, 23, 0),
    )
    bt.record(tokens_in=1000, tokens_out=500, usd_cost=0.4)
    # next day, fresh tracker reading the same file
    bt2 = BudgetTracker(
        path=path,
        daily_usd_cap=0.5,
        daily_token_cap=200_000,
        now=lambda: datetime(2026, 5, 21, 1, 0),
    )
    assert bt2.tokens_today == 0
    assert bt2.usd_today == 0.0


def test_budget_persists_across_instances(tmp_path):
    from tutor.budget import BudgetTracker
    path = tmp_path / "budget.json"
    bt = BudgetTracker(
        path=path,
        daily_usd_cap=0.5,
        daily_token_cap=200_000,
        now=lambda: datetime(2026, 5, 20, 12, 0),
    )
    bt.record(tokens_in=1000, tokens_out=500, usd_cost=0.1)
    bt2 = BudgetTracker(
        path=path,
        daily_usd_cap=0.5,
        daily_token_cap=200_000,
        now=lambda: datetime(2026, 5, 20, 13, 0),
    )
    assert bt2.tokens_today == 1500
    assert bt2.usd_today == pytest.approx(0.1)
