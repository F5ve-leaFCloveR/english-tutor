# Stage 1b — Polish + Stats Design

- **Date:** 2026-05-21
- **Author:** Stas Arkhipov
- **Status:** Draft, pending implementation plan

## 1. Context

Stage 1a shipped the core learning loop on 2026-05-21: Evaluator producing GrowthPoints, SRSEngine with SM-2 scheduling, voice-based review with LLM grading, +2 scenarios, 5 polish fixes from Stage 0 final review. Smoke test confirmed end-to-end flow works.

Five medium-priority issues surfaced in the Stage 1a final review. They are real gaps but did not block Stage 1a shipping. Stage 1b closes them.

At the same time, the user is entering a use phase — they will accumulate sessions and cards over the next 2-4 weeks. Without any way to see progress, the daily habit is harder to sustain. A `tutor stats` command gives concrete visibility (streak, retention, card distribution) without requiring infrastructure changes.

What Stage 1b is **not**: the original Stage 1b in the project spec also called for Postgres migration, evaluator golden-set tooling, and card dedup via embedding similarity. Two of those (golden-set, dedup) are data-dependent and premature with current usage (~1 session, ~5 cards). Postgres is data-independent but premature without analytics needs that justify the migration cost. All three remain deferred.

## 2. Goals

- Close the 5 medium-priority gaps from the Stage 1a final review — make existing failure modes either invisible-but-safe or user-visible-but-graceful (never silent data loss, never raw tracebacks).
- Add `tutor stats` so the user can see their own progress without inspecting JSON files manually. Cover streak, session counts, card distribution, retention rate.

## 3. Non-Goals

- Postgres migration. Stage 1c or later.
- Evaluator golden-set framework. Defer until 2-3 weeks of real session data accumulate.
- Card dedup via embedding similarity. Defer until duplicate cards become an observable annoyance.
- New scenarios. Three is sufficient for Stage 1b validation.
- TTS / voice quality improvements. macOS `say` with the user's chosen Siri voice is acceptable.
- PWA / web UI. Stage 2 territory.

## 4. Approach

Two parallel tracks of small, focused changes — no architectural restructuring.

**Track A: 5 polish fixes.** Each is a 1-file change (or 2 files including tests) with a regression test that proves the fix actually does what it claims.

**Track B: `tutor stats` command.** New `tutor/stats.py` module computes a `StatsSummary` from `SessionStorage` and `SRSEngine`. CLI subcommand wires it. Stats is pure aggregation — no LLM calls, no network, no state mutation. Cheap to test, cheap to run.

The two tracks are independent. They could ship as one stage or two; we ship them together as Stage 1b to keep ceremony low.

## 5. Architecture

```
[ tutor stats [--days N] ]
        │
        ▼
[ StatsCalculator ]
   ├─► SessionStorage.list_sessions()  (new method, rglob over sessions/)
   ├─► SRSEngine.all_cards()           (new accessor)
   └─► StatsSummary (dataclass) ──► formatter ──► stdout

Polish-only changes touch existing modules:
  evaluator.py  — retry prompt now includes "STRICT JSON only" reminder
  srs_engine.py — corrupt cards.json: rename to .broken-<ts>, raise RuntimeError
  session.py    — wire set_growth_points_error; visible error on srs.create_cards failure
  review.py     — catch BudgetExceededError in review loop, graceful exit
  storage.py    — + list_sessions() (used by stats only)
```

## 6. Components

### 6.1 Polish P1: `ReviewOrchestrator.run` catches `BudgetExceededError`

**File:** `tutor/review.py`

Currently the grader call inside the per-card loop is unwrapped. If the daily budget cap trips mid-review, the exception propagates to the CLI as a traceback.

Wrap the grader call:

```python
try:
    quality = self._grader.grade(target=card.corrected_version, attempt=attempt_text)
except BudgetExceededError as e:
    print(f"\n[budget exhausted during review: {e}]\n[review ending]")
    break
```

Behavior: review ends cleanly after the partial card. Previous cards' reviews are already persisted. Summary reflects cards actually completed.

### 6.2 Polish P2: `SRSEngine._load` backs up corrupt `cards.json` before raising

**File:** `tutor/srs_engine.py`

Currently a corrupt or unreadable `cards.json` returns `{}` silently. The next `_flush()` writes the empty dict, destroying the user's card data.

New behavior:

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
    ...
```

If JSON loads but contains invalid Card data (extra/missing fields after a future schema change), the exception from `Card(**c)` still bubbles up — caller (CLI) sees a Python-level traceback. That's acceptable for now: schema drift is rare and explicit.

### 6.3 Polish P3: `SessionOrchestrator` makes `srs.create_cards` failures visible

**File:** `tutor/session.py`

Current code logs a warning and silently drops the cards. The session ends as if everything succeeded — `[saved N cards]` is never printed, and the user has no way to know.

New behavior in the post-loop block:

```python
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
```

Behavior: any failure is both printed to stdout and persisted to the session JSON as `growth_points_error`. The growth points themselves are still saved (they were persisted before this try block).

### 6.4 Polish P4: Wire `storage.set_growth_points_error` for evaluator failures

**File:** `tutor/session.py`

The method `SessionStorage.set_growth_points_error` was added in Stage 1a Task 4 but never wired. When the evaluator raises, the session JSON has no `growth_points_error` field — the failure is invisible at rest.

Add to the existing try/except around `self._evaluator.evaluate(...)`:

```python
try:
    growth_points = self._evaluator.evaluate(transcript=history)
except Exception as e:
    log.warning("Evaluator raised unexpectedly: %s", e)
    growth_points = []
    self._storage.set_growth_points_error(session_id, f"evaluator failed: {e}")
```

**Important distinction:** an empty list returned from `evaluator.evaluate(...)` (the evaluator's own catch-all behavior) means "no growth points found OR parse failed twice." We do NOT write `growth_points_error` in that case — only when the evaluator itself raises. The distinction matters because the user may legitimately have a clean session worth reviewing (no growth points = nothing to fix).

If we later want finer error attribution (parse-fail vs API-fail), the Evaluator can be updated to return a richer result type. Out of scope for now.

### 6.5 Polish P5: Evaluator retry includes a "STRICT JSON" reminder

**File:** `tutor/evaluator.py`

The retry currently re-sends the exact same prompt at the same temperature. On low temperature, the model may produce nearly identical bad output. A targeted reminder on the second attempt improves the hit rate.

New behavior in the retry loop:

```python
for attempt in range(2):
    if attempt > 0:
        call_messages = messages + [{
            "role": "user",
            "content": (
                "Your previous response was not valid JSON. Return STRICT JSON only, "
                "no commentary, no markdown fences. Just the {\"growth_points\": [...]} object."
            ),
        }]
    else:
        call_messages = messages
    try:
        raw = self._llm.complete(messages=call_messages, temperature=0.2, model_override=self._model)
    ...
```

The reminder is appended (not replacing the original system + transcript), so the model retains full context.

### 6.6 `SessionStorage.list_sessions() -> list[dict]`

**File:** `tutor/storage.py`

New read-only accessor used by `StatsCalculator`. Walks `self.root.rglob("*.json")`, loads each, returns the list sorted by `started_at` descending. Sessions with unreadable JSON are skipped (logged at warning level) so a single corrupt file doesn't break the stats command.

### 6.7 `SRSEngine.all_cards() -> list[Card]`

**File:** `tutor/srs_engine.py`

New read-only accessor. Returns a snapshot list: `list(self._cards.values())`. Callers should treat the result as read-only — the engine itself never relies on cached snapshots being stable.

### 6.8 `StatsCalculator` and `StatsSummary`

**File:** `tutor/stats.py` (new)

```python
@dataclass
class StatsSummary:
    today: str                          # ISO date for display
    streak_days: int
    last_activity: str | None           # ISO date or None
    sessions_total: int
    sessions_last_7d: int
    sessions_last_30d: int
    sessions_by_scenario: dict[str, int]
    cards_total: int
    cards_by_tag: dict[str, int]
    cards_by_state: dict[str, int]      # keys: "new", "learning", "mature"
    retention_rate: float | None        # 0.0–1.0 or None
    retention_sample_size: int


class StatsCalculator:
    def __init__(
        self,
        storage: SessionStorage,
        srs: SRSEngine,
        now: Callable[[], date] = date.today,
    ) -> None: ...

    def compute(self, days: int | None = None) -> StatsSummary: ...
```

`compute` reads from `storage.list_sessions()` and `srs.all_cards()`, performs the aggregations defined below, and returns a `StatsSummary`.

#### Aggregation definitions

**Streak (days):**
```python
def _compute_streak(session_dates: set[str], today: date) -> int:
    """Return the longest consecutive run of days ending at today (or yesterday
    if today has no activity) where each day has >=1 session."""
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
```

So: if you have a session today, streak counts from today. If not but yesterday yes, counts from yesterday. If neither, 0.

**Card state:**
- `new`: `repetitions == 0`
- `learning`: `1 <= interval_days <= 7`
- `mature`: `interval_days > 7`

**Retention rate:**
- Pool: cards with `repetitions >= 3`
- Numerator: cards in pool with `last_review_quality >= 3`
- Denominator: size of pool
- Returns `None` if pool size `< 5`

**Window (--days N):**
Filters `sessions_total` / `sessions_by_scenario` to sessions with `started_at[:10] >= today - N days`. `cards_*` are NOT filtered (cards are state, not events; filtering them by creation date is potentially confusing — stick to global card state for now).

### 6.9 `tutor/cli.py` — `stats` subcommand

```bash
tutor stats             # all-time
tutor stats --days 7    # 7-day window applied to session counts
```

argparse validation: `--days` must be `>= 1` if provided.

The subcommand wires `SessionStorage` + `SRSEngine` from project paths, computes the summary, formats and prints. No LLM calls, no network — `--help` and execution work without an OpenRouter key (no `get_settings()`).

#### Output format

Plain text, scannable. Example:

```
=== English Tutor Stats ===

Streak: 3 days  (last activity: 2026-05-21)

Sessions
  Total:        12
  Last 7 days:  5
  Last 30 days: 12
  By scenario:
    tech_interview_behavioral: 8
    daily_standup:             3
    apartment_rental_abroad:   1

Cards
  Total:    47
  By tag:   vocab 28 | grammar 19
  By state: new 12 | learning 28 | mature 7

Retention: 73% (16 of 22 mature cards passing)
```

With `--days 7` the header becomes `=== English Tutor Stats (last 7 days) ===` and the session counts apply the window.

Empty state (no sessions yet):
```
=== English Tutor Stats ===

No sessions yet. Run `tutor interview` to get started.
```

## 7. Data Flow

`tutor stats` is straight read-aggregation:

```
1. CLI parses argv, gets days filter (optional)
2. CLI constructs SessionStorage(root=project_root/"sessions"),
                  SRSEngine(path=project_root/"cards.json")
3. CLI constructs StatsCalculator(storage, srs)
4. summary = calculator.compute(days=...)
5. CLI formats summary and prints
```

Polish changes do not introduce new data flow — they tighten existing paths.

## 8. Error Handling

| Scenario | Handling |
|---|---|
| `cards.json` corrupt | Backup to `cards.json.broken-<ts>`, RuntimeError raised. User must inspect/delete before continuing. |
| `cards.json` valid JSON but invalid Card shape | `Card(**c)` raises TypeError. Bubbles up. Schema drift requires explicit action. |
| One session JSON corrupt during `list_sessions` | Skip + log warning. Stats does not fail for a single bad file. |
| `tutor stats` with no sessions | Print empty-state message, exit 0. |
| `tutor stats --days 0` | argparse error: `--days must be >= 1`. |
| Evaluator raises during session | Wire `growth_points_error` to session JSON (P4); session ends cleanly. |
| Evaluator returns empty list | No error written. Session JSON has `growth_points: []`. |
| `srs.create_cards` raises | Print user-visible message + persist `growth_points_error` (P3). |
| Review `grader.grade` raises BudgetExceededError | Catch + print message + break (P1). |

## 9. Budget

No new LLM usage in this stage. Stats is offline aggregation; polish changes do not add calls. Daily caps remain unchanged.

## 10. Testing

### Unit tests

- **`tests/test_stats.py`** (new) — 7–8 tests:
  - Empty state (no sessions, no cards) → all counts zero, retention None.
  - Streak: today only → 1; today + yesterday → 2; today missing but yesterday yes → 1; broken (gap > 1) → 0.
  - Sessions aggregated by scenario.
  - Cards classified by state (new/learning/mature).
  - Retention pool threshold (pool < 5 → None).
  - `--days N` window filters sessions but not cards.

- **`tests/test_evaluator.py`** — extend with `test_evaluator_retry_includes_reminder_message` (P5).
- **`tests/test_srs_engine.py`** — extend with `test_srs_engine_corrupt_cards_json_backs_up_and_raises` (P2).
- **`tests/test_session.py`** — extend with `test_session_writes_growth_points_error_on_evaluator_raise` (P4) and `test_session_create_cards_failure_visible` (P3).
- **`tests/test_review.py`** — extend with `test_review_catches_budget_exception_during_grade` (P1).
- **`tests/test_storage.py`** — extend with `test_storage_list_sessions_returns_all_sorted` and `test_storage_list_sessions_skips_corrupt_files`.
- **`tests/test_cli.py`** — extend with `test_cli_stats_no_data` and `test_cli_stats_help` (smoke).

### Integration

The stats output format is verified via golden-text comparison in one test that exercises the full formatter on a known-state fixture.

### Manual smoke

After implementation:
- Run `tutor interview` to add a session and create a card.
- Run `tutor stats` — verify output reflects the new session and card.
- Run `tutor stats --days 7` — verify the windowed output.

## 11. Decisions

| Decision | Choice | Why |
|---|---|---|
| Postgres in Stage 1b? | No | JSON works; migration cost not yet justified |
| Golden-set tooling? | No | Premature without 2-3 weeks of data |
| Card dedup? | No | Premature without observed duplicates |
| Stats command in same stage as polish? | Yes | Both small, independent, low ceremony |
| Stats output format? | Plain text, scannable | No JSON/machine output for now — single user, no integrations |
| Card state buckets? | new / learning (1–7d) / mature (>7d) | Simple, matches user mental model |
| Retention pool threshold? | `repetitions >= 3` | Three reviews = enough signal to call it retained |
| Retention small-sample handling? | `None` returned, displayed `N/A` | Avoid misleading percentages |
| Streak fallback to yesterday? | Yes | "If you trained yesterday you still have streak today" matches Anki/Duolingo conventions |
| `--days` filter affects cards? | No, only sessions | Cards are state, not events |

## 12. Open Questions / Risks

- **Stats output is unstable as content grows.** Today's format fits in one screen. With 100+ scenarios (won't happen at this scale) it wouldn't. Acceptable.
- **`list_sessions` scans the whole sessions directory each call.** Fine at the current volume. If it becomes slow (years of daily use) we'd switch to a DB. Not a concern now.
- **Retention metric is naive.** Counts last quality only, ignores trajectory. A card that failed 3 times then passed once gets counted as "retained." More sophisticated retention (e.g., proportion of last-N reviews passing) deferred until the simple metric proves misleading.
- **`tutor stats --days N` window choice is global to the command.** No per-section windows. If we ever want "card growth in last 7 days" separately from "session count in last 7 days" we'd add additional flags. Out of scope.

## 13. Success Criteria

Stage 1b is considered successful when:

- All 5 polish fixes ship with regression tests; the original behaviors they target no longer occur in the test suite.
- `tutor stats` outputs accurate counts on a fresh JSON state (verified by integration test).
- `tutor stats` outputs accurate counts on real user data (verified by manual smoke).
- Full `pytest` suite stays green (~90+ tests after Stage 1b additions).
- The user reports (qualitatively) that `tutor stats` gives them at least one signal worth checking — streak, retention, or distribution — that motivates them to maintain the practice.
