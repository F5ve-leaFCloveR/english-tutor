"""Load YAML scenarios and build their system prompts."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Template


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


def _scenario_path(scenario_id: str) -> Path:
    return SCENARIOS_DIR / f"{scenario_id}.yaml"


def list_scenarios() -> list[str]:
    return sorted(p.stem for p in SCENARIOS_DIR.glob("*.yaml"))


def load_scenario(scenario_id: str) -> Scenario:
    path = _scenario_path(scenario_id)
    if not path.exists():
        raise ScenarioNotFoundError(f"No scenario file at {path}")
    data: dict[str, Any] = yaml.safe_load(path.read_text())
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


def build_system_prompt(scenario: Scenario, user_native_language: str = "Russian") -> str:
    template = Template(scenario.system_prompt_template)
    return template.render(user_native_language=user_native_language).strip()
