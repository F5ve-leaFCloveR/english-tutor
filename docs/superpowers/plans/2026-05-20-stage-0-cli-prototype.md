# Stage 0: CLI Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python CLI that lets the user have a real spoken English conversation with an LLM playing a behavioral-interview role — proving the core voice loop works end-to-end before investing in any UI.

**Architecture:** Single-process Python CLI. User presses Enter to start/stop recording, audio is captured via `sounddevice`, transcribed locally via `faster-whisper`, sent to OpenRouter for the LLM response, spoken back via macOS `say`. Session transcripts persist to JSON files. A budget tracker enforces a daily USD/token cap before any LLM call.

**Tech Stack:**
- Python 3.11+
- `openai` SDK pointed at OpenRouter base URL (LLM)
- `faster-whisper` (ASR, runs on CPU, fine for short clips)
- `sounddevice` + `soundfile` + `numpy` (mic recording)
- macOS `say` via `subprocess` (TTS)
- `pydantic-settings` (config / `.env` loading)
- `pyyaml` (scenario definitions)
- `pytest` + `pytest-mock` (tests)
- `ruff` (linting, optional but recommended)

**Prerequisites the user does before starting:**
1. OpenRouter account exists, has a small balance (~$5), daily cap = $0.5 set in dashboard.
2. A fresh API key (the leaked one from the chat is already revoked and replaced).
3. macOS (the plan assumes `say` is available). If on Linux, swap to `espeak-ng` — same interface.
4. Python 3.11+ available on PATH.

---

## File Structure

```
english-tutor/
├── .env                              # gitignored; OPENROUTER_API_KEY=...
├── .env.example                      # committed; documents required vars
├── .gitignore                        # already exists
├── pyproject.toml                    # project + dependencies
├── README.md                         # how to run
├── docs/superpowers/
│   ├── specs/2026-05-20-english-tutor-design.md   # already exists
│   └── plans/2026-05-20-stage-0-cli-prototype.md  # this file
├── tutor/
│   ├── __init__.py
│   ├── settings.py                   # pydantic-settings, loads .env
│   ├── budget.py                     # token/cost tracker + hard caps
│   ├── llm.py                        # OpenRouter client wrapper
│   ├── asr.py                        # faster-whisper wrapper
│   ├── tts.py                        # macOS `say` wrapper
│   ├── audio.py                      # mic recording (sounddevice)
│   ├── scenarios/
│   │   ├── __init__.py
│   │   ├── loader.py                 # YAML loader + Jinja prompt builder
│   │   └── tech_interview_behavioral.yaml
│   ├── storage.py                    # session JSON persistence
│   ├── session.py                    # voice loop orchestrator
│   └── cli.py                        # argparse entry point
├── tests/
│   ├── __init__.py
│   ├── conftest.py                   # shared fixtures
│   ├── test_settings.py
│   ├── test_budget.py
│   ├── test_llm.py
│   ├── test_scenarios.py
│   ├── test_tts.py
│   ├── test_asr.py
│   ├── test_audio.py
│   ├── test_storage.py
│   └── test_session.py
└── sessions/                         # gitignored; JSON files appear here
```

Each file has one responsibility. The session orchestrator (`session.py`) wires the rest together but contains no I/O of its own — that keeps it testable with mocks.

---

## Task 1: Project setup and smoke test

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `README.md`
- Create: `tutor/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/test_smoke.py`

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "english-tutor"
version = "0.1.0"
description = "Voice-first CLI for English speaking practice via LLM roleplay"
requires-python = ">=3.11"
dependencies = [
    "openai>=1.40.0",
    "faster-whisper>=1.0.0",
    "sounddevice>=0.4.7",
    "soundfile>=0.12.1",
    "numpy>=1.26.0",
    "pydantic-settings>=2.4.0",
    "pyyaml>=6.0.2",
    "jinja2>=3.1.4",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-mock>=3.14.0",
    "ruff>=0.6.0",
]

[project.scripts]
tutor = "tutor.cli:main"

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short"

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["tutor*"]
```

- [ ] **Step 2: Create `.env.example`**

```
# Copy this file to .env and fill in real values.
# .env is gitignored. NEVER commit secrets.

OPENROUTER_API_KEY=sk-or-v1-REPLACE_ME
OPENROUTER_MODEL=google/gemini-2.5-flash
DAILY_USD_BUDGET=0.5
DAILY_TOKEN_BUDGET=200000
PER_SESSION_TURN_LIMIT=25
WHISPER_MODEL_SIZE=small
```

- [ ] **Step 3: Create minimal `README.md`**

```markdown
# English Tutor — Stage 0 CLI

Voice-first CLI for practicing English via LLM roleplay.

## Setup
1. `cp .env.example .env` and fill in your OpenRouter API key.
2. `python -m venv .venv && source .venv/bin/activate`
3. `pip install -e ".[dev]"`
4. `pytest` — all tests should pass.

## Run a session
`tutor interview` — starts a tech-interview behavioral practice session.

Press Enter to start/stop recording each turn. Type `end` instead of speaking to finish the session.
```

- [ ] **Step 4: Create empty package init files**

`tutor/__init__.py`:
```python
__version__ = "0.1.0"
```

`tests/__init__.py`:
```python
# tests package
```

- [ ] **Step 5: Create `tests/conftest.py` with a smoke test fixture**

```python
"""Shared pytest fixtures."""
import pytest


@pytest.fixture
def fixed_now():
    """Deterministic 'now' for budget reset tests."""
    from datetime import datetime
    return datetime(2026, 5, 20, 12, 0, 0)
```

- [ ] **Step 6: Create `tests/test_smoke.py`**

```python
def test_package_importable():
    import tutor
    assert tutor.__version__ == "0.1.0"
```

- [ ] **Step 7: Install and verify**

Run: `python -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
Expected: installation succeeds.

Run: `pytest`
Expected: 1 passed.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .env.example README.md tutor/ tests/
git commit -m "chore: project scaffolding and smoke test"
```

---

## Task 2: Settings module

Loads `.env`, validates required keys are present, exposes typed config.

**Files:**
- Create: `tutor/settings.py`
- Create: `tests/test_settings.py`

- [ ] **Step 1: Write the failing test**

`tests/test_settings.py`:
```python
import os
import pytest
from pydantic import ValidationError


def test_settings_loads_api_key(monkeypatch):
    from tutor.settings import Settings
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    s = Settings()
    assert s.openrouter_api_key == "sk-or-v1-test"
    assert s.openrouter_model == "google/gemini-2.5-flash"
    assert s.daily_usd_budget == 0.5
    assert s.daily_token_budget == 200_000
    assert s.per_session_turn_limit == 25
    assert s.whisper_model_size == "small"


def test_settings_raises_without_api_key(monkeypatch):
    from tutor.settings import Settings
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    # disable .env file loading for this test
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_rejects_placeholder_key(monkeypatch):
    from tutor.settings import Settings
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-REPLACE_ME")
    with pytest.raises(ValidationError):
        Settings()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_settings.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'tutor.settings'`)

- [ ] **Step 3: Implement settings module**

`tutor/settings.py`:
```python
"""Application configuration. Reads .env via pydantic-settings."""
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    openrouter_api_key: str = Field(..., description="OpenRouter API key")
    openrouter_model: str = Field(default="google/gemini-2.5-flash")
    daily_usd_budget: float = Field(default=0.5, gt=0)
    daily_token_budget: int = Field(default=200_000, gt=0)
    per_session_turn_limit: int = Field(default=25, gt=0)
    whisper_model_size: str = Field(default="small")

    @field_validator("openrouter_api_key")
    @classmethod
    def reject_placeholder(cls, v: str) -> str:
        if "REPLACE_ME" in v:
            raise ValueError("OPENROUTER_API_KEY still contains placeholder value")
        if not v.startswith("sk-or-"):
            raise ValueError("OPENROUTER_API_KEY does not look like an OpenRouter key")
        return v


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_settings.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add tutor/settings.py tests/test_settings.py
git commit -m "feat: settings module loads and validates .env"
```

---

## Task 3: Budget tracker

Tracks daily USD spend and token usage. Blocks calls when either cap is reached. Persists to `budget.json` so a process restart doesn't reset the day.

**Files:**
- Create: `tutor/budget.py`
- Create: `tests/test_budget.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_budget.py`:
```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_budget.py -v`
Expected: 5 errors (`ModuleNotFoundError: No module named 'tutor.budget'`)

- [ ] **Step 3: Implement budget tracker**

`tutor/budget.py`:
```python
"""Daily USD + token budget tracker. Persists across process restarts."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Callable


class BudgetExceededError(Exception):
    """Raised when continuing would exceed the daily budget."""


@dataclass
class _DailyState:
    day: str  # ISO date
    tokens: int
    usd: float


class BudgetTracker:
    def __init__(
        self,
        path: Path,
        daily_usd_cap: float,
        daily_token_cap: int,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.path = Path(path)
        self.daily_usd_cap = daily_usd_cap
        self.daily_token_cap = daily_token_cap
        self._now = now
        self._state = self._load_or_init()

    def _today_iso(self) -> str:
        return self._now().date().isoformat()

    def _load_or_init(self) -> _DailyState:
        if not self.path.exists():
            return _DailyState(day=self._today_iso(), tokens=0, usd=0.0)
        try:
            data = json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return _DailyState(day=self._today_iso(), tokens=0, usd=0.0)
        if data.get("day") != self._today_iso():
            return _DailyState(day=self._today_iso(), tokens=0, usd=0.0)
        return _DailyState(
            day=data["day"],
            tokens=int(data.get("tokens", 0)),
            usd=float(data.get("usd", 0.0)),
        )

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "day": self._state.day,
            "tokens": self._state.tokens,
            "usd": self._state.usd,
        }))

    @property
    def tokens_today(self) -> int:
        return self._state.tokens

    @property
    def usd_today(self) -> float:
        return self._state.usd

    def record(self, tokens_in: int, tokens_out: int, usd_cost: float) -> None:
        self._state.tokens += tokens_in + tokens_out
        self._state.usd += usd_cost
        self._flush()

    def check_can_spend(self) -> None:
        """Raise BudgetExceededError if either cap has been reached."""
        if self._state.usd >= self.daily_usd_cap:
            raise BudgetExceededError(
                f"Daily USD cap reached ({self._state.usd:.4f} >= {self.daily_usd_cap})"
            )
        if self._state.tokens >= self.daily_token_cap:
            raise BudgetExceededError(
                f"Daily token cap reached ({self._state.tokens} >= {self.daily_token_cap})"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_budget.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add tutor/budget.py tests/test_budget.py
git commit -m "feat: budget tracker with USD/token caps and daily reset"
```

---

## Task 4: LLM client (OpenRouter)

Thin wrapper around OpenAI SDK pointed at OpenRouter. Records token usage to the budget tracker. Retries on 429/5xx with capped backoff.

**Files:**
- Create: `tutor/llm.py`
- Create: `tests/test_llm.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_llm.py`:
```python
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
        # OpenRouter returns cost in usage object via a custom field
        response.model_extra = {"cost": cost}
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
    # first call: 500. second call: ok.
    error = openai.InternalServerError(
        message="server error",
        response=MagicMock(status_code=500),
        body=None,
    )
    fake_client.chat.completions.create.side_effect = [
        error,
        _make_response("OK", 10, 5, 0.0001),
    ]
    # patch sleep so the test is instant
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
        cost=None,  # OpenRouter sometimes omits cost
    )

    llm = LLMClient(
        client=fake_client,
        model="google/gemini-2.5-flash",
        budget=budget,
    )
    llm.complete(messages=[{"role": "user", "content": "Hi"}])

    # No cost field → estimate is 0. Tokens still recorded.
    assert budget.tokens_today == 1500
    assert budget.usd_today == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_llm.py -v`
Expected: 4 errors (`ModuleNotFoundError: No module named 'tutor.llm'`)

- [ ] **Step 3: Implement LLM client**

`tutor/llm.py`:
```python
"""OpenRouter LLM client with retry and budget enforcement."""
from __future__ import annotations

import logging
import time
from typing import Any

import openai
from openai import OpenAI

from tutor.budget import BudgetTracker

log = logging.getLogger(__name__)

_RETRYABLE = (
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
    openai.RateLimitError,
)


class LLMClient:
    def __init__(
        self,
        client: OpenAI,
        model: str,
        budget: BudgetTracker,
        max_retries: int = 2,
        base_delay: float = 1.0,
    ) -> None:
        self._client = client
        self._model = model
        self._budget = budget
        self._max_retries = max_retries
        self._base_delay = base_delay

    @classmethod
    def from_settings(cls, settings, budget: BudgetTracker) -> "LLMClient":
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openrouter_api_key,
        )
        return cls(client=client, model=settings.openrouter_model, budget=budget)

    def complete(self, messages: list[dict[str, str]], temperature: float = 0.7) -> str:
        self._budget.check_can_spend()

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.chat.completions.create(
                    model=self._model,
                    messages=messages,
                    temperature=temperature,
                )
                self._record_usage(response)
                return response.choices[0].message.content or ""
            except _RETRYABLE as e:
                last_error = e
                if attempt >= self._max_retries:
                    break
                delay = self._base_delay * (2 ** attempt)
                log.warning("LLM call failed (%s); retrying in %.1fs", type(e).__name__, delay)
                time.sleep(delay)

        assert last_error is not None
        raise last_error

    def _record_usage(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        tokens_in = getattr(usage, "prompt_tokens", 0) or 0
        tokens_out = getattr(usage, "completion_tokens", 0) or 0
        # OpenRouter exposes cost via model_extra in newer SDK versions
        cost = 0.0
        extra = getattr(response, "model_extra", None) or {}
        if "cost" in extra:
            try:
                cost = float(extra["cost"])
            except (TypeError, ValueError):
                cost = 0.0
        self._budget.record(tokens_in=tokens_in, tokens_out=tokens_out, usd_cost=cost)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_llm.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add tutor/llm.py tests/test_llm.py
git commit -m "feat: OpenRouter LLM client with retry and budget enforcement"
```

---

## Task 5: Scenario library

YAML scenario files + a loader that builds the system prompt from the YAML using Jinja.

**Files:**
- Create: `tutor/scenarios/__init__.py`
- Create: `tutor/scenarios/loader.py`
- Create: `tutor/scenarios/tech_interview_behavioral.yaml`
- Create: `tests/test_scenarios.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_scenarios.py`:
```python
import pytest
from pathlib import Path


def test_load_scenario_by_id():
    from tutor.scenarios.loader import load_scenario
    sc = load_scenario("tech_interview_behavioral")
    assert sc.id == "tech_interview_behavioral"
    assert "interview" in sc.name.lower()
    assert sc.opening_line  # non-empty
    assert sc.system_prompt  # non-empty


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
```

- [ ] **Step 2: Create the scenario YAML**

`tutor/scenarios/tech_interview_behavioral.yaml`:
```yaml
id: tech_interview_behavioral
name: "Tech interview — behavioral round"
difficulty: intermediate
counterpart:
  role: "Senior engineering manager at a mid-size US-based ML startup"
  persona: |
    Professional, warm but probing. Asks STAR-style follow-ups when answers are vague.
    Curious about real engineering details, not buzzwords.
goal: >
  Help the candidate practice behavioral interview answers: past projects, challenges,
  conflicts, collaboration moments, mistakes, future goals.
vocab_focus:
  - "STAR-format phrasing (situation, task, action, result)"
  - "Ownership and impact vocabulary"
  - "Hedging and clarification phrases"
opening_line: >
  Hi, thanks for taking the time today. To start — could you tell me a bit about yourself
  and what you're currently working on?
system_prompt_template: |
  You are a senior engineering manager at a US-based ML startup, conducting a behavioral
  interview round in English. The candidate is a {{ user_native_language }} native speaker
  practicing their spoken English.

  STRICT RULES:
  - Keep responses concise — 1 to 3 sentences. This is real interview pace.
  - Ask one question at a time. Wait for the candidate's answer.
  - Probe with follow-ups when answers are vague or generic ("Can you give a concrete example?").
  - Stay in role. Do NOT break character. Do NOT mention you are an AI, a model, or a tutor.
  - Reply ONLY in English. If the candidate slips into {{ user_native_language }},
    politely ask them to repeat in English.
  - Cover behavioral territory: past projects, challenges overcome, collaboration,
    conflicts, mistakes, learnings, motivations.
  - Do NOT correct the candidate's English mid-interview. That happens later.

  Begin the conversation with your opening line, then proceed naturally based on
  their responses.
```

- [ ] **Step 3: Implement the loader**

`tutor/scenarios/__init__.py`:
```python
# scenarios package
```

`tutor/scenarios/loader.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_scenarios.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add tutor/scenarios/ tests/test_scenarios.py
git commit -m "feat: scenario loader with tech_interview_behavioral YAML"
```

---

## Task 6: TTS wrapper (macOS `say`)

Tiny adapter around `subprocess.run(["say", ...])`. Mockable for tests.

**Files:**
- Create: `tutor/tts.py`
- Create: `tests/test_tts.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_tts.py`:
```python
from unittest.mock import MagicMock


def test_tts_speak_invokes_say(mocker):
    from tutor.tts import MacSayTTS
    fake_run = mocker.patch("tutor.tts.subprocess.run")
    tts = MacSayTTS(voice="Samantha", rate=180)
    tts.speak("Hello, candidate.")
    fake_run.assert_called_once()
    args = fake_run.call_args[0][0]
    assert args[0] == "say"
    assert "-v" in args and "Samantha" in args
    assert "-r" in args and "180" in args
    assert "Hello, candidate." in args


def test_tts_speak_empty_text_is_noop(mocker):
    from tutor.tts import MacSayTTS
    fake_run = mocker.patch("tutor.tts.subprocess.run")
    tts = MacSayTTS()
    tts.speak("")
    tts.speak("   ")
    fake_run.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_tts.py -v`
Expected: 2 errors (`ModuleNotFoundError: No module named 'tutor.tts'`)

- [ ] **Step 3: Implement TTS wrapper**

`tutor/tts.py`:
```python
"""macOS `say` TTS adapter."""
from __future__ import annotations

import subprocess


class MacSayTTS:
    def __init__(self, voice: str = "Samantha", rate: int = 180) -> None:
        self._voice = voice
        self._rate = rate

    def speak(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        subprocess.run(
            ["say", "-v", self._voice, "-r", str(self._rate), text],
            check=False,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_tts.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add tutor/tts.py tests/test_tts.py
git commit -m "feat: macOS say TTS wrapper"
```

---

## Task 7: ASR wrapper (faster-whisper)

Wraps `faster-whisper` model. Loaded lazily on first call so tests don't pay model-load cost when the ASR isn't exercised directly.

**Files:**
- Create: `tutor/asr.py`
- Create: `tests/test_asr.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_asr.py`:
```python
from unittest.mock import MagicMock
from pathlib import Path


def test_asr_transcribes_wav_file(mocker, tmp_path):
    from tutor.asr import WhisperASR

    # mock the faster-whisper model so the test doesn't load real weights
    fake_segment = MagicMock()
    fake_segment.text = "Hello, how are you?"
    fake_info = MagicMock()
    fake_model = MagicMock()
    fake_model.transcribe.return_value = (iter([fake_segment]), fake_info)

    fake_loader = mocker.patch("tutor.asr.WhisperModel", return_value=fake_model)

    asr = WhisperASR(model_size="small")
    wav_path = tmp_path / "audio.wav"
    wav_path.write_bytes(b"")  # contents don't matter — model is mocked

    text = asr.transcribe(wav_path)
    assert text == "Hello, how are you?"
    fake_loader.assert_called_once()
    fake_model.transcribe.assert_called_once_with(
        str(wav_path),
        language="en",
        beam_size=5,
    )


def test_asr_joins_multiple_segments(mocker, tmp_path):
    from tutor.asr import WhisperASR

    s1 = MagicMock(); s1.text = "Hello,"
    s2 = MagicMock(); s2.text = " how are you?"
    fake_model = MagicMock()
    fake_model.transcribe.return_value = (iter([s1, s2]), MagicMock())
    mocker.patch("tutor.asr.WhisperModel", return_value=fake_model)

    asr = WhisperASR(model_size="small")
    wav_path = tmp_path / "audio.wav"
    wav_path.write_bytes(b"")
    text = asr.transcribe(wav_path)
    assert text == "Hello, how are you?"


def test_asr_model_loaded_only_once(mocker, tmp_path):
    from tutor.asr import WhisperASR

    fake_model = MagicMock()
    fake_model.transcribe.return_value = (iter([]), MagicMock())
    loader = mocker.patch("tutor.asr.WhisperModel", return_value=fake_model)

    asr = WhisperASR(model_size="small")
    wav_path = tmp_path / "audio.wav"
    wav_path.write_bytes(b"")
    asr.transcribe(wav_path)
    asr.transcribe(wav_path)
    assert loader.call_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_asr.py -v`
Expected: 3 errors (`ModuleNotFoundError: No module named 'tutor.asr'`)

- [ ] **Step 3: Implement ASR wrapper**

`tutor/asr.py`:
```python
"""faster-whisper adapter for English-only short-clip transcription."""
from __future__ import annotations

import logging
from pathlib import Path

from faster_whisper import WhisperModel

log = logging.getLogger(__name__)


class WhisperASR:
    def __init__(self, model_size: str = "small", device: str = "cpu", compute_type: str = "int8") -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._model: WhisperModel | None = None

    def _ensure_model(self) -> WhisperModel:
        if self._model is None:
            log.info("Loading faster-whisper model: %s (%s)", self._model_size, self._device)
            self._model = WhisperModel(
                self._model_size,
                device=self._device,
                compute_type=self._compute_type,
            )
        return self._model

    def transcribe(self, wav_path: Path) -> str:
        model = self._ensure_model()
        segments, _info = model.transcribe(
            str(wav_path),
            language="en",
            beam_size=5,
        )
        return "".join(seg.text for seg in segments).strip()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_asr.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add tutor/asr.py tests/test_asr.py
git commit -m "feat: faster-whisper ASR wrapper with lazy model load"
```

---

## Task 8: Audio recorder

Press-Enter-to-start, press-Enter-to-stop recording from the default mic. Writes a WAV to a temp path.

**Files:**
- Create: `tutor/audio.py`
- Create: `tests/test_audio.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_audio.py`:
```python
from unittest.mock import MagicMock, patch
from pathlib import Path
import numpy as np


def test_audio_recorder_records_to_wav(mocker, tmp_path):
    from tutor.audio import AudioRecorder

    fake_stream = MagicMock()
    fake_stream.__enter__ = MagicMock(return_value=fake_stream)
    fake_stream.__exit__ = MagicMock(return_value=False)
    fake_input_stream = mocker.patch(
        "tutor.audio.sd.InputStream",
        return_value=fake_stream,
    )

    fake_sf_write = mocker.patch("tutor.audio.sf.write")

    # simulate "press Enter twice" by replacing input()
    inputs = iter(["", ""])
    mocker.patch("builtins.input", side_effect=lambda *_a, **_kw: next(inputs))

    rec = AudioRecorder(sample_rate=16000, channels=1)
    out_path = tmp_path / "turn.wav"

    # inject a chunk into the recorder's callback so something gets written
    def fake_start():
        # call the audio callback once with fake data
        rec._on_audio(np.zeros((1600, 1), dtype=np.float32), 1600, None, None)
    fake_stream.start = fake_start

    result_path = rec.record_to_wav(out_path)

    assert result_path == out_path
    fake_input_stream.assert_called_once()
    fake_sf_write.assert_called_once()
    args, _ = fake_sf_write.call_args
    assert args[0] == str(out_path)
    assert args[2] == 16000  # sample rate
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_audio.py -v`
Expected: error (`ModuleNotFoundError: No module named 'tutor.audio'`)

- [ ] **Step 3: Implement audio recorder**

`tutor/audio.py`:
```python
"""Microphone recorder: press Enter to start, press Enter to stop."""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf

log = logging.getLogger(__name__)


class AudioRecorder:
    def __init__(self, sample_rate: int = 16000, channels: int = 1) -> None:
        self._sample_rate = sample_rate
        self._channels = channels
        self._buffer: list[np.ndarray] = []

    def _on_audio(self, indata, frames, time_info, status) -> None:
        if status:
            log.debug("sounddevice status: %s", status)
        self._buffer.append(indata.copy())

    def record_to_wav(self, out_path: Path) -> Path:
        """Block until user signals stop (Enter twice). Writes a WAV. Returns the path."""
        self._buffer = []
        input("[press Enter to start recording] ")
        stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=self._channels,
            dtype="float32",
            callback=self._on_audio,
        )
        with stream:
            stream.start()
            input("[recording... press Enter to stop] ")

        if not self._buffer:
            log.warning("No audio captured")
            audio = np.zeros((1, self._channels), dtype=np.float32)
        else:
            audio = np.concatenate(self._buffer, axis=0)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(out_path), audio, self._sample_rate)
        return out_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_audio.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add tutor/audio.py tests/test_audio.py
git commit -m "feat: press-Enter-to-start mic recorder"
```

---

## Task 9: Session storage

Append-only JSON file per session under `sessions/{date}/{session_id}.json`. No DB yet.

**Files:**
- Create: `tutor/storage.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_storage.py`:
```python
import json
from datetime import datetime
from pathlib import Path


def test_storage_creates_session_file(tmp_path):
    from tutor.storage import SessionStorage

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 20, 14, 30, 5))
    session_id = storage.create_session(scenario_id="tech_interview_behavioral")
    assert session_id  # truthy

    sessions = list(tmp_path.rglob("*.json"))
    assert len(sessions) == 1
    data = json.loads(sessions[0].read_text())
    assert data["scenario_id"] == "tech_interview_behavioral"
    assert data["started_at"].startswith("2026-05-20T14:30")
    assert data["turns"] == []


def test_storage_appends_turn(tmp_path):
    from tutor.storage import SessionStorage

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 20, 14, 30, 5))
    session_id = storage.create_session("tech_interview_behavioral")
    storage.append_turn(session_id, user_text="Hi, I'm a candidate.", llm_text="Welcome.")
    storage.append_turn(session_id, user_text="Thanks.", llm_text="Let's begin.")

    data = storage.load_session(session_id)
    assert len(data["turns"]) == 2
    assert data["turns"][0]["user_text"] == "Hi, I'm a candidate."
    assert data["turns"][1]["llm_text"] == "Let's begin."


def test_storage_marks_session_ended(tmp_path):
    from tutor.storage import SessionStorage

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 20, 14, 30, 5))
    session_id = storage.create_session("tech_interview_behavioral")
    storage.end_session(session_id)

    data = storage.load_session(session_id)
    assert data["ended_at"] is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_storage.py -v`
Expected: 3 errors (`ModuleNotFoundError: No module named 'tutor.storage'`)

- [ ] **Step 3: Implement storage**

`tutor/storage.py`:
```python
"""JSON-file session persistence. One file per session, grouped by date."""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable


@dataclass
class SessionStorage:
    root: Path
    now: Callable[[], datetime] = datetime.now

    def _session_path(self, session_id: str, day: str) -> Path:
        return self.root / day / f"{session_id}.json"

    def _find_session_path(self, session_id: str) -> Path:
        matches = list(self.root.rglob(f"{session_id}.json"))
        if not matches:
            raise FileNotFoundError(f"No session file for id={session_id}")
        return matches[0]

    def _write(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def create_session(self, scenario_id: str) -> str:
        now = self.now()
        day = now.date().isoformat()
        session_id = uuid.uuid4().hex[:12]
        path = self._session_path(session_id, day)
        self._write(path, {
            "session_id": session_id,
            "scenario_id": scenario_id,
            "started_at": now.isoformat(),
            "ended_at": None,
            "turns": [],
        })
        return session_id

    def append_turn(self, session_id: str, user_text: str, llm_text: str) -> None:
        path = self._find_session_path(session_id)
        data = json.loads(path.read_text())
        data["turns"].append({
            "ts": self.now().isoformat(),
            "user_text": user_text,
            "llm_text": llm_text,
        })
        self._write(path, data)

    def end_session(self, session_id: str) -> None:
        path = self._find_session_path(session_id)
        data = json.loads(path.read_text())
        data["ended_at"] = self.now().isoformat()
        self._write(path, data)

    def load_session(self, session_id: str) -> dict:
        path = self._find_session_path(session_id)
        return json.loads(path.read_text())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_storage.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add tutor/storage.py tests/test_storage.py
git commit -m "feat: JSON session storage with per-day grouping"
```

---

## Task 10: Session orchestrator

Wires LLM + ASR + TTS + audio + storage into the voice loop. No I/O of its own — uses injected adapters. This is where the bulk of integration tests live.

**Files:**
- Create: `tutor/session.py`
- Create: `tests/test_session.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_session.py`:
```python
from unittest.mock import MagicMock
from pathlib import Path
import pytest


def _stub_adapters(turn_user_texts, turn_llm_replies):
    """Build mock LLM/ASR/TTS/recorder that replay the given turns."""
    llm = MagicMock()
    llm.complete.side_effect = turn_llm_replies

    asr = MagicMock()
    asr.transcribe.side_effect = turn_user_texts

    tts = MagicMock()

    recorder = MagicMock()
    # record_to_wav returns a path; we never read it because ASR is mocked
    recorder.record_to_wav.side_effect = [Path(f"/tmp/fake_{i}.wav") for i in range(50)]

    return llm, asr, tts, recorder


def test_session_runs_three_turns_then_user_ends(tmp_path, mocker):
    from tutor.session import SessionOrchestrator
    from tutor.storage import SessionStorage
    from tutor.scenarios.loader import load_scenario

    user_inputs = iter(["go", "go", "go", "end"])  # 3 turns then end
    mocker.patch("builtins.input", side_effect=lambda *_a, **_kw: next(user_inputs))

    llm, asr, tts, recorder = _stub_adapters(
        turn_user_texts=["I led a project.", "It was hard.", "I learned a lot."],
        turn_llm_replies=[
            "Hi, tell me about yourself.",  # opening generated by LLM
            "What was the project?",
            "What made it hard?",
            "What did you learn?",
        ],
    )

    storage = SessionStorage(root=tmp_path)
    orch = SessionOrchestrator(
        llm=llm,
        asr=asr,
        tts=tts,
        recorder=recorder,
        storage=storage,
        scenario=load_scenario("tech_interview_behavioral"),
        per_session_turn_limit=25,
    )
    session_id = orch.run()

    data = storage.load_session(session_id)
    assert len(data["turns"]) == 3
    assert data["ended_at"] is not None
    # TTS spoke 4 times: opening + 3 replies
    assert tts.speak.call_count == 4


def test_session_stops_at_turn_limit(tmp_path, mocker):
    from tutor.session import SessionOrchestrator
    from tutor.storage import SessionStorage
    from tutor.scenarios.loader import load_scenario

    # user always says "go" — limit is what stops the session
    mocker.patch("builtins.input", side_effect=lambda *_a, **_kw: "go")

    llm, asr, tts, recorder = _stub_adapters(
        turn_user_texts=["hi"] * 100,
        turn_llm_replies=["opening"] + ["reply"] * 100,
    )

    storage = SessionStorage(root=tmp_path)
    orch = SessionOrchestrator(
        llm=llm, asr=asr, tts=tts, recorder=recorder, storage=storage,
        scenario=load_scenario("tech_interview_behavioral"),
        per_session_turn_limit=2,
    )
    session_id = orch.run()

    data = storage.load_session(session_id)
    assert len(data["turns"]) == 2


def test_session_stops_on_budget_exceeded(tmp_path, mocker):
    from tutor.session import SessionOrchestrator
    from tutor.storage import SessionStorage
    from tutor.scenarios.loader import load_scenario
    from tutor.budget import BudgetExceededError

    mocker.patch("builtins.input", side_effect=lambda *_a, **_kw: "go")

    llm, asr, tts, recorder = _stub_adapters(
        turn_user_texts=["hi", "hi"],
        turn_llm_replies=[
            "opening",
            BudgetExceededError("daily cap hit"),  # second LLM call raises
        ],
    )

    storage = SessionStorage(root=tmp_path)
    orch = SessionOrchestrator(
        llm=llm, asr=asr, tts=tts, recorder=recorder, storage=storage,
        scenario=load_scenario("tech_interview_behavioral"),
        per_session_turn_limit=25,
    )
    session_id = orch.run()

    data = storage.load_session(session_id)
    # Opening succeeded, then user spoke, then second LLM call blew up before recording the turn.
    assert data["ended_at"] is not None
    # At most 1 turn was persisted (the opening doesn't count as a turn — first user reply is turn 1)
    assert len(data["turns"]) <= 1


def test_session_builds_system_prompt_once(tmp_path, mocker):
    from tutor.session import SessionOrchestrator
    from tutor.storage import SessionStorage
    from tutor.scenarios.loader import load_scenario

    mocker.patch("builtins.input", side_effect=lambda *_a, **_kw: "end")

    llm, asr, tts, recorder = _stub_adapters(
        turn_user_texts=[],
        turn_llm_replies=["Hi, tell me about yourself."],
    )

    storage = SessionStorage(root=tmp_path)
    orch = SessionOrchestrator(
        llm=llm, asr=asr, tts=tts, recorder=recorder, storage=storage,
        scenario=load_scenario("tech_interview_behavioral"),
        per_session_turn_limit=25,
    )
    orch.run()

    # opening call should include a system message
    first_call = llm.complete.call_args_list[0]
    messages = first_call.kwargs.get("messages") or first_call.args[0]
    assert messages[0]["role"] == "system"
    assert "Russian" in messages[0]["content"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_session.py -v`
Expected: 4 errors (`ModuleNotFoundError: No module named 'tutor.session'`)

- [ ] **Step 3: Implement the orchestrator**

`tutor/session.py`:
```python
"""Session orchestrator: ties LLM + ASR + TTS + recorder + storage into the voice loop."""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Protocol

from tutor.budget import BudgetExceededError
from tutor.scenarios.loader import Scenario, build_system_prompt
from tutor.storage import SessionStorage

log = logging.getLogger(__name__)


class _LLM(Protocol):
    def complete(self, messages: list[dict[str, str]], temperature: float = ...) -> str: ...


class _ASR(Protocol):
    def transcribe(self, wav_path: Path) -> str: ...


class _TTS(Protocol):
    def speak(self, text: str) -> None: ...


class _Recorder(Protocol):
    def record_to_wav(self, out_path: Path) -> Path: ...


_END_SENTINEL = "end"


class SessionOrchestrator:
    def __init__(
        self,
        llm: _LLM,
        asr: _ASR,
        tts: _TTS,
        recorder: _Recorder,
        storage: SessionStorage,
        scenario: Scenario,
        per_session_turn_limit: int = 25,
        user_native_language: str = "Russian",
    ) -> None:
        self._llm = llm
        self._asr = asr
        self._tts = tts
        self._recorder = recorder
        self._storage = storage
        self._scenario = scenario
        self._limit = per_session_turn_limit
        self._system_prompt = build_system_prompt(scenario, user_native_language=user_native_language)

    def run(self) -> str:
        session_id = self._storage.create_session(scenario_id=self._scenario.id)
        history: list[dict[str, str]] = [{"role": "system", "content": self._system_prompt}]

        try:
            opening = self._llm.complete(messages=history)
            history.append({"role": "assistant", "content": opening})
            print(f"\n[interviewer] {opening}\n")
            self._tts.speak(opening)

            turn_count = 0
            while turn_count < self._limit:
                cmd = input(f"[turn {turn_count + 1}/{self._limit}] press Enter to speak, or type 'end' to finish: ").strip().lower()
                if cmd == _END_SENTINEL:
                    break

                wav_path = Path(tempfile.gettempdir()) / f"tutor_turn_{session_id}_{turn_count}.wav"
                self._recorder.record_to_wav(wav_path)
                user_text = self._asr.transcribe(wav_path).strip()
                if not user_text:
                    print("[didn't catch that — try again]")
                    continue
                print(f"[you] {user_text}\n")
                history.append({"role": "user", "content": user_text})

                try:
                    reply = self._llm.complete(messages=history)
                except BudgetExceededError as e:
                    print(f"\n[budget exhausted: {e}]\n[session ending]")
                    break

                history.append({"role": "assistant", "content": reply})
                print(f"[interviewer] {reply}\n")
                self._tts.speak(reply)

                self._storage.append_turn(session_id, user_text=user_text, llm_text=reply)
                turn_count += 1
        finally:
            self._storage.end_session(session_id)

        return session_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_session.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add tutor/session.py tests/test_session.py
git commit -m "feat: session orchestrator with turn limit and budget halt"
```

---

## Task 11: CLI entry point

`tutor interview` starts a session with the tech_interview_behavioral scenario. Loads settings, wires adapters, runs the orchestrator.

**Files:**
- Create: `tutor/cli.py`

- [ ] **Step 1: Implement the CLI**

`tutor/cli.py`:
```python
"""CLI entry point. Wires real adapters and runs a session."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from openai import OpenAI

from tutor.asr import WhisperASR
from tutor.audio import AudioRecorder
from tutor.budget import BudgetTracker
from tutor.llm import LLMClient
from tutor.scenarios.loader import load_scenario, list_scenarios
from tutor.session import SessionOrchestrator
from tutor.settings import get_settings
from tutor.storage import SessionStorage
from tutor.tts import MacSayTTS


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tutor", description="English speaking practice CLI")
    sub = p.add_subparsers(dest="command", required=True)

    sub_interview = sub.add_parser("interview", help="Run a tech interview behavioral session")
    sub_interview.add_argument("--scenario", default="tech_interview_behavioral",
                                help="Scenario id (default: tech_interview_behavioral)")

    sub.add_parser("list-scenarios", help="List available scenarios")

    return p


def _run_interview(scenario_id: str) -> int:
    settings = get_settings()
    project_root = Path(__file__).resolve().parents[1]

    budget = BudgetTracker(
        path=project_root / "budget.json",
        daily_usd_cap=settings.daily_usd_budget,
        daily_token_cap=settings.daily_token_budget,
    )

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=settings.openrouter_api_key)
    llm = LLMClient(client=client, model=settings.openrouter_model, budget=budget)
    asr = WhisperASR(model_size=settings.whisper_model_size)
    tts = MacSayTTS()
    recorder = AudioRecorder()
    storage = SessionStorage(root=project_root / "sessions")
    scenario = load_scenario(scenario_id)

    print(f"\n=== {scenario.name} ===")
    print(f"Budget today: ${budget.usd_today:.4f} / ${settings.daily_usd_budget}")
    print(f"Press Enter to start each turn. Type 'end' to finish the session.\n")

    orch = SessionOrchestrator(
        llm=llm, asr=asr, tts=tts, recorder=recorder, storage=storage,
        scenario=scenario,
        per_session_turn_limit=settings.per_session_turn_limit,
    )
    session_id = orch.run()
    print(f"\nSession {session_id} saved. Budget after: ${budget.usd_today:.4f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "interview":
        return _run_interview(args.scenario)
    if args.command == "list-scenarios":
        for sid in list_scenarios():
            print(sid)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Smoke-check that the CLI parses**

Run: `tutor --help`
Expected: usage text including `interview` and `list-scenarios` subcommands.

Run: `tutor list-scenarios`
Expected: prints `tech_interview_behavioral` on its own line.

- [ ] **Step 3: Run full test suite**

Run: `pytest`
Expected: all tests pass (≈ 22 tests across the modules).

- [ ] **Step 4: Commit**

```bash
git add tutor/cli.py
git commit -m "feat: CLI entry point with interview and list-scenarios subcommands"
```

---

## Task 12: Manual end-to-end smoke

No automated test — the goal is to actually use the thing.

- [ ] **Step 1: Confirm `.env` is real**

Verify `.env` exists, contains a real OpenRouter key (NOT the placeholder), and is gitignored.

Run: `git check-ignore .env`
Expected: output is `.env` (proving it's ignored).

If the file is missing: `cp .env.example .env` and fill in the real key.

- [ ] **Step 2: Confirm Whisper downloads on first run**

Run: `python -c "from tutor.asr import WhisperASR; a = WhisperASR(model_size='small'); a._ensure_model(); print('ok')"`
Expected: model downloads (one-time, ~500MB to `~/.cache/huggingface/`), then prints `ok`.

This is slow on first run. Subsequent runs are instant.

- [ ] **Step 3: Confirm `say` is available**

Run: `say "Hello, this is a test."`
Expected: macOS speaks the line.

- [ ] **Step 4: Confirm mic is accessible**

Run: `python -c "import sounddevice as sd; print(sd.query_devices())"`
Expected: prints a device list. There's at least one input device (your built-in mic).

If macOS hasn't granted mic permission to the terminal, it will prompt — accept.

- [ ] **Step 5: Run a real session**

Run: `tutor interview`

Expected flow:
1. CLI prints "=== Tech interview — behavioral round ===".
2. Interviewer speaks the opening line.
3. CLI prompts "press Enter to speak".
4. Press Enter, speak for 5-10 seconds, press Enter to stop.
5. CLI shows the transcript of what you said.
6. Interviewer replies (text + spoken).
7. Repeat 2-3 turns, then type `end`.
8. CLI prints "Session XYZ saved."

Verify: a JSON file exists at `sessions/2026-05-20/XYZ.json` with your turns.

- [ ] **Step 6: Review the budget file**

Run: `cat budget.json`
Expected: shows non-zero `tokens` and (depending on OpenRouter's cost reporting) possibly non-zero `usd`. Both should be well under the caps.

- [ ] **Step 7: Final commit (if any tweaks needed)**

If you had to adjust anything during smoke (a voice that sounded better, a model variant that worked better, etc.), commit those tweaks:

```bash
git add -p  # review changes
git commit -m "chore: post-smoke tweaks from first real session"
```

If nothing changed, no commit needed.

---

## Self-review checklist

After every task is implemented, before declaring Stage 0 done:

1. **Spec coverage:**
   - Section 11 (MVP Stage 0) requires: CLI command ✓ (Task 11), single scenario ✓ (Task 5), voice loop mic→Whisper→LLM→`say` ✓ (Tasks 7,8,10,6,4), JSON transcript ✓ (Task 9), budget tracker with $0.5/day hard stop ✓ (Task 3 + Task 4 integration), `.env` gitignored from first commit ✓ (already done in initial spec commit).
   - All Stage 0 inclusions are covered.

2. **Type consistency:**
   - `SessionStorage.append_turn(session_id, user_text, llm_text)` — same signature used in `session.py`. ✓
   - `LLMClient.complete(messages)` — same signature in session orchestrator. ✓
   - `WhisperASR.transcribe(wav_path: Path)` — session passes a `Path`. ✓
   - `MacSayTTS.speak(text)` — session passes a string. ✓
   - `BudgetTracker.check_can_spend()` — called by `LLMClient.complete()`. ✓

3. **No placeholders:** every step has code or an exact command. No "TBD". No "similar to Task N". Code blocks present where code is required.

4. **Failure modes covered:** budget exceeded (Task 10 test), turn limit (Task 10 test), LLM retry on 5xx (Task 4 test), session end (Task 10 test), empty audio (Task 10 implementation: continues loop, doesn't crash).

---

## Definition of Done for Stage 0

- All 12 tasks committed.
- `pytest` shows green across the suite.
- One real session has been completed end-to-end (Task 12, step 5) and the JSON transcript exists.
- Budget tracker shows the session's actual cost, well under $0.5.
- `.env` is gitignored and contains a real key not present in git history.

When the above is true, Stage 0 is done. Time to actually use it for a few weeks before starting Stage 1.
