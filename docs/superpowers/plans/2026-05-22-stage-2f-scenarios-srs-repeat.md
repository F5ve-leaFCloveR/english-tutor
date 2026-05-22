# Stage 2f — Scenarios + SRS dedupe/limit + Repeat practice — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (1) Add 4 built-in YAML scenarios + the ability to create/delete custom scenarios via the UI. (2) Cross-session dedupe + 5-per-session cap when creating SRS cards. (3) "Try again" button on /practice that lets the user retry a card without affecting SRS scheduling.

**Architecture:** Custom scenarios live in `custom_scenarios.json` (single JSON file, gitignored). Scenario loader merges built-in (YAML) + custom. SRS engine `create_cards` filters duplicates (lowered+stripped `user_utterance`) and caps at 5 (grammar > vocab priority). "Try again" is a frontend-only state reset, plus a new `practice_only=true` query flag on the grade route so re-grading doesn't bump SRS.

**Tech Stack:** Same as Stage 2e. No new deps.

**Prerequisites:**
- Stage 2e on `main` (`5e2295f` or later).
- All current tests green: 201 pytest, 49 vitest, build succeeds.

---

## File Structure

```
tutor/scenarios/
├── casual_conversation.yaml          (NEW)
├── travel_directions.yaml            (NEW)
├── coffee_chat_colleague.yaml        (NEW)
├── customer_service_call.yaml        (NEW)
├── custom_storage.py                 (NEW: JSON CRUD)
└── loader.py                         (MOD: merge built-in + custom)

tutor/srs_engine.py                   (MOD: create_cards dedup + cap)

tutor/web/
├── schemas.py                        (MOD: ScenarioSummary.is_custom, CustomScenarioCreate)
├── services.py                       (MOD: list/create/delete custom scenarios; grade_card practice_only)
├── api.py                            (MOD: POST/DELETE /api/scenarios/custom; grade practice_only)
└── deps.py                           (MOD: custom_scenarios_path attribute)

tutor/settings.py                     (MOD: custom_scenarios_path)

tests/
├── test_custom_scenarios.py          (NEW: CustomScenarioStorage)
├── test_scenarios.py                 (MOD or NEW: loader merge)
├── test_srs_engine.py                (MOD: dedupe + cap tests)
└── web/
    ├── test_api.py                   (MOD: + custom scenario endpoints + grade practice_only)
    └── test_services_session.py      (MOD: + SRS create_cards behavior via service)

frontend/src/
├── api/
│   ├── types.ts                      (MOD: ScenarioSummary.is_custom, CustomScenarioCreate)
│   ├── client.ts                     (MOD: createCustomScenario, deleteCustomScenario, gradeCard practice_only)
│   └── client.test.ts                (MOD: + tests for new methods)
├── pages/
│   ├── ScenariosPage.tsx             (MOD: + Create button, delete on custom)
│   ├── ScenariosPage.test.tsx        (MOD: + custom/delete tests)
│   ├── NewScenarioPage.tsx           (NEW: form)
│   ├── NewScenarioPage.test.tsx      (NEW)
│   ├── PracticePage.tsx              (MOD: + Try again button, calls practice_only)
│   └── PracticePage.test.tsx         (MOD: + try-again test)
└── App.tsx                           (MOD: /scenarios/new route)
```

---

## Task 1: New built-in YAML scenarios (4)

**Files:**
- Create: `tutor/scenarios/casual_conversation.yaml`
- Create: `tutor/scenarios/travel_directions.yaml`
- Create: `tutor/scenarios/coffee_chat_colleague.yaml`
- Create: `tutor/scenarios/customer_service_call.yaml`

- [ ] **Step 1: Create `tutor/scenarios/casual_conversation.yaml`**

```yaml
id: casual_conversation
name: "Casual conversation with a new acquaintance"
difficulty: intermediate
counterpart:
  role: "A friendly stranger you just met at a coworking space in a new city"
  persona: |
    Curious, easygoing, mid-30s. Asks about your background, what brings you here,
    your hobbies. Shares brief bits about themselves. No agenda.
goal: >
  Practice everyday small-talk vocabulary: greetings, hobbies, background, plans
  for the weekend. Build fluency on common questions and natural transitions.
vocab_focus:
  - "Small-talk connectors ('actually', 'speaking of', 'by the way')"
  - "Casual back-channeling ('oh really?', 'no way', 'that's cool')"
  - "Hedged opinions ('I guess', 'kind of', 'sort of')"
opening_line: >
  Hey! I don't think we've met — I'm new here too. Where are you from originally?
system_prompt_template: |
  You are a friendly stranger at a coworking space, in your mid-30s, easygoing.
  The other person is a {{ user_native_language }} native speaker practicing
  conversational English.

  STRICT RULES:
  - Keep responses casual and short — 1-3 sentences. Real chitchat pace.
  - Ask natural follow-up questions about hobbies, background, weekend plans.
  - Share short bits about yourself when relevant (don't monologue).
  - Stay in role. Do NOT break character. Do NOT mention you are an AI.
  - Reply ONLY in English. If they slip into {{ user_native_language }},
    gently say "Sorry, can you say that in English?"
  - Do NOT correct their English mid-chat.
```

- [ ] **Step 2: Create `tutor/scenarios/travel_directions.yaml`**

```yaml
id: travel_directions
name: "Asking directions and ordering food while traveling"
difficulty: intermediate
counterpart:
  role: "A helpful local in a European city (could be a shopkeeper, waiter, or passerby)"
  persona: |
    Polite, helpful, gives clear directions or recommendations. Adjusts to the speaker's
    English level — repeats or rephrases when asked.
goal: >
  Practice travel scenarios: asking for directions, ordering at a cafe, requesting
  recommendations, dealing with simple misunderstandings.
vocab_focus:
  - "Direction phrases ('go straight', 'turn left at', 'across from')"
  - "Polite requests ('could I have', 'do you mind if', 'what would you recommend')"
  - "Clarification ('sorry, could you repeat', 'did you say X?', 'I didn't catch that')"
opening_line: >
  Yes? Can I help you with something?
system_prompt_template: |
  You are a polite local in a European city. The traveler is a {{ user_native_language }}
  native speaker practicing English travel scenarios.

  STRICT RULES:
  - Respond naturally to whatever the traveler asks: directions, food order, recommendation.
  - Stay in character — adapt to whatever situation they introduce in their first message.
  - Keep responses short and helpful — 1-2 sentences typical.
  - When they ask for directions, give specific simple ones ("two blocks straight, then
    left at the bakery").
  - Repeat or rephrase if asked.
  - Stay in role. Do NOT break character.
  - Reply ONLY in English. If they slip into {{ user_native_language }},
    politely ask in English.
```

- [ ] **Step 3: Create `tutor/scenarios/coffee_chat_colleague.yaml`**

```yaml
id: coffee_chat_colleague
name: "Coffee chat with a new colleague"
difficulty: intermediate
counterpart:
  role: "A senior engineer at the same company you just joined, having an informal intro coffee"
  persona: |
    Friendly senior, 10+ years at the company. Curious about your background and what
    drew you to the team. Shares advice and team gossip lightly. Not a performance review.
goal: >
  Practice informal professional English: introducing yourself, talking about past
  projects, asking about the team and company culture without being formal.
vocab_focus:
  - "Informal professional verbs ('shipped', 'owned', 'paired on', 'jumped in')"
  - "Team/culture vocab ('on-call rotation', 'design review', 'roadmap')"
  - "Soft opinions ('I'd lean toward', 'in my experience', 'depending on the team')"
opening_line: >
  Hey! Great to finally grab coffee. So — what brought you over to our team?
system_prompt_template: |
  You are a senior engineer at the same company, having a casual intro coffee with
  a new teammate. The new teammate is a {{ user_native_language }} native speaker
  practicing professional spoken English.

  STRICT RULES:
  - Keep it casual and warm — 2-3 sentences usually. Not an interview.
  - Ask about their background, past projects, what they're looking forward to.
  - Share short bits about the team, company, your own role.
  - Stay in role. Do NOT break character. Do NOT mention you are an AI.
  - Reply ONLY in English. If they slip into {{ user_native_language }},
    say "Mind switching back to English? I want to follow along."
  - Do NOT correct their English mid-chat.
```

- [ ] **Step 4: Create `tutor/scenarios/customer_service_call.yaml`**

```yaml
id: customer_service_call
name: "Phone call to customer service (billing dispute)"
difficulty: advanced
counterpart:
  role: "A customer service rep at a US internet provider, handling a billing dispute call"
  persona: |
    Professional, somewhat scripted, asks for account info, looks up details, offers
    standard resolutions (refund, credit, escalation). Mildly defensive of company
    policy but cooperative when pressed politely.
goal: >
  Practice high-stakes service English: explaining a problem clearly, pushing back
  politely, requesting specific outcomes, negotiating a resolution.
vocab_focus:
  - "Problem framing ('I was charged for X but I didn't', 'the agreed rate was')"
  - "Polite escalation ('I'd like to speak with a supervisor', 'can we escalate this?')"
  - "Outcome-specific requests ('a credit on next month's bill', 'a refund to my card')"
opening_line: >
  Thank you for calling tech support. My name is Alex. Can I have your account number
  to start?
system_prompt_template: |
  You are a customer service rep at a US internet provider, on a billing dispute call.
  The caller is a {{ user_native_language }} native speaker practicing professional
  English for high-stakes service interactions.

  STRICT RULES:
  - Keep responses concise — 1-3 sentences. Real phone-support pace.
  - Ask for account info early, then probe what the issue is.
  - Offer standard resolutions when the caller explains the problem clearly.
  - Be mildly scripted — push back gently if they're vague, accommodate when they're specific.
  - Stay in role. Do NOT break character. Do NOT mention you are an AI.
  - Reply ONLY in English. If the caller slips into {{ user_native_language }},
    say "I'm sorry, I'll need you to speak English for me to help."
  - Do NOT correct the caller's English mid-call.
```

- [ ] **Step 5: Verify and run tests**

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor && source .venv/bin/activate
python3 -c "
from tutor.scenarios.loader import list_scenarios, load_scenario
sids = list_scenarios()
print('scenarios:', sids)
assert 'casual_conversation' in sids
assert 'travel_directions' in sids
assert 'coffee_chat_colleague' in sids
assert 'customer_service_call' in sids
for sid in ['casual_conversation', 'travel_directions', 'coffee_chat_colleague', 'customer_service_call']:
    s = load_scenario(sid)
    print(f'  loaded {s.id} ({s.difficulty}): {s.name}')
"
pytest 2>&1 | tail -5
```

→ 4 scenarios visible, loadable. Full suite still 201 green (no test changes yet).

- [ ] **Step 6: Commit**

```bash
git add tutor/scenarios/casual_conversation.yaml tutor/scenarios/travel_directions.yaml tutor/scenarios/coffee_chat_colleague.yaml tutor/scenarios/customer_service_call.yaml
git commit -m "feat(scenarios): add 4 built-in scenarios (casual, travel, coffee chat, service call)"
```

## Context

- Branch: `main`. Previous commit: `fac890c` (Stage 2f design).
- Task 1 of 8 in Stage 2f.

---

## Task 2: `CustomScenarioStorage` module

**Files:**
- Create: `tutor/scenarios/custom_storage.py`
- Create: `tests/test_custom_scenarios.py`

- [ ] **Step 1: Write failing tests** `tests/test_custom_scenarios.py`:

```python
from datetime import datetime
from pathlib import Path
import json
import pytest


def test_create_returns_dict_with_id_and_timestamps(tmp_path):
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    storage = CustomScenarioStorage(path=tmp_path / "custom.json", now=lambda: datetime(2026, 5, 22, 12, 0))
    out = storage.create(
        name="My restaurant chat",
        difficulty="intermediate",
        system_prompt="You are a waiter...",
        opening_line="Welcome!",
    )
    assert out["id"] == "my-restaurant-chat"
    assert out["name"] == "My restaurant chat"
    assert out["difficulty"] == "intermediate"
    assert out["system_prompt"] == "You are a waiter..."
    assert out["opening_line"] == "Welcome!"
    assert out["created_at"] == "2026-05-22T12:00:00"


def test_create_writes_to_storage_file(tmp_path):
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    p = tmp_path / "custom.json"
    storage = CustomScenarioStorage(path=p)
    storage.create(name="X", difficulty="easy", system_prompt="...", opening_line="")
    data = json.loads(p.read_text())
    assert len(data["scenarios"]) == 1
    assert data["scenarios"][0]["id"] == "x"


def test_create_collision_appends_suffix(tmp_path):
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    storage = CustomScenarioStorage(path=tmp_path / "custom.json")
    s1 = storage.create(name="Talk", difficulty="easy", system_prompt="A", opening_line="")
    s2 = storage.create(name="Talk", difficulty="easy", system_prompt="B", opening_line="")
    s3 = storage.create(name="Talk", difficulty="easy", system_prompt="C", opening_line="")
    assert s1["id"] == "talk"
    assert s2["id"] == "talk-2"
    assert s3["id"] == "talk-3"


def test_list_all_returns_sorted_by_created_at_desc(tmp_path):
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    times = [datetime(2026, 5, 22, h, 0) for h in (10, 12, 11)]
    it = iter(times)
    storage = CustomScenarioStorage(path=tmp_path / "custom.json", now=lambda: next(it))
    storage.create(name="A", difficulty="easy", system_prompt="...", opening_line="")
    storage.create(name="B", difficulty="easy", system_prompt="...", opening_line="")
    storage.create(name="C", difficulty="easy", system_prompt="...", opening_line="")
    out = storage.list_all()
    names = [s["name"] for s in out]
    assert names == ["B", "C", "A"]  # 12h, 11h, 10h


def test_load_returns_existing(tmp_path):
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    storage = CustomScenarioStorage(path=tmp_path / "custom.json")
    created = storage.create(name="My Talk", difficulty="advanced", system_prompt="P", opening_line="O")
    loaded = storage.load(created["id"])
    assert loaded["system_prompt"] == "P"


def test_load_missing_raises(tmp_path):
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    from tutor.scenarios.loader import ScenarioNotFoundError
    storage = CustomScenarioStorage(path=tmp_path / "custom.json")
    with pytest.raises(ScenarioNotFoundError):
        storage.load("nonexistent")


def test_delete_removes_and_persists(tmp_path):
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    p = tmp_path / "custom.json"
    storage = CustomScenarioStorage(path=p)
    s = storage.create(name="Talk", difficulty="easy", system_prompt="A", opening_line="")
    storage.delete(s["id"])
    assert storage.list_all() == []
    data = json.loads(p.read_text())
    assert data["scenarios"] == []


def test_delete_missing_raises(tmp_path):
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    from tutor.scenarios.loader import ScenarioNotFoundError
    storage = CustomScenarioStorage(path=tmp_path / "custom.json")
    with pytest.raises(ScenarioNotFoundError):
        storage.delete("missing")


def test_empty_file_treated_as_empty(tmp_path):
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    storage = CustomScenarioStorage(path=tmp_path / "missing.json")
    assert storage.list_all() == []


def test_corrupt_file_backed_up(tmp_path):
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    p = tmp_path / "custom.json"
    p.write_text("{ this is not valid json")
    storage = CustomScenarioStorage(path=p)
    assert storage.list_all() == []
    # corrupt file moved aside
    backups = list(tmp_path.glob("custom.json.broken-*"))
    assert len(backups) == 1
```

- [ ] **Step 2: Run** `pytest tests/test_custom_scenarios.py -v` → 10 fails (module missing).

- [ ] **Step 3: Implement `tutor/scenarios/custom_storage.py`**:

```python
"""User-defined scenarios persisted as a single JSON file."""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from tutor.scenarios.loader import ScenarioNotFoundError

log = logging.getLogger(__name__)


def _slugify(name: str) -> str:
    """ASCII-lowercase, hyphenated; strip non-alphanumerics."""
    out = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return out or "scenario"


@dataclass
class CustomScenarioStorage:
    path: Path
    now: Callable[[], datetime] = datetime.now

    def _load_raw(self) -> dict:
        if not self.path.exists():
            return {"scenarios": []}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            backup = self.path.with_suffix(self.path.suffix + f".broken-{int(time.time())}")
            try:
                self.path.rename(backup)
            except OSError:
                pass
            log.warning("custom_scenarios.json corrupt; backed up to %s; using empty list. %s", backup, e)
            return {"scenarios": []}

    def _write(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            import os
            os.replace(str(tmp), str(self.path))
        except Exception:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def list_all(self) -> list[dict]:
        data = self._load_raw()
        scenarios = list(data.get("scenarios", []))
        scenarios.sort(key=lambda s: s.get("created_at", ""), reverse=True)
        return scenarios

    def load(self, scenario_id: str) -> dict:
        for s in self.list_all():
            if s.get("id") == scenario_id:
                return s
        raise ScenarioNotFoundError(f"No custom scenario with id={scenario_id}")

    def create(
        self,
        name: str,
        difficulty: str,
        system_prompt: str,
        opening_line: str,
    ) -> dict:
        data = self._load_raw()
        existing_ids = {s.get("id") for s in data.get("scenarios", [])}
        base = _slugify(name)
        new_id = base
        n = 2
        while new_id in existing_ids:
            new_id = f"{base}-{n}"
            n += 1
        entry = {
            "id": new_id,
            "name": name,
            "difficulty": difficulty,
            "system_prompt": system_prompt,
            "opening_line": opening_line,
            "created_at": self.now().isoformat(),
        }
        data.setdefault("scenarios", []).append(entry)
        self._write(data)
        return entry

    def delete(self, scenario_id: str) -> None:
        data = self._load_raw()
        before = data.get("scenarios", [])
        after = [s for s in before if s.get("id") != scenario_id]
        if len(after) == len(before):
            raise ScenarioNotFoundError(f"No custom scenario with id={scenario_id}")
        data["scenarios"] = after
        self._write(data)
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/test_custom_scenarios.py -v
pytest 2>&1 | tail -5
```

→ 10 green, full suite 211.

```bash
git add tutor/scenarios/custom_storage.py tests/test_custom_scenarios.py
git commit -m "feat(scenarios): CustomScenarioStorage — JSON CRUD for user scenarios"
```

## Context

- Branch: `main`. Previous: T1 commit.
- Task 2 of 8.

---

## Task 3: Loader merges built-in + custom

**Files:**
- Modify: `tutor/scenarios/loader.py`
- Create: `tests/test_scenarios_loader.py` (new — covers the merge behaviour)

- [ ] **Step 1: Write failing tests** `tests/test_scenarios_loader.py`:

```python
import os
from pathlib import Path
from unittest.mock import patch


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
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    # manually inject a custom scenario with built-in id
    import json
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
    # the test-loaded sanity:
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
```

- [ ] **Step 2: Run** `pytest tests/test_scenarios_loader.py -v` → 5 fails.

- [ ] **Step 3: Modify `tutor/scenarios/loader.py`**

Add the merge logic. Replace `list_scenarios()` and `load_scenario()`:

```python
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
    custom = set()
    # Local import to avoid cycles
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    try:
        storage = CustomScenarioStorage(path=_custom_storage_path())
        custom = {s["id"] for s in storage.list_all()}
    except Exception:
        # If custom storage fails, fall back to built-in only.
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

    # Fall back to custom storage
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    storage = CustomScenarioStorage(path=_custom_storage_path())
    custom = storage.load(scenario_id)  # raises ScenarioNotFoundError on missing
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
    # If the prompt has no `{{ user_native_language }}` placeholders, render still works.
    # If it does (built-in scenarios), the placeholder is filled.
    return template.render(user_native_language=user_native_language).strip()
```

Notes:
- Reuse `ScenarioNotFoundError` (custom_storage already imports it from `loader`).
- `CustomScenarioStorage` import is inside the function to avoid circular dependency at module load time.
- Custom scenarios with `{{ user_native_language }}` work because `build_system_prompt` always passes that variable.
- Custom scenarios WITHOUT Jinja placeholders also work — `StrictUndefined` only errors on REFERENCED-but-missing vars; ones not in the template are fine.

- [ ] **Step 4: Run + commit**

```bash
pytest tests/test_scenarios_loader.py -v
pytest 2>&1 | tail -5
```

→ 5 green, full suite 216.

```bash
git add tutor/scenarios/loader.py tests/test_scenarios_loader.py
git commit -m "feat(scenarios): loader merges built-in YAML + custom JSON"
```

## Context

- Branch: `main`. Previous: T2 commit.
- Task 3 of 8.

---

## Task 4: Backend `/api/scenarios/custom` CRUD + `is_custom` flag

**Files:**
- Modify: `tutor/settings.py` — `custom_scenarios_path`.
- Modify: `tutor/web/schemas.py` — `ScenarioSummary.is_custom`, `CustomScenarioCreate`.
- Modify: `tutor/web/services.py` — `list_scenarios_service` adds `is_custom`; new `create_custom_scenario_service`, `delete_custom_scenario_service`.
- Modify: `tutor/web/api.py` — new routes.
- Modify: `tests/web/test_api.py` — new tests.

- [ ] **Step 1: Add to `tutor/settings.py`** — append a new field:

```python
    custom_scenarios_path: str = Field(
        default="custom_scenarios.json",
        description="Path to the user's custom scenarios JSON file",
    )
```

- [ ] **Step 2: Update `tutor/web/schemas.py`** — modify `ScenarioSummary` + add `CustomScenarioCreate`

Find `ScenarioSummary` and add `is_custom: bool = False`:

```python
class ScenarioSummary(BaseModel):
    id: str
    name: str
    difficulty: str
    is_custom: bool = False
```

Append:

```python
class CustomScenarioCreate(BaseModel):
    name: str
    difficulty: str = "intermediate"
    system_prompt: str
    opening_line: str | None = None
```

- [ ] **Step 3: Write failing tests** in `tests/web/test_api.py`:

```python
def test_post_custom_scenario_returns_summary(tmp_path, mocker, monkeypatch):
    monkeypatch.setenv("CUSTOM_SCENARIOS_PATH", str(tmp_path / "custom.json"))
    client, _ = _client(tmp_path, mocker)
    r = client.post("/api/scenarios/custom", json={
        "name": "My Talk",
        "difficulty": "easy",
        "system_prompt": "You are a friend.",
        "opening_line": "Hey!",
    })
    assert r.status_code == 201
    data = r.json()
    assert data["id"] == "my-talk"
    assert data["name"] == "My Talk"
    assert data["is_custom"] is True


def test_post_custom_scenario_rejects_empty_name(tmp_path, mocker, monkeypatch):
    monkeypatch.setenv("CUSTOM_SCENARIOS_PATH", str(tmp_path / "custom.json"))
    client, _ = _client(tmp_path, mocker)
    r = client.post("/api/scenarios/custom", json={
        "name": "  ",
        "difficulty": "easy",
        "system_prompt": "P",
    })
    assert r.status_code == 422


def test_post_custom_scenario_rejects_empty_prompt(tmp_path, mocker, monkeypatch):
    monkeypatch.setenv("CUSTOM_SCENARIOS_PATH", str(tmp_path / "custom.json"))
    client, _ = _client(tmp_path, mocker)
    r = client.post("/api/scenarios/custom", json={
        "name": "X",
        "difficulty": "easy",
        "system_prompt": "",
    })
    assert r.status_code == 422


def test_delete_custom_scenario_removes_it(tmp_path, mocker, monkeypatch):
    monkeypatch.setenv("CUSTOM_SCENARIOS_PATH", str(tmp_path / "custom.json"))
    client, _ = _client(tmp_path, mocker)
    created = client.post("/api/scenarios/custom", json={
        "name": "Talk", "difficulty": "easy", "system_prompt": "P",
    }).json()
    r = client.delete(f"/api/scenarios/custom/{created['id']}")
    assert r.status_code == 204
    # Verify gone
    list_resp = client.get("/api/scenarios")
    ids = [s["id"] for s in list_resp.json()["scenarios"]]
    assert created["id"] not in ids


def test_delete_custom_scenario_missing_returns_404(tmp_path, mocker, monkeypatch):
    monkeypatch.setenv("CUSTOM_SCENARIOS_PATH", str(tmp_path / "custom.json"))
    client, _ = _client(tmp_path, mocker)
    r = client.delete("/api/scenarios/custom/nonexistent")
    assert r.status_code == 404


def test_get_scenarios_marks_custom(tmp_path, mocker, monkeypatch):
    monkeypatch.setenv("CUSTOM_SCENARIOS_PATH", str(tmp_path / "custom.json"))
    client, _ = _client(tmp_path, mocker)
    created = client.post("/api/scenarios/custom", json={
        "name": "Talk", "difficulty": "easy", "system_prompt": "P",
    }).json()
    r = client.get("/api/scenarios")
    items = r.json()["scenarios"] if isinstance(r.json(), dict) else r.json()
    # Find both a built-in and the custom one
    found_custom = next((s for s in items if s["id"] == created["id"]), None)
    assert found_custom is not None
    assert found_custom["is_custom"] is True
    found_builtin = next((s for s in items if s["id"] == "tech_interview_behavioral"), None)
    assert found_builtin is not None
    assert found_builtin.get("is_custom") is False or found_builtin.get("is_custom") is None
```

Note: the existing `GET /api/scenarios` returns a bare list (no wrapper). Adapt the `items =` line in `test_get_scenarios_marks_custom` based on what the route actually returns. If it's `[{...}, ...]`, use `r.json()` directly; if it's `{"scenarios": [...]}`, use the `.get("scenarios")` path. Look at the existing route at `tutor/web/api.py` to confirm before writing the test — it's `GET /api/scenarios` returning `list[ScenarioSummary]` directly (no wrapper).

So the line should be: `items = r.json()` and find_custom uses that list directly.

- [ ] **Step 4: Run** `pytest tests/web/test_api.py -v 2>&1 | tail -20` → 6 fails (routes missing).

- [ ] **Step 5: Modify `tutor/web/services.py`** — extend list + add new services

Find `list_scenarios_service`. Replace with:

```python
def list_scenarios_service(deps: Dependencies) -> list[ScenarioSummary]:
    """Built-in YAML scenarios + custom JSON scenarios; mark each with is_custom."""
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    summaries: list[ScenarioSummary] = []

    builtin_ids = set()
    for sid in list_scenarios():
        sc = load_scenario(sid)
        builtin_ids.add(sid)
        summaries.append(ScenarioSummary(id=sc.id, name=sc.name, difficulty=sc.difficulty, is_custom=False))

    # Re-flag custom-only ones. `list_scenarios()` already includes them but we
    # marked all as is_custom=False; correct by looking at custom storage.
    storage = CustomScenarioStorage(path=Path(deps.custom_scenarios_path))
    custom_ids = {s["id"] for s in storage.list_all()}
    for summary in summaries:
        if summary.id in custom_ids and summary.id not in {p.stem for p in (SCENARIOS_DIR.glob("*.yaml"))}:
            object.__setattr__(summary, "is_custom", True)
    return summaries
```

Wait — that's awkward because Pydantic models aren't `frozen`. Simpler approach: rebuild the list cleanly.

Rewrite as:

```python
def list_scenarios_service(deps: Dependencies) -> list[ScenarioSummary]:
    from pathlib import Path
    from tutor.scenarios.loader import SCENARIOS_DIR
    from tutor.scenarios.custom_storage import CustomScenarioStorage

    storage = CustomScenarioStorage(path=Path(deps.custom_scenarios_path))
    custom_ids = {s["id"] for s in storage.list_all()}
    builtin_ids = {p.stem for p in SCENARIOS_DIR.glob("*.yaml")}

    summaries: list[ScenarioSummary] = []
    for sid in list_scenarios():
        sc = load_scenario(sid)
        is_custom = sid in custom_ids and sid not in builtin_ids
        summaries.append(ScenarioSummary(
            id=sc.id, name=sc.name, difficulty=sc.difficulty, is_custom=is_custom,
        ))
    return summaries
```

Add two new service functions:

```python
def create_custom_scenario_service(deps: Dependencies, payload) -> ScenarioSummary:
    from pathlib import Path
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    storage = CustomScenarioStorage(path=Path(deps.custom_scenarios_path))
    created = storage.create(
        name=payload.name.strip(),
        difficulty=payload.difficulty,
        system_prompt=payload.system_prompt.strip(),
        opening_line=(payload.opening_line or "").strip(),
    )
    return ScenarioSummary(
        id=created["id"],
        name=created["name"],
        difficulty=created["difficulty"],
        is_custom=True,
    )


def delete_custom_scenario_service(deps: Dependencies, scenario_id: str) -> None:
    from pathlib import Path
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    storage = CustomScenarioStorage(path=Path(deps.custom_scenarios_path))
    storage.delete(scenario_id)  # raises ScenarioNotFoundError → 404
```

- [ ] **Step 6: Update `tutor/web/deps.py`** — add `custom_scenarios_path` field

Find the `Dependencies` dataclass. Add:

```python
    custom_scenarios_path: str = "custom_scenarios.json"
```

In `build_dependencies(settings)`, set it:

```python
    custom_scenarios_path=settings.custom_scenarios_path,
```

- [ ] **Step 7: Modify `tutor/web/api.py`** — add routes

Update imports:

```python
from tutor.web.schemas import (
    BudgetSummary,
    ChatRequest,
    ChatResponseDict,
    CustomScenarioCreate,
    DueCardsResult,
    EndSessionResult,
    GradeResult,
    ScenarioSummary,
    SessionListResult,
    StartSessionResult,
    TTSRequest,
    TurnResult,
)
from tutor.scenarios.loader import ScenarioNotFoundError
```

Inside `create_app`, add the two routes near the existing scenarios route:

```python
    @app.post("/api/scenarios/custom", response_model=ScenarioSummary, status_code=201)
    async def create_custom_scenario(req: CustomScenarioCreate, d: Dependencies = Depends(get_deps)):
        if not req.name.strip() or not req.system_prompt.strip():
            raise HTTPException(status_code=422, detail="name and system_prompt are required")
        return services.create_custom_scenario_service(d, req)


    @app.delete("/api/scenarios/custom/{scenario_id}", status_code=204)
    async def delete_custom_scenario(scenario_id: str, d: Dependencies = Depends(get_deps)):
        try:
            services.delete_custom_scenario_service(d, scenario_id)
        except ScenarioNotFoundError:
            raise HTTPException(status_code=404, detail="custom scenario not found")
        return None
```

The existing `GET /api/scenarios` route just calls `services.list_scenarios_service(d)` and returns it as `list[ScenarioSummary]`. The added `is_custom` field will appear automatically in the response.

- [ ] **Step 8: Run + commit**

```bash
pytest tests/web/test_api.py -v 2>&1 | tail -30
pytest 2>&1 | tail -5
```

If `_client(tmp_path, mocker)` in `test_api.py` doesn't pass `custom_scenarios_path` to `Dependencies`, you may need to add it. Look at how it builds Dependencies; pass `custom_scenarios_path=str(tmp_path / "custom.json")` (or set via env var which the `_load_raw` will pick up).

Actually the test uses `monkeypatch.setenv("CUSTOM_SCENARIOS_PATH", ...)` — that env var is read by the loader's `_custom_storage_path()` helper. But the SERVICE constructs the storage from `deps.custom_scenarios_path` (from settings). To unify, prefer reading from `deps`. Tests using env-var will fail unless `_client(tmp_path, mocker)` reads the env var and passes it to deps.

Two options:
1. Tests pass `custom_scenarios_path=str(tmp_path / "custom.json")` to `Dependencies` constructor directly (skip env var). Update tests.
2. The service reads `os.getenv("CUSTOM_SCENARIOS_PATH", deps.custom_scenarios_path)` — slight hack.

Pick option (1). Adjust the 6 new tests to pass `custom_scenarios_path` explicitly:

Replace each `monkeypatch.setenv("CUSTOM_SCENARIOS_PATH", str(tmp_path / "custom.json"))` with: build the Dependencies in `_client` to include `custom_scenarios_path=str(tmp_path / "custom.json")`.

OR — simplest — extend `_client` helper to accept an optional `custom_scenarios_path`:

```python
def _client(tmp_path, mocker, custom_scenarios_path: str | None = None):
    ...
    deps = Dependencies(
        ...,
        custom_scenarios_path=custom_scenarios_path or str(tmp_path / "custom.json"),
    )
    ...
```

Then tests just call `_client(tmp_path, mocker)` and the default uses `tmp_path / "custom.json"` (clean per-test scenario file). Drop the `monkeypatch.setenv` lines.

Update the 6 new tests accordingly.

Also: the loader's `_custom_storage_path()` uses `os.getenv("CUSTOM_SCENARIOS_PATH", "custom_scenarios.json")`. For the loader-level tests (`tests/test_scenarios_loader.py`), keep the env var pattern — they don't go through deps.

→ all green, full suite 222.

```bash
git add tutor/settings.py tutor/web/schemas.py tutor/web/services.py tutor/web/api.py tutor/web/deps.py tests/web/test_api.py
git commit -m "feat(web): custom scenarios CRUD + is_custom flag on /api/scenarios"
```

## Context

- Branch: `main`. Previous: T3 commit.
- Task 4 of 8.

---

## Task 5: Frontend types + API client for custom scenarios + grade practice_only

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/api/client.test.ts`

- [ ] **Step 1: Update `frontend/src/api/types.ts`**

Find `ScenarioSummary`:

```typescript
export interface ScenarioSummary {
  id: string;
  name: string;
  difficulty: string;
  is_custom?: boolean;
}
```

Append at the bottom of the file:

```typescript
export interface CustomScenarioCreate {
  name: string;
  difficulty: string;
  system_prompt: string;
  opening_line?: string;
}
```

- [ ] **Step 2: Append failing tests** in `frontend/src/api/client.test.ts`:

```typescript
it("createCustomScenario posts payload and returns summary", async () => {
  (globalThis as any).fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ id: "my-talk", name: "My Talk", difficulty: "easy", is_custom: true }),
  });
  const res = await api.createCustomScenario({
    name: "My Talk", difficulty: "easy", system_prompt: "P", opening_line: "Hi",
  });
  expect(res.id).toBe("my-talk");
  const call = ((globalThis as any).fetch as any).mock.calls[0];
  expect(call[0]).toBe("/api/scenarios/custom");
  expect(call[1].method).toBe("POST");
});

it("deleteCustomScenario sends DELETE", async () => {
  (globalThis as any).fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({}),
  });
  await api.deleteCustomScenario("my-talk");
  const call = ((globalThis as any).fetch as any).mock.calls[0];
  expect(call[0]).toBe("/api/scenarios/custom/my-talk");
  expect(call[1].method).toBe("DELETE");
});

it("gradeCard supports practice_only flag", async () => {
  (globalThis as any).fetch = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({ card_id: "c1", quality: 4, user_attempt_text: "x", target: "y", explanation: "z", next_due: "2026-05-23" }),
  });
  await api.gradeCard("c1", new Blob(["a"]), false, true);
  const call = ((globalThis as any).fetch as any).mock.calls[0];
  expect(String(call[0])).toContain("/api/review/c1/grade");
  expect(String(call[0])).toContain("practice_only=true");
});
```

- [ ] **Step 3: Run** `npm test client 2>&1 | tail -10` → 3 fail.

- [ ] **Step 4: Update `frontend/src/api/client.ts`**

Update type imports:

```typescript
import type {
  // existing types...
  CustomScenarioCreate,
} from "./types";
```

Inside the `api` object, add:

```typescript
  createCustomScenario(req: CustomScenarioCreate): Promise<ScenarioSummary> {
    return request<ScenarioSummary>("/api/scenarios/custom", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req),
    });
  },

  deleteCustomScenario(scenario_id: string): Promise<void> {
    return request<void>(`/api/scenarios/custom/${encodeURIComponent(scenario_id)}`, {
      method: "DELETE",
    });
  },
```

Modify the existing `gradeCard` to accept an optional `practice_only` flag:

```typescript
  gradeCard(card_id: string, audio: Blob | null, skip: boolean, practice_only: boolean = false): Promise<GradeResult> {
    const qs = new URLSearchParams();
    if (skip) qs.set("skip", "true");
    if (practice_only) qs.set("practice_only", "true");
    const suffix = qs.toString() ? `?${qs}` : "";
    if (skip) {
      const form = new FormData();
      form.append("skip", "true");
      return request(`/api/review/${card_id}/grade${suffix}`, {
        method: "POST",
        body: form,
      });
    }
    const form = new FormData();
    if (audio) form.append("audio", audio, "grade.webm");
    return request(`/api/review/${card_id}/grade${suffix}`, { method: "POST", body: form });
  },
```

Note: `request<void>` — if `request` requires a JSON body in the response, the 204 from DELETE might break it. Look at how `request<T>` handles empty responses: if it always calls `res.json()`, a 204 with no body would throw. Read the existing `request<T>` impl. If it does always JSON-parse, return early on 204:

```typescript
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let body: ApiErrorBody;
    try { body = await res.json(); } catch { body = { error: "unknown_error" }; }
    throw new ApiError(res.status, body);
  }
  if (res.status === 204) return undefined as T;  // ADD THIS
  return res.json();
}
```

Add that one-line guard to `request` so 204 DELETE responses work.

- [ ] **Step 5: Update `gradeCard` test for the new `false`/default args**

The existing tests for `gradeCard` (skip + non-skip) pass 3 args; the new optional arg means they still work. Verify by re-running existing client tests.

- [ ] **Step 6: Run + commit**

```bash
npm test 2>&1 | tail -10
npm run build 2>&1 | tail -5

cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/api/
git commit -m "feat(api): createCustomScenario, deleteCustomScenario, gradeCard practice_only"
```

## Context

- Branch: `main`. Previous: T4 commit.
- Task 5 of 8.

---

## Task 6: Frontend NewScenarioPage + ScenariosPage delete + route + grade practice_only

**Files:**
- Create: `frontend/src/pages/NewScenarioPage.tsx`
- Create: `frontend/src/pages/NewScenarioPage.test.tsx`
- Modify: `frontend/src/pages/ScenariosPage.tsx`
- Modify: `frontend/src/pages/ScenariosPage.test.tsx`
- Modify: `frontend/src/pages/PracticePage.tsx`
- Modify: `frontend/src/pages/PracticePage.test.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Write failing tests** `frontend/src/pages/NewScenarioPage.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

function wrap(node: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <BrowserRouter>
      <QueryClientProvider client={qc}>{node}</QueryClientProvider>
    </BrowserRouter>
  );
}

describe("NewScenarioPage", () => {
  it("renders form with required fields", async () => {
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: { createCustomScenario: vi.fn() },
      ApiError: class extends Error {},
    }));
    const { NewScenarioPage } = await import("./NewScenarioPage");
    render(wrap(<NewScenarioPage />));
    expect(screen.getByLabelText(/name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/system prompt/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /create/i })).toBeInTheDocument();
  });

  it("submits payload and calls API", async () => {
    vi.resetModules();
    const create = vi.fn().mockResolvedValue({
      id: "my-talk", name: "My Talk", difficulty: "easy", is_custom: true,
    });
    vi.doMock("../api/client", () => ({
      api: { createCustomScenario: create },
      ApiError: class extends Error {},
    }));
    const { NewScenarioPage } = await import("./NewScenarioPage");
    render(wrap(<NewScenarioPage />));

    fireEvent.change(screen.getByLabelText(/name/i), { target: { value: "My Talk" } });
    fireEvent.change(screen.getByLabelText(/system prompt/i), { target: { value: "You are a friend." } });
    fireEvent.click(screen.getByRole("button", { name: /create/i }));

    await waitFor(() => {
      expect(create).toHaveBeenCalledWith({
        name: "My Talk",
        difficulty: "intermediate",
        system_prompt: "You are a friend.",
        opening_line: "",
      });
    });
  });
});
```

Run `npm test NewScenarioPage 2>&1 | tail -10` → 2 fail (module missing).

- [ ] **Step 2: Implement `frontend/src/pages/NewScenarioPage.tsx`**:

```typescript
import { FormEvent, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError } from "../api/client";

export function NewScenarioPage() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [difficulty, setDifficulty] = useState("intermediate");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [openingLine, setOpeningLine] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!name.trim() || !systemPrompt.trim()) {
      setError("Name and system prompt are required.");
      return;
    }
    setSubmitting(true);
    try {
      await api.createCustomScenario({
        name: name.trim(),
        difficulty,
        system_prompt: systemPrompt.trim(),
        opening_line: openingLine.trim(),
      });
      navigate("/");
    } catch (e) {
      setError(e instanceof ApiError ? (e.body.message || e.body.error || "Failed") : (e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto p-6 w-full">
      <h1 className="text-2xl font-semibold mb-4 text-slate-900">New custom scenario</h1>
      <form onSubmit={onSubmit} className="space-y-4">
        <div>
          <label htmlFor="scenario-name" className="block text-sm font-medium text-slate-700 mb-1">Name</label>
          <input
            id="scenario-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Talk to a barber"
            className="w-full border border-slate-300 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
          />
        </div>
        <div>
          <label htmlFor="scenario-difficulty" className="block text-sm font-medium text-slate-700 mb-1">Difficulty</label>
          <select
            id="scenario-difficulty"
            value={difficulty}
            onChange={(e) => setDifficulty(e.target.value)}
            className="border border-slate-300 rounded px-3 py-2 text-sm bg-white"
          >
            <option value="easy">easy</option>
            <option value="intermediate">intermediate</option>
            <option value="advanced">advanced</option>
          </select>
        </div>
        <div>
          <label htmlFor="scenario-prompt" className="block text-sm font-medium text-slate-700 mb-1">System prompt</label>
          <textarea
            id="scenario-prompt"
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            placeholder="Describe the bot's role, behavior, and any constraints. Example: 'You are a friendly barber in NYC. Keep responses casual and short.'"
            rows={8}
            className="w-full border border-slate-300 rounded px-3 py-2 text-sm font-mono focus:outline-none focus:border-blue-500"
          />
        </div>
        <div>
          <label htmlFor="scenario-opening" className="block text-sm font-medium text-slate-700 mb-1">Opening line (optional)</label>
          <textarea
            id="scenario-opening"
            value={openingLine}
            onChange={(e) => setOpeningLine(e.target.value)}
            placeholder="What the bot says first. If left empty, a default opener is used."
            rows={2}
            className="w-full border border-slate-300 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
          />
        </div>
        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-800">{error}</div>
        )}
        <div className="flex gap-3">
          <button
            type="submit"
            disabled={submitting}
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-6 py-2 rounded text-sm font-medium"
          >
            {submitting ? "Creating…" : "Create"}
          </button>
          <button
            type="button"
            onClick={() => navigate("/")}
            className="text-slate-600 hover:text-slate-900 text-sm"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}
```

Run `npm test NewScenarioPage` → green.

- [ ] **Step 3: Update `frontend/src/pages/ScenariosPage.tsx`** — add Create button + delete on custom

Read the existing `ScenariosPage.tsx`. Add:
- A "+ Create scenario" link/button in the header that navigates to `/scenarios/new`.
- Next to each scenario where `is_custom === true`, a `×` button that calls `api.deleteCustomScenario(s.id)` then invalidates the React Query cache.

Example shape (adapt to existing structure):

```typescript
import { Link } from "react-router-dom";
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { api } from "../api/client";

// inside ScenariosPage:
const qc = useQueryClient();
const deleteMutation = useMutation({
  mutationFn: (id: string) => api.deleteCustomScenario(id),
  onSuccess: () => qc.invalidateQueries({ queryKey: ["scenarios"] }),
});

// in JSX header:
<div className="flex items-center justify-between mb-4">
  <h1>Scenarios</h1>
  <Link to="/scenarios/new" className="text-sm text-blue-600 hover:underline">+ Create scenario</Link>
</div>

// in each scenario row:
{s.is_custom && (
  <button
    type="button"
    onClick={(e) => { e.preventDefault(); e.stopPropagation(); if (confirm(`Delete "${s.name}"?`)) deleteMutation.mutate(s.id); }}
    className="text-slate-400 hover:text-red-500 text-sm px-2"
    aria-label={`Delete ${s.name}`}
  >
    ×
  </button>
)}
```

Adapt to whatever wrapper element each scenario uses.

Also add a "custom" badge next to custom scenario names:

```tsx
{s.is_custom && <span className="text-xs px-1.5 py-0.5 bg-purple-100 text-purple-800 rounded">custom</span>}
```

- [ ] **Step 4: Update `frontend/src/pages/ScenariosPage.test.tsx`** — add tests

Add 1-2 tests:
- `Create scenario` link is visible.
- `×` button visible only on custom scenarios; clicking calls `api.deleteCustomScenario`.

(Look at existing test setup. Mock `api.getScenarios` to return a mix of built-in + custom.)

- [ ] **Step 5: Update `frontend/src/pages/PracticePage.tsx`** — add "Try again" button + use practice_only

In the result branch (when `lastResult` is set), find the existing button area. Add a "Try again" button alongside "Next card":

```tsx
<div className="flex gap-3 justify-center">
  <button
    onClick={tryAgain}
    className="border border-slate-300 hover:bg-slate-50 text-slate-700 px-6 py-2 rounded"
  >
    Try again
  </button>
  <button
    onClick={advance}
    className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded"
  >
    Next card
  </button>
</div>
```

Add the handler:

```typescript
const tryAgain = () => {
  setLastResult(null);
  // Does NOT advance index; user can record again for the same card.
};
```

Also update the grade mutation to pass `practice_only=true` on retry attempts. Track whether we're in a retry state:

```typescript
const [retryMode, setRetryMode] = useState(false);

const tryAgain = () => {
  setLastResult(null);
  setRetryMode(true);
};

const advance = () => {
  setLastResult(null);
  setRetryMode(false);
  setIndex((i) => i + 1);
};

const gradeMutation = useMutation({
  mutationFn: async (args: { card_id: string; audio: Blob | null; skip: boolean }) =>
    api.gradeCard(args.card_id, args.audio, args.skip, retryMode),
  onSuccess: async (result) => {
    setLastResult(result);
    try { await tts.speak(result.target); } catch { /* */ }
  },
});

// Also reset retryMode when moving to a new card
// (already covered by advance())
```

- [ ] **Step 6: Update `frontend/src/pages/PracticePage.test.tsx`** — add try-again test

```typescript
it("Try again resets result without advancing", async () => {
  // Use the existing mock pattern from this file. Mock getDueCards with at least 1 card,
  // mock gradeCard to return a successful result, simulate submitting a recording,
  // then click "Try again", assert lastResult cleared and same card still shown.
  vi.mocked(api.getDueCards).mockResolvedValueOnce({
    cards: [{
      id: "c1", created_from_session_id: "s1", tag: "grammar",
      user_utterance: "I goed", corrected_version: "I went", explanation: "Past tense.",
      context: null, due_date: "2026-05-22", ease_factor: 2.5, interval_days: 0,
      repetitions: 0, last_review_quality: null, review_history: [],
    }],
    total_due: 1,
  });
  vi.mocked(api.gradeCard).mockResolvedValue({
    card_id: "c1", quality: 4, user_attempt_text: "I went", target: "I went",
    explanation: "Good.", next_due: "2026-05-23",
  });

  render(wrap(<PracticePage />));
  // Wait for the card to render
  await waitFor(() => expect(screen.getByText(/i went/i)).toBeInTheDocument());

  // Submit a recording (push-to-talk via PushToTalkButton, OR find a Submit button
  // depending on PracticePage's UI). Look at PracticePage.tsx to see how grading is invoked.
  // For this test, simulate by directly invoking grade by stopping the recorder.
  // The simplest mock: trigger gradeMutation by calling handleStop.

  // After result appears, click "Try again"
  await waitFor(() => expect(screen.getByRole("button", { name: /next card/i })).toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: /try again/i }));

  // Card UI re-renders (not the result UI)
  await waitFor(() => expect(screen.queryByRole("button", { name: /next card/i })).not.toBeInTheDocument());
});
```

Adapt to whatever push-to-talk simulation the existing PracticePage tests use. If practice-page test is currently very thin (just empty state), this new test may need significantly more mock setup. Match the pattern.

If the test is too complex to wire up in this task, simplify the assertion to:
- Render PracticePage with `lastResult` already set (via a state mock or by triggering grade once).
- Click Try again.
- Assert the result UI disappears.

- [ ] **Step 7: Update `frontend/src/App.tsx`** — add `/scenarios/new` route

Add import:

```typescript
import { NewScenarioPage } from "./pages/NewScenarioPage";
```

Add route:

```typescript
<Route path="/scenarios/new" element={<NewScenarioPage />} />
```

- [ ] **Step 8: Run + build + commit**

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor/frontend
npm test 2>&1 | tail -15
npm run build 2>&1 | tail -5

cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/
git commit -m "feat(scenarios): UI to create/delete custom scenarios + Try again button"
```

## Context

- Branch: `main`. Previous: T5 commit.
- Task 6 of 8.

---

## Task 7: SRS engine — cross-session dedupe + per-session cap

**Files:**
- Modify: `tutor/srs_engine.py`
- Modify: `tests/test_srs_engine.py`

- [ ] **Step 1: Append failing tests** `tests/test_srs_engine.py`:

```python
def test_create_cards_skips_duplicates_by_user_utterance(tmp_path):
    """Cross-session: a growth_point whose user_utterance matches an existing card is skipped."""
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint
    engine = SRSEngine(path=tmp_path / "cards.json")
    # First create one card
    gp1 = GrowthPoint(tag="grammar", user_utterance="I goed",
                     corrected_version="I went", explanation="Past tense.", context=None)
    engine.create_cards([gp1], session_id="s1")
    # Now try to create another with same user_utterance
    gp2 = GrowthPoint(tag="grammar", user_utterance="I goed",
                     corrected_version="I went home", explanation="Better.", context=None)
    new_cards = engine.create_cards([gp2], session_id="s2")
    assert new_cards == []
    assert len(engine.all_cards()) == 1


def test_create_cards_dedupe_is_case_insensitive(tmp_path):
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint
    engine = SRSEngine(path=tmp_path / "cards.json")
    gp1 = GrowthPoint(tag="grammar", user_utterance="  I Goed  ",
                     corrected_version="I went", explanation="X", context=None)
    engine.create_cards([gp1], session_id="s1")
    gp2 = GrowthPoint(tag="vocab", user_utterance="i goed",
                     corrected_version="i went", explanation="Y", context=None)
    new_cards = engine.create_cards([gp2], session_id="s2")
    assert new_cards == []


def test_create_cards_caps_at_5_per_session(tmp_path):
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint
    engine = SRSEngine(path=tmp_path / "cards.json")
    gps = [
        GrowthPoint(tag="grammar", user_utterance=f"sentence number {i}",
                    corrected_version="x", explanation="y", context=None)
        for i in range(8)
    ]
    new_cards = engine.create_cards(gps, session_id="s1")
    assert len(new_cards) == 5


def test_create_cards_prioritizes_grammar_over_vocab(tmp_path):
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint
    engine = SRSEngine(path=tmp_path / "cards.json")
    gps = (
        [GrowthPoint(tag="vocab", user_utterance=f"vocab {i}", corrected_version="c",
                     explanation="e", context=None) for i in range(4)]
        + [GrowthPoint(tag="grammar", user_utterance=f"grammar {i}", corrected_version="c",
                       explanation="e", context=None) for i in range(4)]
    )
    new_cards = engine.create_cards(gps, session_id="s1")
    assert len(new_cards) == 5
    tags = [c.tag for c in new_cards]
    # All 4 grammars should make it; one vocab too
    assert tags.count("grammar") == 4
    assert tags.count("vocab") == 1


def test_create_cards_all_duplicates_returns_empty(tmp_path):
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint
    engine = SRSEngine(path=tmp_path / "cards.json")
    gp = GrowthPoint(tag="grammar", user_utterance="I goed",
                    corrected_version="I went", explanation="x", context=None)
    engine.create_cards([gp], session_id="s1")
    # Second call: all dupes
    result = engine.create_cards([gp, gp], session_id="s2")
    assert result == []
```

- [ ] **Step 2: Run** `pytest tests/test_srs_engine.py -v 2>&1 | tail -20` → 5 fail.

- [ ] **Step 3: Modify `tutor/srs_engine.py`** — rewrite `create_cards`

At top of file, add a constant:

```python
PER_SESSION_CARD_LIMIT = 5
```

Replace `create_cards`:

```python
    def create_cards(self, growth_points: list[GrowthPoint], session_id: str) -> list[Card]:
        # Cross-session dedupe by lowered+stripped user_utterance
        existing_keys = {c.user_utterance.lower().strip() for c in self._cards.values()}
        filtered: list[GrowthPoint] = []
        for gp in growth_points:
            key = gp.user_utterance.lower().strip()
            if not key or key in existing_keys:
                continue
            existing_keys.add(key)  # also dedupe within this batch
            filtered.append(gp)

        # Prioritize: grammar first, vocab second, preserve relative order within tag
        filtered.sort(key=lambda gp: 0 if gp.tag == "grammar" else 1)

        # Cap
        capped = filtered[:PER_SESSION_CARD_LIMIT]
        if not capped:
            return []

        today = self._now()
        tomorrow = (today + timedelta(days=1)).isoformat()
        new_cards: list[Card] = []
        for gp in capped:
            card = Card(
                id=uuid.uuid4().hex[:12],
                created_from_session_id=session_id,
                tag=gp.tag,
                user_utterance=gp.user_utterance,
                corrected_version=gp.corrected_version,
                explanation=gp.explanation,
                context=gp.context,
                due_date=tomorrow,
            )
            self._cards[card.id] = card
            new_cards.append(card)
        self._flush()
        return new_cards
```

Notes:
- `sorted(..., key=lambda gp: 0 if gp.tag == "grammar" else 1)` is stable per Python guarantee, so relative order is preserved within each tag.
- Empty `capped` returns early without writing — avoids no-op disk write.

- [ ] **Step 4: Run + commit**

```bash
pytest tests/test_srs_engine.py -v 2>&1 | tail -15
pytest 2>&1 | tail -5
```

→ 5 new tests green. Some existing SRS tests may need adjustment if they implicitly relied on no-dedup or unlimited cards. Check failures and adapt mock data so each test uses distinct `user_utterance` values.

```bash
git add tutor/srs_engine.py tests/test_srs_engine.py
git commit -m "feat(srs): create_cards cross-session dedupe + 5/session cap (grammar first)"
```

## Context

- Branch: `main`. Previous: T6 commit.
- Task 7 of 8.

---

## Task 8: Backend grade_card `practice_only` flag + manual smoke

**Files:**
- Modify: `tutor/web/services.py` — `grade_card_service` accepts `practice_only`.
- Modify: `tutor/web/api.py` — route reads `practice_only` query param.
- Modify: `tests/web/test_api.py` — test for `practice_only=true`.

### Step 1: Update `grade_card_service` signature

In `tutor/web/services.py`, find `grade_card_service`. Add `practice_only: bool = False` parameter. Skip `deps.srs.record_review(...)` call when True. Same return shape (still grade + explanation, but `next_due` shows current value not the updated one).

Read the existing function first to see its current shape, then modify. The relevant change:

```python
def grade_card_service(
    deps: Dependencies,
    card_id: str,
    audio_bytes: bytes | None,
    skip: bool,
    practice_only: bool = False,
) -> GradeResult:
    card = deps.srs.load_card(card_id)
    # ... existing ASR / grader / quality computation ...
    if not practice_only:
        deps.srs.record_review(card_id, quality)
    # ... rest unchanged, but recompute `next_due` from card AFTER potential update:
    final_card = deps.srs.load_card(card_id)
    return GradeResult(..., next_due=final_card.due_date)
```

### Step 2: Update route

In `tutor/web/api.py`, modify the `grade_card` route to read `practice_only`:

```python
    @app.post("/api/review/{card_id}/grade", response_model=GradeResult)
    async def grade_card(
        card_id: str,
        audio: UploadFile | None = File(None),
        skip: bool = False,
        practice_only: bool = False,
        d: Dependencies = Depends(get_deps),
    ):
        audio_bytes = await audio.read() if audio is not None else None
        return services.grade_card_service(
            d, card_id=card_id, audio_bytes=audio_bytes, skip=skip, practice_only=practice_only,
        )
```

### Step 3: Add test in `tests/web/test_api.py`

```python
def test_post_grade_practice_only_does_not_update_srs(tmp_path, mocker):
    client, deps = _client(tmp_path, mocker)
    # Set up SRS engine with one card via the real engine to keep it simple
    from tutor.evaluator import GrowthPoint
    deps.srs.create_cards(
        [GrowthPoint(tag="grammar", user_utterance="I goed",
                     corrected_version="I went", explanation="x", context=None)],
        session_id="s1",
    )
    card = deps.srs.all_cards()[0]
    original_due = card.due_date

    deps.asr.transcribe.return_value = "I went"
    deps.llm.complete.return_value = "5"  # grader returns 5

    audio_blob = b"audio-bytes"
    files = {"audio": ("test.webm", audio_blob, "audio/webm")}
    r = client.post(f"/api/review/{card.id}/grade?practice_only=true", files=files)
    assert r.status_code == 200

    # SRS state unchanged
    card_after = deps.srs.load_card(card.id)
    assert card_after.due_date == original_due
    assert card_after.repetitions == 0
```

### Step 4: Run + commit

```bash
pytest tests/web/test_api.py -v 2>&1 | tail -20
pytest 2>&1 | tail -5
```

→ new test green; existing grade tests still green.

```bash
git add tutor/web/services.py tutor/web/api.py tests/web/test_api.py
git commit -m "feat(grade): practice_only flag skips SRS scheduling update"
```

### Step 5: Manual smoke — full Stage 2f flow

Backfill existing duplicate cards:

```bash
python3 -c "
import json
with open('cards.json') as f: data = json.load(f)
cards = data['cards']
seen = set()
deduped = []
for c in cards:
    key = c['user_utterance'].lower().strip()
    if key in seen: continue
    seen.add(key)
    deduped.append(c)
data['cards'] = deduped
print(f'before={len(cards)} after={len(deduped)} removed={len(cards)-len(deduped)}')
with open('cards.json','w') as f: json.dump(data, f, indent=2, ensure_ascii=False)
"
```

Push:

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor
git push origin main
```

Run web UI:

```bash
./scripts/build_and_serve.sh
```

Manual checks at `http://127.0.0.1:8000`:

1. Click Scenarios → see 7 scenarios (3 old + 4 new built-in).
2. Click "+ Create scenario" → fill form ("Talk to a barber", advanced, "You are a friendly NYC barber...", optional opening). Submit. Lands on scenarios list. New scenario visible with "custom" badge.
3. Click the new scenario → session starts → bot replies in barber role.
4. End session.
5. Back to Scenarios → click `×` next to your custom scenario → confirm → it disappears.
6. Run another session and intentionally repeat the same mistake 3 times: only 1 card lands in /practice.
7. Run a session with 7 distinct mistakes: max 5 cards land.
8. In /practice tomorrow, grade a card (4/5). Result screen → click "Try again" → record a different attempt → see new result. Original SRS due_date NOT bumped (check `cards.json` for that card's `due_date` — only the first grade should have changed it).

### Step 6: Report

If anything regresses, file a follow-up. Otherwise Stage 2f done.

## Context

- Branch: `main`. Previous: T7 commit.
- Task 8 of 8.

---

## Self-review

1. **Spec coverage:**
   - 4 new built-in YAML scenarios → T1 ✓
   - `CustomScenarioStorage` JSON CRUD → T2 ✓
   - Loader merges built-in + custom → T3 ✓
   - Backend custom scenario routes + `is_custom` flag → T4 ✓
   - Frontend types + API client (create, delete, gradeCard practice_only) → T5 ✓
   - NewScenarioPage + ScenariosPage delete + PracticePage Try again + App route → T6 ✓
   - SRS dedupe + cap → T7 ✓
   - Grade `practice_only` flag → T8 ✓
   - Manual smoke + cards.json backfill → T8 ✓

2. **Placeholder scan:** no TBD/TODO strings.

3. **Type consistency:**
   - `ScenarioSummary.is_custom: bool` (backend default False, frontend optional). Matches across stack.
   - `CustomScenarioCreate` shape identical front/back.
   - `gradeCard(card_id, audio, skip, practice_only=false)` — TS optional param.
   - `PER_SESSION_CARD_LIMIT = 5` constant for SRS.

4. **Failure modes:**
   - Empty name/prompt → 422 (T4 test).
   - Missing custom scenario delete → 404 (T4 test).
   - Loader: custom storage fails → fall back to built-in only (graceful).
   - Built-in scenario id clash with custom → built-in wins (T3 test).
   - SRS all-dupes → returns []  (T7 test).
   - Practice "Try again" double-grading uses practice_only=true → no SRS bump (T8 test).

---

## Definition of Done

- 8 task commits + push on `main`.
- pytest ~230 green (201 + ~30 new).
- npm test ~57 green (49 + 8 new).
- npm run build succeeds.
- 4 new built-in scenarios visible.
- User can create/delete custom scenarios via /scenarios/new and ScenariosPage.
- SRS create_cards dedupes cross-session and caps at 5.
- "Try again" button on /practice resets result without bumping SRS scheduling.
- cards.json backfilled (2 dupes of "okay, show me it." removed).
- No CLI regressions.
