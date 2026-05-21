# Stage 1b — Polish + Stats Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close 5 medium-priority gaps from the Stage 1a final review (graceful errors, visible failures, no silent data loss) AND add a `tutor stats` command for daily progress visibility (streak, sessions, cards, retention).

**Architecture:** Each polish is a small targeted change with a regression test. Stats is a new pure module (`tutor/stats.py`) that reads from `SessionStorage` and `SRSEngine` via two new read-only accessors. No LLM calls in stats. No infrastructure migration.

**Tech Stack:** Same as Stage 1a (Python 3.11+, openai SDK against OpenRouter, faster-whisper, pydantic-settings). No new dependencies.

**Prerequisites:**
- Stage 1a complete (~79 tests green, branch `main` at commit `d0a958d` or later).
- Working `.env` with `OPENROUTER_API_KEY` for session tests (stats tests don't need it).

---

## File Structure

```
tutor/
├── evaluator.py    (MODIFY: P5 retry reminder)
├── srs_engine.py   (MODIFY: P2 corrupt cards backup; ADD all_cards())
├── session.py      (MODIFY: P3 + P4 — visible errors)
├── review.py       (MODIFY: P1 BudgetExceededError catch)
├── storage.py      (MODIFY: ADD list_sessions())
├── stats.py        (NEW: StatsCalculator + StatsSummary)
└── cli.py          (MODIFY: ADD stats subcommand)

tests/
├── test_evaluator.py    (MODIFY: P5 retry reminder test)
├── test_srs_engine.py   (MODIFY: P2 corrupt cards test; all_cards test)
├── test_session.py      (MODIFY: P3 + P4 regression tests)
├── test_review.py       (MODIFY: P1 regression test)
├── test_storage.py      (MODIFY: list_sessions tests)
├── test_stats.py        (NEW: 7-8 unit tests)
└── test_cli.py          (MODIFY: stats smoke tests)
```

---

## Task 1: P1 — Review catches BudgetExceededError

**Files:**
- Modify: `tutor/review.py`
- Modify: `tests/test_review.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_review.py`:

```python
def test_review_catches_budget_exception_during_grade(tmp_path, mocker, capsys):
    """Regression P1: BudgetExceededError raised by grader must end the loop cleanly,
    not produce a traceback. Cards already reviewed remain persisted."""
    from tutor.review import ReviewOrchestrator
    from tutor.budget import BudgetExceededError

    mocker.patch("builtins.input", side_effect=["", ""])
    srs = _make_srs_with_cards(tmp_path, n_cards=3)
    asr, tts, recorder, grader = _stub_review_adapters(
        transcripts=["c0", "c1"],
        grader_scores=[3, BudgetExceededError("cap hit mid-review")],
    )

    orch = ReviewOrchestrator(grader=grader, asr=asr, tts=tts, recorder=recorder, srs=srs)
    summary = orch.run()

    assert summary.cards_reviewed == 1  # only the first card completed
    captured = capsys.readouterr()
    assert "budget" in captured.out.lower()
    assert "Traceback" not in captured.out
```

- [ ] **Step 2: Run test to verify failure**

Run: `cd /Users/sarkhipov/Work/Personal/english-tutor && source .venv/bin/activate && pytest tests/test_review.py::test_review_catches_budget_exception_during_grade -v`

Expected: FAIL — exception propagates as traceback; `cards_reviewed == 0` because the exception happens before the SRS record.

- [ ] **Step 3: Update `tutor/review.py` to catch BudgetExceededError**

Add the import at the top:

```python
from tutor.budget import BudgetExceededError
```

Wrap the grader call inside the loop. Find this block in the `run` method:

```python
                else:
                    print(f"> you said: \"{attempt_text}\"")
                    print("[grading...]")
                    quality = self._grader.grade(target=card.corrected_version, attempt=attempt_text)
```

Replace with:

```python
                else:
                    print(f"> you said: \"{attempt_text}\"")
                    print("[grading...]")
                    try:
                        quality = self._grader.grade(target=card.corrected_version, attempt=attempt_text)
                    except BudgetExceededError as e:
                        print(f"\n[budget exhausted during review: {e}]\n[review ending]")
                        summary.quality_distribution = dict(quality_counter)
                        print(f"\n=== Done. {summary.cards_reviewed} cards reviewed. ===\n")
                        return summary
```

The early return preserves invariants: `quality_distribution` is finalized and the closing message prints.

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_review.py -v`

Expected: 6 passed (5 existing + 1 new).

- [ ] **Step 5: Run full suite + commit**

Run: `pytest`
Expected: full suite green.

```bash
git add tutor/review.py tests/test_review.py
git commit -m "fix(review): catch BudgetExceededError mid-grade, exit cleanly"
```

---

## Task 2: P2 — SRSEngine backs up corrupt cards.json before raising

**Files:**
- Modify: `tutor/srs_engine.py`
- Modify: `tests/test_srs_engine.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_srs_engine.py`:

```python
def test_srs_engine_corrupt_cards_json_backs_up_and_raises(tmp_path):
    """Regression P2: corrupt cards.json must NOT silently destroy data.
    Engine raises RuntimeError; the bad file is renamed to .broken-<ts>."""
    from tutor.srs_engine import SRSEngine
    import pytest as _pytest

    cards_path = tmp_path / "cards.json"
    cards_path.write_text("{ this is not valid json")

    with _pytest.raises(RuntimeError, match="corrupt"):
        SRSEngine(path=cards_path, now=lambda: date(2026, 5, 21))

    # Original file was renamed to a .broken-* sibling
    backups = list(tmp_path.glob("cards.broken-*"))
    assert len(backups) == 1, f"expected exactly one backup, got {backups}"
    # Original path no longer exists (was renamed away)
    assert not cards_path.exists()
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_srs_engine.py::test_srs_engine_corrupt_cards_json_backs_up_and_raises -v`

Expected: FAIL — current `_load` returns `{}` silently, does not raise.

- [ ] **Step 3: Update `tutor/srs_engine.py`**

Add `import time` near the top (after the other stdlib imports).

Replace the existing `_load` method:

```python
    def _load(self) -> dict[str, Card]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            backup = self._path.with_suffix(f".broken-{int(time.time())}")
            try:
                self._path.rename(backup)
            except OSError:
                pass
            raise RuntimeError(
                f"cards.json is corrupt. Backed up to {backup}. "
                f"Inspect or delete to start fresh. Error: {e}"
            )
        cards: dict[str, Card] = {}
        for c in raw.get("cards", []):
            card = Card(**c)
            cards[card.id] = card
        return cards
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_srs_engine.py -v`

Expected: 8 passed (7 existing + 1 new).

- [ ] **Step 5: Full suite + commit**

Run: `pytest`
Expected: all green.

```bash
git add tutor/srs_engine.py tests/test_srs_engine.py
git commit -m "fix(srs_engine): back up corrupt cards.json and raise instead of silent reset"
```

---

## Task 3: P5 — Evaluator retry includes STRICT JSON reminder

**Files:**
- Modify: `tutor/evaluator.py`
- Modify: `tests/test_evaluator.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_evaluator.py`:

```python
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
```

- [ ] **Step 2: Run test to verify failure**

Run: `pytest tests/test_evaluator.py::test_evaluator_retry_includes_reminder_message -v`

Expected: FAIL — current retry sends identical messages, so `second_call_messages == first_call_messages`.

- [ ] **Step 3: Update `tutor/evaluator.py`**

Find the `evaluate` method's retry loop:

```python
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
```

Replace with:

```python
        last_error: Exception | None = None
        reminder = {
            "role": "user",
            "content": (
                "Your previous response was not valid JSON. Return STRICT JSON only, "
                "no commentary, no markdown fences. Just the {\"growth_points\": [...]} object."
            ),
        }
        for attempt in range(2):
            call_messages = messages if attempt == 0 else messages + [reminder]
            try:
                raw = self._llm.complete(messages=call_messages, temperature=0.2, model_override=self._model)
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
```

- [ ] **Step 4: Run test to verify pass**

Run: `pytest tests/test_evaluator.py -v`

Expected: 6 passed (5 existing + 1 new).

- [ ] **Step 5: Full suite + commit**

Run: `pytest`
Expected: all green.

```bash
git add tutor/evaluator.py tests/test_evaluator.py
git commit -m "fix(evaluator): include STRICT JSON reminder on retry after parse fail"
```

---

## Task 4: P3 + P4 — Session makes evaluator/create_cards failures visible

**Files:**
- Modify: `tutor/session.py`
- Modify: `tests/test_session.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_session.py`:

```python
def test_session_writes_growth_points_error_on_evaluator_raise(tmp_path, mocker):
    """Regression P4: when evaluator raises, session.json records growth_points_error."""
    from tutor.session import SessionOrchestrator
    from tutor.storage import SessionStorage
    from tutor.scenarios.loader import load_scenario

    mocker.patch("builtins.input", side_effect=["", "end"])
    llm, asr, tts, recorder = _stub_adapters(
        turn_user_texts=["hi"],
        turn_llm_replies=["Opening.", "Reply."],
    )

    fake_evaluator = MagicMock()
    fake_evaluator.evaluate.side_effect = RuntimeError("api down")
    fake_srs = MagicMock()

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
    assert "evaluator failed" in data.get("growth_points_error", "")
    assert "api down" in data.get("growth_points_error", "")
    fake_srs.create_cards.assert_not_called()


def test_session_no_growth_points_error_when_evaluator_returns_empty(tmp_path, mocker):
    """Regression P4: empty list is NOT an error — no growth_points_error written."""
    from tutor.session import SessionOrchestrator
    from tutor.storage import SessionStorage
    from tutor.scenarios.loader import load_scenario

    mocker.patch("builtins.input", side_effect=["", "end"])
    llm, asr, tts, recorder = _stub_adapters(
        turn_user_texts=["hi"],
        turn_llm_replies=["Opening.", "Reply."],
    )

    fake_evaluator = MagicMock()
    fake_evaluator.evaluate.return_value = []  # clean: no growth points found
    fake_srs = MagicMock()

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
    assert "growth_points_error" not in data


def test_session_create_cards_failure_visible(tmp_path, mocker, capsys):
    """Regression P3: srs.create_cards failure prints user-visible error AND
    writes growth_points_error to session JSON. Growth points remain persisted."""
    from tutor.session import SessionOrchestrator
    from tutor.storage import SessionStorage
    from tutor.scenarios.loader import load_scenario
    from tutor.evaluator import GrowthPoint

    mocker.patch("builtins.input", side_effect=["", "end"])
    llm, asr, tts, recorder = _stub_adapters(
        turn_user_texts=["hi"],
        turn_llm_replies=["Opening.", "Reply."],
    )

    fake_evaluator = MagicMock()
    fake_evaluator.evaluate.return_value = [
        GrowthPoint(tag="vocab", user_utterance="hi", corrected_version="hello",
                    explanation="more formal", context=None),
    ]
    fake_srs = MagicMock()
    fake_srs.create_cards.side_effect = OSError("disk full")

    storage = SessionStorage(root=tmp_path)
    orch = SessionOrchestrator(
        llm=llm, asr=asr, tts=tts, recorder=recorder, storage=storage,
        scenario=load_scenario("tech_interview_behavioral"),
        per_session_turn_limit=25,
        evaluator=fake_evaluator,
        srs_engine=fake_srs,
    )
    session_id = orch.run()

    captured = capsys.readouterr()
    assert "failed to save cards" in captured.out.lower()
    assert "disk full" in captured.out

    data = storage.load_session(session_id)
    # Growth points were saved BEFORE the create_cards attempt
    assert len(data["growth_points"]) == 1
    # The error is recorded
    assert "create_cards failed" in data.get("growth_points_error", "")
```

- [ ] **Step 2: Run tests to verify failures**

Run: `pytest tests/test_session.py::test_session_writes_growth_points_error_on_evaluator_raise tests/test_session.py::test_session_no_growth_points_error_when_evaluator_returns_empty tests/test_session.py::test_session_create_cards_failure_visible -v`

Expected: First test fails (no `growth_points_error` field in data). Second test may already pass (current code never writes the error field). Third test fails (no user-visible print and no error field).

- [ ] **Step 3: Update `tutor/session.py`**

Find the post-loop block:

```python
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
```

Replace with:

```python
            # After loop: run evaluator if provided and there were turns
            if self._evaluator is not None and self._srs_engine is not None and turn_count > 0:
                evaluator_raised = False
                try:
                    growth_points = self._evaluator.evaluate(transcript=history)
                except Exception as e:
                    log.warning("Evaluator raised unexpectedly: %s", e)
                    self._storage.set_growth_points_error(session_id, f"evaluator failed: {e}")
                    growth_points = []
                    evaluator_raised = True

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
                        self._storage.set_growth_points_error(
                            session_id, f"create_cards failed: {e}"
                        )
                        print(f"\n[failed to save cards: {e}]")
                elif not evaluator_raised:
                    log.info("Evaluator returned no growth points; no cards created.")
```

The `evaluator_raised` flag keeps the empty-list case clean — we only log "no growth points" when the evaluator successfully returned `[]`, not when it crashed.

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_session.py -v`

Expected: 12 passed (9 existing + 3 new).

- [ ] **Step 5: Full suite + commit**

Run: `pytest`
Expected: all green.

```bash
git add tutor/session.py tests/test_session.py
git commit -m "fix(session): wire growth_points_error for evaluator and create_cards failures"
```

---

## Task 5: `SessionStorage.list_sessions()`

**Files:**
- Modify: `tutor/storage.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_storage.py`:

```python
def test_storage_list_sessions_returns_all_sorted(tmp_path):
    from tutor.storage import SessionStorage
    from datetime import datetime

    times = [
        datetime(2026, 5, 19, 9, 0),
        datetime(2026, 5, 21, 14, 0),
        datetime(2026, 5, 20, 11, 0),
    ]
    # Create three sessions on different days
    for t in times:
        s = SessionStorage(root=tmp_path, now=lambda t=t: t)
        s.create_session("tech_interview_behavioral")

    reader = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 15, 0))
    sessions = reader.list_sessions()
    assert len(sessions) == 3
    # Sorted descending by started_at
    started_dates = [s["started_at"][:10] for s in sessions]
    assert started_dates == ["2026-05-21", "2026-05-20", "2026-05-19"]


def test_storage_list_sessions_skips_corrupt_files(tmp_path, caplog):
    from tutor.storage import SessionStorage
    from datetime import datetime
    import logging

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 10, 0))
    storage.create_session("tech_interview_behavioral")

    # Drop a corrupt JSON beside the good one
    corrupt = tmp_path / "2026-05-21" / "corrupt_id.json"
    corrupt.write_text("{ not json")

    with caplog.at_level(logging.WARNING):
        sessions = storage.list_sessions()
    assert len(sessions) == 1  # only the valid one
    assert any("corrupt_id" in r.message or "corrupt" in r.message.lower()
               for r in caplog.records)


def test_storage_list_sessions_empty_when_no_sessions(tmp_path):
    from tutor.storage import SessionStorage
    from datetime import datetime

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 10, 0))
    assert storage.list_sessions() == []
```

- [ ] **Step 2: Run tests to verify failures**

Run: `pytest tests/test_storage.py::test_storage_list_sessions_returns_all_sorted tests/test_storage.py::test_storage_list_sessions_skips_corrupt_files tests/test_storage.py::test_storage_list_sessions_empty_when_no_sessions -v`

Expected: 3 errors — `SessionStorage` has no `list_sessions` method.

- [ ] **Step 3: Add `list_sessions` to `tutor/storage.py`**

Add `import logging` near the top if not already present, then add a module-level logger:

```python
log = logging.getLogger(__name__)
```

Add this method to the `SessionStorage` class, after `load_session`:

```python
    def list_sessions(self) -> list[dict]:
        """Return all session JSONs sorted by started_at descending.
        Skips and logs files that fail to parse."""
        out: list[dict] = []
        if not self.root.exists():
            return out
        for path in self.root.rglob("*.json"):
            try:
                data = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError) as e:
                log.warning("Skipping corrupt session file %s: %s", path, e)
                continue
            out.append(data)
        out.sort(key=lambda d: d.get("started_at", ""), reverse=True)
        return out
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_storage.py -v`

Expected: 11 passed (8 existing + 3 new).

- [ ] **Step 5: Full suite + commit**

Run: `pytest`
Expected: all green.

```bash
git add tutor/storage.py tests/test_storage.py
git commit -m "feat(storage): list_sessions() returns all sessions sorted, skips corrupt"
```

---

## Task 6: `SRSEngine.all_cards()`

**Files:**
- Modify: `tutor/srs_engine.py`
- Modify: `tests/test_srs_engine.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_srs_engine.py`:

```python
def test_srs_engine_all_cards_returns_list_snapshot(tmp_path):
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint

    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    gps = [
        GrowthPoint(tag="vocab", user_utterance="u1", corrected_version="c1",
                    explanation="e", context=None),
        GrowthPoint(tag="grammar", user_utterance="u2", corrected_version="c2",
                    explanation="e", context=None),
    ]
    engine.create_cards(gps, session_id="s1")

    all_cards = engine.all_cards()
    assert len(all_cards) == 2
    tags = sorted(c.tag for c in all_cards)
    assert tags == ["grammar", "vocab"]


def test_srs_engine_all_cards_empty_when_no_cards(tmp_path):
    from tutor.srs_engine import SRSEngine

    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    assert engine.all_cards() == []
```

- [ ] **Step 2: Run tests to verify failures**

Run: `pytest tests/test_srs_engine.py::test_srs_engine_all_cards_returns_list_snapshot tests/test_srs_engine.py::test_srs_engine_all_cards_empty_when_no_cards -v`

Expected: 2 errors — `SRSEngine` has no `all_cards` method.

- [ ] **Step 3: Add `all_cards` to `tutor/srs_engine.py`**

Add this method to the `SRSEngine` class, after `load_card`:

```python
    def all_cards(self) -> list[Card]:
        """Return a snapshot of all cards. Read-only; mutations don't propagate
        back unless callers use record_review/create_cards."""
        return list(self._cards.values())
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_srs_engine.py -v`

Expected: 10 passed (8 existing + 2 new).

- [ ] **Step 5: Full suite + commit**

Run: `pytest`
Expected: all green.

```bash
git add tutor/srs_engine.py tests/test_srs_engine.py
git commit -m "feat(srs_engine): all_cards() read-only accessor for stats"
```

---

## Task 7: Stats module (StatsCalculator + StatsSummary)

**Files:**
- Create: `tutor/stats.py`
- Create: `tests/test_stats.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_stats.py`:

```python
from datetime import date, datetime, timedelta
from pathlib import Path
import pytest


def _make_storage_with_sessions(tmp_path, session_dates):
    """Create N sessions on the given ISO date strings.
    Returns a SessionStorage instance ready for reading."""
    from tutor.storage import SessionStorage

    for ds in session_dates:
        y, m, d = (int(x) for x in ds.split("-"))
        storage = SessionStorage(root=tmp_path, now=lambda y=y, m=m, d=d: datetime(y, m, d, 10, 0))
        storage.create_session("tech_interview_behavioral")

    return SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 12, 0))


def _make_srs_with_cards(tmp_path, configs):
    """Create cards according to configs.

    Each config is a tuple (tag, repetitions, interval_days, last_quality).
    """
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint

    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    gps = [
        GrowthPoint(tag=tag, user_utterance=f"u{i}", corrected_version=f"c{i}",
                    explanation="e", context=None)
        for i, (tag, _, _, _) in enumerate(configs)
    ]
    if gps:
        engine.create_cards(gps, session_id="s1")
        # Mutate the in-memory cards directly to match desired SRS state
        for (tag, reps, interval, qual), card in zip(configs, engine.all_cards()):
            card.repetitions = reps
            card.interval_days = interval
            card.last_review_quality = qual
        engine._flush()

    # Reopen so we read the persisted state
    return SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))


def test_stats_empty_state(tmp_path):
    from tutor.stats import StatsCalculator
    from tutor.storage import SessionStorage
    from tutor.srs_engine import SRSEngine

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 10, 0))
    srs = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    calc = StatsCalculator(storage=storage, srs=srs, now=lambda: date(2026, 5, 21))

    s = calc.compute()
    assert s.streak_days == 0
    assert s.last_activity is None
    assert s.sessions_total == 0
    assert s.cards_total == 0
    assert s.retention_rate is None
    assert s.retention_sample_size == 0


def test_stats_streak_today_only(tmp_path):
    from tutor.stats import StatsCalculator
    from tutor.srs_engine import SRSEngine

    storage = _make_storage_with_sessions(tmp_path, ["2026-05-21"])
    srs = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    calc = StatsCalculator(storage=storage, srs=srs, now=lambda: date(2026, 5, 21))

    s = calc.compute()
    assert s.streak_days == 1
    assert s.last_activity == "2026-05-21"


def test_stats_streak_today_and_yesterday(tmp_path):
    from tutor.stats import StatsCalculator
    from tutor.srs_engine import SRSEngine

    storage = _make_storage_with_sessions(tmp_path, ["2026-05-20", "2026-05-21"])
    srs = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    calc = StatsCalculator(storage=storage, srs=srs, now=lambda: date(2026, 5, 21))

    assert calc.compute().streak_days == 2


def test_stats_streak_yesterday_only_falls_back(tmp_path):
    from tutor.stats import StatsCalculator
    from tutor.srs_engine import SRSEngine

    # Activity yesterday but not today — streak still counts (from yesterday)
    storage = _make_storage_with_sessions(tmp_path, ["2026-05-20"])
    srs = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    calc = StatsCalculator(storage=storage, srs=srs, now=lambda: date(2026, 5, 21))

    assert calc.compute().streak_days == 1


def test_stats_streak_broken(tmp_path):
    from tutor.stats import StatsCalculator
    from tutor.srs_engine import SRSEngine

    # Last activity was 3 days ago — streak is 0
    storage = _make_storage_with_sessions(tmp_path, ["2026-05-17", "2026-05-18"])
    srs = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    calc = StatsCalculator(storage=storage, srs=srs, now=lambda: date(2026, 5, 21))

    assert calc.compute().streak_days == 0


def test_stats_sessions_by_scenario(tmp_path):
    from tutor.stats import StatsCalculator
    from tutor.storage import SessionStorage
    from tutor.srs_engine import SRSEngine

    # Three sessions across two scenarios
    for sid, t in [
        ("tech_interview_behavioral", datetime(2026, 5, 21, 9)),
        ("tech_interview_behavioral", datetime(2026, 5, 21, 10)),
        ("daily_standup", datetime(2026, 5, 20, 9)),
    ]:
        storage = SessionStorage(root=tmp_path, now=lambda t=t: t)
        storage.create_session(sid)

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 12))
    srs = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    calc = StatsCalculator(storage=storage, srs=srs, now=lambda: date(2026, 5, 21))

    s = calc.compute()
    assert s.sessions_total == 3
    assert s.sessions_by_scenario == {"tech_interview_behavioral": 2, "daily_standup": 1}


def test_stats_cards_by_state(tmp_path):
    from tutor.stats import StatsCalculator
    from tutor.storage import SessionStorage

    # (tag, repetitions, interval_days, last_quality)
    configs = [
        ("vocab", 0, 0, None),     # new
        ("vocab", 1, 1, 3),        # learning (interval 1)
        ("vocab", 3, 6, 4),        # learning (interval 6)
        ("grammar", 4, 15, 4),     # mature (interval > 7)
        ("grammar", 5, 30, 5),     # mature
    ]
    srs = _make_srs_with_cards(tmp_path, configs)
    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 12))
    calc = StatsCalculator(storage=storage, srs=srs, now=lambda: date(2026, 5, 21))

    s = calc.compute()
    assert s.cards_total == 5
    assert s.cards_by_tag == {"vocab": 3, "grammar": 2}
    assert s.cards_by_state == {"new": 1, "learning": 2, "mature": 2}


def test_stats_retention_below_threshold_returns_none(tmp_path):
    from tutor.stats import StatsCalculator
    from tutor.storage import SessionStorage

    # Only 2 cards with repetitions >= 3 — below threshold of 5
    configs = [
        ("vocab", 3, 6, 4),
        ("vocab", 4, 15, 4),
        ("vocab", 0, 0, None),  # not in pool
    ]
    srs = _make_srs_with_cards(tmp_path, configs)
    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 12))
    calc = StatsCalculator(storage=storage, srs=srs, now=lambda: date(2026, 5, 21))

    s = calc.compute()
    assert s.retention_rate is None
    assert s.retention_sample_size == 2


def test_stats_retention_above_threshold(tmp_path):
    from tutor.stats import StatsCalculator
    from tutor.storage import SessionStorage

    # 6 cards with repetitions >= 3, 5 of them passing (quality >= 3)
    configs = [
        ("vocab", 3, 6, 4),
        ("vocab", 3, 6, 5),
        ("vocab", 4, 15, 3),
        ("grammar", 5, 30, 4),
        ("grammar", 3, 6, 4),
        ("grammar", 4, 15, 1),  # failed
    ]
    srs = _make_srs_with_cards(tmp_path, configs)
    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 12))
    calc = StatsCalculator(storage=storage, srs=srs, now=lambda: date(2026, 5, 21))

    s = calc.compute()
    assert s.retention_sample_size == 6
    assert s.retention_rate == pytest.approx(5 / 6, abs=0.001)


def test_stats_days_filter_applies_to_sessions_not_cards(tmp_path):
    from tutor.stats import StatsCalculator
    from tutor.storage import SessionStorage

    # Three sessions: one within 7 days, two older
    for t in [
        datetime(2026, 5, 21, 9),  # today
        datetime(2026, 5, 10, 9),  # 11 days ago
        datetime(2026, 5, 1, 9),   # 20 days ago
    ]:
        s = SessionStorage(root=tmp_path, now=lambda t=t: t)
        s.create_session("tech_interview_behavioral")

    # Cards are independent of the filter window
    configs = [("vocab", 0, 0, None), ("grammar", 0, 0, None)]
    srs = _make_srs_with_cards(tmp_path, configs)

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 12))
    calc = StatsCalculator(storage=storage, srs=srs, now=lambda: date(2026, 5, 21))

    s = calc.compute(days=7)
    assert s.sessions_total == 1  # only today
    assert s.cards_total == 2  # all cards regardless of window
```

- [ ] **Step 2: Run tests to verify failures**

Run: `pytest tests/test_stats.py -v`

Expected: 10 errors — `tutor.stats` does not exist.

- [ ] **Step 3: Implement `tutor/stats.py`**

```python
"""Aggregate sessions + cards into a StatsSummary for `tutor stats`."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

from tutor.srs_engine import SRSEngine
from tutor.storage import SessionStorage


_RETENTION_MIN_REPS = 3
_RETENTION_PASS_QUALITY = 3
_RETENTION_MIN_SAMPLE = 5
_MATURE_INTERVAL_DAYS = 7


@dataclass
class StatsSummary:
    today: str
    streak_days: int
    last_activity: str | None
    sessions_total: int
    sessions_last_7d: int
    sessions_last_30d: int
    sessions_by_scenario: dict[str, int] = field(default_factory=dict)
    cards_total: int = 0
    cards_by_tag: dict[str, int] = field(default_factory=dict)
    cards_by_state: dict[str, int] = field(default_factory=dict)
    retention_rate: float | None = None
    retention_sample_size: int = 0


class StatsCalculator:
    def __init__(
        self,
        storage: SessionStorage,
        srs: SRSEngine,
        now: Callable[[], date] = date.today,
    ) -> None:
        self._storage = storage
        self._srs = srs
        self._now = now

    def compute(self, days: int | None = None) -> StatsSummary:
        today = self._now()
        all_sessions = self._storage.list_sessions()
        sessions_in_window = _filter_sessions(all_sessions, today, days)

        # Streak uses ALL sessions, not the windowed slice
        session_date_set = {s.get("started_at", "")[:10] for s in all_sessions if s.get("started_at")}
        streak = _compute_streak(session_date_set, today)
        last_activity = max(session_date_set) if session_date_set else None

        last_7d = _filter_sessions(all_sessions, today, 7)
        last_30d = _filter_sessions(all_sessions, today, 30)

        by_scenario = Counter(s.get("scenario_id", "?") for s in sessions_in_window)

        # Cards are NOT filtered by the days window
        cards = self._srs.all_cards()
        by_tag = Counter(c.tag for c in cards)
        by_state = Counter(_card_state(c) for c in cards)

        # Retention
        pool = [c for c in cards if c.repetitions >= _RETENTION_MIN_REPS]
        if len(pool) >= _RETENTION_MIN_SAMPLE:
            passing = sum(1 for c in pool if (c.last_review_quality or 0) >= _RETENTION_PASS_QUALITY)
            retention = passing / len(pool)
        else:
            retention = None

        return StatsSummary(
            today=today.isoformat(),
            streak_days=streak,
            last_activity=last_activity,
            sessions_total=len(sessions_in_window),
            sessions_last_7d=len(last_7d),
            sessions_last_30d=len(last_30d),
            sessions_by_scenario=dict(by_scenario),
            cards_total=len(cards),
            cards_by_tag=dict(by_tag),
            cards_by_state=dict(by_state),
            retention_rate=retention,
            retention_sample_size=len(pool),
        )


def _filter_sessions(sessions: list[dict], today: date, days: int | None) -> list[dict]:
    if days is None:
        return list(sessions)
    cutoff = today - timedelta(days=days - 1)  # inclusive: last N days incl. today
    cutoff_iso = cutoff.isoformat()
    return [s for s in sessions if s.get("started_at", "")[:10] >= cutoff_iso]


def _compute_streak(session_dates: set[str], today: date) -> int:
    cursor = today
    if cursor.isoformat() not in session_dates:
        cursor = today - timedelta(days=1)
        if cursor.isoformat() not in session_dates:
            return 0
    n = 0
    while cursor.isoformat() in session_dates:
        n += 1
        cursor -= timedelta(days=1)
    return n


def _card_state(card) -> str:
    if card.repetitions == 0:
        return "new"
    if card.interval_days <= _MATURE_INTERVAL_DAYS:
        return "learning"
    return "mature"


def format_summary(s: StatsSummary, days: int | None = None) -> str:
    """Render StatsSummary as scannable plain text for CLI output."""
    header = "=== English Tutor Stats ==="
    if days is not None:
        header = f"=== English Tutor Stats (last {days} days) ==="

    if s.sessions_total == 0 and s.cards_total == 0 and days is None:
        return header + "\n\nNo sessions yet. Run `tutor interview` to get started.\n"

    lines = [header, ""]

    if s.last_activity:
        lines.append(f"Streak: {s.streak_days} days  (last activity: {s.last_activity})")
    else:
        lines.append(f"Streak: {s.streak_days} days")
    lines.append("")

    lines.append("Sessions")
    lines.append(f"  Total:        {s.sessions_total}")
    lines.append(f"  Last 7 days:  {s.sessions_last_7d}")
    lines.append(f"  Last 30 days: {s.sessions_last_30d}")
    if s.sessions_by_scenario:
        lines.append("  By scenario:")
        width = max(len(k) for k in s.sessions_by_scenario)
        for sid, count in sorted(s.sessions_by_scenario.items(), key=lambda kv: -kv[1]):
            lines.append(f"    {sid.ljust(width)}: {count}")
    lines.append("")

    lines.append("Cards")
    lines.append(f"  Total:    {s.cards_total}")
    if s.cards_by_tag:
        tag_str = " | ".join(f"{tag} {count}" for tag, count in sorted(s.cards_by_tag.items()))
        lines.append(f"  By tag:   {tag_str}")
    if s.cards_by_state:
        state_order = ["new", "learning", "mature"]
        state_str = " | ".join(
            f"{state} {s.cards_by_state.get(state, 0)}" for state in state_order
        )
        lines.append(f"  By state: {state_str}")
    lines.append("")

    if s.retention_rate is not None:
        passing = round(s.retention_rate * s.retention_sample_size)
        pct = round(s.retention_rate * 100)
        lines.append(f"Retention: {pct}% ({passing} of {s.retention_sample_size} mature cards passing)")
    else:
        if s.retention_sample_size == 0:
            lines.append("Retention: N/A (no cards reviewed yet)")
        else:
            lines.append(
                f"Retention: N/A (insufficient data — {s.retention_sample_size} cards with "
                f"≥3 reviews, need ≥{_RETENTION_MIN_SAMPLE})"
            )

    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_stats.py -v`

Expected: 10 passed.

- [ ] **Step 5: Full suite + commit**

Run: `pytest`
Expected: all green (~93 tests).

```bash
git add tutor/stats.py tests/test_stats.py
git commit -m "feat(stats): StatsCalculator + StatsSummary with streak, sessions, cards, retention"
```

---

## Task 8: CLI `stats` subcommand

**Files:**
- Modify: `tutor/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_cli.py`:

```python
def test_cli_stats_help_works(monkeypatch, capsys):
    from tutor.cli import main
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        main(["stats", "--help"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert "--days" in captured.out


def test_cli_stats_no_data(monkeypatch, tmp_path, capsys, mocker):
    """Smoke: stats with no sessions/cards prints empty-state message."""
    from tutor.cli import main
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)

    from tutor import cli as cli_mod
    mocker.patch.object(cli_mod, "_project_root", return_value=tmp_path)

    exit_code = main(["stats"])
    assert exit_code == 0
    captured = capsys.readouterr()
    assert "No sessions yet" in captured.out


def test_cli_stats_rejects_zero_days(monkeypatch, tmp_path, capsys, mocker):
    """--days must be >= 1."""
    from tutor.cli import main
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)
    from tutor import cli as cli_mod
    mocker.patch.object(cli_mod, "_project_root", return_value=tmp_path)

    with pytest.raises(SystemExit) as exc_info:
        main(["stats", "--days", "0"])
    assert exc_info.value.code != 0
```

- [ ] **Step 2: Run tests to verify failures**

Run: `pytest tests/test_cli.py -v`

Expected: failures — `stats` subcommand doesn't exist.

- [ ] **Step 3: Add `stats` subcommand to `tutor/cli.py`**

Add imports at the top:

```python
from tutor.stats import StatsCalculator, format_summary
```

Add to `_build_parser`, after the `review` subparser definition:

```python
    sub_stats = sub.add_parser("stats", help="Show progress stats")
    sub_stats.add_argument(
        "--days",
        type=_positive_int,
        default=None,
        help="Window for session counts (sessions only, not cards). Must be >= 1.",
    )
```

Add a helper `_positive_int` near the top of the file (after imports, before `_project_root`):

```python
def _positive_int(value: str) -> int:
    iv = int(value)
    if iv < 1:
        raise argparse.ArgumentTypeError("--days must be >= 1")
    return iv
```

Add the runner function after `_run_review`:

```python
def _run_stats(days: int | None) -> int:
    project_root = _project_root()
    storage = SessionStorage(root=project_root / "sessions")
    srs = SRSEngine(path=project_root / "cards.json")
    calc = StatsCalculator(storage=storage, srs=srs)
    summary = calc.compute(days=days)
    print(format_summary(summary, days=days))
    return 0
```

Wire it in `main`:

```python
    if args.command == "stats":
        return _run_stats(args.days)
```

(Place that line alongside the other `if args.command == "..."` checks.)

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_cli.py -v`

Expected: 6 passed (3 existing + 3 new).

- [ ] **Step 5: Manual smoke from CLI**

Run: `tutor stats --help`
Expected: shows `--days` option.

Run: `tutor stats`
Expected:
- If no `sessions/` directory exists in cwd: empty-state message.
- If sessions exist: full formatted summary.

- [ ] **Step 6: Full suite + commit**

Run: `pytest`
Expected: all green.

```bash
git add tutor/cli.py tests/test_cli.py
git commit -m "feat(cli): add stats subcommand for progress visibility"
```

---

## Task 9: Manual end-to-end smoke

No automated test — verify the integrated system feels right.

- [ ] **Step 1: Confirm everything is green**

Run from project root with venv activated:
- `pytest` → should show ~93 passed.
- `git log --oneline 5d1ac18..HEAD` → should show 8 task commits (Tasks 1-8).

- [ ] **Step 2: Stats with current data**

Run: `tutor stats`

Expected: summary reflects your existing sessions (from Stage 1a smoke + any subsequent runs) and cards. Verify:
- Streak count looks right (if you ran sessions yesterday and today, 2; otherwise 1 or 0).
- Sessions total includes all of `sessions/{date}/` files.
- Cards total matches `cards.json` entry count.

Run: `tutor stats --days 7`

Expected: header changes to "(last 7 days)", session counts reflect the window, cards counts are unchanged.

- [ ] **Step 3: Provoke a polish path (optional)**

To verify P2 specifically without committing data loss:
```bash
cp cards.json cards.json.backup_for_smoke
echo "{ not json" > cards.json
tutor stats
# Expected: traceback-ish error mentioning corrupt; cards.broken-<ts> created
mv cards.json.backup_for_smoke cards.json
ls cards.broken-*
# Delete the broken backup once verified
rm cards.broken-*
```

- [ ] **Step 4: Real session with P3/P4 path (optional)**

A real `tutor interview` session that succeeds will print `[saved N cards for review tomorrow]` (P3 happy path).

If you want to provoke P4 (evaluator failure), temporarily set `OPENROUTER_EVALUATOR_MODEL=this-model-does-not-exist` in `.env`, run a short session, and check the resulting session JSON:
```bash
cat sessions/$(date +%Y-%m-%d)/*.json | python -m json.tool | tail -20
# Expected: growth_points_error field is populated
```
Restore the env afterwards.

- [ ] **Step 5: Push**

```bash
git push
```

Expected: all 8 task commits pushed to `origin/main`.

---

## Self-review checklist

Run yourself before declaring Stage 1b done:

1. **Spec coverage:**
   - P1 review BudgetExceededError → Task 1 ✓
   - P2 SRSEngine corrupt cards → Task 2 ✓
   - P3 session create_cards visible → Task 4 ✓
   - P4 session evaluator-raise wires error → Task 4 ✓
   - P5 evaluator retry reminder → Task 3 ✓
   - `SessionStorage.list_sessions()` → Task 5 ✓
   - `SRSEngine.all_cards()` → Task 6 ✓
   - `StatsCalculator` / `StatsSummary` → Task 7 ✓
   - CLI `stats` subcommand → Task 8 ✓
   - Output format `format_summary` → Task 7 ✓
   - `--days N` validation → Task 8 ✓

2. **Type consistency:**
   - `StatsSummary` fields used identically in `tutor/stats.py` and `tests/test_stats.py`.
   - `Card.tag`, `Card.repetitions`, `Card.interval_days`, `Card.last_review_quality` referenced as defined in `tutor/srs_engine.py`.
   - `SessionStorage.list_sessions()` signature: `() -> list[dict]`. Consumed in `StatsCalculator.compute` and the CLI.
   - `SRSEngine.all_cards()` signature: `() -> list[Card]`.

3. **No placeholders:** every step has either code or exact commands.

4. **Failure modes covered:**
   - Budget exhausted mid-review → Task 1 test.
   - Corrupt cards.json → Task 2 test verifies backup + raise.
   - Evaluator raises → Task 4 test verifies growth_points_error.
   - Evaluator returns [] → Task 4 test verifies NO error written.
   - create_cards raises → Task 4 test verifies print + error field.
   - Corrupt session JSON in list_sessions → Task 5 test verifies skip.
   - Empty stats state → Task 7 test + Task 8 CLI test.

---

## Definition of Done for Stage 1b

- All 8 task commits on `main` and pushed to `origin/main`.
- Full `pytest` suite green (~93 tests after Stage 1b).
- `tutor stats` runs end-to-end against real user data and produces a coherent summary.
- All 5 polish regression tests are green in the suite.
- `tutor stats --days 0` correctly errors out with a non-zero exit code.

When all of the above are true, Stage 1b is done. The user can use `tutor stats` daily to track progress, evaluator/SRS failures are no longer silent, and corrupt state can't destroy data unnoticed.
