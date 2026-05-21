from datetime import datetime
from unittest.mock import MagicMock
import json
import pytest


def _make_budget(tmp_path):
    from tutor.budget import BudgetTracker
    return BudgetTracker(
        path=tmp_path / "budget.json",
        daily_usd_cap=1.0,
        daily_token_cap=1_000_000,
        now=lambda: datetime(2026, 5, 21, 12, 0),
    )


def _stub_llm_returning(json_str: str, tmp_path):
    """Build an LLMClient mock whose complete() returns the given string."""
    from tutor.llm import LLMClient
    client = MagicMock()
    fake_response = MagicMock()
    fake_response.choices = [MagicMock()]
    fake_response.choices[0].message = MagicMock()
    fake_response.choices[0].message.content = json_str
    fake_response.usage = MagicMock()
    fake_response.usage.prompt_tokens = 100
    fake_response.usage.completion_tokens = 50
    fake_response.usage.total_tokens = 150
    fake_response.usage.model_extra = {}
    client.chat.completions.create.return_value = fake_response

    budget = _make_budget(tmp_path)
    return LLMClient(client=client, model="google/gemini-2.5-pro", budget=budget), client


def test_evaluator_parses_valid_json(tmp_path):
    from tutor.evaluator import Evaluator, GrowthPoint

    llm, _ = _stub_llm_returning(json.dumps({
        "growth_points": [
            {
                "tag": "vocab",
                "user_utterance": "I made a project",
                "corrected_version": "I led a project",
                "explanation": "Led signals ownership; made is too generic.",
                "context": "Tell me about a project you've worked on.",
            },
            {
                "tag": "grammar",
                "user_utterance": "I working on backend",
                "corrected_version": "I'm working on backend",
                "explanation": "Missing auxiliary verb 'am' in present continuous.",
                "context": None,
            },
        ]
    }), tmp_path)

    evaluator = Evaluator(llm=llm, model="google/gemini-2.5-pro")
    result = evaluator.evaluate(transcript=[
        {"role": "system", "content": "..."},
        {"role": "assistant", "content": "Tell me about a project you've worked on."},
        {"role": "user", "content": "I made a project to handle backend"},
    ])
    assert len(result) == 2
    assert isinstance(result[0], GrowthPoint)
    assert result[0].tag == "vocab"
    assert result[1].tag == "grammar"
    assert result[1].context is None


def test_evaluator_retries_on_malformed_then_succeeds(tmp_path):
    from tutor.evaluator import Evaluator
    from tutor.llm import LLMClient

    bad_then_good = [
        MagicMock(choices=[MagicMock(message=MagicMock(content="not json"))],
                  usage=MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15, model_extra={})),
        MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps({
            "growth_points": [{"tag": "vocab", "user_utterance": "x", "corrected_version": "y", "explanation": "z", "context": None}]
        })))], usage=MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15, model_extra={})),
    ]
    client = MagicMock()
    client.chat.completions.create.side_effect = bad_then_good
    budget = _make_budget(tmp_path)
    llm = LLMClient(client=client, model="google/gemini-2.5-pro", budget=budget)

    evaluator = Evaluator(llm=llm, model="google/gemini-2.5-pro")
    result = evaluator.evaluate(transcript=[{"role": "user", "content": "hi"}])
    assert len(result) == 1
    assert client.chat.completions.create.call_count == 2


def test_evaluator_returns_empty_on_double_parse_fail(tmp_path):
    from tutor.evaluator import Evaluator
    from tutor.llm import LLMClient

    bad_response = MagicMock(
        choices=[MagicMock(message=MagicMock(content="still not json"))],
        usage=MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15, model_extra={}),
    )
    client = MagicMock()
    client.chat.completions.create.return_value = bad_response
    budget = _make_budget(tmp_path)
    llm = LLMClient(client=client, model="google/gemini-2.5-pro", budget=budget)

    evaluator = Evaluator(llm=llm, model="google/gemini-2.5-pro")
    result = evaluator.evaluate(transcript=[{"role": "user", "content": "hi"}])
    assert result == []
    assert client.chat.completions.create.call_count == 2


def test_evaluator_truncates_to_five(tmp_path):
    from tutor.evaluator import Evaluator

    too_many = json.dumps({"growth_points": [
        {"tag": "vocab", "user_utterance": f"u{i}", "corrected_version": f"c{i}",
         "explanation": "e", "context": None}
        for i in range(8)
    ]})
    llm, _ = _stub_llm_returning(too_many, tmp_path)
    evaluator = Evaluator(llm=llm, model="google/gemini-2.5-pro")
    result = evaluator.evaluate(transcript=[{"role": "user", "content": "x"}])
    assert len(result) == 5


def test_evaluator_returns_empty_on_llm_error(tmp_path):
    from tutor.evaluator import Evaluator
    from tutor.llm import LLMClient

    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("api down")
    budget = _make_budget(tmp_path)
    llm = LLMClient(client=client, model="google/gemini-2.5-pro", budget=budget)

    evaluator = Evaluator(llm=llm, model="google/gemini-2.5-pro")
    result = evaluator.evaluate(transcript=[{"role": "user", "content": "x"}])
    assert result == []


def test_evaluator_retry_includes_reminder_message(tmp_path):
    """Regression P5: on retry after parse fail, append a STRICT JSON reminder."""
    from tutor.evaluator import Evaluator
    from tutor.llm import LLMClient
    import json as _json
    from unittest.mock import MagicMock as _MagicMock

    bad_then_good = [
        _MagicMock(
            choices=[_MagicMock(message=_MagicMock(content="not json"))],
            usage=_MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15, model_extra={}),
        ),
        _MagicMock(
            choices=[_MagicMock(message=_MagicMock(content=_json.dumps({
                "growth_points": [{"tag": "vocab", "user_utterance": "x",
                                   "corrected_version": "y", "explanation": "z", "context": None}]
            })))],
            usage=_MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15, model_extra={}),
        ),
    ]
    client = _MagicMock()
    client.chat.completions.create.side_effect = bad_then_good
    budget = _make_budget(tmp_path)
    llm = LLMClient(client=client, model="google/gemini-2.5-pro", budget=budget)

    evaluator = Evaluator(llm=llm, model="google/gemini-2.5-pro")
    evaluator.evaluate(transcript=[{"role": "user", "content": "hi"}])

    # First call: original messages only
    first_call_messages = client.chat.completions.create.call_args_list[0].kwargs["messages"]
    # Second call: original messages + reminder
    second_call_messages = client.chat.completions.create.call_args_list[1].kwargs["messages"]
    assert len(second_call_messages) == len(first_call_messages) + 1
    reminder = second_call_messages[-1]
    assert reminder["role"] == "user"
    assert "STRICT JSON" in reminder["content"]
