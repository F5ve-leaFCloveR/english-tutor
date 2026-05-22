"""Load YAML scenarios (built-in) and JSON custom scenarios; build their system prompts."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Template, StrictUndefined


SCENARIOS_DIR = Path(__file__).parent


class ScenarioNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class Scenario:
    id: str
    name: str
    difficulty: str
    counterpart: dict
    goal: str
    vocab_focus: list[str]
    opening_line: str
    system_prompt_template: str


_DEFAULT_CUSTOM_OPENING = "Hi! Let's get started."


def _custom_storage_path() -> Path:
    return Path(os.getenv("CUSTOM_SCENARIOS_PATH", "custom_scenarios.json"))


def _scenario_path(scenario_id: str) -> Path:
    return SCENARIOS_DIR / f"{scenario_id}.yaml"


def list_scenarios() -> list[str]:
    """Return sorted list of all scenario ids (built-in YAML + custom JSON)."""
    builtin = {p.stem for p in SCENARIOS_DIR.glob("*.yaml")}
    custom: set[str] = set()
    # Local import to avoid circular import at module load time.
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    try:
        storage = CustomScenarioStorage(path=_custom_storage_path())
        custom = {s["id"] for s in storage.list_all()}
    except Exception:
        # If custom storage fails entirely, fall back to built-in only.
        custom = set()
    return sorted(builtin | custom)


def load_scenario(scenario_id: str) -> Scenario:
    """Load a scenario by id. Prefers built-in YAML; falls back to custom JSON."""
    path = _scenario_path(scenario_id)
    if path.exists():
        data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
        return Scenario(
            id=data["id"],
            name=data["name"],
            difficulty=data["difficulty"],
            counterpart=data["counterpart"],
            goal=data["goal"],
            vocab_focus=list(data["vocab_focus"]),
            opening_line=data["opening_line"].strip(),
            system_prompt_template=data["system_prompt_template"],
        )

    # Fall back to custom storage.
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    storage = CustomScenarioStorage(path=_custom_storage_path())
    custom = storage.load(scenario_id)  # raises ScenarioNotFoundError if missing
    return Scenario(
        id=custom["id"],
        name=custom["name"],
        difficulty=custom["difficulty"],
        counterpart={},
        goal="",
        vocab_focus=[],
        opening_line=(custom.get("opening_line") or _DEFAULT_CUSTOM_OPENING).strip(),
        system_prompt_template=custom["system_prompt"],
    )


def build_system_prompt(scenario: Scenario, user_native_language: str = "Russian") -> str:
    template = Template(scenario.system_prompt_template, undefined=StrictUndefined)
    return template.render(user_native_language=user_native_language).strip()
