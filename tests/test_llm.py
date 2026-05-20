from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock
import pytest


def _make_response(content: str, prompt_tokens: int, completion_tokens: int, cost: float | None = None):
    """Build an object mimicking the OpenAI SDK response shape."""
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message = MagicMock()
    response.choices[0].message.content = content
    response.usage = MagicMock()
    response.usage.prompt_tokens = prompt_tokens
    response.usage.completion_tokens = completion_tokens
    response.usage.total_tokens = prompt_tokens + completion_tokens
    if cost is not None:
        response.usage.model_extra = {"cost": cost}
    else:
        response.usage.model_extra = {}
    return response


def _make_budget(tmp_path):
    from tutor.budget import BudgetTracker
    return BudgetTracker(
        path=tmp_path / "budget.json",
        daily_usd_cap=1.0,
        daily_token_cap=1_000_000,
        now=lambda: datetime(2026, 5, 20, 12, 0),
    )


def test_llm_complete_returns_text_and_records_usage(tmp_path, mocker):
    from tutor.llm import LLMClient

    budget = _make_budget(tmp_path)
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _make_response(
        content="Hello, candidate.",
        prompt_tokens=100,
        completion_tokens=50,
        cost=0.001,
    )

    llm = LLMClient(
        client=fake_client,
        model="google/gemini-2.5-flash",
        budget=budget,
    )
    reply = llm.complete(messages=[{"role": "user", "content": "Hi"}])

    assert reply == "Hello, candidate."
    assert budget.tokens_today == 150
    assert budget.usd_today == pytest.approx(0.001)


def test_llm_complete_blocks_if_budget_exhausted(tmp_path):
    from tutor.llm import LLMClient
    from tutor.budget import BudgetExceededError, BudgetTracker

    budget = BudgetTracker(
        path=tmp_path / "budget.json",
        daily_usd_cap=0.0001,
        daily_token_cap=1_000_000,
        now=lambda: datetime(2026, 5, 20, 12, 0),
    )
    budget.record(tokens_in=10, tokens_out=10, usd_cost=0.001)  # already over

    llm = LLMClient(
        client=MagicMock(),
        model="google/gemini-2.5-flash",
        budget=budget,
    )
    with pytest.raises(BudgetExceededError):
        llm.complete(messages=[{"role": "user", "content": "Hi"}])


def test_llm_complete_retries_on_5xx(tmp_path, mocker):
    from tutor.llm import LLMClient
    import openai

    budget = _make_budget(tmp_path)
    fake_client = MagicMock()
    error = openai.InternalServerError(
        message="server error",
        response=MagicMock(status_code=500),
        body=None,
    )
    fake_client.chat.completions.create.side_effect = [
        error,
        _make_response("OK", 10, 5, 0.0001),
    ]
    mocker.patch("tutor.llm.time.sleep", return_value=None)

    llm = LLMClient(
        client=fake_client,
        model="google/gemini-2.5-flash",
        budget=budget,
        max_retries=2,
    )
    reply = llm.complete(messages=[{"role": "user", "content": "Hi"}])

    assert reply == "OK"
    assert fake_client.chat.completions.create.call_count == 2


def test_llm_complete_falls_back_to_estimated_cost_when_missing(tmp_path):
    from tutor.llm import LLMClient

    budget = _make_budget(tmp_path)
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _make_response(
        content="Hi",
        prompt_tokens=1000,
        completion_tokens=500,
        cost=None,
    )

    llm = LLMClient(
        client=fake_client,
        model="google/gemini-2.5-flash",
        budget=budget,
    )
    llm.complete(messages=[{"role": "user", "content": "Hi"}])

    assert budget.tokens_today == 1500
    assert budget.usd_today == 0.0


def test_llm_complete_records_cost_from_usage_model_extra(tmp_path):
    """Regression: cost lives inside response.usage.model_extra, NOT response.model_extra.

    If a future refactor moves the lookup back to the top-level response, this test fails.
    """
    from tutor.llm import LLMClient

    budget = _make_budget(tmp_path)
    fake_client = MagicMock()

    # Build the response so that response.model_extra is EMPTY but usage carries the cost.
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message = MagicMock()
    response.choices[0].message.content = "ok"
    response.model_extra = {}  # top-level has no cost
    response.usage = MagicMock()
    response.usage.prompt_tokens = 10
    response.usage.completion_tokens = 5
    response.usage.total_tokens = 15
    response.usage.model_extra = {"cost": 0.0025}

    fake_client.chat.completions.create.return_value = response

    llm = LLMClient(
        client=fake_client,
        model="google/gemini-2.5-flash",
        budget=budget,
    )
    llm.complete(messages=[{"role": "user", "content": "Hi"}])

    assert budget.tokens_today == 15
    assert budget.usd_today == pytest.approx(0.0025)
