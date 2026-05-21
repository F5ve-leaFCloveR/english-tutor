from datetime import datetime
from unittest.mock import MagicMock
import pytest


def _make_budget(tmp_path):
    from tutor.budget import BudgetTracker
    return BudgetTracker(
        path=tmp_path / "budget.json",
        daily_usd_cap=1.0,
        daily_token_cap=1_000_000,
        now=lambda: datetime(2026, 5, 21, 12, 0),
    )


def _stub_llm(content: str, tmp_path):
    from tutor.llm import LLMClient
    client = MagicMock()
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message = MagicMock()
    resp.choices[0].message.content = content
    resp.usage = MagicMock(prompt_tokens=50, completion_tokens=1, total_tokens=51, model_extra={})
    client.chat.completions.create.return_value = resp
    budget = _make_budget(tmp_path)
    return LLMClient(client=client, model="google/gemini-2.5-flash", budget=budget)


def test_grader_returns_clean_integer(tmp_path):
    from tutor.grader import LLMGrader
    llm = _stub_llm("4", tmp_path)
    grader = LLMGrader(llm=llm, model="google/gemini-2.5-flash")
    score = grader.grade(target="I led a project.", attempt="I led the project.")
    assert score == 4


def test_grader_parses_integer_from_verbose_response(tmp_path):
    from tutor.grader import LLMGrader
    llm = _stub_llm("Score: 3 out of 5", tmp_path)
    grader = LLMGrader(llm=llm, model="google/gemini-2.5-flash")
    score = grader.grade(target="x", attempt="y")
    assert score == 3


def test_grader_defaults_to_3_on_unparseable(tmp_path):
    from tutor.grader import LLMGrader
    llm = _stub_llm("hmm, that was tricky", tmp_path)
    grader = LLMGrader(llm=llm, model="google/gemini-2.5-flash")
    score = grader.grade(target="x", attempt="y")
    assert score == 3


def test_grader_clamps_out_of_range(tmp_path):
    from tutor.grader import LLMGrader
    llm = _stub_llm("9", tmp_path)
    grader = LLMGrader(llm=llm, model="google/gemini-2.5-flash")
    score = grader.grade(target="x", attempt="y")
    # Out of range → default 3
    assert score == 3


def test_grader_propagates_budget_exception(tmp_path):
    from tutor.grader import LLMGrader
    from tutor.llm import LLMClient
    from tutor.budget import BudgetTracker, BudgetExceededError

    budget = BudgetTracker(
        path=tmp_path / "budget.json",
        daily_usd_cap=0.0001,
        daily_token_cap=1_000_000,
        now=lambda: datetime(2026, 5, 21, 12, 0),
    )
    budget.record(tokens_in=10, tokens_out=10, usd_cost=0.001)
    llm = LLMClient(client=MagicMock(), model="google/gemini-2.5-flash", budget=budget)

    grader = LLMGrader(llm=llm, model="google/gemini-2.5-flash")
    with pytest.raises(BudgetExceededError):
        grader.grade(target="x", attempt="y")
