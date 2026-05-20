import pytest
from pathlib import Path


def test_load_scenario_by_id():
    from tutor.scenarios.loader import load_scenario
    sc = load_scenario("tech_interview_behavioral")
    assert sc.id == "tech_interview_behavioral"
    assert "interview" in sc.name.lower()
    assert sc.opening_line  # non-empty
    assert sc.system_prompt_template  # non-empty


def test_load_scenario_unknown_id_raises():
    from tutor.scenarios.loader import load_scenario, ScenarioNotFoundError
    with pytest.raises(ScenarioNotFoundError):
        load_scenario("does_not_exist")


def test_list_scenarios():
    from tutor.scenarios.loader import list_scenarios
    ids = list_scenarios()
    assert "tech_interview_behavioral" in ids


def test_build_system_prompt_substitutes_user_profile():
    from tutor.scenarios.loader import load_scenario, build_system_prompt
    sc = load_scenario("tech_interview_behavioral")
    prompt = build_system_prompt(sc, user_native_language="Russian")
    assert "Russian" in prompt
    assert "AI" not in prompt or "do not" in prompt.lower() or "do NOT" in prompt


def test_build_system_prompt_raises_on_unknown_placeholder():
    """Regression: StrictUndefined ensures typo'd template variables fail loudly."""
    from tutor.scenarios.loader import Scenario, build_system_prompt
    from jinja2.exceptions import UndefinedError

    sc = Scenario(
        id="t",
        name="t",
        difficulty="t",
        counterpart={},
        goal="g",
        vocab_focus=[],
        opening_line="hi",
        system_prompt_template="Hello {{ user_lang }}",  # typo: should be user_native_language
    )
    with pytest.raises(UndefinedError):
        build_system_prompt(sc, user_native_language="Russian")
