import json


def test_list_scenarios_includes_builtin(monkeypatch, tmp_path):
    """Built-in YAML stems must always show up."""
    monkeypatch.setenv("CUSTOM_SCENARIOS_PATH", str(tmp_path / "empty.json"))
    from tutor.scenarios.loader import list_scenarios
    sids = list_scenarios()
    assert "tech_interview_behavioral" in sids
    assert "daily_standup" in sids


def test_list_scenarios_includes_custom(monkeypatch, tmp_path):
    """Custom scenarios from CUSTOM_SCENARIOS_PATH must merge in."""
    monkeypatch.setenv("CUSTOM_SCENARIOS_PATH", str(tmp_path / "custom.json"))
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    storage = CustomScenarioStorage(path=tmp_path / "custom.json")
    storage.create(name="My Custom", difficulty="easy", system_prompt="P", opening_line="O")

    from tutor.scenarios.loader import list_scenarios
    sids = list_scenarios()
    assert "my-custom" in sids


def test_load_scenario_loads_custom(monkeypatch, tmp_path):
    """load_scenario falls back to custom storage when YAML missing."""
    monkeypatch.setenv("CUSTOM_SCENARIOS_PATH", str(tmp_path / "custom.json"))
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    storage = CustomScenarioStorage(path=tmp_path / "custom.json")
    storage.create(name="Talk to Bartender", difficulty="advanced",
                   system_prompt="You are a bartender.", opening_line="What can I get ya?")

    from tutor.scenarios.loader import load_scenario
    s = load_scenario("talk-to-bartender")
    assert s.id == "talk-to-bartender"
    assert s.name == "Talk to Bartender"
    assert s.difficulty == "advanced"
    assert s.opening_line == "What can I get ya?"
    assert s.system_prompt_template == "You are a bartender."
    # structured fields default to empty
    assert s.counterpart == {}
    assert s.goal == ""
    assert s.vocab_focus == []


def test_load_scenario_builtin_wins_on_id_clash(monkeypatch, tmp_path):
    """If a custom id matches a YAML stem, the YAML still wins."""
    monkeypatch.setenv("CUSTOM_SCENARIOS_PATH", str(tmp_path / "custom.json"))
    # manually inject a custom scenario with built-in id
    (tmp_path / "custom.json").write_text(json.dumps({
        "scenarios": [{
            "id": "tech_interview_behavioral",
            "name": "Hijacked",
            "difficulty": "easy",
            "system_prompt": "I am the imposter.",
            "opening_line": "Hi",
            "created_at": "2026-05-22T12:00:00",
        }]
    }))
    from tutor.scenarios.loader import load_scenario
    s = load_scenario("tech_interview_behavioral")
    assert s.name != "Hijacked"  # built-in YAML wins
    assert "interview" in s.name.lower()


def test_load_scenario_uses_empty_opening_default(monkeypatch, tmp_path):
    """Custom scenario without opening_line gets a sensible default."""
    monkeypatch.setenv("CUSTOM_SCENARIOS_PATH", str(tmp_path / "custom.json"))
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    storage = CustomScenarioStorage(path=tmp_path / "custom.json")
    storage.create(name="No Opening", difficulty="easy", system_prompt="P", opening_line="")

    from tutor.scenarios.loader import load_scenario
    s = load_scenario("no-opening")
    assert s.opening_line  # non-empty default
