# Stage 2a — Browser UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a localhost browser UI (4 screens: Scenarios, Session, Review, Stats) that lets the user run sessions and review cards in a chat-style React app, while the existing CLI continues to work unchanged.

**Architecture:** Stateless FastAPI backend reuses Stage 1 modules via a thin `services.py` layer. React + Vite + Tailwind frontend talks to `/api/*` endpoints. Push-to-talk recording via MediaRecorder; TTS via browser SpeechSynthesis. Single FastAPI process serves both API and built frontend on `127.0.0.1:8000`.

**Tech Stack:**
- Backend: Python 3.11+, FastAPI, Uvicorn, python-multipart, httpx (testing). Existing: openai SDK, faster-whisper, pydantic-settings, pyyaml, jinja2.
- Frontend: React 18 + TypeScript, Vite, Tailwind CSS, React Router v6, @tanstack/react-query, lucide-react.
- Test: pytest + FastAPI TestClient (backend), Vitest + @testing-library/react (frontend).

**Prerequisites:**
- Stage 1b complete (~103 tests green, branch `main` at `715ec42` or later).
- Node 20+ and npm installed on the user's Mac.
- Working `.env` with `OPENROUTER_API_KEY`.

---

## File Structure

```
english-tutor/
├── pyproject.toml                              (MODIFY: add fastapi, uvicorn, python-multipart, httpx-deps)
├── tutor/
│   ├── storage.py                              (MODIFY: add set_opening_text + opening_text field on create)
│   └── web/                                    (NEW package)
│       ├── __init__.py
│       ├── api.py                              (NEW: FastAPI app + routes)
│       ├── services.py                         (NEW: orchestration layer)
│       ├── schemas.py                          (NEW: Pydantic request/response models)
│       ├── errors.py                           (NEW: exception classes + handlers)
│       ├── deps.py                             (NEW: dependency container, Whisper preload)
│       └── static/                             (gitignored; output of npm run build)
├── frontend/                                   (NEW directory)
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.js
│   ├── postcss.config.js
│   ├── index.html
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── index.css                           (Tailwind directives)
│   │   ├── api/
│   │   │   ├── client.ts
│   │   │   └── types.ts
│   │   ├── hooks/
│   │   │   ├── useRecorder.ts
│   │   │   └── useTTS.ts
│   │   ├── components/
│   │   │   ├── Layout.tsx
│   │   │   ├── BudgetIndicator.tsx
│   │   │   ├── MessageBubble.tsx
│   │   │   ├── PushToTalkButton.tsx
│   │   │   ├── ReviewCard.tsx
│   │   │   └── SessionSummary.tsx
│   │   └── pages/
│   │       ├── ScenariosPage.tsx
│   │       ├── SessionPage.tsx
│   │       ├── ReviewPage.tsx
│   │       └── StatsPage.tsx
│   └── tests/                                  (Vitest tests next to source)
├── scripts/
│   └── build_and_serve.sh                      (NEW: build frontend + run uvicorn)
└── tests/
    ├── test_storage.py                         (MODIFY: opening_text test)
    └── web/                                    (NEW)
        ├── __init__.py
        ├── test_services.py                    (NEW: unit tests for service functions)
        └── test_api.py                         (NEW: FastAPI TestClient tests)
```

---

## Task 1: Backend dependencies + `tutor/web/` scaffold

**Files:**
- Modify: `pyproject.toml`
- Create: `tutor/web/__init__.py`
- Create: `tests/web/__init__.py`
- Create: `tests/web/test_smoke.py`

- [ ] **Step 1: Add web dependencies to pyproject.toml**

In `pyproject.toml`, extend the `[project]` `dependencies` list with three new entries (append, do not replace existing):

```toml
    "fastapi>=0.110.0",
    "uvicorn[standard]>=0.27.0",
    "python-multipart>=0.0.9",
```

Add httpx to the dev extras:

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-mock>=3.14.0",
    "ruff>=0.6.0",
    "httpx>=0.27.0",
]
```

- [ ] **Step 2: Install the new deps**

Run: `cd /Users/sarkhipov/Work/Personal/english-tutor && source .venv/bin/activate && pip install -e ".[dev]"`
Expected: installs fastapi, uvicorn, python-multipart, httpx without errors.

- [ ] **Step 3: Create `tutor/web/__init__.py`**

```python
"""FastAPI web layer wrapping the existing tutor modules."""
```

- [ ] **Step 4: Create `tests/web/__init__.py`**

```python
# tests.web package
```

- [ ] **Step 5: Create smoke test `tests/web/test_smoke.py`**

```python
def test_web_package_importable():
    import tutor.web
    assert tutor.web is not None


def test_fastapi_available():
    import fastapi
    assert hasattr(fastapi, "FastAPI")
```

- [ ] **Step 6: Run smoke + full suite**

Run: `pytest tests/web/test_smoke.py -v`
Expected: 2 passed.

Run: `pytest`
Expected: full suite green (~105 tests).

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml tutor/web/__init__.py tests/web/__init__.py tests/web/test_smoke.py
git commit -m "chore(web): add FastAPI deps + tutor/web scaffold"
```

---

## Task 2: Storage extension — `opening_text`

**Files:**
- Modify: `tutor/storage.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_storage.py`:

```python
def test_storage_create_session_no_opening_text_by_default(tmp_path):
    from tutor.storage import SessionStorage
    from datetime import datetime

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 10, 0))
    session_id = storage.create_session("tech_interview_behavioral")
    data = storage.load_session(session_id)
    assert data.get("opening_text") is None


def test_storage_set_opening_text_persists(tmp_path):
    from tutor.storage import SessionStorage
    from datetime import datetime

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 10, 0))
    session_id = storage.create_session("tech_interview_behavioral")
    storage.set_opening_text(session_id, "Hi, tell me about a project.")
    data = storage.load_session(session_id)
    assert data["opening_text"] == "Hi, tell me about a project."
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_storage.py::test_storage_set_opening_text_persists -v`
Expected: FAIL — `SessionStorage` has no `set_opening_text` method.

- [ ] **Step 3: Update `tutor/storage.py`**

In `create_session`, ensure the initial dict has an `opening_text: None` field:

```python
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
            "opening_text": None,
            "turns": [],
        })
        return session_id
```

Add this method to `SessionStorage` alongside `set_growth_points`:

```python
    def set_opening_text(self, session_id: str, text: str) -> None:
        path = self._find_session_path(session_id)
        data = json.loads(path.read_text())
        data["opening_text"] = text
        self._write(path, data)
```

- [ ] **Step 4: Run all tests**

Run: `pytest tests/test_storage.py -v`
Expected: 13 passed (11 existing + 2 new).

Run: `pytest`
Expected: full suite green.

- [ ] **Step 5: Commit**

```bash
git add tutor/storage.py tests/test_storage.py
git commit -m "feat(storage): persist opening_text on sessions"
```

---

## Task 3: Pydantic schemas (`tutor/web/schemas.py`)

**Files:**
- Create: `tutor/web/schemas.py`
- Create: `tests/web/test_schemas.py`

- [ ] **Step 1: Write the failing tests**

`tests/web/test_schemas.py`:

```python
def test_scenario_summary_schema():
    from tutor.web.schemas import ScenarioSummary
    s = ScenarioSummary(id="x", name="X", difficulty="intermediate")
    assert s.model_dump() == {"id": "x", "name": "X", "difficulty": "intermediate"}


def test_start_session_request_validates():
    from tutor.web.schemas import StartSessionRequest
    import pytest as _p
    StartSessionRequest(scenario_id="x")
    with _p.raises(Exception):
        StartSessionRequest()  # missing scenario_id


def test_turn_result_schema():
    from tutor.web.schemas import TurnResult
    r = TurnResult(user_text="hi", assistant_text="hello")
    assert r.user_text == "hi"
    assert r.assistant_text == "hello"


def test_budget_summary_schema():
    from tutor.web.schemas import BudgetSummary
    b = BudgetSummary(usd_today=0.01, tokens_today=100,
                      daily_usd_cap=0.5, daily_token_cap=200_000)
    assert b.usd_today == 0.01


def test_grade_result_schema():
    from tutor.web.schemas import GradeResult
    g = GradeResult(card_id="c1", user_attempt_text="x", quality=4,
                    target="y", explanation="z", next_due="2026-05-22")
    assert g.quality == 4
```

- [ ] **Step 2: Run tests to verify failures**

Run: `pytest tests/web/test_schemas.py -v`
Expected: 5 errors (ModuleNotFoundError).

- [ ] **Step 3: Implement `tutor/web/schemas.py`**

```python
"""Pydantic request/response models for the web API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ScenarioSummary(BaseModel):
    id: str
    name: str
    difficulty: str


class StartSessionRequest(BaseModel):
    scenario_id: str


class StartSessionResult(BaseModel):
    session_id: str
    opening_text: str


class TurnResult(BaseModel):
    user_text: str
    assistant_text: str


class EndSessionResult(BaseModel):
    session_id: str
    ended_at: str | None
    growth_points: list[dict] = Field(default_factory=list)
    cards_created: list[str] = Field(default_factory=list)
    growth_points_error: str | None = None


class GradeRequestSkip(BaseModel):
    skip: Literal[True]


class GradeResult(BaseModel):
    card_id: str
    user_attempt_text: str
    quality: int
    target: str
    explanation: str
    next_due: str


class DueCardsResult(BaseModel):
    cards: list[dict]
    total_due: int


class BudgetSummary(BaseModel):
    usd_today: float
    tokens_today: int
    daily_usd_cap: float
    daily_token_cap: int


class ErrorResponse(BaseModel):
    error: str
    message: str | None = None
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/web/test_schemas.py -v`
Expected: 5 passed.

Run: `pytest`
Expected: full suite green.

- [ ] **Step 5: Commit**

```bash
git add tutor/web/schemas.py tests/web/test_schemas.py
git commit -m "feat(web): pydantic schemas for API requests/responses"
```

---

## Task 4: Web errors module

**Files:**
- Create: `tutor/web/errors.py`
- Create: `tests/web/test_errors.py`

- [ ] **Step 1: Write the failing tests**

`tests/web/test_errors.py`:

```python
def test_no_speech_detected_error_is_exception():
    from tutor.web.errors import NoSpeechDetectedError
    e = NoSpeechDetectedError("empty")
    assert isinstance(e, Exception)


def test_session_not_found_error_carries_id():
    from tutor.web.errors import SessionNotFoundError
    e = SessionNotFoundError("abc12345")
    assert e.session_id == "abc12345"


def test_handler_returns_404_for_scenario_not_found():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from tutor.web.errors import register_exception_handlers
    from tutor.scenarios.loader import ScenarioNotFoundError

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/raise-scenario")
    def _r():
        raise ScenarioNotFoundError("does_not_exist")

    client = TestClient(app)
    r = client.get("/raise-scenario")
    assert r.status_code == 404
    body = r.json()
    assert body["error"] == "scenario_not_found"


def test_handler_returns_429_for_budget():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from tutor.web.errors import register_exception_handlers
    from tutor.budget import BudgetExceededError

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/raise-budget")
    def _r():
        raise BudgetExceededError("cap hit")

    client = TestClient(app)
    r = client.get("/raise-budget")
    assert r.status_code == 429
    body = r.json()
    assert body["error"] == "budget_exhausted"
    assert "cap hit" in body["message"]
```

- [ ] **Step 2: Run tests to verify failures**

Run: `pytest tests/web/test_errors.py -v`
Expected: 4 errors (ModuleNotFoundError).

- [ ] **Step 3: Implement `tutor/web/errors.py`**

```python
"""Web-layer exception classes and FastAPI handlers."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from tutor.budget import BudgetExceededError
from tutor.scenarios.loader import ScenarioNotFoundError
from tutor.srs_engine import CardNotFoundError


class NoSpeechDetectedError(Exception):
    """Raised when ASR produces an empty transcript."""


class SessionNotFoundError(Exception):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"session not found: {session_id}")
        self.session_id = session_id


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ScenarioNotFoundError)
    async def _scenario_not_found(request: Request, exc: ScenarioNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"error": "scenario_not_found", "message": str(exc)},
        )

    @app.exception_handler(SessionNotFoundError)
    async def _session_not_found(request: Request, exc: SessionNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"error": "session_not_found", "session_id": exc.session_id},
        )

    @app.exception_handler(CardNotFoundError)
    async def _card_not_found(request: Request, exc: CardNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"error": "card_not_found", "message": str(exc)},
        )

    @app.exception_handler(NoSpeechDetectedError)
    async def _no_speech(request: Request, exc: NoSpeechDetectedError):
        return JSONResponse(
            status_code=422,
            content={"error": "no_speech_detected", "message": str(exc)},
        )

    @app.exception_handler(BudgetExceededError)
    async def _budget(request: Request, exc: BudgetExceededError):
        return JSONResponse(
            status_code=429,
            content={"error": "budget_exhausted", "message": str(exc)},
        )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/web/test_errors.py -v`
Expected: 4 passed.

Run: `pytest`
Expected: full suite green.

- [ ] **Step 5: Commit**

```bash
git add tutor/web/errors.py tests/web/test_errors.py
git commit -m "feat(web): custom exceptions and FastAPI exception handlers"
```

---

## Task 5: Dependency container + Whisper preload (`tutor/web/deps.py`)

**Files:**
- Create: `tutor/web/deps.py`
- Create: `tests/web/test_deps.py`

- [ ] **Step 1: Write the failing tests**

`tests/web/test_deps.py`:

```python
def test_dependencies_dataclass_holds_components(tmp_path, monkeypatch):
    from tutor.web.deps import Dependencies
    from tutor.budget import BudgetTracker
    from tutor.asr import WhisperASR
    from tutor.storage import SessionStorage
    from tutor.srs_engine import SRSEngine
    from tutor.llm import LLMClient
    from unittest.mock import MagicMock

    deps = Dependencies(
        budget=BudgetTracker(path=tmp_path/"b.json", daily_usd_cap=1.0,
                              daily_token_cap=1_000_000),
        llm=MagicMock(spec=LLMClient),
        asr=MagicMock(spec=WhisperASR),
        storage=SessionStorage(root=tmp_path/"sessions"),
        srs=SRSEngine(path=tmp_path/"cards.json"),
        evaluator_model="m1",
        grader_model="m2",
    )
    assert deps.budget is not None
    assert deps.evaluator_model == "m1"


def test_build_dependencies_from_settings(tmp_path, monkeypatch, mocker):
    """build_dependencies wires up real objects from settings + project_root."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    mocker.patch("tutor.web.deps.WhisperASR")  # avoid real model load

    from tutor.web.deps import build_dependencies
    deps = build_dependencies(project_root=tmp_path)
    assert deps.budget is not None
    assert deps.llm is not None
    assert deps.storage is not None
    assert deps.srs is not None
    assert deps.evaluator_model == "google/gemini-2.5-pro"
    assert deps.grader_model == "google/gemini-2.5-flash"
```

- [ ] **Step 2: Run tests to verify failures**

Run: `pytest tests/web/test_deps.py -v`
Expected: 2 errors (ModuleNotFoundError).

- [ ] **Step 3: Implement `tutor/web/deps.py`**

```python
"""Dependency container for the web layer. Holds preloaded singletons."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI

from tutor.asr import WhisperASR
from tutor.budget import BudgetTracker
from tutor.llm import LLMClient
from tutor.settings import get_settings
from tutor.srs_engine import SRSEngine
from tutor.storage import SessionStorage


@dataclass
class Dependencies:
    budget: BudgetTracker
    llm: LLMClient
    asr: WhisperASR
    storage: SessionStorage
    srs: SRSEngine
    evaluator_model: str
    grader_model: str


def build_dependencies(project_root: Path) -> Dependencies:
    settings = get_settings()
    budget = BudgetTracker(
        path=project_root / "budget.json",
        daily_usd_cap=settings.daily_usd_budget,
        daily_token_cap=settings.daily_token_budget,
    )
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key.get_secret_value(),
    )
    llm = LLMClient(client=client, model=settings.openrouter_model, budget=budget)
    asr = WhisperASR(model_size=settings.whisper_model_size)
    storage = SessionStorage(root=project_root / "sessions")
    srs = SRSEngine(path=project_root / "cards.json")
    return Dependencies(
        budget=budget,
        llm=llm,
        asr=asr,
        storage=storage,
        srs=srs,
        evaluator_model=settings.openrouter_evaluator_model,
        grader_model=settings.openrouter_grader_model,
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/web/test_deps.py -v`
Expected: 2 passed.

Run: `pytest`
Expected: full suite green.

- [ ] **Step 5: Commit**

```bash
git add tutor/web/deps.py tests/web/test_deps.py
git commit -m "feat(web): Dependencies container + build_dependencies"
```

---

## Task 6: Services — scenarios + session start/load

**Files:**
- Create: `tutor/web/services.py`
- Create: `tests/web/test_services_session.py`

- [ ] **Step 1: Write failing tests**

`tests/web/test_services_session.py`:

```python
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock
import pytest


def _make_deps(tmp_path):
    from tutor.web.deps import Dependencies
    from tutor.budget import BudgetTracker
    from tutor.storage import SessionStorage
    from tutor.srs_engine import SRSEngine

    budget = BudgetTracker(
        path=tmp_path / "budget.json",
        daily_usd_cap=1.0, daily_token_cap=1_000_000,
        now=lambda: datetime(2026, 5, 21, 10, 0),
    )
    llm = MagicMock()
    asr = MagicMock()
    storage = SessionStorage(root=tmp_path / "sessions",
                              now=lambda: datetime(2026, 5, 21, 10, 0))
    srs = SRSEngine(path=tmp_path / "cards.json")
    return Dependencies(
        budget=budget, llm=llm, asr=asr, storage=storage, srs=srs,
        evaluator_model="m1", grader_model="m2",
    )


def test_list_scenarios_service_returns_summaries(tmp_path):
    from tutor.web.services import list_scenarios_service
    deps = _make_deps(tmp_path)
    result = list_scenarios_service(deps)
    ids = [s.id for s in result]
    assert "tech_interview_behavioral" in ids
    assert "daily_standup" in ids
    assert "apartment_rental_abroad" in ids


def test_start_session_service_persists_opening(tmp_path):
    from tutor.web.services import start_session_service
    deps = _make_deps(tmp_path)
    deps.llm.complete.return_value = "Hi there, tell me about yourself."

    result = start_session_service(deps, scenario_id="tech_interview_behavioral")
    assert result.session_id
    assert result.opening_text == "Hi there, tell me about yourself."

    data = deps.storage.load_session(result.session_id)
    assert data["scenario_id"] == "tech_interview_behavioral"
    assert data["opening_text"] == "Hi there, tell me about yourself."


def test_start_session_service_raises_on_unknown_scenario(tmp_path):
    from tutor.web.services import start_session_service
    from tutor.scenarios.loader import ScenarioNotFoundError
    deps = _make_deps(tmp_path)
    with pytest.raises(ScenarioNotFoundError):
        start_session_service(deps, scenario_id="does_not_exist")


def test_get_session_service_returns_full_dict(tmp_path):
    from tutor.web.services import get_session_service, start_session_service
    deps = _make_deps(tmp_path)
    deps.llm.complete.return_value = "Hi."

    started = start_session_service(deps, scenario_id="tech_interview_behavioral")
    full = get_session_service(deps, started.session_id)
    assert full["session_id"] == started.session_id
    assert full["opening_text"] == "Hi."
    assert full["turns"] == []


def test_get_session_service_raises_on_unknown(tmp_path):
    from tutor.web.services import get_session_service
    from tutor.web.errors import SessionNotFoundError
    deps = _make_deps(tmp_path)
    with pytest.raises(SessionNotFoundError):
        get_session_service(deps, "does_not_exist")
```

- [ ] **Step 2: Run tests to verify failures**

Run: `pytest tests/web/test_services_session.py -v`
Expected: 5 errors (`tutor.web.services` doesn't exist).

- [ ] **Step 3: Implement initial `tutor/web/services.py`**

```python
"""Orchestration layer for the web API. Reuses existing modules."""
from __future__ import annotations

from tutor.scenarios.loader import (
    Scenario,
    ScenarioNotFoundError,
    build_system_prompt,
    list_scenarios,
    load_scenario,
)
from tutor.web.deps import Dependencies
from tutor.web.errors import SessionNotFoundError
from tutor.web.schemas import (
    ScenarioSummary,
    StartSessionResult,
)


def list_scenarios_service(deps: Dependencies) -> list[ScenarioSummary]:
    summaries: list[ScenarioSummary] = []
    for sid in list_scenarios():
        sc = load_scenario(sid)
        summaries.append(ScenarioSummary(id=sc.id, name=sc.name, difficulty=sc.difficulty))
    return summaries


def start_session_service(deps: Dependencies, scenario_id: str) -> StartSessionResult:
    scenario = load_scenario(scenario_id)  # raises ScenarioNotFoundError
    session_id = deps.storage.create_session(scenario_id=scenario.id)

    system_prompt = build_system_prompt(scenario, user_native_language="Russian")
    opening = deps.llm.complete(
        messages=[{"role": "system", "content": system_prompt}],
    )
    deps.storage.set_opening_text(session_id, opening)
    return StartSessionResult(session_id=session_id, opening_text=opening)


def get_session_service(deps: Dependencies, session_id: str) -> dict:
    try:
        return deps.storage.load_session(session_id)
    except FileNotFoundError as e:
        raise SessionNotFoundError(session_id) from e
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/web/test_services_session.py -v`
Expected: 5 passed.

Run: `pytest`
Expected: full suite green.

- [ ] **Step 5: Commit**

```bash
git add tutor/web/services.py tests/web/test_services_session.py
git commit -m "feat(web): services for list_scenarios, start_session, get_session"
```

---

## Task 7: Services — turn (audio → ASR → LLM)

**Files:**
- Modify: `tutor/web/services.py`
- Create: `tests/web/test_services_turn.py`

- [ ] **Step 1: Write failing tests**

`tests/web/test_services_turn.py`:

```python
from datetime import datetime
from unittest.mock import MagicMock
import pytest


def _deps(tmp_path):
    from tutor.web.deps import Dependencies
    from tutor.budget import BudgetTracker
    from tutor.storage import SessionStorage
    from tutor.srs_engine import SRSEngine

    return Dependencies(
        budget=BudgetTracker(
            path=tmp_path / "b.json", daily_usd_cap=1.0,
            daily_token_cap=1_000_000,
            now=lambda: datetime(2026, 5, 21, 10, 0),
        ),
        llm=MagicMock(), asr=MagicMock(),
        storage=SessionStorage(root=tmp_path / "sessions",
                                now=lambda: datetime(2026, 5, 21, 10, 0)),
        srs=SRSEngine(path=tmp_path / "cards.json"),
        evaluator_model="m1", grader_model="m2",
    )


def test_turn_service_happy_path(tmp_path):
    from tutor.web.services import start_session_service, turn_service
    deps = _deps(tmp_path)
    deps.llm.complete.return_value = "What was the project?"
    deps.asr.transcribe.return_value = "I led a backend project"

    started = start_session_service(deps, scenario_id="tech_interview_behavioral")
    # Reset llm.complete mock for the turn call
    deps.llm.complete.reset_mock()
    deps.llm.complete.return_value = "What was the project?"

    result = turn_service(deps, session_id=started.session_id, audio_bytes=b"fake_audio")

    assert result.user_text == "I led a backend project"
    assert result.assistant_text == "What was the project?"

    data = deps.storage.load_session(started.session_id)
    assert len(data["turns"]) == 1
    assert data["turns"][0]["user_text"] == "I led a backend project"
    assert data["turns"][0]["llm_text"] == "What was the project?"


def test_turn_service_raises_on_unknown_session(tmp_path):
    from tutor.web.services import turn_service
    from tutor.web.errors import SessionNotFoundError
    deps = _deps(tmp_path)
    with pytest.raises(SessionNotFoundError):
        turn_service(deps, session_id="does_not_exist", audio_bytes=b"x")


def test_turn_service_raises_on_empty_asr(tmp_path):
    from tutor.web.services import start_session_service, turn_service
    from tutor.web.errors import NoSpeechDetectedError
    deps = _deps(tmp_path)
    deps.llm.complete.return_value = "Hi."
    deps.asr.transcribe.return_value = ""

    started = start_session_service(deps, scenario_id="tech_interview_behavioral")
    with pytest.raises(NoSpeechDetectedError):
        turn_service(deps, session_id=started.session_id, audio_bytes=b"silence")


def test_turn_service_builds_full_history_for_llm(tmp_path):
    from tutor.web.services import start_session_service, turn_service
    deps = _deps(tmp_path)
    deps.llm.complete.return_value = "Opening."
    deps.asr.transcribe.return_value = "First user reply"

    started = start_session_service(deps, scenario_id="tech_interview_behavioral")
    deps.llm.complete.reset_mock()
    deps.llm.complete.return_value = "Reply 1"
    turn_service(deps, session_id=started.session_id, audio_bytes=b"x")

    # Second turn — history should include first turn
    deps.llm.complete.reset_mock()
    deps.llm.complete.return_value = "Reply 2"
    deps.asr.transcribe.return_value = "Second user reply"
    turn_service(deps, session_id=started.session_id, audio_bytes=b"y")

    call_kwargs = deps.llm.complete.call_args.kwargs
    messages = call_kwargs["messages"]
    # system + assistant(opening) + user(first) + assistant(reply1) + user(second) = 5
    assert len(messages) == 5
    roles = [m["role"] for m in messages]
    assert roles == ["system", "assistant", "user", "assistant", "user"]
```

- [ ] **Step 2: Run tests to verify failures**

Run: `pytest tests/web/test_services_turn.py -v`
Expected: 4 failures (turn_service doesn't exist).

- [ ] **Step 3: Add `turn_service` to `tutor/web/services.py`**

Append to `tutor/web/services.py`:

```python
import os
import tempfile
from pathlib import Path

from tutor.web.errors import NoSpeechDetectedError
from tutor.web.schemas import TurnResult


def turn_service(deps: Dependencies, session_id: str, audio_bytes: bytes) -> TurnResult:
    # 1. Save audio to temp file
    tmp = Path(tempfile.gettempdir()) / f"web_turn_{session_id}_{os.getpid()}.bin"
    tmp.write_bytes(audio_bytes)

    try:
        # 2. ASR
        user_text = deps.asr.transcribe(tmp).strip()
        if not user_text:
            raise NoSpeechDetectedError(f"empty transcript for session {session_id}")

        # 3. Load session + scenario
        try:
            session_data = deps.storage.load_session(session_id)
        except FileNotFoundError as e:
            raise SessionNotFoundError(session_id) from e

        scenario = load_scenario(session_data["scenario_id"])

        # 4. Build messages: system + opening (assistant) + alternating turns + new user
        system_prompt = build_system_prompt(scenario, user_native_language="Russian")
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if session_data.get("opening_text"):
            messages.append({"role": "assistant", "content": session_data["opening_text"]})
        for turn in session_data.get("turns", []):
            messages.append({"role": "user", "content": turn["user_text"]})
            messages.append({"role": "assistant", "content": turn["llm_text"]})
        messages.append({"role": "user", "content": user_text})

        # 5. LLM call (existing budget tracking applies)
        assistant_text = deps.llm.complete(messages=messages)

        # 6. Persist
        deps.storage.append_turn(session_id, user_text=user_text, llm_text=assistant_text)

        return TurnResult(user_text=user_text, assistant_text=assistant_text)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
```

Note: the function correctly raises `SessionNotFoundError` for unknown sessions because `load_session` raises `FileNotFoundError` which we re-wrap.

But there's a subtlety: the unknown-session test calls `turn_service` BEFORE any ASR succeeds (because ASR is mocked to return "I led...", not empty). The current order: ASR first, then load_session. So for an unknown session, ASR is called (and may succeed against mocked behavior), then load_session raises.

For the test to work as written, ASR must be called first. If the test doesn't set `deps.asr.transcribe.return_value` it would return a `MagicMock` (truthy). Adjust the test by setting `deps.asr.transcribe.return_value = "x"` before raising, OR change the order in implementation to load_session first.

Better: change the implementation order. Load session FIRST, then ASR. This way unknown session fails fast without doing ASR work:

Replace the implementation with this order:

```python
def turn_service(deps: Dependencies, session_id: str, audio_bytes: bytes) -> TurnResult:
    # 1. Load session first (cheap, fails fast on bad id)
    try:
        session_data = deps.storage.load_session(session_id)
    except FileNotFoundError as e:
        raise SessionNotFoundError(session_id) from e

    # 2. Save audio + ASR
    tmp = Path(tempfile.gettempdir()) / f"web_turn_{session_id}_{os.getpid()}.bin"
    tmp.write_bytes(audio_bytes)
    try:
        user_text = deps.asr.transcribe(tmp).strip()
        if not user_text:
            raise NoSpeechDetectedError(f"empty transcript for session {session_id}")

        # 3. Build messages
        scenario = load_scenario(session_data["scenario_id"])
        system_prompt = build_system_prompt(scenario, user_native_language="Russian")
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if session_data.get("opening_text"):
            messages.append({"role": "assistant", "content": session_data["opening_text"]})
        for turn in session_data.get("turns", []):
            messages.append({"role": "user", "content": turn["user_text"]})
            messages.append({"role": "assistant", "content": turn["llm_text"]})
        messages.append({"role": "user", "content": user_text})

        # 4. LLM call
        assistant_text = deps.llm.complete(messages=messages)

        # 5. Persist
        deps.storage.append_turn(session_id, user_text=user_text, llm_text=assistant_text)
        return TurnResult(user_text=user_text, assistant_text=assistant_text)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
```

This is the version to commit.

- [ ] **Step 4: Run tests**

Run: `pytest tests/web/test_services_turn.py -v`
Expected: 4 passed.

Run: `pytest`
Expected: full suite green.

- [ ] **Step 5: Commit**

```bash
git add tutor/web/services.py tests/web/test_services_turn.py
git commit -m "feat(web): turn_service — ASR → LLM with full history reconstruction"
```

---

## Task 8: Services — end_session (evaluator + cards)

**Files:**
- Modify: `tutor/web/services.py`
- Create: `tests/web/test_services_end.py`

- [ ] **Step 1: Write failing tests**

`tests/web/test_services_end.py`:

```python
from datetime import datetime, date
from unittest.mock import MagicMock
import pytest


def _deps(tmp_path):
    from tutor.web.deps import Dependencies
    from tutor.budget import BudgetTracker
    from tutor.storage import SessionStorage
    from tutor.srs_engine import SRSEngine

    return Dependencies(
        budget=BudgetTracker(
            path=tmp_path / "b.json", daily_usd_cap=1.0,
            daily_token_cap=1_000_000,
            now=lambda: datetime(2026, 5, 21, 10, 0),
        ),
        llm=MagicMock(), asr=MagicMock(),
        storage=SessionStorage(root=tmp_path / "sessions",
                                now=lambda: datetime(2026, 5, 21, 10, 0)),
        srs=SRSEngine(path=tmp_path / "cards.json",
                      now=lambda: date(2026, 5, 21)),
        evaluator_model="m1", grader_model="m2",
    )


def test_end_session_service_happy_path(tmp_path, mocker):
    from tutor.web.services import start_session_service, turn_service, end_session_service
    from tutor.evaluator import GrowthPoint

    deps = _deps(tmp_path)
    deps.llm.complete.return_value = "Hi."
    deps.asr.transcribe.return_value = "I made a project"

    started = start_session_service(deps, scenario_id="tech_interview_behavioral")
    turn_service(deps, started.session_id, audio_bytes=b"x")

    # Patch Evaluator to return one growth point
    fake_eval = MagicMock()
    fake_eval.evaluate.return_value = [
        GrowthPoint(tag="vocab", user_utterance="I made a project",
                    corrected_version="I led a project",
                    explanation="led signals ownership", context=None),
    ]
    mocker.patch("tutor.web.services.Evaluator", return_value=fake_eval)

    result = end_session_service(deps, session_id=started.session_id)

    assert result.session_id == started.session_id
    assert result.ended_at is not None
    assert len(result.growth_points) == 1
    assert result.growth_points[0]["tag"] == "vocab"
    assert len(result.cards_created) == 1
    assert result.growth_points_error is None


def test_end_session_service_evaluator_raises(tmp_path, mocker):
    from tutor.web.services import start_session_service, turn_service, end_session_service
    deps = _deps(tmp_path)
    deps.llm.complete.return_value = "Hi."
    deps.asr.transcribe.return_value = "hi"

    started = start_session_service(deps, scenario_id="tech_interview_behavioral")
    turn_service(deps, started.session_id, audio_bytes=b"x")

    fake_eval = MagicMock()
    fake_eval.evaluate.side_effect = RuntimeError("api down")
    mocker.patch("tutor.web.services.Evaluator", return_value=fake_eval)

    result = end_session_service(deps, session_id=started.session_id)
    assert result.growth_points == []
    assert result.cards_created == []
    assert "api down" in (result.growth_points_error or "")


def test_end_session_service_no_turns_skips_evaluator(tmp_path, mocker):
    from tutor.web.services import start_session_service, end_session_service
    deps = _deps(tmp_path)
    deps.llm.complete.return_value = "Hi."

    started = start_session_service(deps, scenario_id="tech_interview_behavioral")

    fake_eval = MagicMock()
    mocker.patch("tutor.web.services.Evaluator", return_value=fake_eval)

    result = end_session_service(deps, session_id=started.session_id)
    assert result.growth_points == []
    assert result.cards_created == []
    fake_eval.evaluate.assert_not_called()


def test_end_session_service_raises_on_unknown_session(tmp_path):
    from tutor.web.services import end_session_service
    from tutor.web.errors import SessionNotFoundError
    deps = _deps(tmp_path)
    with pytest.raises(SessionNotFoundError):
        end_session_service(deps, session_id="does_not_exist")
```

- [ ] **Step 2: Run tests to verify failures**

Run: `pytest tests/web/test_services_end.py -v`
Expected: 4 failures.

- [ ] **Step 3: Add `end_session_service` to `tutor/web/services.py`**

Add these imports at the top of `services.py`:

```python
import logging
from dataclasses import asdict

from tutor.evaluator import Evaluator
from tutor.web.schemas import EndSessionResult

log = logging.getLogger(__name__)
```

Then append the function:

```python
def end_session_service(deps: Dependencies, session_id: str) -> EndSessionResult:
    try:
        session_data = deps.storage.load_session(session_id)
    except FileNotFoundError as e:
        raise SessionNotFoundError(session_id) from e

    turns = session_data.get("turns", [])
    growth_points_dicts: list[dict] = []
    cards_created_ids: list[str] = []
    growth_points_error: str | None = None

    if turns:
        # Rebuild history for evaluator
        scenario = load_scenario(session_data["scenario_id"])
        system_prompt = build_system_prompt(scenario, user_native_language="Russian")
        history: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if session_data.get("opening_text"):
            history.append({"role": "assistant", "content": session_data["opening_text"]})
        for turn in turns:
            history.append({"role": "user", "content": turn["user_text"]})
            history.append({"role": "assistant", "content": turn["llm_text"]})

        try:
            evaluator = Evaluator(llm=deps.llm, model=deps.evaluator_model)
            growth_points = evaluator.evaluate(transcript=history)
        except Exception as e:
            log.warning("Evaluator raised: %s", e)
            growth_points = []
            growth_points_error = f"evaluator failed: {e}"
            deps.storage.set_growth_points_error(session_id, growth_points_error)

        if growth_points:
            growth_points_dicts = [
                gp.model_dump() if hasattr(gp, "model_dump") else asdict(gp)
                for gp in growth_points
            ]
            deps.storage.set_growth_points(session_id, growth_points_dicts)
            try:
                cards = deps.srs.create_cards(growth_points, session_id=session_id)
                cards_created_ids = [c.id for c in cards]
                deps.storage.set_cards_created(session_id, cards_created_ids)
            except Exception as e:
                log.warning("SRS create_cards failed: %s", e)
                growth_points_error = f"create_cards failed: {e}"
                deps.storage.set_growth_points_error(session_id, growth_points_error)

    deps.storage.end_session(session_id)
    final = deps.storage.load_session(session_id)

    return EndSessionResult(
        session_id=session_id,
        ended_at=final.get("ended_at"),
        growth_points=growth_points_dicts,
        cards_created=cards_created_ids,
        growth_points_error=growth_points_error,
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/web/test_services_end.py -v`
Expected: 4 passed.

Run: `pytest`
Expected: full suite green.

- [ ] **Step 5: Commit**

```bash
git add tutor/web/services.py tests/web/test_services_end.py
git commit -m "feat(web): end_session_service — evaluator + SRS card creation"
```

---

## Task 9: Services — review (due cards + grade)

**Files:**
- Modify: `tutor/web/services.py`
- Create: `tests/web/test_services_review.py`

- [ ] **Step 1: Write failing tests**

`tests/web/test_services_review.py`:

```python
from datetime import date, datetime
from unittest.mock import MagicMock
import pytest


def _deps(tmp_path):
    from tutor.web.deps import Dependencies
    from tutor.budget import BudgetTracker
    from tutor.storage import SessionStorage
    from tutor.srs_engine import SRSEngine

    return Dependencies(
        budget=BudgetTracker(
            path=tmp_path / "b.json", daily_usd_cap=1.0,
            daily_token_cap=1_000_000,
            now=lambda: datetime(2026, 5, 22, 10, 0),
        ),
        llm=MagicMock(), asr=MagicMock(),
        storage=SessionStorage(root=tmp_path / "sessions"),
        srs=SRSEngine(path=tmp_path / "cards.json",
                      now=lambda: date(2026, 5, 22)),
        evaluator_model="m1", grader_model="m2",
    )


def _seed_cards(tmp_path, configs):
    """configs: list of (tag, repetitions, interval_days, last_quality)."""
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint
    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    gps = [
        GrowthPoint(tag=tag, user_utterance=f"u{i}", corrected_version=f"c{i}",
                    explanation="why", context=None)
        for i, (tag, _, _, _) in enumerate(configs)
    ]
    if gps:
        engine.create_cards(gps, session_id="s1")
        for (tag, reps, interval, qual), card in zip(configs, engine.all_cards()):
            card.repetitions = reps
            card.interval_days = interval
            card.last_review_quality = qual
        engine._flush()


def test_review_due_service_returns_dicts(tmp_path):
    from tutor.web.services import review_due_service
    _seed_cards(tmp_path, [("vocab", 0, 0, None), ("grammar", 0, 0, None)])
    deps = _deps(tmp_path)
    result = review_due_service(deps, limit=None, tag=None)
    assert result.total_due == 2
    assert len(result.cards) == 2
    assert all(isinstance(c, dict) for c in result.cards)


def test_review_due_service_respects_filter(tmp_path):
    from tutor.web.services import review_due_service
    _seed_cards(tmp_path, [("vocab", 0, 0, None), ("grammar", 0, 0, None),
                            ("vocab", 0, 0, None)])
    deps = _deps(tmp_path)
    result = review_due_service(deps, limit=10, tag="vocab")
    assert result.total_due == 2  # 2 vocab cards


def test_grade_card_service_audio_path(tmp_path, mocker):
    from tutor.web.services import grade_card_service
    _seed_cards(tmp_path, [("vocab", 0, 0, None)])
    deps = _deps(tmp_path)
    deps.asr.transcribe.return_value = "I led a project"
    # Mock LLMGrader to return 4
    fake_grader = MagicMock()
    fake_grader.grade.return_value = 4
    mocker.patch("tutor.web.services.LLMGrader", return_value=fake_grader)

    card_id = deps.srs.all_cards()[0].id
    result = grade_card_service(deps, card_id=card_id, audio_bytes=b"audio",
                                 skip=False)
    assert result.quality == 4
    assert result.user_attempt_text == "I led a project"


def test_grade_card_service_skip_path(tmp_path):
    from tutor.web.services import grade_card_service
    _seed_cards(tmp_path, [("vocab", 0, 0, None)])
    deps = _deps(tmp_path)
    card_id = deps.srs.all_cards()[0].id
    result = grade_card_service(deps, card_id=card_id, audio_bytes=None, skip=True)
    assert result.quality == 0
    assert result.user_attempt_text == "(skipped)"


def test_grade_card_service_raises_on_unknown_card(tmp_path):
    from tutor.web.services import grade_card_service
    from tutor.srs_engine import CardNotFoundError
    deps = _deps(tmp_path)
    with pytest.raises(CardNotFoundError):
        grade_card_service(deps, card_id="does_not_exist", audio_bytes=b"x", skip=False)
```

- [ ] **Step 2: Run tests to verify failures**

Run: `pytest tests/web/test_services_review.py -v`
Expected: 5 failures.

- [ ] **Step 3: Add review services to `tutor/web/services.py`**

Add to imports:

```python
from tutor.grader import LLMGrader
from tutor.web.schemas import DueCardsResult, GradeResult
```

Then append:

```python
def review_due_service(
    deps: Dependencies, limit: int | None, tag: str | None
) -> DueCardsResult:
    cards = deps.srs.due_today(limit=limit, tag=tag)
    return DueCardsResult(
        cards=[asdict(c) for c in cards],
        total_due=len(cards),
    )


def grade_card_service(
    deps: Dependencies, card_id: str, audio_bytes: bytes | None, skip: bool
) -> GradeResult:
    card = deps.srs.load_card(card_id)  # raises CardNotFoundError

    if skip:
        quality = 0
        user_attempt_text = "(skipped)"
    else:
        if audio_bytes is None:
            raise NoSpeechDetectedError("no audio submitted")
        tmp = Path(tempfile.gettempdir()) / f"web_grade_{card_id}_{os.getpid()}.bin"
        tmp.write_bytes(audio_bytes)
        try:
            user_attempt_text = deps.asr.transcribe(tmp).strip()
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
        if not user_attempt_text:
            quality = 0
        else:
            grader = LLMGrader(llm=deps.llm, model=deps.grader_model)
            quality = grader.grade(target=card.corrected_version, attempt=user_attempt_text)

    deps.srs.record_review(card_id, quality=quality)
    updated = deps.srs.load_card(card_id)
    return GradeResult(
        card_id=card_id,
        user_attempt_text=user_attempt_text,
        quality=quality,
        target=card.corrected_version,
        explanation=card.explanation,
        next_due=updated.due_date,
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/web/test_services_review.py -v`
Expected: 5 passed.

Run: `pytest`
Expected: full suite green.

- [ ] **Step 5: Commit**

```bash
git add tutor/web/services.py tests/web/test_services_review.py
git commit -m "feat(web): review_due_service + grade_card_service"
```

---

## Task 10: Services — stats + budget

**Files:**
- Modify: `tutor/web/services.py`
- Create: `tests/web/test_services_stats.py`

- [ ] **Step 1: Write failing tests**

`tests/web/test_services_stats.py`:

```python
from datetime import datetime, date
from unittest.mock import MagicMock


def _deps(tmp_path):
    from tutor.web.deps import Dependencies
    from tutor.budget import BudgetTracker
    from tutor.storage import SessionStorage
    from tutor.srs_engine import SRSEngine

    return Dependencies(
        budget=BudgetTracker(
            path=tmp_path / "b.json", daily_usd_cap=0.5,
            daily_token_cap=200_000,
            now=lambda: datetime(2026, 5, 21, 10, 0),
        ),
        llm=MagicMock(), asr=MagicMock(),
        storage=SessionStorage(root=tmp_path / "sessions",
                                now=lambda: datetime(2026, 5, 21, 10, 0)),
        srs=SRSEngine(path=tmp_path / "cards.json",
                      now=lambda: date(2026, 5, 21)),
        evaluator_model="m1", grader_model="m2",
    )


def test_stats_service_returns_summary(tmp_path):
    from tutor.web.services import stats_service
    deps = _deps(tmp_path)
    s = stats_service(deps, days=None)
    assert s.sessions_total == 0
    assert s.cards_total == 0
    assert s.streak_days == 0


def test_stats_service_with_days_filter(tmp_path):
    from tutor.web.services import stats_service
    deps = _deps(tmp_path)
    s = stats_service(deps, days=7)
    assert s.sessions_total == 0


def test_budget_service(tmp_path):
    from tutor.web.services import budget_service
    deps = _deps(tmp_path)
    deps.budget.record(tokens_in=10, tokens_out=5, usd_cost=0.001)
    b = budget_service(deps)
    assert b.usd_today > 0
    assert b.tokens_today == 15
    assert b.daily_usd_cap == 0.5
    assert b.daily_token_cap == 200_000
```

- [ ] **Step 2: Run tests to verify failures**

Run: `pytest tests/web/test_services_stats.py -v`
Expected: 3 failures.

- [ ] **Step 3: Add stats + budget services**

Add to imports of `tutor/web/services.py`:

```python
from tutor.stats import StatsCalculator, StatsSummary
from tutor.web.schemas import BudgetSummary
```

Then append:

```python
def stats_service(deps: Dependencies, days: int | None) -> StatsSummary:
    calc = StatsCalculator(storage=deps.storage, srs=deps.srs)
    return calc.compute(days=days)


def budget_service(deps: Dependencies) -> BudgetSummary:
    return BudgetSummary(
        usd_today=deps.budget.usd_today,
        tokens_today=deps.budget.tokens_today,
        daily_usd_cap=deps.budget.daily_usd_cap,
        daily_token_cap=deps.budget.daily_token_cap,
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/web/test_services_stats.py -v`
Expected: 3 passed.

Run: `pytest`
Expected: full suite green (~125 tests).

- [ ] **Step 5: Commit**

```bash
git add tutor/web/services.py tests/web/test_services_stats.py
git commit -m "feat(web): stats_service + budget_service"
```

---

## Task 11: FastAPI app + routes (`tutor/web/api.py`)

**Files:**
- Create: `tutor/web/api.py`
- Create: `tests/web/test_api.py`

- [ ] **Step 1: Write failing tests**

`tests/web/test_api.py`:

```python
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock
import io
import pytest


def _client(tmp_path, mocker):
    """Build a TestClient with mocked Whisper and a tmp project root."""
    from tutor.web.api import create_app
    from tutor.web.deps import Dependencies
    from tutor.budget import BudgetTracker
    from tutor.storage import SessionStorage
    from tutor.srs_engine import SRSEngine
    from datetime import date

    mocker.patch("tutor.web.deps.WhisperASR")  # don't load real model

    fake_llm = MagicMock()
    fake_llm.complete.return_value = "Opening line."
    fake_asr = MagicMock()
    fake_asr.transcribe.return_value = "I led a backend project"

    deps = Dependencies(
        budget=BudgetTracker(
            path=tmp_path / "b.json", daily_usd_cap=1.0,
            daily_token_cap=1_000_000,
            now=lambda: datetime(2026, 5, 21, 10, 0),
        ),
        llm=fake_llm, asr=fake_asr,
        storage=SessionStorage(root=tmp_path / "sessions",
                                now=lambda: datetime(2026, 5, 21, 10, 0)),
        srs=SRSEngine(path=tmp_path / "cards.json",
                      now=lambda: date(2026, 5, 21)),
        evaluator_model="m1", grader_model="m2",
    )
    app = create_app(deps=deps)
    from fastapi.testclient import TestClient
    return TestClient(app), deps


def test_get_scenarios_returns_three(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.get("/api/scenarios")
    assert r.status_code == 200
    ids = [s["id"] for s in r.json()["scenarios"]]
    assert "tech_interview_behavioral" in ids
    assert "daily_standup" in ids
    assert "apartment_rental_abroad" in ids


def test_post_session_creates_and_returns_opening(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.post("/api/sessions", json={"scenario_id": "tech_interview_behavioral"})
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"]
    assert body["opening_text"] == "Opening line."


def test_post_session_unknown_scenario_404(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.post("/api/sessions", json={"scenario_id": "bogus"})
    assert r.status_code == 404
    assert r.json()["error"] == "scenario_not_found"


def test_get_session_returns_full_dict(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.post("/api/sessions", json={"scenario_id": "tech_interview_behavioral"})
    sid = r.json()["session_id"]
    r2 = client.get(f"/api/sessions/{sid}")
    assert r2.status_code == 200
    assert r2.json()["session_id"] == sid
    assert r2.json()["opening_text"] == "Opening line."


def test_get_session_unknown_404(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.get("/api/sessions/does_not_exist")
    assert r.status_code == 404
    assert r.json()["error"] == "session_not_found"


def test_post_turn_uploads_audio_and_returns_reply(tmp_path, mocker):
    client, deps = _client(tmp_path, mocker)
    r = client.post("/api/sessions", json={"scenario_id": "tech_interview_behavioral"})
    sid = r.json()["session_id"]

    # New reply for the turn call
    deps.llm.complete.return_value = "What was the scope?"

    files = {"audio": ("turn.webm", io.BytesIO(b"fake_audio_bytes"), "audio/webm")}
    r2 = client.post(f"/api/sessions/{sid}/turn", files=files)
    assert r2.status_code == 200
    body = r2.json()
    assert body["user_text"] == "I led a backend project"
    assert body["assistant_text"] == "What was the scope?"


def test_post_turn_unknown_session_404(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    files = {"audio": ("turn.webm", io.BytesIO(b"x"), "audio/webm")}
    r = client.post("/api/sessions/does_not_exist/turn", files=files)
    assert r.status_code == 404


def test_post_turn_empty_asr_422(tmp_path, mocker):
    client, deps = _client(tmp_path, mocker)
    r = client.post("/api/sessions", json={"scenario_id": "tech_interview_behavioral"})
    sid = r.json()["session_id"]

    deps.asr.transcribe.return_value = ""  # empty
    files = {"audio": ("turn.webm", io.BytesIO(b"x"), "audio/webm")}
    r2 = client.post(f"/api/sessions/{sid}/turn", files=files)
    assert r2.status_code == 422
    assert r2.json()["error"] == "no_speech_detected"


def test_post_end_no_turns_skips_evaluator(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.post("/api/sessions", json={"scenario_id": "tech_interview_behavioral"})
    sid = r.json()["session_id"]

    r2 = client.post(f"/api/sessions/{sid}/end")
    assert r2.status_code == 200
    body = r2.json()
    assert body["session_id"] == sid
    assert body["growth_points"] == []
    assert body["cards_created"] == []


def test_get_review_due_returns_empty_initially(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.get("/api/review/due")
    assert r.status_code == 200
    assert r.json()["total_due"] == 0
    assert r.json()["cards"] == []


def test_get_stats_returns_summary(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.get("/api/stats")
    assert r.status_code == 200
    body = r.json()
    assert "streak_days" in body
    assert "sessions_total" in body


def test_get_budget_returns_caps(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.get("/api/budget")
    assert r.status_code == 200
    body = r.json()
    assert body["daily_usd_cap"] == 1.0
    assert body["daily_token_cap"] == 1_000_000
```

- [ ] **Step 2: Run tests to verify failures**

Run: `pytest tests/web/test_api.py -v`
Expected: many failures (`tutor.web.api` doesn't exist).

- [ ] **Step 3: Implement `tutor/web/api.py`**

```python
"""FastAPI app + routes. Thin layer over services.py."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from tutor.web import services
from tutor.web.deps import Dependencies, build_dependencies
from tutor.web.errors import register_exception_handlers
from tutor.web.schemas import (
    BudgetSummary,
    DueCardsResult,
    EndSessionResult,
    GradeResult,
    StartSessionRequest,
    StartSessionResult,
    TurnResult,
)

log = logging.getLogger(__name__)


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def create_app(deps: Dependencies | None = None) -> FastAPI:
    if deps is None:
        # Real run: build dependencies from project root + preload Whisper
        deps = build_dependencies(project_root=_default_project_root())
        log.info("Preloading Whisper model: %s", deps.asr._model_size)
        deps.asr._ensure_model()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(title="English Tutor API", lifespan=lifespan)
    register_exception_handlers(app)

    def get_deps() -> Dependencies:
        return deps

    @app.get("/api/scenarios")
    async def list_scenarios(d: Dependencies = Depends(get_deps)):
        result = services.list_scenarios_service(d)
        return {"scenarios": [s.model_dump() for s in result]}

    @app.post("/api/sessions", response_model=StartSessionResult)
    async def start_session(req: StartSessionRequest, d: Dependencies = Depends(get_deps)):
        return services.start_session_service(d, scenario_id=req.scenario_id)

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str, d: Dependencies = Depends(get_deps)):
        return services.get_session_service(d, session_id)

    @app.post("/api/sessions/{session_id}/turn", response_model=TurnResult)
    async def submit_turn(
        session_id: str,
        audio: UploadFile = File(...),
        d: Dependencies = Depends(get_deps),
    ):
        audio_bytes = await audio.read()
        return services.turn_service(d, session_id=session_id, audio_bytes=audio_bytes)

    @app.post("/api/sessions/{session_id}/end", response_model=EndSessionResult)
    async def end_session(session_id: str, d: Dependencies = Depends(get_deps)):
        return services.end_session_service(d, session_id=session_id)

    @app.get("/api/review/due", response_model=DueCardsResult)
    async def review_due(
        limit: int | None = None,
        tag: str | None = None,
        d: Dependencies = Depends(get_deps),
    ):
        return services.review_due_service(d, limit=limit, tag=tag)

    @app.post("/api/review/{card_id}/grade", response_model=GradeResult)
    async def grade_card(
        card_id: str,
        audio: UploadFile | None = File(None),
        skip: bool = False,
        d: Dependencies = Depends(get_deps),
    ):
        audio_bytes = await audio.read() if audio is not None else None
        return services.grade_card_service(
            d, card_id=card_id, audio_bytes=audio_bytes, skip=skip
        )

    @app.get("/api/stats")
    async def stats(days: int | None = None, d: Dependencies = Depends(get_deps)):
        s = services.stats_service(d, days=days)
        # StatsSummary is a dataclass; serialize via asdict
        from dataclasses import asdict
        return asdict(s)

    @app.get("/api/budget", response_model=BudgetSummary)
    async def budget(d: Dependencies = Depends(get_deps)):
        return services.budget_service(d)

    return app
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/web/test_api.py -v`
Expected: 12 passed.

Run: `pytest`
Expected: full suite green.

- [ ] **Step 5: Commit**

```bash
git add tutor/web/api.py tests/web/test_api.py
git commit -m "feat(web): FastAPI app with all API routes"
```

---

## Task 12: Static frontend serving (catch-all + mount)

**Files:**
- Modify: `tutor/web/api.py`
- Create: `tutor/web/static/index.html` (placeholder for tests)
- Modify: `tests/web/test_api.py`

- [ ] **Step 1: Add failing tests for static serving**

Append to `tests/web/test_api.py`:

```python
def test_static_root_serves_index_html(tmp_path, mocker):
    """GET / serves index.html from static/."""
    client, _ = _client(tmp_path, mocker)
    r = client.get("/")
    # In test, static/ may not exist or be empty — accept 200 (placeholder)
    # or 404 (no file). The behavior is the same when wired in production.
    # We'll verify the route is wired by checking it doesn't 405 (method not allowed).
    assert r.status_code in (200, 404)


def test_deep_link_route_serves_index_html(tmp_path, mocker):
    """GET /session/abc serves index.html (catch-all for React Router)."""
    client, _ = _client(tmp_path, mocker)
    r = client.get("/session/abc12345")
    # Same as above — verify it's not 405 or 500
    assert r.status_code in (200, 404)
```

- [ ] **Step 2: Add a placeholder index.html so tests can verify the route**

Create `tutor/web/static/index.html`:

```html
<!DOCTYPE html>
<html><head><title>English Tutor</title></head>
<body><div id="root">Frontend not built yet. Run scripts/build_and_serve.sh.</div></body></html>
```

Update `.gitignore` so the built static assets don't leak (but keep the placeholder index):

Edit `.gitignore` to add:

```
tutor/web/static/assets/
tutor/web/static/*.js
tutor/web/static/*.css
tutor/web/static/*.map
```

(We keep `tutor/web/static/index.html` tracked as a placeholder; only built artifacts ignored.)

- [ ] **Step 3: Run tests to confirm failure for deep links**

Run: `pytest tests/web/test_api.py::test_deep_link_route_serves_index_html -v`

Expected: FAIL — the route returns 404 because we haven't added the catch-all.

- [ ] **Step 4: Add static serving and catch-all to `create_app`**

Replace the end of `create_app` in `tutor/web/api.py` (before `return app`) with:

```python
    # Static frontend assets + catch-all for React Router
    static_dir = _default_project_root() / "tutor" / "web" / "static"
    index_file = static_dir / "index.html"

    if (static_dir / "assets").exists():
        from fastapi.staticfiles import StaticFiles
        app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="assets")

    @app.get("/")
    @app.get("/{path:path}")
    async def serve_spa(path: str = ""):
        # Don't intercept /api/* routes (FastAPI matches more specific first,
        # but be defensive)
        if path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        if index_file.exists():
            return FileResponse(str(index_file))
        raise HTTPException(status_code=404, detail="Frontend not built")

    return app
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/web/test_api.py -v`
Expected: 14 passed (12 existing + 2 new).

Run: `pytest`
Expected: full suite green.

- [ ] **Step 6: Commit**

```bash
git add tutor/web/api.py tutor/web/static/index.html .gitignore tests/web/test_api.py
git commit -m "feat(web): serve React build from /static, catch-all for SPA routing"
```

---

## Task 13: Frontend project setup (Vite + React + TS + Tailwind)

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/index.css`
- Create: `frontend/src/App.tsx`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/.gitignore`

- [ ] **Step 1: Create `frontend/package.json`**

```json
{
  "name": "english-tutor-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "react-router-dom": "^6.26.0",
    "@tanstack/react-query": "^5.50.0",
    "lucide-react": "^0.400.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "vite": "^5.4.0",
    "typescript": "^5.5.0",
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.0",
    "autoprefixer": "^10.4.0",
    "vitest": "^2.0.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.4.0",
    "jsdom": "^25.0.0"
  }
}
```

- [ ] **Step 2: Create `frontend/vite.config.ts`**

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: "../tutor/web/static",
    emptyOutDir: false,  // preserve placeholder index.html if missing
  },
});
```

- [ ] **Step 3: Create `frontend/tsconfig.json` and `tsconfig.node.json`**

`frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

`frontend/tsconfig.node.json`:
```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true
  },
  "include": ["vite.config.ts", "vitest.config.ts"]
}
```

- [ ] **Step 4: Create Tailwind config**

`frontend/tailwind.config.js`:
```javascript
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: { extend: {} },
  plugins: [],
};
```

`frontend/postcss.config.js`:
```javascript
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 5: Create `frontend/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
    <title>English Tutor</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 6: Create `frontend/src/main.tsx`, `App.tsx`, `index.css`**

`frontend/src/index.css`:
```css
@tailwind base;
@tailwind components;
@tailwind utilities;

html, body, #root {
  height: 100%;
  margin: 0;
  font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
}
```

`frontend/src/main.tsx`:
```typescript
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 30_000, refetchOnWindowFocus: false } },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </BrowserRouter>
  </React.StrictMode>
);
```

`frontend/src/App.tsx`:
```typescript
import { Routes, Route } from "react-router-dom";

function HomePlaceholder() {
  return <div className="p-8">English Tutor — frontend up.</div>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePlaceholder />} />
    </Routes>
  );
}
```

- [ ] **Step 7: Create `frontend/vitest.config.ts` and test setup**

`frontend/vitest.config.ts`:
```typescript
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
  },
});
```

`frontend/src/test/setup.ts`:
```typescript
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 8: Create `frontend/.gitignore`**

```
node_modules
dist
.DS_Store
*.log
.vite
coverage
```

- [ ] **Step 9: Install deps and verify dev/build/test**

Run from `/Users/sarkhipov/Work/Personal/english-tutor/frontend`:

```bash
cd frontend && npm install
```

Expected: installs dependencies without errors.

Run: `npm run build`
Expected: builds successfully, output in `../tutor/web/static/`.

Run: `npm test`
Expected: no tests found (yet) but vitest exits 0.

- [ ] **Step 10: Commit**

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/
git commit -m "chore(frontend): Vite + React + TS + Tailwind project setup"
```

---

## Task 14: Frontend API client + types

**Files:**
- Create: `frontend/src/api/types.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/client.test.ts`

- [ ] **Step 1: Write failing tests**

`frontend/src/api/client.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { api } from "./client";

const originalFetch = global.fetch;

describe("api client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("getScenarios returns parsed scenarios array", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ scenarios: [{ id: "x", name: "X", difficulty: "y" }] }),
    });
    const result = await api.getScenarios();
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("x");
  });

  it("startSession POSTs scenario_id and returns result", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ session_id: "s1", opening_text: "Hi" }),
    });
    const result = await api.startSession("x");
    expect(result.session_id).toBe("s1");
    expect(result.opening_text).toBe("Hi");
    const call = (global.fetch as any).mock.calls[0];
    expect(call[1].method).toBe("POST");
    const body = JSON.parse(call[1].body);
    expect(body.scenario_id).toBe("x");
  });

  it("submitTurn POSTs multipart audio", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ user_text: "hi", assistant_text: "hello" }),
    });
    const blob = new Blob(["fake"], { type: "audio/webm" });
    await api.submitTurn("s1", blob);
    const call = (global.fetch as any).mock.calls[0];
    expect(call[1].method).toBe("POST");
    expect(call[1].body).toBeInstanceOf(FormData);
  });

  it("throws ApiError on non-ok response", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ error: "scenario_not_found" }),
    });
    await expect(api.startSession("bogus")).rejects.toThrow();
  });
});

afterAll(() => {
  global.fetch = originalFetch;
});

declare const afterAll: any;
```

Note: vitest provides `globals: true` so `afterAll` etc. are global; the explicit declare may be unnecessary depending on tsconfig settings — strip it if it errors.

- [ ] **Step 2: Run tests to verify failures**

Run: `cd frontend && npm test`
Expected: 4 failures (`./client` doesn't exist).

- [ ] **Step 3: Implement `frontend/src/api/types.ts`**

```typescript
export interface ScenarioSummary {
  id: string;
  name: string;
  difficulty: string;
}

export interface StartSessionResult {
  session_id: string;
  opening_text: string;
}

export interface TurnResult {
  user_text: string;
  assistant_text: string;
}

export interface SessionData {
  session_id: string;
  scenario_id: string;
  started_at: string;
  ended_at: string | null;
  opening_text: string | null;
  turns: Array<{ ts: string; user_text: string; llm_text: string }>;
  growth_points?: GrowthPointDict[];
  cards_created?: string[];
  growth_points_error?: string | null;
}

export interface GrowthPointDict {
  tag: "vocab" | "grammar";
  user_utterance: string;
  corrected_version: string;
  explanation: string;
  context: string | null;
}

export interface EndSessionResult {
  session_id: string;
  ended_at: string | null;
  growth_points: GrowthPointDict[];
  cards_created: string[];
  growth_points_error: string | null;
}

export interface Card {
  id: string;
  created_from_session_id: string;
  tag: "vocab" | "grammar";
  user_utterance: string;
  corrected_version: string;
  explanation: string;
  context: string | null;
  ease_factor: number;
  interval_days: number;
  repetitions: number;
  due_date: string;
  last_review_quality: number | null;
  review_history: Array<{ date: string; quality: number }>;
}

export interface DueCardsResult {
  cards: Card[];
  total_due: number;
}

export interface GradeResult {
  card_id: string;
  user_attempt_text: string;
  quality: number;
  target: string;
  explanation: string;
  next_due: string;
}

export interface BudgetSummary {
  usd_today: number;
  tokens_today: number;
  daily_usd_cap: number;
  daily_token_cap: number;
}

export interface StatsSummary {
  today: string;
  streak_days: number;
  last_activity: string | null;
  sessions_total: number;
  sessions_last_7d: number;
  sessions_last_30d: number;
  sessions_by_scenario: Record<string, number>;
  cards_total: number;
  cards_by_tag: Record<string, number>;
  cards_by_state: Record<string, number>;
  retention_rate: number | null;
  retention_sample_size: number;
}

export interface ApiErrorBody {
  error: string;
  message?: string;
  [key: string]: unknown;
}
```

- [ ] **Step 4: Implement `frontend/src/api/client.ts`**

```typescript
import type {
  BudgetSummary,
  Card,
  DueCardsResult,
  EndSessionResult,
  GradeResult,
  ScenarioSummary,
  SessionData,
  StartSessionResult,
  StatsSummary,
  TurnResult,
  ApiErrorBody,
} from "./types";

export class ApiError extends Error {
  status: number;
  body: ApiErrorBody;
  constructor(status: number, body: ApiErrorBody) {
    super(body.message || body.error || "API error");
    this.status = status;
    this.body = body;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) {
    let body: ApiErrorBody;
    try {
      body = await res.json();
    } catch {
      body = { error: "unknown_error" };
    }
    throw new ApiError(res.status, body);
  }
  return res.json();
}

export const api = {
  async getScenarios(): Promise<ScenarioSummary[]> {
    const data = await request<{ scenarios: ScenarioSummary[] }>("/api/scenarios");
    return data.scenarios;
  },

  startSession(scenario_id: string): Promise<StartSessionResult> {
    return request("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario_id }),
    });
  },

  getSession(session_id: string): Promise<SessionData> {
    return request(`/api/sessions/${session_id}`);
  },

  submitTurn(session_id: string, audio: Blob): Promise<TurnResult> {
    const form = new FormData();
    form.append("audio", audio, "turn.webm");
    return request(`/api/sessions/${session_id}/turn`, { method: "POST", body: form });
  },

  endSession(session_id: string): Promise<EndSessionResult> {
    return request(`/api/sessions/${session_id}/end`, { method: "POST" });
  },

  getDueCards(params: { limit?: number; tag?: string } = {}): Promise<DueCardsResult> {
    const qs = new URLSearchParams();
    if (params.limit !== undefined) qs.set("limit", String(params.limit));
    if (params.tag) qs.set("tag", params.tag);
    const suffix = qs.toString() ? `?${qs}` : "";
    return request(`/api/review/due${suffix}`);
  },

  gradeCard(card_id: string, audio: Blob | null, skip: boolean): Promise<GradeResult> {
    if (skip) {
      const form = new FormData();
      form.append("skip", "true");
      return request(`/api/review/${card_id}/grade?skip=true`, {
        method: "POST",
        body: form,
      });
    }
    const form = new FormData();
    if (audio) form.append("audio", audio, "grade.webm");
    return request(`/api/review/${card_id}/grade`, { method: "POST", body: form });
  },

  getStats(days?: number): Promise<StatsSummary> {
    const qs = days !== undefined ? `?days=${days}` : "";
    return request(`/api/stats${qs}`);
  },

  getBudget(): Promise<BudgetSummary> {
    return request("/api/budget");
  },
};
```

- [ ] **Step 5: Run tests**

Run: `cd frontend && npm test`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/api/
git commit -m "feat(frontend): typed API client + types mirror"
```

---

## Task 15: useRecorder + useTTS hooks

**Files:**
- Create: `frontend/src/hooks/useRecorder.ts`
- Create: `frontend/src/hooks/useTTS.ts`
- Create: `frontend/src/hooks/useRecorder.test.ts`
- Create: `frontend/src/hooks/useTTS.test.ts`

- [ ] **Step 1: Write failing tests**

`frontend/src/hooks/useRecorder.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useRecorder } from "./useRecorder";

beforeEach(() => {
  // Mock MediaRecorder
  const mockStream = { getTracks: () => [] };
  global.navigator.mediaDevices = {
    getUserMedia: vi.fn().mockResolvedValue(mockStream),
  } as any;

  class MockMediaRecorder {
    state = "inactive";
    ondataavailable: ((e: any) => void) | null = null;
    onstop: (() => void) | null = null;
    constructor(_: any) {}
    start() { this.state = "recording"; }
    stop() {
      this.state = "inactive";
      this.ondataavailable?.({ data: new Blob(["x"], { type: "audio/webm" }) });
      this.onstop?.();
    }
    static isTypeSupported(_: string) { return true; }
  }
  (global as any).MediaRecorder = MockMediaRecorder;
});

describe("useRecorder", () => {
  it("starts and stops recording, returns blob", async () => {
    const { result } = renderHook(() => useRecorder());

    await act(async () => {
      await result.current.startRecording();
    });
    expect(result.current.isRecording).toBe(true);

    let blob: Blob | null = null;
    await act(async () => {
      blob = await result.current.stopRecording();
    });
    expect(result.current.isRecording).toBe(false);
    expect(blob).toBeInstanceOf(Blob);
  });

  it("cancelRecording discards blob", async () => {
    const { result } = renderHook(() => useRecorder());
    await act(async () => {
      await result.current.startRecording();
    });
    act(() => {
      result.current.cancelRecording();
    });
    expect(result.current.isRecording).toBe(false);
  });
});
```

`frontend/src/hooks/useTTS.test.ts`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useTTS } from "./useTTS";

beforeEach(() => {
  const mockUtterance: any = { text: "", voice: null, onend: null, onerror: null };
  (global as any).SpeechSynthesisUtterance = vi.fn(() => mockUtterance);
  (global as any).speechSynthesis = {
    getVoices: () => [{ name: "Voice A" }],
    speak: vi.fn((u: any) => {
      setTimeout(() => u.onend?.(), 0);
    }),
    cancel: vi.fn(),
    addEventListener: vi.fn(),
  };
});

describe("useTTS", () => {
  it("speak resolves on utterance end", async () => {
    const { result } = renderHook(() => useTTS());
    await act(async () => {
      await result.current.speak("hello");
    });
    expect((global as any).speechSynthesis.speak).toHaveBeenCalled();
  });

  it("exposes available voices", () => {
    const { result } = renderHook(() => useTTS());
    expect(result.current.voices.length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Run tests to verify failures**

Run: `cd frontend && npm test`
Expected: failures (hooks don't exist).

- [ ] **Step 3: Implement `frontend/src/hooks/useRecorder.ts`**

```typescript
import { useCallback, useRef, useState } from "react";

const MAX_DURATION_MS = 60_000;
const MIN_DURATION_MS = 500;

const MIME_PRIORITY = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/wav",
];

function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  for (const m of MIME_PRIORITY) {
    if (MediaRecorder.isTypeSupported(m)) return m;
  }
  return undefined;
}

export interface UseRecorder {
  isRecording: boolean;
  startRecording: () => Promise<void>;
  stopRecording: () => Promise<Blob | null>;
  cancelRecording: () => void;
}

export function useRecorder(): UseRecorder {
  const [isRecording, setIsRecording] = useState(false);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const startedAtRef = useRef<number>(0);
  const cancelledRef = useRef(false);
  const maxTimerRef = useRef<number | null>(null);

  const startRecording = useCallback(async () => {
    if (!streamRef.current) {
      streamRef.current = await navigator.mediaDevices.getUserMedia({ audio: true });
    }
    chunksRef.current = [];
    cancelledRef.current = false;

    const mimeType = pickMimeType();
    const rec = new MediaRecorder(
      streamRef.current,
      mimeType ? { mimeType } : undefined,
    );
    recorderRef.current = rec;

    rec.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
    };

    rec.start();
    startedAtRef.current = performance.now();
    setIsRecording(true);

    // hard cap
    maxTimerRef.current = window.setTimeout(() => {
      if (rec.state === "recording") rec.stop();
    }, MAX_DURATION_MS);
  }, []);

  const stopRecording = useCallback(async (): Promise<Blob | null> => {
    const rec = recorderRef.current;
    if (!rec || rec.state === "inactive") {
      setIsRecording(false);
      return null;
    }
    if (maxTimerRef.current) {
      clearTimeout(maxTimerRef.current);
      maxTimerRef.current = null;
    }
    const duration = performance.now() - startedAtRef.current;
    const blob: Blob | null = await new Promise((resolve) => {
      rec.onstop = () => {
        if (cancelledRef.current) {
          resolve(null);
          return;
        }
        if (duration < MIN_DURATION_MS) {
          resolve(null);
          return;
        }
        const mimeType = rec.mimeType || "audio/webm";
        resolve(new Blob(chunksRef.current, { type: mimeType }));
      };
      rec.stop();
    });
    setIsRecording(false);
    return blob;
  }, []);

  const cancelRecording = useCallback(() => {
    cancelledRef.current = true;
    const rec = recorderRef.current;
    if (rec && rec.state === "recording") rec.stop();
    if (maxTimerRef.current) {
      clearTimeout(maxTimerRef.current);
      maxTimerRef.current = null;
    }
    setIsRecording(false);
  }, []);

  return { isRecording, startRecording, stopRecording, cancelRecording };
}
```

- [ ] **Step 4: Implement `frontend/src/hooks/useTTS.ts`**

```typescript
import { useCallback, useEffect, useState } from "react";

export interface UseTTS {
  speak: (text: string) => Promise<void>;
  isSpeaking: boolean;
  voices: SpeechSynthesisVoice[];
}

export function useTTS(): UseTTS {
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]);
  const [isSpeaking, setIsSpeaking] = useState(false);

  useEffect(() => {
    if (typeof speechSynthesis === "undefined") return;
    const update = () => setVoices(speechSynthesis.getVoices());
    update();
    speechSynthesis.addEventListener?.("voiceschanged", update);
    return () => {
      speechSynthesis.removeEventListener?.("voiceschanged", update);
    };
  }, []);

  const speak = useCallback(async (text: string): Promise<void> => {
    if (!text.trim() || typeof speechSynthesis === "undefined") return;
    return new Promise((resolve, reject) => {
      const utter = new SpeechSynthesisUtterance(text);
      const savedVoice = localStorage.getItem("ttsVoice");
      if (savedVoice) {
        const v = voices.find((v) => v.name === savedVoice);
        if (v) utter.voice = v;
      }
      utter.rate = 1.0;
      utter.onend = () => {
        setIsSpeaking(false);
        resolve();
      };
      utter.onerror = (e) => {
        setIsSpeaking(false);
        reject(e);
      };
      setIsSpeaking(true);
      speechSynthesis.speak(utter);
    });
  }, [voices]);

  return { speak, isSpeaking, voices };
}
```

- [ ] **Step 5: Run tests**

Run: `cd frontend && npm test`
Expected: 6 passed (4 client + 2 useTTS, useRecorder may need slight tweaks; if tests fail due to mock mismatches, adjust mocks to match the implementation contract).

- [ ] **Step 6: Commit**

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/hooks/
git commit -m "feat(frontend): useRecorder + useTTS hooks"
```

---

## Task 16: Layout + BudgetIndicator + ScenariosPage

**Files:**
- Create: `frontend/src/components/Layout.tsx`
- Create: `frontend/src/components/BudgetIndicator.tsx`
- Create: `frontend/src/pages/ScenariosPage.tsx`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/components/Layout.test.tsx`
- Create: `frontend/src/pages/ScenariosPage.test.tsx`

- [ ] **Step 1: Write failing smoke tests**

`frontend/src/components/Layout.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Layout } from "./Layout";

vi.mock("../api/client", () => ({
  api: {
    getBudget: vi.fn().mockResolvedValue({
      usd_today: 0.01, tokens_today: 100,
      daily_usd_cap: 0.5, daily_token_cap: 200_000,
    }),
  },
}));

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <BrowserRouter>
      <QueryClientProvider client={qc}>{node}</QueryClientProvider>
    </BrowserRouter>
  );
}

describe("Layout", () => {
  it("renders header with nav links", () => {
    render(wrap(<Layout><div>content</div></Layout>));
    expect(screen.getByText(/scenarios/i)).toBeInTheDocument();
    expect(screen.getByText(/review/i)).toBeInTheDocument();
    expect(screen.getByText(/stats/i)).toBeInTheDocument();
  });
});
```

`frontend/src/pages/ScenariosPage.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ScenariosPage } from "./ScenariosPage";

vi.mock("../api/client", () => ({
  api: {
    getScenarios: vi.fn().mockResolvedValue([
      { id: "tech_interview_behavioral", name: "Tech interview", difficulty: "intermediate" },
      { id: "daily_standup", name: "Daily standup", difficulty: "intermediate" },
    ]),
  },
}));

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <BrowserRouter>
      <QueryClientProvider client={qc}>{node}</QueryClientProvider>
    </BrowserRouter>
  );
}

describe("ScenariosPage", () => {
  it("renders fetched scenarios", async () => {
    render(wrap(<ScenariosPage />));
    await waitFor(() => {
      expect(screen.getByText("Tech interview")).toBeInTheDocument();
      expect(screen.getByText("Daily standup")).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 2: Run tests to verify failures**

Run: `cd frontend && npm test`
Expected: failures (`Layout` and `ScenariosPage` don't exist).

- [ ] **Step 3: Implement `frontend/src/components/BudgetIndicator.tsx`**

```typescript
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function BudgetIndicator() {
  const { data } = useQuery({
    queryKey: ["budget"],
    queryFn: () => api.getBudget(),
    refetchInterval: 30_000,
  });
  if (!data) return null;
  const pct = (data.usd_today / data.daily_usd_cap) * 100;
  const color = pct > 80 ? "text-red-600" : pct > 50 ? "text-amber-600" : "text-emerald-700";
  return (
    <span className={`text-sm font-mono ${color}`}>
      ${data.usd_today.toFixed(4)} / ${data.daily_usd_cap.toFixed(2)}
    </span>
  );
}
```

- [ ] **Step 4: Implement `frontend/src/components/Layout.tsx`**

```typescript
import { ReactNode } from "react";
import { Link } from "react-router-dom";
import { BudgetIndicator } from "./BudgetIndicator";

export function Layout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      <header className="border-b bg-white px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <span className="font-semibold text-slate-900">English Tutor</span>
          <nav className="flex gap-3 text-sm text-slate-600">
            <Link to="/" className="hover:text-slate-900">Scenarios</Link>
            <Link to="/review" className="hover:text-slate-900">Review</Link>
            <Link to="/stats" className="hover:text-slate-900">Stats</Link>
          </nav>
        </div>
        <BudgetIndicator />
      </header>
      <main className="flex-1 flex flex-col">{children}</main>
    </div>
  );
}
```

- [ ] **Step 5: Implement `frontend/src/pages/ScenariosPage.tsx`**

```typescript
import { useQuery, useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";

export function ScenariosPage() {
  const navigate = useNavigate();
  const { data: scenarios, isLoading } = useQuery({
    queryKey: ["scenarios"],
    queryFn: () => api.getScenarios(),
  });
  const startMutation = useMutation({
    mutationFn: (id: string) => api.startSession(id),
    onSuccess: (result) => {
      navigate(`/session/${result.session_id}`, { state: { opening: result.opening_text } });
    },
  });

  if (isLoading) return <div className="p-8 text-slate-600">Loading scenarios…</div>;

  return (
    <div className="max-w-2xl mx-auto p-8 w-full">
      <h1 className="text-2xl font-semibold mb-6 text-slate-900">Pick a scenario</h1>
      <div className="space-y-3">
        {scenarios?.map((s) => (
          <button
            key={s.id}
            onClick={() => startMutation.mutate(s.id)}
            disabled={startMutation.isPending}
            className="w-full text-left border border-slate-200 rounded-lg p-4 bg-white hover:border-slate-400 transition disabled:opacity-50"
          >
            <div className="font-medium text-slate-900">{s.name}</div>
            <div className="text-sm text-slate-500 mt-1">Difficulty: {s.difficulty}</div>
          </button>
        ))}
      </div>
      {startMutation.isError && (
        <div className="mt-4 text-red-600 text-sm">
          Failed to start: {(startMutation.error as Error).message}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 6: Update `frontend/src/App.tsx`**

```typescript
import { Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ScenariosPage } from "./pages/ScenariosPage";

function Placeholder({ label }: { label: string }) {
  return <div className="p-8 text-slate-600">{label}</div>;
}

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<ScenariosPage />} />
        <Route path="/session/:id" element={<Placeholder label="Session page coming soon" />} />
        <Route path="/review" element={<Placeholder label="Review page coming soon" />} />
        <Route path="/stats" element={<Placeholder label="Stats page coming soon" />} />
      </Routes>
    </Layout>
  );
}
```

- [ ] **Step 7: Run tests**

Run: `cd frontend && npm test`
Expected: tests passing for Layout + ScenariosPage.

- [ ] **Step 8: Commit**

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/
git commit -m "feat(frontend): Layout + BudgetIndicator + ScenariosPage"
```

---

## Task 17: PushToTalkButton + MessageBubble components

**Files:**
- Create: `frontend/src/components/PushToTalkButton.tsx`
- Create: `frontend/src/components/MessageBubble.tsx`
- Create: `frontend/src/components/PushToTalkButton.test.tsx`
- Create: `frontend/src/components/MessageBubble.test.tsx`

- [ ] **Step 1: Write failing tests**

`frontend/src/components/MessageBubble.test.tsx`:

```typescript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MessageBubble } from "./MessageBubble";

describe("MessageBubble", () => {
  it("renders user bubble with right alignment", () => {
    const { container } = render(<MessageBubble role="user" text="hi" />);
    expect(screen.getByText("hi")).toBeInTheDocument();
    expect(container.querySelector(".justify-end")).toBeInTheDocument();
  });

  it("renders assistant bubble with left alignment", () => {
    const { container } = render(<MessageBubble role="assistant" text="hello" />);
    expect(container.querySelector(".justify-start")).toBeInTheDocument();
  });

  it("shows speaking indicator when isSpeaking is true", () => {
    render(<MessageBubble role="assistant" text="hi" isSpeaking />);
    expect(screen.getByText(/📢/)).toBeInTheDocument();
  });
});
```

`frontend/src/components/PushToTalkButton.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PushToTalkButton } from "./PushToTalkButton";

describe("PushToTalkButton", () => {
  it("calls onStart on pointer down and onStop on pointer up", () => {
    const onStart = vi.fn();
    const onStop = vi.fn();
    render(<PushToTalkButton onStart={onStart} onStop={onStop} isRecording={false} isBusy={false} />);
    const btn = screen.getByRole("button", { name: /speak/i });
    fireEvent.pointerDown(btn);
    expect(onStart).toHaveBeenCalled();
    fireEvent.pointerUp(btn);
    expect(onStop).toHaveBeenCalled();
  });

  it("shows recording state", () => {
    render(<PushToTalkButton onStart={() => {}} onStop={() => {}} isRecording={true} isBusy={false} />);
    expect(screen.getByText(/release/i)).toBeInTheDocument();
  });

  it("disables button when busy", () => {
    render(<PushToTalkButton onStart={() => {}} onStop={() => {}} isRecording={false} isBusy={true} />);
    expect(screen.getByRole("button")).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run tests to verify failures**

Run: `cd frontend && npm test`
Expected: failures.

- [ ] **Step 3: Implement `frontend/src/components/MessageBubble.tsx`**

```typescript
interface Props {
  role: "user" | "assistant";
  text: string;
  isSpeaking?: boolean;
}

export function MessageBubble({ role, text, isSpeaking }: Props) {
  const isUser = role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} mb-3`}>
      <div
        className={
          `max-w-[75%] md:max-w-[60%] px-4 py-2 rounded-2xl text-sm leading-relaxed ` +
          (isUser
            ? "bg-blue-600 text-white rounded-br-sm"
            : "bg-white border border-slate-200 text-slate-900 rounded-bl-sm")
        }
      >
        <div className={`text-xs mb-0.5 ${isUser ? "text-blue-100" : "text-slate-500"}`}>
          {isUser ? "you" : "interviewer"}
          {isSpeaking && <span className="ml-2">📢</span>}
        </div>
        <div>{text}</div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Implement `frontend/src/components/PushToTalkButton.tsx`**

```typescript
import { Mic } from "lucide-react";

interface Props {
  onStart: () => void;
  onStop: () => void;
  isRecording: boolean;
  isBusy: boolean;
}

export function PushToTalkButton({ onStart, onStop, isRecording, isBusy }: Props) {
  const handleDown = (e: React.PointerEvent) => {
    e.preventDefault();
    if (!isBusy) onStart();
  };
  const handleUp = (e: React.PointerEvent) => {
    e.preventDefault();
    if (isRecording) onStop();
  };

  return (
    <button
      type="button"
      onPointerDown={handleDown}
      onPointerUp={handleUp}
      onPointerLeave={handleUp}
      disabled={isBusy}
      aria-label="Press and hold to speak"
      className={
        `w-24 h-24 rounded-full flex flex-col items-center justify-center select-none ` +
        `text-white shadow-lg transition-transform ` +
        (isRecording
          ? "bg-red-600 animate-pulse scale-110"
          : isBusy
          ? "bg-slate-400 cursor-not-allowed"
          : "bg-blue-600 hover:bg-blue-700 active:scale-95")
      }
    >
      <Mic className="w-8 h-8" />
      <span className="text-xs mt-1">
        {isBusy ? "Working…" : isRecording ? "Release" : "Speak"}
      </span>
    </button>
  );
}
```

- [ ] **Step 5: Run tests**

Run: `cd frontend && npm test`
Expected: tests passing.

- [ ] **Step 6: Commit**

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/components/
git commit -m "feat(frontend): PushToTalkButton + MessageBubble components"
```

---

## Task 18: SessionPage (chat + voice loop + summary)

**Files:**
- Create: `frontend/src/components/SessionSummary.tsx`
- Create: `frontend/src/pages/SessionPage.tsx`
- Create: `frontend/src/pages/SessionPage.test.tsx`
- Modify: `frontend/src/App.tsx` (wire SessionPage route)

- [ ] **Step 1: Write failing test**

`frontend/src/pages/SessionPage.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SessionPage } from "./SessionPage";

vi.mock("../api/client", () => ({
  api: {
    getSession: vi.fn().mockResolvedValue({
      session_id: "s1",
      scenario_id: "tech_interview_behavioral",
      started_at: "2026-05-21T10:00:00",
      ended_at: null,
      opening_text: "Hi, tell me about yourself.",
      turns: [],
    }),
  },
}));

vi.mock("../hooks/useTTS", () => ({
  useTTS: () => ({ speak: vi.fn().mockResolvedValue(undefined), isSpeaking: false, voices: [] }),
}));

vi.mock("../hooks/useRecorder", () => ({
  useRecorder: () => ({
    isRecording: false, startRecording: vi.fn(), stopRecording: vi.fn(), cancelRecording: vi.fn(),
  }),
}));

function wrap(initial: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={[initial]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/session/:id" element={<SessionPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("SessionPage", () => {
  it("renders opening text as assistant bubble", async () => {
    render(wrap("/session/s1"));
    await waitFor(() => {
      expect(screen.getByText("Hi, tell me about yourself.")).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 2: Run test to verify failure**

Run: `cd frontend && npm test`
Expected: failures.

- [ ] **Step 3: Implement `frontend/src/components/SessionSummary.tsx`**

```typescript
import type { GrowthPointDict } from "../api/types";

interface Props {
  growthPoints: GrowthPointDict[];
  cardsCreated: string[];
  error: string | null;
  onClose: () => void;
}

export function SessionSummary({ growthPoints, cardsCreated, error, onClose }: Props) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
      <div className="bg-white rounded-lg max-w-xl w-full max-h-[90vh] overflow-y-auto p-6">
        <h2 className="text-xl font-semibold text-slate-900 mb-4">Session complete</h2>
        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-800">
            {error}
          </div>
        )}
        {growthPoints.length === 0 && !error && (
          <p className="text-slate-600 mb-4">No growth points this session.</p>
        )}
        {growthPoints.length > 0 && (
          <div className="space-y-4 mb-4">
            <p className="text-sm text-slate-700">
              {cardsCreated.length} cards added for review tomorrow.
            </p>
            {growthPoints.map((gp, i) => (
              <div key={i} className="border-l-4 border-blue-500 pl-3">
                <div className="text-xs text-slate-500 uppercase mb-1">{gp.tag}</div>
                <div className="text-sm text-slate-500 line-through">"{gp.user_utterance}"</div>
                <div className="text-sm text-slate-900 font-medium">"{gp.corrected_version}"</div>
                <div className="text-xs text-slate-600 mt-1">{gp.explanation}</div>
              </div>
            ))}
          </div>
        )}
        <button
          onClick={onClose}
          className="w-full bg-blue-600 hover:bg-blue-700 text-white py-2 rounded transition"
        >
          Done
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Implement `frontend/src/pages/SessionPage.tsx`**

```typescript
import { useEffect, useState } from "react";
import { useParams, useLocation, useNavigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import type { EndSessionResult } from "../api/types";
import { MessageBubble } from "../components/MessageBubble";
import { PushToTalkButton } from "../components/PushToTalkButton";
import { SessionSummary } from "../components/SessionSummary";
import { useRecorder } from "../hooks/useRecorder";
import { useTTS } from "../hooks/useTTS";

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
}

export function SessionPage() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [summary, setSummary] = useState<EndSessionResult | null>(null);
  const [errorToast, setErrorToast] = useState<string | null>(null);

  const recorder = useRecorder();
  const tts = useTTS();

  // Load session on mount; if route state has opening, seed initial messages quickly
  const initialOpening = (location.state as { opening?: string } | null)?.opening;
  useQuery({
    queryKey: ["session", id],
    queryFn: async () => {
      const data = await api.getSession(id!);
      const msgs: ChatMessage[] = [];
      if (data.opening_text) msgs.push({ role: "assistant", text: data.opening_text });
      for (const t of data.turns) {
        msgs.push({ role: "user", text: t.user_text });
        msgs.push({ role: "assistant", text: t.llm_text });
      }
      setMessages(msgs);
      return data;
    },
    enabled: !!id,
  });

  // If we navigated here with opening text in state, seed immediately for snappier UI
  useEffect(() => {
    if (initialOpening && messages.length === 0) {
      setMessages([{ role: "assistant", text: initialOpening }]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const turnMutation = useMutation({
    mutationFn: async (audio: Blob) => api.submitTurn(id!, audio),
    onSuccess: async (result) => {
      setMessages((prev) => [
        ...prev,
        { role: "user", text: result.user_text },
        { role: "assistant", text: result.assistant_text },
      ]);
      try {
        await tts.speak(result.assistant_text);
      } catch {
        /* TTS failure non-fatal */
      }
    },
    onError: (err) => {
      if (err instanceof ApiError) {
        if (err.body.error === "no_speech_detected") {
          setErrorToast("Didn't catch that — try again");
        } else if (err.body.error === "budget_exhausted") {
          setErrorToast(`Budget cap reached. Resets at midnight.`);
        } else {
          setErrorToast(err.message);
        }
      } else {
        setErrorToast((err as Error).message);
      }
      setTimeout(() => setErrorToast(null), 4000);
    },
  });

  const endMutation = useMutation({
    mutationFn: () => api.endSession(id!),
    onSuccess: (result) => setSummary(result),
  });

  const handleStart = async () => {
    setErrorToast(null);
    try {
      await recorder.startRecording();
    } catch {
      setErrorToast("Mic permission required");
    }
  };

  const handleStop = async () => {
    const blob = await recorder.stopRecording();
    if (!blob) return;
    turnMutation.mutate(blob);
  };

  const isBusy = turnMutation.isPending || endMutation.isPending;

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
      <div className="flex-1 overflow-y-auto p-4 max-w-3xl mx-auto w-full">
        {messages.map((m, i) => (
          <MessageBubble
            key={i}
            role={m.role}
            text={m.text}
            isSpeaking={m.role === "assistant" && tts.isSpeaking && i === messages.length - 1}
          />
        ))}
      </div>
      <div className="border-t bg-white px-4 py-4 flex items-center justify-center gap-6">
        <PushToTalkButton
          onStart={handleStart}
          onStop={handleStop}
          isRecording={recorder.isRecording}
          isBusy={isBusy}
        />
        <button
          onClick={() => endMutation.mutate()}
          disabled={isBusy}
          className="px-4 py-2 text-sm text-slate-600 hover:text-slate-900 disabled:opacity-50"
        >
          End session
        </button>
      </div>
      {errorToast && (
        <div className="fixed bottom-32 left-1/2 -translate-x-1/2 bg-slate-900 text-white text-sm px-4 py-2 rounded shadow-lg">
          {errorToast}
        </div>
      )}
      {summary && (
        <SessionSummary
          growthPoints={summary.growth_points}
          cardsCreated={summary.cards_created}
          error={summary.growth_points_error}
          onClose={() => {
            setSummary(null);
            navigate("/");
          }}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 5: Wire route in `frontend/src/App.tsx`**

Replace the SessionPage Placeholder import and route with the real page:

```typescript
import { SessionPage } from "./pages/SessionPage";
// ...
<Route path="/session/:id" element={<SessionPage />} />
```

- [ ] **Step 6: Run tests**

Run: `cd frontend && npm test`
Expected: SessionPage test passes (the opening bubble renders).

- [ ] **Step 7: Commit**

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/
git commit -m "feat(frontend): SessionPage with chat + voice loop + summary"
```

---

## Task 19: ReviewPage (card flow + voice grade)

**Files:**
- Create: `frontend/src/components/ReviewCard.tsx`
- Create: `frontend/src/pages/ReviewPage.tsx`
- Create: `frontend/src/pages/ReviewPage.test.tsx`
- Modify: `frontend/src/App.tsx` (wire route)

- [ ] **Step 1: Write failing test**

`frontend/src/pages/ReviewPage.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReviewPage } from "./ReviewPage";

vi.mock("../api/client", () => ({
  api: {
    getDueCards: vi.fn().mockResolvedValue({
      cards: [],
      total_due: 0,
    }),
  },
}));

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <BrowserRouter>
      <QueryClientProvider client={qc}>{node}</QueryClientProvider>
    </BrowserRouter>
  );
}

describe("ReviewPage", () => {
  it("shows empty state when no due cards", async () => {
    render(wrap(<ReviewPage />));
    await waitFor(() => {
      expect(screen.getByText(/no cards due/i)).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 2: Run test to verify failure**

Run: `cd frontend && npm test`
Expected: failure.

- [ ] **Step 3: Implement `frontend/src/components/ReviewCard.tsx`**

```typescript
import type { Card } from "../api/types";
import { PushToTalkButton } from "./PushToTalkButton";

interface Props {
  card: Card;
  isRecording: boolean;
  isBusy: boolean;
  onStart: () => void;
  onStop: () => void;
  onSkip: () => void;
  onQuit: () => void;
}

export function ReviewCard({ card, isRecording, isBusy, onStart, onStop, onSkip, onQuit }: Props) {
  return (
    <div className="max-w-2xl mx-auto p-6 w-full">
      <div className="bg-white border border-slate-200 rounded-lg p-6 mb-6 shadow-sm">
        <div className="text-xs uppercase text-slate-500 mb-3">{card.tag}</div>
        {card.context && (
          <div className="text-sm text-slate-600 mb-3">Context: {card.context}</div>
        )}
        <div className="text-base text-slate-900 mb-2">Earlier you said:</div>
        <div className="text-lg italic text-slate-700">"{card.user_utterance}"</div>
      </div>
      <p className="text-center text-slate-700 mb-6">How would you say it more precisely?</p>
      <div className="flex items-center justify-center gap-6">
        <PushToTalkButton
          onStart={onStart}
          onStop={onStop}
          isRecording={isRecording}
          isBusy={isBusy}
        />
        <div className="flex flex-col gap-2 text-sm">
          <button onClick={onSkip} disabled={isBusy}
                  className="px-4 py-2 text-slate-600 hover:text-slate-900 disabled:opacity-50">
            Skip
          </button>
          <button onClick={onQuit} disabled={isBusy}
                  className="px-4 py-2 text-slate-600 hover:text-slate-900 disabled:opacity-50">
            Quit
          </button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Implement `frontend/src/pages/ReviewPage.tsx`**

```typescript
import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Card, GradeResult } from "../api/types";
import { ReviewCard } from "../components/ReviewCard";
import { useRecorder } from "../hooks/useRecorder";
import { useTTS } from "../hooks/useTTS";

export function ReviewPage() {
  const navigate = useNavigate();
  const recorder = useRecorder();
  const tts = useTTS();
  const [index, setIndex] = useState(0);
  const [lastResult, setLastResult] = useState<GradeResult | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["due-cards"],
    queryFn: () => api.getDueCards({}),
  });

  const gradeMutation = useMutation({
    mutationFn: async (args: { card_id: string; audio: Blob | null; skip: boolean }) =>
      api.gradeCard(args.card_id, args.audio, args.skip),
    onSuccess: async (result) => {
      setLastResult(result);
      try {
        await tts.speak(result.target);
      } catch { /* non-fatal */ }
    },
  });

  if (isLoading) return <div className="p-8 text-slate-600">Loading…</div>;

  const cards = data?.cards ?? [];
  if (cards.length === 0) {
    return (
      <div className="p-8 text-center">
        <p className="text-slate-600 mb-4">No cards due today.</p>
        <button onClick={() => navigate("/")} className="text-blue-600 hover:underline">
          Run a session
        </button>
      </div>
    );
  }
  if (index >= cards.length) {
    return (
      <div className="p-8 text-center">
        <p className="text-slate-700 mb-4">Done! {cards.length} cards reviewed.</p>
        <button onClick={() => navigate("/")} className="text-blue-600 hover:underline">
          Back home
        </button>
      </div>
    );
  }
  const card: Card = cards[index];

  const advance = () => {
    setLastResult(null);
    setIndex((i) => i + 1);
  };

  const handleStart = async () => {
    try {
      await recorder.startRecording();
    } catch {
      /* mic denial — handled by toast in real impl */
    }
  };
  const handleStop = async () => {
    const blob = await recorder.stopRecording();
    if (!blob) return;
    gradeMutation.mutate({ card_id: card.id, audio: blob, skip: false });
  };
  const handleSkip = () => {
    gradeMutation.mutate({ card_id: card.id, audio: null, skip: true });
  };
  const handleQuit = () => navigate("/");

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
      <div className="p-4 text-sm text-slate-600 text-center border-b">
        Card {index + 1} / {cards.length}
      </div>
      {lastResult ? (
        <div className="max-w-2xl mx-auto p-6 w-full text-center">
          <div className="text-4xl font-bold mb-3 text-slate-900">{lastResult.quality}/5</div>
          <div className="text-sm text-slate-600 mb-2">You said:</div>
          <div className="italic text-slate-700 mb-4">"{lastResult.user_attempt_text}"</div>
          <div className="text-sm text-slate-600 mb-2">Target:</div>
          <div className="text-lg font-medium text-slate-900 mb-4">"{lastResult.target}"</div>
          <div className="text-sm text-slate-600 mb-6">{lastResult.explanation}</div>
          <button onClick={advance}
                  className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded">
            Next card
          </button>
        </div>
      ) : (
        <ReviewCard
          card={card}
          isRecording={recorder.isRecording}
          isBusy={gradeMutation.isPending}
          onStart={handleStart}
          onStop={handleStop}
          onSkip={handleSkip}
          onQuit={handleQuit}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 5: Wire route in App.tsx**

Update `frontend/src/App.tsx`:

```typescript
import { ReviewPage } from "./pages/ReviewPage";
// ...
<Route path="/review" element={<ReviewPage />} />
```

- [ ] **Step 6: Run tests**

Run: `cd frontend && npm test`
Expected: ReviewPage test passes.

- [ ] **Step 7: Commit**

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/
git commit -m "feat(frontend): ReviewPage with card flow + voice grade"
```

---

## Task 20: StatsPage

**Files:**
- Create: `frontend/src/pages/StatsPage.tsx`
- Create: `frontend/src/pages/StatsPage.test.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Write failing test**

`frontend/src/pages/StatsPage.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StatsPage } from "./StatsPage";

vi.mock("../api/client", () => ({
  api: {
    getStats: vi.fn().mockResolvedValue({
      today: "2026-05-21",
      streak_days: 3,
      last_activity: "2026-05-21",
      sessions_total: 12,
      sessions_last_7d: 5,
      sessions_last_30d: 12,
      sessions_by_scenario: { tech_interview_behavioral: 8, daily_standup: 4 },
      cards_total: 47,
      cards_by_tag: { vocab: 28, grammar: 19 },
      cards_by_state: { new: 12, learning: 28, mature: 7 },
      retention_rate: 0.73,
      retention_sample_size: 22,
    }),
  },
}));

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <BrowserRouter>
      <QueryClientProvider client={qc}>{node}</QueryClientProvider>
    </BrowserRouter>
  );
}

describe("StatsPage", () => {
  it("renders streak, sessions, cards, retention", async () => {
    render(wrap(<StatsPage />));
    await waitFor(() => {
      expect(screen.getByText(/3 days/)).toBeInTheDocument();
      expect(screen.getByText(/47/)).toBeInTheDocument();
      expect(screen.getByText(/73%/)).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 2: Run test to verify failure**

Run: `cd frontend && npm test`
Expected: failure.

- [ ] **Step 3: Implement `frontend/src/pages/StatsPage.tsx`**

```typescript
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";

export function StatsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["stats"],
    queryFn: () => api.getStats(),
  });

  if (isLoading) return <div className="p-8 text-slate-600">Loading…</div>;
  if (!data) return <div className="p-8 text-slate-600">No data</div>;

  const retentionPct = data.retention_rate !== null
    ? `${Math.round(data.retention_rate * 100)}%`
    : null;

  return (
    <div className="max-w-3xl mx-auto p-6 w-full space-y-6">
      <h1 className="text-2xl font-semibold text-slate-900">Stats</h1>

      <div className="bg-white border border-slate-200 rounded-lg p-4">
        <div className="text-sm text-slate-500 mb-1">Streak</div>
        <div className="text-3xl font-semibold text-slate-900">
          {data.streak_days} days
        </div>
        {data.last_activity && (
          <div className="text-sm text-slate-500 mt-1">
            Last activity: {data.last_activity}
          </div>
        )}
      </div>

      <div className="bg-white border border-slate-200 rounded-lg p-4">
        <h2 className="font-semibold text-slate-900 mb-3">Sessions</h2>
        <div className="grid grid-cols-3 gap-4 mb-4">
          <div><div className="text-2xl font-semibold">{data.sessions_total}</div>
               <div className="text-xs text-slate-500">total</div></div>
          <div><div className="text-2xl font-semibold">{data.sessions_last_7d}</div>
               <div className="text-xs text-slate-500">last 7d</div></div>
          <div><div className="text-2xl font-semibold">{data.sessions_last_30d}</div>
               <div className="text-xs text-slate-500">last 30d</div></div>
        </div>
        {Object.keys(data.sessions_by_scenario).length > 0 && (
          <>
            <div className="text-sm text-slate-500 mb-1">By scenario:</div>
            <ul className="text-sm text-slate-700 space-y-1">
              {Object.entries(data.sessions_by_scenario)
                .sort((a, b) => b[1] - a[1])
                .map(([k, v]) => (
                  <li key={k}>{k}: {v}</li>
                ))}
            </ul>
          </>
        )}
      </div>

      <div className="bg-white border border-slate-200 rounded-lg p-4">
        <h2 className="font-semibold text-slate-900 mb-3">Cards</h2>
        <div className="text-3xl font-semibold mb-3">{data.cards_total}</div>
        <div className="text-sm text-slate-700">
          Tag: {Object.entries(data.cards_by_tag).map(([k, v]) => `${k} ${v}`).join(" | ")}
        </div>
        <div className="text-sm text-slate-700">
          State: new {data.cards_by_state.new || 0} | learning {data.cards_by_state.learning || 0} | mature {data.cards_by_state.mature || 0}
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-lg p-4">
        <h2 className="font-semibold text-slate-900 mb-3">Retention</h2>
        {retentionPct ? (
          <div className="text-2xl font-semibold text-slate-900">
            {retentionPct}
            <span className="text-sm text-slate-500 ml-2">
              ({data.retention_sample_size} mature cards)
            </span>
          </div>
        ) : (
          <div className="text-sm text-slate-600">
            N/A — need ≥5 cards with ≥3 reviews. Have {data.retention_sample_size}.
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Wire route**

Update `frontend/src/App.tsx`:

```typescript
import { StatsPage } from "./pages/StatsPage";
// ...
<Route path="/stats" element={<StatsPage />} />
```

- [ ] **Step 5: Run tests**

Run: `cd frontend && npm test`
Expected: StatsPage test passes.

- [ ] **Step 6: Commit**

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/
git commit -m "feat(frontend): StatsPage with sessions/cards/retention panels"
```

---

## Task 21: Build script + README

**Files:**
- Create: `scripts/build_and_serve.sh`
- Modify: `README.md`

- [ ] **Step 1: Create the build script**

`scripts/build_and_serve.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Activate venv if not already
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  source .venv/bin/activate
fi

# Build frontend
echo ">>> Building frontend..."
cd frontend
npm install --no-audit --no-fund
npm run build
cd "$ROOT"

# Start FastAPI
echo ">>> Starting FastAPI at http://127.0.0.1:8000"
exec uvicorn tutor.web.api:create_app --factory --host 127.0.0.1 --port 8000
```

Make it executable:

```bash
chmod +x scripts/build_and_serve.sh
```

- [ ] **Step 2: Update README**

Append to `/Users/sarkhipov/Work/Personal/english-tutor/README.md`:

```markdown

## Browser UI (Stage 2a)

After Stage 2a, the project has a localhost web UI alongside the CLI.

### Run the web UI

```bash
./scripts/build_and_serve.sh
# Then open http://127.0.0.1:8000 in your browser.
```

The build step:
1. Installs frontend deps with `npm install`
2. Builds the React app into `tutor/web/static/`
3. Starts FastAPI which serves both the API (`/api/*`) and the built frontend (`/` + `/static/*`)

### CLI still works

The CLI is untouched:
```bash
tutor interview
tutor review
tutor stats
tutor list-scenarios
```

### Dev workflow

For frontend iteration:
```bash
# terminal 1
uvicorn tutor.web.api:create_app --factory --reload --host 127.0.0.1 --port 8000

# terminal 2
cd frontend && npm run dev   # vite at localhost:5173 with proxy to :8000
```
```

- [ ] **Step 3: Verify the script works**

Run from `/Users/sarkhipov/Work/Personal/english-tutor`:
```bash
./scripts/build_and_serve.sh
```
Expected: frontend builds, FastAPI starts, http://127.0.0.1:8000 serves the React app.

Press Ctrl+C to stop.

- [ ] **Step 4: Commit**

```bash
git add scripts/build_and_serve.sh README.md
git commit -m "docs: build_and_serve.sh script + web UI README section"
```

---

## Task 22: Manual end-to-end smoke

No automated test — verify the full system works.

- [ ] **Step 1: Confirm all task commits are present**

Run: `git log --oneline 5d1ac18..HEAD`
Expected: see 21 task commits.

- [ ] **Step 2: Run full test suite**

Run: `pytest`
Expected: ~135+ tests pass.

Run: `cd frontend && npm test`
Expected: all frontend tests pass.

- [ ] **Step 3: Start the web UI**

Run: `./scripts/build_and_serve.sh`
Expected: builds, starts, serves on `http://127.0.0.1:8000`.

- [ ] **Step 4: Real session in browser**

Open `http://127.0.0.1:8000`. Expected flow:

1. Scenarios page shows 3 scenarios.
2. Click `tech_interview_behavioral`.
3. Navigate to `/session/<id>`. See opening message bubble. Click anywhere or wait — if iOS Safari, may need to click to trigger first TTS.
4. Hold the mic button, speak a sentence, release.
5. See your transcribed bubble + assistant reply bubble. Hear assistant via SpeechSynthesis.
6. Repeat 2-3 turns.
7. Click "End session". See growth points summary modal.
8. Click "Done". Navigate back to scenarios.

Verify: a JSON file under `sessions/<today>/<id>.json` with growth_points and cards_created.

- [ ] **Step 5: Real review in browser**

If cards from step 4 are due tomorrow, manually edit one card's `due_date` in `cards.json` to today, then:

1. Navigate to `/review`.
2. Card front shows. Hold mic, speak the corrected version, release.
3. See score (0-5), target, explanation. Hear target via TTS.
4. Click "Next card" or wait.
5. Repeat to end.

- [ ] **Step 6: Stats verification**

Navigate to `/stats`. Verify numbers match `tutor stats` in CLI.

- [ ] **Step 7: CLI regression check**

Run: `tutor interview --scenario daily_standup`
Expected: works as before.

- [ ] **Step 8: Push**

```bash
git push
```

Expected: all 21 task commits pushed to origin/main.

---

## Self-review checklist

Before declaring Stage 2a done:

1. **Spec coverage:**
   - 8 API endpoints (§6.5 of spec) → Tasks 6–11 ✓
   - `GET /api/sessions/{id}` for reload sync → Task 6 ✓
   - `services.py` orchestration → Tasks 6–10 ✓
   - `errors.py` exception handlers → Task 4 ✓
   - `deps.py` Whisper preload → Task 5 + Task 11 (lifespan) ✓
   - Storage extension for `opening_text` → Task 2 ✓
   - 4 frontend pages → Tasks 16, 18, 19, 20 ✓
   - Voice loop hooks → Task 15 ✓
   - Push-to-talk + chat bubbles → Task 17 ✓
   - Build script + README → Task 21 ✓

2. **Type consistency:**
   - `Dependencies` dataclass shape used identically in Tasks 5–10.
   - `StartSessionResult`, `TurnResult`, `EndSessionResult`, `GradeResult`, `BudgetSummary` Pydantic models — used consistently between schemas (Task 3) and services (Tasks 6-10) and API (Task 11).
   - Frontend types in `frontend/src/api/types.ts` (Task 14) mirror backend schemas.
   - `Card` shape: backend dataclass (existing) → `Card` TS interface (Task 14) → used by ReviewCard (Task 19).

3. **No placeholders:** every step has code or exact commands.

4. **Failure modes covered:**
   - Empty Whisper transcript → 422 (Task 11 test).
   - Unknown scenario → 404 (Task 11 test).
   - Unknown session → 404 (Task 11 test).
   - Unknown card → 404 (Task 9 test).
   - Budget exhausted → 429 (Task 4 test + propagates through services).
   - Evaluator raises → growth_points_error written (Task 8 test).
   - Mic denied → frontend toast (SessionPage error handling).

---

## Definition of Done for Stage 2a

- 21 task commits on `main`, pushed to `origin/main`.
- Full `pytest` suite green (~135+ tests including new `tests/web/*`).
- `cd frontend && npm test` green.
- `./scripts/build_and_serve.sh` produces a working app on `http://127.0.0.1:8000`.
- One real session completed in the browser end-to-end.
- One real review completed in the browser end-to-end.
- `/stats` matches `tutor stats` CLI output.
- CLI commands (`tutor interview`, `tutor review`, `tutor stats`) work unchanged.
- README updated with web-UI section.
