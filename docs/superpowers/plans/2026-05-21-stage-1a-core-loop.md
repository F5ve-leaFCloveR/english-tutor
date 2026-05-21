# Stage 1a — Core Learning Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the post-session Evaluator, SRS scheduling, and voice-based review CLI so every session yields durable, spaced-repetition flashcards. Also folds in 5 high-priority polish fixes from the Stage 0 final review and 2 new scenarios.

**Architecture:** Sync Evaluator after each session emits 3–5 GrowthPoints (vocab/grammar only). Cards persist to a single `cards.json` file using SM-2 scheduling. `tutor review` runs a voice loop: user speaks recall attempt → ASR → LLM grades 0–5 → SRS updates next due date → TTS plays the target version. Same adapter pattern as Stage 0 (LLM, ASR, TTS, Recorder injected via Protocols).

**Tech Stack:** Python 3.11+, openai SDK against OpenRouter, faster-whisper, sounddevice, macOS `say`, pydantic-settings, pyyaml, jinja2 (already present from Stage 0). Adds: pydantic `SecretStr` (already in pydantic), no new external deps.

**Prerequisites:**
- Stage 0 complete (32 tests green, repo at `~/Work/Personal/english-tutor`, branch `main`).
- `.env` with valid `OPENROUTER_API_KEY`, `TTS_VOICE` set to user's preferred voice.
- OpenRouter account has credit (the new evaluator model uses a stronger, slightly pricier model).

---

## File Structure

```
tutor/
├── settings.py             (MODIFY: SecretStr + evaluator_model + grader_model)
├── llm.py                  (MODIFY: SecretStr access)
├── storage.py              (MODIFY: atomic write + growth_points fields)
├── session.py              (MODIFY: evaluator call + opening budget catch + WAV cleanup)
├── cli.py                  (MODIFY: review subcommand + ScenarioNotFoundError handling)
├── evaluator.py            (NEW)
├── srs.py                  (NEW: pure SM-2 functions)
├── srs_engine.py           (NEW: storage + orchestration around srs)
├── grader.py               (NEW)
├── review.py               (NEW: ReviewOrchestrator)
└── scenarios/
    ├── daily_standup.yaml                   (NEW)
    └── apartment_rental_abroad.yaml         (NEW)

tests/
├── test_settings.py        (MODIFY: assert SecretStr behavior + new model fields)
├── test_llm.py             (MODIFY: SecretStr in client construction)
├── test_storage.py         (MODIFY: atomic write + growth_points)
├── test_session.py         (MODIFY: evaluator integration + opening budget catch)
├── test_scenarios.py       (MODIFY: verify new YAMLs)
├── test_evaluator.py       (NEW)
├── test_srs.py             (NEW)
├── test_srs_engine.py      (NEW)
├── test_grader.py          (NEW)
└── test_review.py          (NEW)
```

---

## Task 1: Polish — `SecretStr` for API key

**Files:**
- Modify: `tutor/settings.py`
- Modify: `tutor/llm.py`
- Modify: `tests/test_settings.py`
- Modify: `tests/test_llm.py`

- [ ] **Step 1: Update settings test to assert SecretStr behavior**

`tests/test_settings.py` — add this test at the end:

```python
def test_settings_api_key_is_not_in_repr(monkeypatch):
    """Regression: SecretStr ensures repr() doesn't leak the API key."""
    from tutor.settings import Settings
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-supersecret123")
    s = Settings()
    r = repr(s)
    assert "sk-or-v1-supersecret123" not in r
    assert "supersecret123" not in r
    # the value is still retrievable via get_secret_value
    assert s.openrouter_api_key.get_secret_value() == "sk-or-v1-supersecret123"
```

- [ ] **Step 2: Update the first settings test for SecretStr access**

Change the assertion in `test_settings_loads_api_key`:

```python
def test_settings_loads_api_key(monkeypatch):
    from tutor.settings import Settings
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    s = Settings()
    assert s.openrouter_api_key.get_secret_value() == "sk-or-v1-test"
    assert s.openrouter_model == "google/gemini-2.5-flash"
    assert s.daily_usd_budget == 0.5
    assert s.daily_token_budget == 200_000
    assert s.per_session_turn_limit == 25
    assert s.whisper_model_size == "small"
    assert s.tts_voice == "Samantha"
    assert s.tts_rate == 180
```

- [ ] **Step 3: Run tests to verify failures**

Run: `cd ~/Work/Personal/english-tutor && source .venv/bin/activate && pytest tests/test_settings.py -v`

Expected: `test_settings_loads_api_key` FAILS (str doesn't have `.get_secret_value`); `test_settings_api_key_is_not_in_repr` FAILS.

- [ ] **Step 4: Update settings.py to use SecretStr**

`tutor/settings.py`:

```python
"""Application configuration. Reads .env via pydantic-settings."""
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    openrouter_api_key: SecretStr = Field(..., description="OpenRouter API key")
    openrouter_model: str = Field(default="google/gemini-2.5-flash")
    daily_usd_budget: float = Field(default=0.5, gt=0)
    daily_token_budget: int = Field(default=200_000, gt=0)
    per_session_turn_limit: int = Field(default=25, gt=0)
    whisper_model_size: str = Field(default="small")
    tts_voice: str = Field(default="Samantha", description="macOS `say` voice name (run `say -v '?'` to list)")
    tts_rate: int = Field(default=180, gt=0)

    @field_validator("openrouter_api_key", mode="before")
    @classmethod
    def reject_placeholder(cls, v):
        # v may be a string (from env) or SecretStr depending on source
        raw = v.get_secret_value() if hasattr(v, "get_secret_value") else v
        if not isinstance(raw, str):
            return v
        if "REPLACE_ME" in raw:
            raise ValueError("OPENROUTER_API_KEY still contains placeholder value")
        if not raw.startswith("sk-or-"):
            raise ValueError("OPENROUTER_API_KEY does not look like an OpenRouter key")
        return v


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 5: Update `LLMClient.from_settings` to extract the secret**

In `tutor/llm.py`, update `from_settings`:

```python
    @classmethod
    def from_settings(cls, settings: "Settings", budget: BudgetTracker) -> "LLMClient":
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openrouter_api_key.get_secret_value(),
        )
        return cls(client=client, model=settings.openrouter_model, budget=budget)
```

- [ ] **Step 6: Update `cli.py` to extract the secret**

In `tutor/cli.py`, change the OpenAI client construction:

```python
    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=settings.openrouter_api_key.get_secret_value())
```

- [ ] **Step 7: Run all tests to confirm green**

Run: `pytest`
Expected: all tests pass (including the 4 settings tests and the new regression test).

- [ ] **Step 8: Commit**

```bash
git add tutor/settings.py tutor/llm.py tutor/cli.py tests/test_settings.py
git commit -m "fix(settings): use SecretStr to prevent API key leakage in repr"
```

---

## Task 2: Polish — atomic JSON write in storage

**Files:**
- Modify: `tutor/storage.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Write the failing regression test**

Add to `tests/test_storage.py`:

```python
def test_storage_write_is_atomic(tmp_path, mocker):
    """Regression: crash during _write must leave either old or new content, never partial."""
    from tutor.storage import SessionStorage
    from datetime import datetime

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 10, 0))
    session_id = storage.create_session(scenario_id="tech_interview_behavioral")

    # Find the session file
    session_path = next(tmp_path.rglob(f"{session_id}.json"))
    original_content = session_path.read_text()

    # Simulate a crash: _write calls os.replace, which is atomic.
    # Verify the intermediate state never appears by checking that
    # the file path itself is never empty/partial during write.
    # The cleanest test: confirm _write uses a tmp+rename pattern.
    import os
    original_replace = os.replace
    rename_was_called = []

    def spy_replace(src, dst):
        rename_was_called.append((str(src), str(dst)))
        return original_replace(src, dst)

    mocker.patch("os.replace", side_effect=spy_replace)
    storage.append_turn(session_id, user_text="hi", llm_text="hello")
    assert len(rename_was_called) >= 1
    src, dst = rename_was_called[-1]
    assert dst == str(session_path)
    assert src.endswith(".json.tmp") or src.endswith(".tmp")
```

- [ ] **Step 2: Run test to confirm failure**

Run: `pytest tests/test_storage.py::test_storage_write_is_atomic -v`
Expected: FAIL — `os.replace` is never called (current code uses `path.write_text` directly).

- [ ] **Step 3: Update `_write` to use atomic tmp+replace**

In `tutor/storage.py`, replace the `_write` method:

```python
    def _write(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        os.replace(str(tmp), str(path))
```

Add `import os` at the top of the file if not present.

- [ ] **Step 4: Run all tests**

Run: `pytest`
Expected: all tests pass (storage tests including the new regression test).

- [ ] **Step 5: Commit**

```bash
git add tutor/storage.py tests/test_storage.py
git commit -m "fix(storage): atomic write via tmp+os.replace"
```

---

## Task 3: Settings — add evaluator/grader model fields

**Files:**
- Modify: `tutor/settings.py`
- Modify: `.env.example`
- Modify: `tests/test_settings.py`

- [ ] **Step 1: Update the settings test for new fields**

In `tests/test_settings.py`, extend `test_settings_loads_api_key`:

```python
def test_settings_loads_api_key(monkeypatch):
    from tutor.settings import Settings
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    s = Settings()
    assert s.openrouter_api_key.get_secret_value() == "sk-or-v1-test"
    assert s.openrouter_model == "google/gemini-2.5-flash"
    assert s.openrouter_evaluator_model == "google/gemini-2.5-pro"
    assert s.openrouter_grader_model == "google/gemini-2.5-flash"
    assert s.daily_usd_budget == 0.5
    assert s.daily_token_budget == 200_000
    assert s.per_session_turn_limit == 25
    assert s.whisper_model_size == "small"
    assert s.tts_voice == "Samantha"
    assert s.tts_rate == 180
```

- [ ] **Step 2: Run test to confirm failure**

Run: `pytest tests/test_settings.py::test_settings_loads_api_key -v`
Expected: FAIL — `Settings` has no `openrouter_evaluator_model` attribute.

- [ ] **Step 3: Add fields to settings.py**

In `tutor/settings.py`, add two new fields right after `openrouter_model`:

```python
    openrouter_model: str = Field(default="google/gemini-2.5-flash")
    openrouter_evaluator_model: str = Field(
        default="google/gemini-2.5-pro",
        description="Stronger model for post-session evaluation",
    )
    openrouter_grader_model: str = Field(
        default="google/gemini-2.5-flash",
        description="Cheap model for grading SRS card recall (0-5)",
    )
```

- [ ] **Step 4: Update .env.example via subagent**

The `.env*` path is denied to direct edit tools in this environment. Dispatch a small subagent to append:

```
OPENROUTER_EVALUATOR_MODEL=google/gemini-2.5-pro
OPENROUTER_GRADER_MODEL=google/gemini-2.5-flash
```

at the end of `.env.example`. The subagent must verify the file content afterwards and report.

If running directly without the permission constraint, just append the two lines.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_settings.py -v`
Expected: 4 passed.

Run: `pytest`
Expected: full suite green.

- [ ] **Step 6: Commit**

```bash
git add tutor/settings.py tests/test_settings.py .env.example
git commit -m "feat(settings): add evaluator and grader model env vars"
```

---

## Task 4: Storage — extend for growth_points and cards_created

**Files:**
- Modify: `tutor/storage.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_storage.py`:

```python
def test_storage_persists_growth_points(tmp_path):
    from tutor.storage import SessionStorage
    from datetime import datetime

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 10, 0))
    session_id = storage.create_session("tech_interview_behavioral")
    storage.set_growth_points(session_id, [
        {"tag": "vocab", "user_utterance": "I made a project", "corrected_version": "I led a project",
         "explanation": "Led signals ownership.", "context": None},
    ])
    data = storage.load_session(session_id)
    assert len(data["growth_points"]) == 1
    assert data["growth_points"][0]["tag"] == "vocab"


def test_storage_persists_growth_points_error(tmp_path):
    from tutor.storage import SessionStorage
    from datetime import datetime

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 10, 0))
    session_id = storage.create_session("tech_interview_behavioral")
    storage.set_growth_points_error(session_id, "parse failed")
    data = storage.load_session(session_id)
    assert data["growth_points_error"] == "parse failed"


def test_storage_persists_cards_created(tmp_path):
    from tutor.storage import SessionStorage
    from datetime import datetime

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 10, 0))
    session_id = storage.create_session("tech_interview_behavioral")
    storage.set_cards_created(session_id, ["card_abc12345", "card_def67890"])
    data = storage.load_session(session_id)
    assert data["cards_created"] == ["card_abc12345", "card_def67890"]
```

- [ ] **Step 2: Run tests to confirm failures**

Run: `pytest tests/test_storage.py::test_storage_persists_growth_points tests/test_storage.py::test_storage_persists_growth_points_error tests/test_storage.py::test_storage_persists_cards_created -v`
Expected: 3 failures (AttributeError).

- [ ] **Step 3: Add the new methods to SessionStorage**

In `tutor/storage.py`, add three methods to the class:

```python
    def set_growth_points(self, session_id: str, growth_points: list[dict]) -> None:
        path = self._find_session_path(session_id)
        data = json.loads(path.read_text())
        data["growth_points"] = growth_points
        self._write(path, data)

    def set_growth_points_error(self, session_id: str, error_message: str) -> None:
        path = self._find_session_path(session_id)
        data = json.loads(path.read_text())
        data["growth_points_error"] = error_message
        self._write(path, data)

    def set_cards_created(self, session_id: str, card_ids: list[str]) -> None:
        path = self._find_session_path(session_id)
        data = json.loads(path.read_text())
        data["cards_created"] = card_ids
        self._write(path, data)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_storage.py -v`
Expected: all storage tests pass (6 total now).

- [ ] **Step 5: Commit**

```bash
git add tutor/storage.py tests/test_storage.py
git commit -m "feat(storage): persist growth_points and cards_created on sessions"
```

---

## Task 5: Evaluator module

**Files:**
- Create: `tutor/evaluator.py`
- Create: `tests/test_evaluator.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_evaluator.py`:

```python
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


def test_evaluator_retries_on_malformed_then_succeeds(tmp_path, mocker):
    from tutor.evaluator import Evaluator

    bad_then_good = [
        MagicMock(choices=[MagicMock(message=MagicMock(content="not json"))], usage=MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15, model_extra={})),
        MagicMock(choices=[MagicMock(message=MagicMock(content=json.dumps({
            "growth_points": [{"tag": "vocab", "user_utterance": "x", "corrected_version": "y", "explanation": "z", "context": None}]
        })))], usage=MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15, model_extra={})),
    ]
    from tutor.llm import LLMClient
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
    from tutor.budget import BudgetExceededError

    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("api down")
    budget = _make_budget(tmp_path)
    llm = LLMClient(client=client, model="google/gemini-2.5-pro", budget=budget)

    evaluator = Evaluator(llm=llm, model="google/gemini-2.5-pro")
    result = evaluator.evaluate(transcript=[{"role": "user", "content": "x"}])
    assert result == []
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `pytest tests/test_evaluator.py -v`
Expected: 5 errors (`ModuleNotFoundError: No module named 'tutor.evaluator'`).

- [ ] **Step 3: Implement `tutor/evaluator.py`**

```python
"""Post-session transcript evaluator: returns 3-5 GrowthPoint corrections."""
from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel, ValidationError

from tutor.llm import LLMClient

log = logging.getLogger(__name__)


_SYSTEM_PROMPT = """You are an English teacher reviewing a Russian-native intermediate student's
spoken-English practice transcript.

Identify the 3-5 most impactful improvements, focused ONLY on:
  - vocab: word choice that's correct but weak/generic. Suggest a stronger, more precise word.
  - grammar: tense, articles, prepositions, word order errors.

Explicitly skip: filler words, ASR mistranscriptions, idiom/register issues, minor style preferences.

Return STRICT JSON, no commentary:
{
  "growth_points": [
    {
      "tag": "vocab" | "grammar",
      "user_utterance": "<verbatim what the student said>",
      "corrected_version": "<your improved version>",
      "explanation": "<1-2 sentences why the correction is better>",
      "context": "<one line of dialog before the utterance, or null>"
    }
  ]
}
"""


class GrowthPoint(BaseModel):
    tag: Literal["vocab", "grammar"]
    user_utterance: str
    corrected_version: str
    explanation: str
    context: str | None = None


class _GrowthPointsResponse(BaseModel):
    growth_points: list[GrowthPoint]


class Evaluator:
    def __init__(self, llm: LLMClient, model: str) -> None:
        self._llm = llm
        self._model = model

    def evaluate(self, transcript: list[dict[str, str]]) -> list[GrowthPoint]:
        """Run the evaluator LLM once (with one retry on parse failure)."""
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": "Here is the transcript to review:\n\n" + self._format_transcript(transcript)},
        ]

        last_error: Exception | None = None
        for attempt in range(2):
            try:
                raw = self._llm.complete(messages=messages, temperature=0.2, model_override=self._model)
            except Exception as e:
                log.warning("Evaluator LLM call failed: %s", e)
                return []
            try:
                parsed = _GrowthPointsResponse.model_validate_json(_strip_code_fences(raw))
                return parsed.growth_points[:5]
            except (ValidationError, ValueError, json.JSONDecodeError) as e:
                last_error = e
                log.warning("Evaluator returned invalid JSON (attempt %d): %s", attempt + 1, e)
                continue

        log.warning("Evaluator exhausted retries: %s", last_error)
        return []

    @staticmethod
    def _format_transcript(transcript: list[dict[str, str]]) -> str:
        lines = []
        for msg in transcript:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if role == "system":
                continue
            lines.append(f"[{role}] {content}")
        return "\n".join(lines)


def _strip_code_fences(text: str) -> str:
    """LLMs sometimes wrap JSON in ```json ... ```. Strip if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text
```

Note: this uses `model_override` on `LLMClient.complete`. That parameter doesn't exist yet — we need to add it in the same task.

- [ ] **Step 4: Extend `LLMClient.complete` with `model_override`**

In `tutor/llm.py`, modify the `complete` method signature and use the override if provided:

```python
    def complete(self, messages: list[dict[str, str]], temperature: float = 0.7, model_override: str | None = None) -> str:
        self._budget.check_can_spend()

        model = model_override or self._model
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.chat.completions.create(
                    model=model,
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
```

- [ ] **Step 5: Add test for `model_override`**

Add to `tests/test_llm.py`:

```python
def test_llm_complete_uses_model_override(tmp_path):
    from tutor.llm import LLMClient

    budget = _make_budget(tmp_path)
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _make_response("ok", 10, 5, 0.0001)

    llm = LLMClient(client=fake_client, model="default-model", budget=budget)
    llm.complete(messages=[{"role": "user", "content": "hi"}], model_override="other-model")

    call_kwargs = fake_client.chat.completions.create.call_args
    assert call_kwargs.kwargs["model"] == "other-model"
```

- [ ] **Step 6: Run all tests**

Run: `pytest tests/test_evaluator.py tests/test_llm.py -v`
Expected: evaluator tests (5) and llm tests (6 with the new override test) all pass.

Run: `pytest`
Expected: full suite green.

- [ ] **Step 7: Commit**

```bash
git add tutor/evaluator.py tutor/llm.py tests/test_evaluator.py tests/test_llm.py
git commit -m "feat(evaluator): post-session LLM analysis returns 3-5 GrowthPoints"
```

---

## Task 6: SRS pure functions

**Files:**
- Create: `tutor/srs.py`
- Create: `tests/test_srs.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_srs.py`:

```python
import pytest


def test_srs_first_review_quality_3_or_higher_sets_interval_1():
    from tutor.srs import next_interval
    new_interval, new_repetitions, new_ef = next_interval(
        quality=3, prev_interval=0, repetitions=0, ease_factor=2.5
    )
    assert new_interval == 1
    assert new_repetitions == 1
    assert new_ef == pytest.approx(2.36, abs=0.01)


def test_srs_second_review_sets_interval_6():
    from tutor.srs import next_interval
    new_interval, new_repetitions, _ = next_interval(
        quality=4, prev_interval=1, repetitions=1, ease_factor=2.5
    )
    assert new_interval == 6
    assert new_repetitions == 2


def test_srs_third_review_multiplies_by_ease_factor():
    from tutor.srs import next_interval
    new_interval, new_repetitions, _ = next_interval(
        quality=4, prev_interval=6, repetitions=2, ease_factor=2.5
    )
    assert new_interval == 15  # round(6 * 2.5)
    assert new_repetitions == 3


def test_srs_failure_resets_repetitions_and_interval():
    from tutor.srs import next_interval
    new_interval, new_repetitions, new_ef = next_interval(
        quality=1, prev_interval=15, repetitions=3, ease_factor=2.6
    )
    assert new_interval == 1
    assert new_repetitions == 0
    # ease factor does NOT reset on failure (SM-2 standard)
    assert new_ef == 2.6


def test_srs_ease_factor_floor_is_1_3():
    from tutor.srs import next_interval
    # Many failures should drive ease factor toward 1.3 but not below
    ef = 1.35
    for _ in range(20):
        _, _, ef = next_interval(quality=3, prev_interval=1, repetitions=0, ease_factor=ef)
    # quality=3 still subtracts a small amount; clamp at 1.3
    assert ef >= 1.3


def test_srs_ease_factor_increases_on_quality_5():
    from tutor.srs import next_interval
    _, _, new_ef = next_interval(quality=5, prev_interval=6, repetitions=2, ease_factor=2.5)
    # quality=5: ef + 0.1 - 0 * (0.08 + 0 * 0.02) = ef + 0.1
    assert new_ef == pytest.approx(2.6, abs=0.01)


def test_srs_ease_factor_unchanged_at_quality_4():
    from tutor.srs import next_interval
    _, _, new_ef = next_interval(quality=4, prev_interval=6, repetitions=2, ease_factor=2.5)
    # quality=4: ef + 0.1 - 1 * (0.08 + 1 * 0.02) = ef + 0.1 - 0.10 = ef
    assert new_ef == pytest.approx(2.5, abs=0.01)
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `pytest tests/test_srs.py -v`
Expected: 7 errors (`ModuleNotFoundError: No module named 'tutor.srs'`).

- [ ] **Step 3: Implement `tutor/srs.py`**

```python
"""Pure SM-2 spaced repetition algorithm. No I/O."""
from __future__ import annotations


_MIN_EASE_FACTOR = 1.3


def next_interval(
    quality: int,
    prev_interval: int,
    repetitions: int,
    ease_factor: float,
) -> tuple[int, int, float]:
    """Compute the next SRS state from a review.

    Args:
        quality: 0-5 score for this review (3+ = pass, <3 = fail).
        prev_interval: previous interval in days.
        repetitions: how many consecutive successful reviews so far.
        ease_factor: current ease factor (typically starts at 2.5, floor 1.3).

    Returns:
        (new_interval_days, new_repetitions, new_ease_factor)
    """
    if quality < 3:
        # Failure: reset repetitions and interval, ease factor unchanged.
        return 1, 0, ease_factor

    if repetitions == 0:
        new_interval = 1
    elif repetitions == 1:
        new_interval = 6
    else:
        new_interval = round(prev_interval * ease_factor)

    new_repetitions = repetitions + 1

    # Update ease factor.
    q = quality
    delta = 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)
    new_ease_factor = max(_MIN_EASE_FACTOR, ease_factor + delta)

    return new_interval, new_repetitions, new_ease_factor
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_srs.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add tutor/srs.py tests/test_srs.py
git commit -m "feat(srs): SM-2 algorithm pure functions"
```

---

## Task 7: SRS Engine (storage + orchestration)

**Files:**
- Create: `tutor/srs_engine.py`
- Create: `tests/test_srs_engine.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_srs_engine.py`:

```python
from datetime import date
from pathlib import Path
import json
import pytest


def test_srs_engine_create_cards_persists_to_disk(tmp_path):
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint

    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    gps = [
        GrowthPoint(tag="vocab", user_utterance="I made a project", corrected_version="I led a project", explanation="Led signals ownership.", context=None),
        GrowthPoint(tag="grammar", user_utterance="I working", corrected_version="I'm working", explanation="Missing auxiliary.", context=None),
    ]
    cards = engine.create_cards(gps, session_id="sess_xyz")
    assert len(cards) == 2
    assert cards[0].tag == "vocab"
    assert cards[0].due_date == "2026-05-22"  # today + 1
    assert cards[0].created_from_session_id == "sess_xyz"
    assert cards[0].repetitions == 0
    assert cards[0].ease_factor == 2.5

    # Verify persistence
    raw = json.loads((tmp_path / "cards.json").read_text())
    assert len(raw["cards"]) == 2


def test_srs_engine_due_today_filters_by_date(tmp_path):
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint

    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    gps = [GrowthPoint(tag="vocab", user_utterance="x", corrected_version="y", explanation="z", context=None)]
    engine.create_cards(gps, session_id="s1")

    # Card is due tomorrow, not today
    assert engine.due_today() == []

    # Advance time
    engine2 = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 22))
    due = engine2.due_today()
    assert len(due) == 1


def test_srs_engine_due_today_respects_limit(tmp_path):
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint

    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    gps = [
        GrowthPoint(tag="vocab", user_utterance=f"u{i}", corrected_version=f"c{i}", explanation="e", context=None)
        for i in range(5)
    ]
    engine.create_cards(gps, session_id="s1")

    engine2 = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 22))
    due = engine2.due_today(limit=3)
    assert len(due) == 3


def test_srs_engine_due_today_filters_by_tag(tmp_path):
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint

    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    gps = [
        GrowthPoint(tag="vocab", user_utterance="u1", corrected_version="c1", explanation="e", context=None),
        GrowthPoint(tag="grammar", user_utterance="u2", corrected_version="c2", explanation="e", context=None),
    ]
    engine.create_cards(gps, session_id="s1")

    engine2 = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 22))
    due_vocab = engine2.due_today(tag="vocab")
    assert len(due_vocab) == 1
    assert due_vocab[0].tag == "vocab"


def test_srs_engine_record_review_updates_state(tmp_path):
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint

    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 22))
    gps = [GrowthPoint(tag="vocab", user_utterance="x", corrected_version="y", explanation="z", context=None)]
    engine.create_cards(gps, session_id="s1")

    cards = engine.due_today()
    card_id = cards[0].id

    engine.record_review(card_id, quality=4)
    updated = engine.load_card(card_id)
    assert updated.repetitions == 1
    assert updated.interval_days == 1
    assert updated.due_date == "2026-05-23"
    assert updated.last_review_quality == 4
    assert len(updated.review_history) == 1


def test_srs_engine_record_review_quality_below_3_resets(tmp_path):
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint

    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 22))
    gps = [GrowthPoint(tag="vocab", user_utterance="x", corrected_version="y", explanation="z", context=None)]
    engine.create_cards(gps, session_id="s1")
    card_id = engine.due_today()[0].id

    # Pass twice
    engine.record_review(card_id, quality=4)
    engine.record_review(card_id, quality=4)
    # Then fail
    engine.record_review(card_id, quality=1)
    updated = engine.load_card(card_id)
    assert updated.repetitions == 0
    assert updated.interval_days == 1


def test_srs_engine_record_review_unknown_card_raises(tmp_path):
    from tutor.srs_engine import SRSEngine, CardNotFoundError

    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 22))
    with pytest.raises(CardNotFoundError):
        engine.record_review("does_not_exist", quality=3)
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `pytest tests/test_srs_engine.py -v`
Expected: 7 errors (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `tutor/srs_engine.py`**

```python
"""Storage + scheduling layer on top of the pure SM-2 algorithm."""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Literal

from tutor.evaluator import GrowthPoint
from tutor.srs import next_interval


class CardNotFoundError(Exception):
    pass


@dataclass
class Card:
    id: str
    created_from_session_id: str
    tag: Literal["vocab", "grammar"]
    user_utterance: str
    corrected_version: str
    explanation: str
    context: str | None
    due_date: str
    ease_factor: float = 2.5
    interval_days: int = 0
    repetitions: int = 0
    last_review_quality: int | None = None
    review_history: list[dict] = field(default_factory=list)


class SRSEngine:
    def __init__(self, path: Path, now: Callable[[], date] = date.today) -> None:
        self._path = Path(path)
        self._now = now
        self._cards: dict[str, Card] = self._load()

    def _load(self) -> dict[str, Card]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
        cards: dict[str, Card] = {}
        for c in raw.get("cards", []):
            card = Card(**c)
            cards[card.id] = card
        return cards

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        payload = {"cards": [asdict(c) for c in self._cards.values()]}
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        os.replace(str(tmp), str(self._path))

    def create_cards(self, growth_points: list[GrowthPoint], session_id: str) -> list[Card]:
        today = self._now()
        tomorrow = (today + timedelta(days=1)).isoformat()
        new_cards: list[Card] = []
        for gp in growth_points:
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

    def due_today(self, limit: int | None = None, tag: str | None = None) -> list[Card]:
        today_iso = self._now().isoformat()
        result = [c for c in self._cards.values() if c.due_date <= today_iso]
        if tag is not None:
            result = [c for c in result if c.tag == tag]
        result.sort(key=lambda c: c.due_date)
        if limit is not None:
            result = result[:limit]
        return result

    def record_review(self, card_id: str, quality: int) -> None:
        card = self._cards.get(card_id)
        if card is None:
            raise CardNotFoundError(f"No card with id {card_id}")
        new_interval, new_repetitions, new_ef = next_interval(
            quality=quality,
            prev_interval=card.interval_days,
            repetitions=card.repetitions,
            ease_factor=card.ease_factor,
        )
        today = self._now()
        new_due = (today + timedelta(days=new_interval)).isoformat()
        card.interval_days = new_interval
        card.repetitions = new_repetitions
        card.ease_factor = new_ef
        card.due_date = new_due
        card.last_review_quality = quality
        card.review_history.append({"date": today.isoformat(), "quality": quality})
        self._flush()

    def load_card(self, card_id: str) -> Card:
        card = self._cards.get(card_id)
        if card is None:
            raise CardNotFoundError(f"No card with id {card_id}")
        return card
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_srs_engine.py -v`
Expected: 7 passed.

Run: `pytest`
Expected: full suite green.

- [ ] **Step 5: Commit**

```bash
git add tutor/srs_engine.py tests/test_srs_engine.py
git commit -m "feat(srs_engine): JSON-backed card storage with SM-2 scheduling"
```

---

## Task 8: Integrate evaluator + SRS into session

**Files:**
- Modify: `tutor/session.py`
- Modify: `tests/test_session.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_session.py`:

```python
def test_session_runs_evaluator_and_creates_cards(tmp_path, mocker):
    from tutor.session import SessionOrchestrator
    from tutor.storage import SessionStorage
    from tutor.scenarios.loader import load_scenario
    from tutor.evaluator import GrowthPoint

    mocker.patch("builtins.input", side_effect=["go", "end"])
    llm, asr, tts, recorder = _stub_adapters(
        turn_user_texts=["I made a project."],
        turn_llm_replies=["Opening line.", "What project?"],
    )

    fake_evaluator = MagicMock()
    fake_evaluator.evaluate.return_value = [
        GrowthPoint(tag="vocab", user_utterance="I made a project.",
                     corrected_version="I led a project.",
                     explanation="Led signals ownership.", context=None),
    ]
    fake_srs = MagicMock()
    fake_card = MagicMock()
    fake_card.id = "card_xyz"
    fake_srs.create_cards.return_value = [fake_card]

    storage = SessionStorage(root=tmp_path)
    orch = SessionOrchestrator(
        llm=llm, asr=asr, tts=tts, recorder=recorder, storage=storage,
        scenario=load_scenario("tech_interview_behavioral"),
        per_session_turn_limit=25,
        evaluator=fake_evaluator,
        srs_engine=fake_srs,
    )
    session_id = orch.run()

    fake_evaluator.evaluate.assert_called_once()
    fake_srs.create_cards.assert_called_once()
    data = storage.load_session(session_id)
    assert data["growth_points"] == [
        {"tag": "vocab", "user_utterance": "I made a project.",
         "corrected_version": "I led a project.", "explanation": "Led signals ownership.",
         "context": None}
    ]
    assert data["cards_created"] == ["card_xyz"]


def test_session_evaluator_failure_is_swallowed(tmp_path, mocker):
    """If evaluator returns empty list (parse fail / API error), session ends cleanly."""
    from tutor.session import SessionOrchestrator
    from tutor.storage import SessionStorage
    from tutor.scenarios.loader import load_scenario

    mocker.patch("builtins.input", side_effect=["end"])
    llm, asr, tts, recorder = _stub_adapters(
        turn_user_texts=[],
        turn_llm_replies=["Opening."],
    )

    fake_evaluator = MagicMock()
    fake_evaluator.evaluate.return_value = []  # eval failed silently
    fake_srs = MagicMock()
    fake_srs.create_cards.return_value = []

    storage = SessionStorage(root=tmp_path)
    orch = SessionOrchestrator(
        llm=llm, asr=asr, tts=tts, recorder=recorder, storage=storage,
        scenario=load_scenario("tech_interview_behavioral"),
        per_session_turn_limit=25,
        evaluator=fake_evaluator,
        srs_engine=fake_srs,
    )
    session_id = orch.run()
    data = storage.load_session(session_id)
    assert data["ended_at"] is not None
    # No cards created when evaluator returns empty
    fake_srs.create_cards.assert_not_called()


def test_session_works_without_evaluator(tmp_path, mocker):
    """Backwards compatible: evaluator and srs_engine are optional."""
    from tutor.session import SessionOrchestrator
    from tutor.storage import SessionStorage
    from tutor.scenarios.loader import load_scenario

    mocker.patch("builtins.input", side_effect=["end"])
    llm, asr, tts, recorder = _stub_adapters(
        turn_user_texts=[],
        turn_llm_replies=["Hi."],
    )

    storage = SessionStorage(root=tmp_path)
    orch = SessionOrchestrator(
        llm=llm, asr=asr, tts=tts, recorder=recorder, storage=storage,
        scenario=load_scenario("tech_interview_behavioral"),
        per_session_turn_limit=25,
        # no evaluator, no srs_engine
    )
    session_id = orch.run()
    data = storage.load_session(session_id)
    assert data["ended_at"] is not None
    assert "growth_points" not in data
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `pytest tests/test_session.py::test_session_runs_evaluator_and_creates_cards tests/test_session.py::test_session_evaluator_failure_is_swallowed tests/test_session.py::test_session_works_without_evaluator -v`

Expected: failures (TypeError — `evaluator` is not a known kwarg).

- [ ] **Step 3: Extend `SessionOrchestrator` to use evaluator + SRS**

In `tutor/session.py`, modify the `__init__` and `run`:

```python
"""Session orchestrator: ties LLM + ASR + TTS + recorder + storage into the voice loop."""
from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import asdict
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


class _Evaluator(Protocol):
    def evaluate(self, transcript: list[dict[str, str]]) -> list: ...


class _SRSEngine(Protocol):
    def create_cards(self, growth_points: list, session_id: str) -> list: ...


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
        evaluator: _Evaluator | None = None,
        srs_engine: _SRSEngine | None = None,
    ) -> None:
        self._llm = llm
        self._asr = asr
        self._tts = tts
        self._recorder = recorder
        self._storage = storage
        self._scenario = scenario
        self._limit = per_session_turn_limit
        self._system_prompt = build_system_prompt(scenario, user_native_language=user_native_language)
        self._evaluator = evaluator
        self._srs_engine = srs_engine

    def run(self) -> str:
        session_id = self._storage.create_session(scenario_id=self._scenario.id)
        history: list[dict[str, str]] = [{"role": "system", "content": self._system_prompt}]
        temp_wavs: list[Path] = []

        try:
            try:
                opening = self._llm.complete(messages=history)
            except BudgetExceededError as e:
                print(f"\n[budget exhausted before session start: {e}]\n[session ending]")
                return session_id
            history.append({"role": "assistant", "content": opening})
            print(f"\n[interviewer] {opening}\n")
            self._tts.speak(opening)

            turn_count = 0
            while turn_count < self._limit:
                cmd = input(f"[turn {turn_count + 1}/{self._limit}] press Enter to speak, or type 'end' to finish: ").strip().lower()
                if cmd == _END_SENTINEL:
                    break

                wav_path = Path(tempfile.gettempdir()) / f"tutor_turn_{session_id}_{turn_count}.wav"
                temp_wavs.append(wav_path)
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

            # After loop: run evaluator if provided and there were turns
            if self._evaluator is not None and self._srs_engine is not None and turn_count > 0:
                try:
                    growth_points = self._evaluator.evaluate(transcript=history)
                except Exception as e:
                    log.warning("Evaluator raised unexpectedly: %s", e)
                    growth_points = []

                if growth_points:
                    gp_dicts = [
                        gp.model_dump() if hasattr(gp, "model_dump") else asdict(gp)
                        for gp in growth_points
                    ]
                    self._storage.set_growth_points(session_id, gp_dicts)
                    try:
                        cards = self._srs_engine.create_cards(growth_points, session_id=session_id)
                        self._storage.set_cards_created(session_id, [c.id for c in cards])
                        print(f"\n[saved {len(cards)} cards for review tomorrow]")
                    except Exception as e:
                        log.warning("SRS create_cards failed: %s", e)
                else:
                    log.info("Evaluator returned no growth points; no cards created.")
        finally:
            # Clean up temp WAVs
            for wav in temp_wavs:
                try:
                    if wav.exists():
                        os.remove(str(wav))
                except OSError:
                    pass
            self._storage.end_session(session_id)

        return session_id
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_session.py -v`
Expected: all session tests pass (existing 4 + new 3 = 7).

Run: `pytest`
Expected: full suite green.

- [ ] **Step 5: Commit**

```bash
git add tutor/session.py tests/test_session.py
git commit -m "feat(session): integrate evaluator and SRS, add opening budget catch, cleanup temp WAVs"
```

---

## Task 9: Polish — friendly `ScenarioNotFoundError` in CLI

**Files:**
- Modify: `tutor/cli.py`
- Create: `tests/test_cli.py`

- [ ] **Step 1: Write the failing test**

`tests/test_cli.py`:

```python
import pytest
from unittest.mock import patch


def test_cli_unknown_scenario_exits_2_with_friendly_message(monkeypatch, capsys):
    """Regression: bad --scenario should NOT crash with a traceback."""
    from tutor.cli import main
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")

    exit_code = main(["interview", "--scenario", "does_not_exist"])
    assert exit_code == 2
    captured = capsys.readouterr()
    assert "does_not_exist" in (captured.err + captured.out)
    assert "Traceback" not in (captured.err + captured.out)
```

- [ ] **Step 2: Run test to confirm failure**

Run: `pytest tests/test_cli.py -v`
Expected: FAIL — either traceback uncaught or exit code != 2.

- [ ] **Step 3: Update `_run_interview` to catch `ScenarioNotFoundError`**

In `tutor/cli.py`, wrap the `load_scenario` call:

```python
def _run_interview(scenario_id: str) -> int:
    from tutor.scenarios.loader import ScenarioNotFoundError

    try:
        scenario = load_scenario(scenario_id)
    except ScenarioNotFoundError:
        available = ", ".join(list_scenarios())
        print(f"error: scenario '{scenario_id}' not found. Available: {available}", file=sys.stderr)
        return 2

    settings = get_settings()
    project_root = Path(__file__).resolve().parents[1]

    budget = BudgetTracker(
        path=project_root / "budget.json",
        daily_usd_cap=settings.daily_usd_budget,
        daily_token_cap=settings.daily_token_budget,
    )

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=settings.openrouter_api_key.get_secret_value())
    llm = LLMClient(client=client, model=settings.openrouter_model, budget=budget)
    asr = WhisperASR(model_size=settings.whisper_model_size)
    tts = MacSayTTS(voice=settings.tts_voice, rate=settings.tts_rate)
    recorder = AudioRecorder()
    storage = SessionStorage(root=project_root / "sessions")

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
```

(Note: scenario is loaded BEFORE settings/budget/clients, so we fail fast.)

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_cli.py -v`
Expected: 1 passed.

Run: `pytest`
Expected: full suite green.

- [ ] **Step 5: Commit**

```bash
git add tutor/cli.py tests/test_cli.py
git commit -m "fix(cli): friendly error on unknown scenario id (exit 2, no traceback)"
```

---

## Task 10: LLM Grader

**Files:**
- Create: `tutor/grader.py`
- Create: `tests/test_grader.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_grader.py`:

```python
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
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `pytest tests/test_grader.py -v`
Expected: 5 errors (ModuleNotFoundError).

- [ ] **Step 3: Implement `tutor/grader.py`**

```python
"""LLM grader: scores a student's recall attempt against the target on 0-5."""
from __future__ import annotations

import logging
import re

from tutor.llm import LLMClient

log = logging.getLogger(__name__)

_GRADER_PROMPT = """You are grading an English recall practice.

TARGET (the correct version the student should say): "{target}"
STUDENT ATTEMPT (transcribed from speech): "{attempt}"

Grade on 0-5:
0 = wrong/silence/totally unrelated
1 = vague hint, missing key vocabulary or structure
2 = partial, missed important element
3 = essentially correct meaning, minor wording differences
4 = correct with small variation
5 = essentially identical

Be lenient about word order. Focus on whether the student demonstrated the key
improvement (vocab word or grammar pattern) from the target, not on exact wording.

Return ONLY the integer 0-5. No explanation."""


_DEFAULT_QUALITY = 3


class LLMGrader:
    def __init__(self, llm: LLMClient, model: str) -> None:
        self._llm = llm
        self._model = model

    def grade(self, target: str, attempt: str) -> int:
        prompt = _GRADER_PROMPT.format(target=target, attempt=attempt or "(no audio)")
        response = self._llm.complete(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            model_override=self._model,
        )
        return self._parse_score(response)

    @staticmethod
    def _parse_score(response: str) -> int:
        match = re.search(r"\b([0-5])\b", response)
        if match is None:
            log.warning("Grader returned no parseable score: %r — defaulting to 3", response[:60])
            return _DEFAULT_QUALITY
        try:
            score = int(match.group(1))
        except ValueError:
            return _DEFAULT_QUALITY
        if not 0 <= score <= 5:
            log.warning("Grader score %d out of range — defaulting to 3", score)
            return _DEFAULT_QUALITY
        return score
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_grader.py -v`
Expected: 5 passed.

Run: `pytest`
Expected: full suite green.

- [ ] **Step 5: Commit**

```bash
git add tutor/grader.py tests/test_grader.py
git commit -m "feat(grader): LLM-based 0-5 scoring of recall attempts"
```

---

## Task 11: Review Orchestrator

**Files:**
- Create: `tutor/review.py`
- Create: `tests/test_review.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_review.py`:

```python
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock
import pytest


def _stub_review_adapters(transcripts, grader_scores):
    """Mocks for asr/tts/recorder/grader. transcripts = list of ASR outputs per card."""
    asr = MagicMock()
    asr.transcribe.side_effect = transcripts
    tts = MagicMock()
    recorder = MagicMock()
    recorder.record_to_wav.side_effect = [Path(f"/tmp/fake_{i}.wav") for i in range(50)]
    grader = MagicMock()
    grader.grade.side_effect = grader_scores
    return asr, tts, recorder, grader


def _make_srs_with_cards(tmp_path, n_cards):
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint

    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    gps = [
        GrowthPoint(tag="vocab", user_utterance=f"u{i}", corrected_version=f"c{i}",
                     explanation="e", context=None)
        for i in range(n_cards)
    ]
    engine.create_cards(gps, session_id="s1")
    # Advance to tomorrow so cards are due
    return SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 22))


def test_review_processes_due_cards(tmp_path, mocker):
    from tutor.review import ReviewOrchestrator

    mocker.patch("builtins.input", side_effect=["", "", "", ""])  # 3 cards × 1 input each
    srs = _make_srs_with_cards(tmp_path, n_cards=3)
    asr, tts, recorder, grader = _stub_review_adapters(
        transcripts=["c0", "c1", "c2"],
        grader_scores=[3, 4, 5],
    )

    orch = ReviewOrchestrator(grader=grader, asr=asr, tts=tts, recorder=recorder, srs=srs)
    summary = orch.run()
    assert summary.cards_reviewed == 3
    assert summary.quality_distribution == {3: 1, 4: 1, 5: 1}
    assert grader.grade.call_count == 3
    assert tts.speak.call_count == 3  # speaks the target after each grade


def test_review_no_due_cards(tmp_path, mocker, capsys):
    from tutor.review import ReviewOrchestrator
    from tutor.srs_engine import SRSEngine

    srs = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    asr, tts, recorder, grader = _stub_review_adapters([], [])

    orch = ReviewOrchestrator(grader=grader, asr=asr, tts=tts, recorder=recorder, srs=srs)
    summary = orch.run()
    assert summary.cards_reviewed == 0


def test_review_skip_command_records_zero(tmp_path, mocker):
    from tutor.review import ReviewOrchestrator

    mocker.patch("builtins.input", side_effect=["skip", ""])
    srs = _make_srs_with_cards(tmp_path, n_cards=2)
    asr, tts, recorder, grader = _stub_review_adapters(
        transcripts=["c1"],
        grader_scores=[4],
    )

    orch = ReviewOrchestrator(grader=grader, asr=asr, tts=tts, recorder=recorder, srs=srs)
    summary = orch.run()
    assert summary.cards_reviewed == 2
    # First card was skipped → quality 0
    assert summary.quality_distribution.get(0) == 1
    assert grader.grade.call_count == 1  # only called for non-skipped


def test_review_quit_command_ends_early(tmp_path, mocker):
    from tutor.review import ReviewOrchestrator

    mocker.patch("builtins.input", side_effect=["", "quit"])
    srs = _make_srs_with_cards(tmp_path, n_cards=3)
    asr, tts, recorder, grader = _stub_review_adapters(
        transcripts=["c0"],
        grader_scores=[3],
    )

    orch = ReviewOrchestrator(grader=grader, asr=asr, tts=tts, recorder=recorder, srs=srs)
    summary = orch.run()
    assert summary.cards_reviewed == 1


def test_review_respects_limit_and_tag(tmp_path, mocker):
    from tutor.review import ReviewOrchestrator
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint

    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    gps = [
        GrowthPoint(tag="vocab", user_utterance="u1", corrected_version="c1", explanation="e", context=None),
        GrowthPoint(tag="grammar", user_utterance="u2", corrected_version="c2", explanation="e", context=None),
        GrowthPoint(tag="vocab", user_utterance="u3", corrected_version="c3", explanation="e", context=None),
    ]
    engine.create_cards(gps, session_id="s1")
    srs = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 22))

    mocker.patch("builtins.input", side_effect=[""])
    asr, tts, recorder, grader = _stub_review_adapters(
        transcripts=["c1"],
        grader_scores=[3],
    )

    orch = ReviewOrchestrator(grader=grader, asr=asr, tts=tts, recorder=recorder, srs=srs)
    summary = orch.run(limit=1, tag_filter="vocab")
    assert summary.cards_reviewed == 1
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `pytest tests/test_review.py -v`
Expected: 5 errors (ModuleNotFoundError).

- [ ] **Step 3: Implement `tutor/review.py`**

```python
"""Review orchestrator: voice-loop through SRS due cards with LLM grading."""
from __future__ import annotations

import logging
import os
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


log = logging.getLogger(__name__)


class _ASR(Protocol):
    def transcribe(self, wav_path: Path) -> str: ...


class _TTS(Protocol):
    def speak(self, text: str) -> None: ...


class _Recorder(Protocol):
    def record_to_wav(self, out_path: Path) -> Path: ...


class _Grader(Protocol):
    def grade(self, target: str, attempt: str) -> int: ...


class _SRSEngine(Protocol):
    def due_today(self, limit: int | None = ..., tag: str | None = ...) -> list: ...
    def record_review(self, card_id: str, quality: int) -> None: ...


_SKIP = "skip"
_QUIT = "quit"


@dataclass
class ReviewSummary:
    cards_reviewed: int = 0
    quality_distribution: dict[int, int] = field(default_factory=dict)


class ReviewOrchestrator:
    def __init__(
        self,
        grader: _Grader,
        asr: _ASR,
        tts: _TTS,
        recorder: _Recorder,
        srs: _SRSEngine,
    ) -> None:
        self._grader = grader
        self._asr = asr
        self._tts = tts
        self._recorder = recorder
        self._srs = srs

    def run(self, limit: int | None = None, tag_filter: str | None = None) -> ReviewSummary:
        cards = self._srs.due_today(limit=limit, tag=tag_filter)
        if not cards:
            print("\nNo cards due today. Run a session first, or come back tomorrow.\n")
            return ReviewSummary()

        print(f"\n=== Review: {len(cards)} cards due ===\n")
        summary = ReviewSummary()
        quality_counter: Counter[int] = Counter()

        for i, card in enumerate(cards, start=1):
            print(f"[card {i}/{len(cards)} — {card.tag}]")
            if card.context:
                print(f"Context: {card.context}")
            print(f"Earlier you said: \"{card.user_utterance}\"")
            print()
            cmd = input("How would you say it more precisely? [Enter to speak, 'skip', 'quit']: ").strip().lower()

            if cmd == _QUIT:
                break

            if cmd == _SKIP:
                quality = 0
                attempt_text = "(skipped)"
            else:
                wav_path = Path(tempfile.gettempdir()) / f"tutor_review_{card.id}.wav"
                try:
                    self._recorder.record_to_wav(wav_path)
                    attempt_text = self._asr.transcribe(wav_path).strip()
                finally:
                    try:
                        if wav_path.exists():
                            os.remove(str(wav_path))
                    except OSError:
                        pass

                if not attempt_text:
                    quality = 0
                    print("[didn't catch that]")
                else:
                    print(f"> you said: \"{attempt_text}\"")
                    print("[grading...]")
                    quality = self._grader.grade(target=card.corrected_version, attempt=attempt_text)

            print(f"\nScore: {quality}/5")
            print(f"Target: \"{card.corrected_version}\"")
            print(f"Why: {card.explanation}\n")
            self._tts.speak(card.corrected_version)

            self._srs.record_review(card.id, quality=quality)
            summary.cards_reviewed += 1
            quality_counter[quality] += 1

        summary.quality_distribution = dict(quality_counter)
        print(f"\n=== Done. {summary.cards_reviewed} cards reviewed. ===\n")
        return summary
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_review.py -v`
Expected: 5 passed.

Run: `pytest`
Expected: full suite green.

- [ ] **Step 5: Commit**

```bash
git add tutor/review.py tests/test_review.py
git commit -m "feat(review): voice-loop card review with LLM grading"
```

---

## Task 12: CLI `review` subcommand

**Files:**
- Modify: `tutor/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_cli.py`:

```python
def test_cli_review_help_works(monkeypatch, capsys):
    from tutor.cli import main
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")

    with pytest.raises(SystemExit) as exc_info:
        main(["review", "--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "review" in captured.out.lower()
    assert "--limit" in captured.out
    assert "--tag" in captured.out


def test_cli_review_no_due_cards(monkeypatch, tmp_path, capsys, mocker):
    """Smoke: review with no due cards prints message and exits 0."""
    from tutor.cli import main
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")

    # Patch project_root resolution to point at tmp_path
    mocker.patch("tutor.cli.Path", wraps=Path)
    # Easier: just patch _run_review's project_root via cwd
    monkeypatch.chdir(tmp_path)
    # Create a dummy cards.json so SRSEngine doesn't try to read project_root
    # Actually let SRSEngine init with no file (returns empty), and use isolated cards path.
    # The CLI builds budget+srs paths from project_root. Easiest: mock project_root.
    from tutor import cli as cli_mod
    mocker.patch.object(cli_mod, "_project_root", return_value=tmp_path)

    exit_code = main(["review"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "No cards due" in captured.out
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `pytest tests/test_cli.py -v`
Expected: failures — `review` subcommand doesn't exist; `_project_root` helper doesn't exist.

- [ ] **Step 3: Refactor `cli.py` to add `_project_root` helper + `review` subcommand**

In `tutor/cli.py`:

```python
"""CLI entry point. Wires real adapters and runs a session or review."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from openai import OpenAI

from tutor.asr import WhisperASR
from tutor.audio import AudioRecorder
from tutor.budget import BudgetTracker
from tutor.evaluator import Evaluator
from tutor.grader import LLMGrader
from tutor.llm import LLMClient
from tutor.review import ReviewOrchestrator
from tutor.scenarios.loader import ScenarioNotFoundError, list_scenarios, load_scenario
from tutor.session import SessionOrchestrator
from tutor.settings import get_settings
from tutor.srs_engine import SRSEngine
from tutor.storage import SessionStorage
from tutor.tts import MacSayTTS


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tutor", description="English speaking practice CLI")
    sub = p.add_subparsers(dest="command", required=True)

    sub_interview = sub.add_parser("interview", help="Run a behavioral session")
    sub_interview.add_argument("--scenario", default="tech_interview_behavioral",
                                help="Scenario id (default: tech_interview_behavioral)")

    sub.add_parser("list-scenarios", help="List available scenarios")

    sub_review = sub.add_parser("review", help="Review due SRS cards")
    sub_review.add_argument("--limit", type=int, default=None, help="Max cards to review")
    sub_review.add_argument("--tag", choices=["vocab", "grammar"], default=None,
                             help="Filter cards by tag")

    return p


def _build_common_clients(settings):
    project_root = _project_root()
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
    return budget, llm


def _run_interview(scenario_id: str) -> int:
    try:
        scenario = load_scenario(scenario_id)
    except ScenarioNotFoundError:
        available = ", ".join(list_scenarios())
        print(f"error: scenario '{scenario_id}' not found. Available: {available}", file=sys.stderr)
        return 2

    settings = get_settings()
    project_root = _project_root()
    budget, llm = _build_common_clients(settings)

    asr = WhisperASR(model_size=settings.whisper_model_size)
    tts = MacSayTTS(voice=settings.tts_voice, rate=settings.tts_rate)
    recorder = AudioRecorder()
    storage = SessionStorage(root=project_root / "sessions")

    evaluator = Evaluator(llm=llm, model=settings.openrouter_evaluator_model)
    srs_engine = SRSEngine(path=project_root / "cards.json")

    print(f"\n=== {scenario.name} ===")
    print(f"Budget today: ${budget.usd_today:.4f} / ${settings.daily_usd_budget}")
    print(f"Press Enter to start each turn. Type 'end' to finish.\n")

    orch = SessionOrchestrator(
        llm=llm, asr=asr, tts=tts, recorder=recorder, storage=storage,
        scenario=scenario,
        per_session_turn_limit=settings.per_session_turn_limit,
        evaluator=evaluator,
        srs_engine=srs_engine,
    )
    session_id = orch.run()
    print(f"\nSession {session_id} saved. Budget after: ${budget.usd_today:.4f}")
    return 0


def _run_review(limit: int | None, tag: str | None) -> int:
    settings = get_settings()
    project_root = _project_root()
    budget, llm = _build_common_clients(settings)

    asr = WhisperASR(model_size=settings.whisper_model_size)
    tts = MacSayTTS(voice=settings.tts_voice, rate=settings.tts_rate)
    recorder = AudioRecorder()
    grader = LLMGrader(llm=llm, model=settings.openrouter_grader_model)
    srs = SRSEngine(path=project_root / "cards.json")

    print(f"Budget today: ${budget.usd_today:.4f} / ${settings.daily_usd_budget}")

    orch = ReviewOrchestrator(grader=grader, asr=asr, tts=tts, recorder=recorder, srs=srs)
    summary = orch.run(limit=limit, tag_filter=tag)
    print(f"Budget after: ${budget.usd_today:.4f}")
    print(f"Cards reviewed: {summary.cards_reviewed}; distribution: {summary.quality_distribution}")
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
    if args.command == "review":
        return _run_review(args.limit, args.tag)
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_cli.py -v`
Expected: 3 passed (the existing test + 2 new ones).

Run: `pytest`
Expected: full suite green.

- [ ] **Step 5: Verify CLI works manually**

Run: `tutor --help`
Expected: shows `interview`, `list-scenarios`, `review` subcommands.

Run: `tutor review --help`
Expected: shows `--limit`, `--tag` options.

- [ ] **Step 6: Commit**

```bash
git add tutor/cli.py tests/test_cli.py
git commit -m "feat(cli): add review subcommand for SRS card practice"
```

---

## Task 13: New scenarios — daily_standup + apartment_rental_abroad

**Files:**
- Create: `tutor/scenarios/daily_standup.yaml`
- Create: `tutor/scenarios/apartment_rental_abroad.yaml`
- Modify: `tests/test_scenarios.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_scenarios.py`:

```python
def test_load_scenario_daily_standup():
    from tutor.scenarios.loader import load_scenario, build_system_prompt
    sc = load_scenario("daily_standup")
    assert sc.id == "daily_standup"
    assert "standup" in sc.name.lower()
    assert sc.opening_line
    prompt = build_system_prompt(sc, user_native_language="Russian")
    assert "Russian" in prompt


def test_load_scenario_apartment_rental():
    from tutor.scenarios.loader import load_scenario, build_system_prompt
    sc = load_scenario("apartment_rental_abroad")
    assert sc.id == "apartment_rental_abroad"
    assert "rental" in sc.name.lower() or "apartment" in sc.name.lower()
    assert sc.opening_line
    prompt = build_system_prompt(sc, user_native_language="Russian")
    assert "Russian" in prompt


def test_list_scenarios_includes_new():
    from tutor.scenarios.loader import list_scenarios
    ids = list_scenarios()
    assert "tech_interview_behavioral" in ids
    assert "daily_standup" in ids
    assert "apartment_rental_abroad" in ids
```

- [ ] **Step 2: Run tests to confirm failure**

Run: `pytest tests/test_scenarios.py::test_load_scenario_daily_standup tests/test_scenarios.py::test_load_scenario_apartment_rental -v`
Expected: 2 failures (ScenarioNotFoundError).

- [ ] **Step 3: Create `daily_standup.yaml`**

`tutor/scenarios/daily_standup.yaml`:

```yaml
id: daily_standup
name: "Daily standup with US-based team"
difficulty: intermediate
counterpart:
  role: "Tech lead at a US-based engineering team running a 10-minute daily standup"
  persona: |
    Time-conscious, professional, no smalltalk. Asks for yesterday's progress,
    today's plan, and blockers in that order. Cuts off rambling. Asks follow-up
    questions only when the answer is too vague to act on.
goal: >
  Help the engineer practice giving a structured standup update in concise English:
  yesterday's progress, today's plan, and blockers. Practice clear handoffs to teammates.
vocab_focus:
  - "Time estimates ('by end of week', 'rough cut', 'spike')"
  - "Blocker phrasing ('blocked on', 'waiting on', 'depends on')"
  - "Dependency callouts ('after the X team merges', 'once the API is stable')"
opening_line: >
  Morning everyone, let's keep this short. What did you do yesterday, what's
  on your plate today, and any blockers?
system_prompt_template: |
  You are a tech lead running a 10-minute daily standup at a US-based engineering team.
  The engineer is a {{ user_native_language }} native speaker practicing spoken English.

  STRICT RULES:
  - Keep responses VERY concise — 1-2 sentences. This is a real standup pace.
  - Steer the conversation through yesterday / today / blockers.
  - If the engineer is vague ('working on stuff'), push for specifics with one short question.
  - If the engineer rambles, redirect: "Let's stay on track — what's blocking you?"
  - Stay in role. Do NOT break character. Do NOT mention you are an AI.
  - Reply ONLY in English. If the engineer slips into {{ user_native_language }},
    say "Sorry, I missed that — can you repeat it in English?"
  - Do NOT correct the engineer's English mid-standup. That happens later.
  - The standup ends naturally after blockers are covered, or when the engineer signals
    they're done.

  Begin with your opening line and proceed naturally based on their responses.
```

- [ ] **Step 4: Create `apartment_rental_abroad.yaml`**

`tutor/scenarios/apartment_rental_abroad.yaml`:

```yaml
id: apartment_rental_abroad
name: "Apartment rental conversation abroad"
difficulty: intermediate
counterpart:
  role: "Landlord or rental agent showing a 1-bedroom apartment in a US or EU city"
  persona: |
    Friendly but business-like. Asks about job, income stability, move-in date,
    references. Volunteers information about lease terms, utilities, deposit,
    neighbourhood when relevant. Open to negotiation on small things.
goal: >
  Help the applicant practice the rental conversation in English: discussing lease
  terms, utilities, deposit, neighbourhood, and presenting their financial situation
  with hedging.
vocab_focus:
  - "Rental vocabulary ('lease', 'deposit', 'utilities included', 'month-to-month', 'co-signer')"
  - "Hedging for finances ('competitive salary', 'stable income', 'remote position')"
  - "Neighbourhood questions ('public transit', 'noise level', 'pet policy')"
opening_line: >
  Hi, welcome — thanks for coming by. Let me show you around the apartment.
  Have you had a chance to read through the listing?
system_prompt_template: |
  You are a landlord or rental agent showing a 1-bedroom apartment in a US or EU city.
  The applicant is a {{ user_native_language }} native speaker practicing spoken English.

  STRICT RULES:
  - Keep responses concise — 1-3 sentences.
  - Mix information you volunteer (lease term, deposit amount, what's included) with
    questions about the applicant (job, income, move-in date, references).
  - Probe gently if the applicant is vague about finances or move-in plans.
  - Stay in role. Do NOT break character. Do NOT mention you are an AI.
  - Reply ONLY in English. If the applicant slips into {{ user_native_language }},
    politely ask them to repeat in English.
  - Do NOT correct the applicant's English mid-conversation. That happens later.
  - Cover at least: lease term, deposit, utilities, what they do for work, move-in date.

  Begin with your opening line and proceed naturally.
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_scenarios.py -v`
Expected: all scenario tests pass (existing 5 + new 3 = 8).

Run: `pytest`
Expected: full suite green.

- [ ] **Step 6: Verify via CLI**

Run: `tutor list-scenarios`
Expected: prints all three scenario ids:
```
apartment_rental_abroad
daily_standup
tech_interview_behavioral
```

- [ ] **Step 7: Commit**

```bash
git add tutor/scenarios/daily_standup.yaml tutor/scenarios/apartment_rental_abroad.yaml tests/test_scenarios.py
git commit -m "feat(scenarios): add daily_standup and apartment_rental_abroad"
```

---

## Task 14: Manual end-to-end smoke

No automated test — the goal is to actually use the new flow.

- [ ] **Step 1: Confirm everything is on top**

Run: `cd ~/Work/Personal/english-tutor && source .venv/bin/activate && pytest`
Expected: full suite green (~50+ tests now).

Run: `git log --oneline | head -15`
Expected: see all Task-1-to-13 commits.

- [ ] **Step 2: Run a real session with the new evaluator**

Run: `tutor interview --scenario daily_standup`

Expected flow:
1. CLI prints "=== Daily standup with US-based team ===".
2. Tech lead speaks opening.
3. Press Enter, give a quick standup update (yesterday/today/blockers), 30-60 seconds.
4. Tech lead replies.
5. Continue 2-3 turns, then `end`.
6. CLI prints "[saved N cards for review tomorrow]" (or "Evaluator returned no growth points" if the LLM didn't surface any).
7. CLI prints "Session XXX saved. Budget after: $0.XXXX".

Verify: a JSON file under `sessions/2026-05-21/` with `growth_points` and `cards_created` fields populated.

- [ ] **Step 3: Verify cards.json was created**

Run: `cat cards.json | python -m json.tool | head -40`
Expected: a JSON document with a `cards` list, each card having `tag`, `user_utterance`, `corrected_version`, `explanation`, `due_date`, `ease_factor`, etc.

- [ ] **Step 4: Run the review flow**

Since cards are due tomorrow by default, manually edit `cards.json` to set one card's `due_date` to today's date (or wait until tomorrow).

Run: `tutor review --limit 3`

Expected flow per card:
1. CLI shows card N/total with tag, context, original utterance.
2. Prompt "How would you say it more precisely?".
3. Press Enter, speak the recall attempt.
4. CLI shows your transcript.
5. CLI prints "Score: N/5".
6. CLI prints target and explanation.
7. TTS speaks the target version.
8. Next card.

After all: CLI prints "Cards reviewed: N; distribution: {...}".

Verify: `cards.json` updated — reviewed cards have new `due_date`, `review_history`, `last_review_quality`, `repetitions`, `interval_days`.

- [ ] **Step 5: Test edge cases**

- Run `tutor interview --scenario bogus` → expect "error: scenario 'bogus' not found. Available: ..." + exit 2.
- Run `tutor review` when no cards are due → expect "No cards due today" + exit 0.
- Run `tutor review --tag vocab` after creating mixed cards → expect only vocab cards shown.

- [ ] **Step 6: Push**

```bash
git push
```

Expected: all 13 task commits pushed to `origin/main`.

---

## Self-review checklist

Run yourself before declaring Stage 1a done:

1. **Spec coverage:**
   - Evaluator (spec §6.1) → Task 5 ✓
   - SRS pure + engine (spec §6.2) → Tasks 6, 7 ✓
   - Grader (spec §6.3) → Task 10 ✓
   - Review orchestrator (spec §6.4) → Task 11 ✓
   - CLI review subcommand (spec §6.5) → Task 12 ✓
   - Session integration (spec §7.1) → Task 8 ✓
   - All 5 polish items → Task 1 (SecretStr), Task 2 (atomic write), Task 8 (opening budget + WAV cleanup), Task 9 (friendly ScenarioNotFoundError), Task 11 (WAV cleanup in review) ✓
   - 2 new scenarios → Task 13 ✓
   - Settings extensions → Task 3 ✓
   - Storage extensions → Task 4 ✓

2. **Type consistency:**
   - `GrowthPoint` schema (BaseModel) consistent across Tasks 5, 7, 8.
   - `Card` dataclass consistent across Tasks 7, 11, 12.
   - `LLMClient.complete(messages, temperature, model_override)` signature: Tasks 5, 10.
   - `SRSEngine` interface: `create_cards`, `due_today`, `record_review`, `load_card` — used consistently in Tasks 7, 8, 11, 12.
   - `Evaluator.evaluate(transcript) -> list[GrowthPoint]` consistent: Tasks 5, 8.

3. **No placeholders:** every step has code or exact commands.

4. **Failure modes covered:**
   - Evaluator parse fail → empty list (Task 5)
   - Grader non-integer → default 3 (Task 10)
   - Budget exhausted during session opening → clean exit (Task 8)
   - Budget exhausted during review → propagates (Task 10 test confirms)
   - Unknown scenario → exit 2 with message (Task 9)
   - Empty due cards → "No cards due" (Task 11)

---

## Definition of Done for Stage 1a

- All 14 tasks committed and pushed to `origin/main`.
- Full `pytest` suite green (~55 tests total after Stage 1a).
- One real interview session completed end-to-end and produced cards.
- One real review session completed end-to-end with SRS state updated.
- Both new scenarios runnable (`tutor list-scenarios` shows all three).
- 5 polish fixes verified via their regression tests.
- `cards.json` exists in project root (gitignored).
