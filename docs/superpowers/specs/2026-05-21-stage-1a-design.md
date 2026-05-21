# Stage 1a — Core Learning Loop Design

- **Date:** 2026-05-21
- **Author:** Stas Arkhipov
- **Status:** Draft, pending implementation plan

## 1. Context

Stage 0 (CLI prototype) shipped 2026-05-20: voice-first session loop end-to-end with one scenario (tech interview behavioral), JSON session transcripts, $0.5/day budget cap. First real session validated the core technical premise — cost was negligible ($0.0005 for two turns), Whisper transcription was usable, macOS `say` is functional placeholder TTS.

Stage 0's missing piece: every session was isolated. The user spoke for 15 minutes, the transcript was saved, that was it. Nothing carried forward to the next session. Stage 1a closes that loop: every session now produces durable learning artifacts that resurface on a schedule.

The original Stage 1 envisioned in the project's main design doc included five components (Evaluator, SRS Engine, Review CLI, Postgres, +2 scenarios). Stage 1a explicitly defers Postgres — JSON files still work fine at the current data volume, and the migration effort would slow down delivery of the core learning value. Postgres is held for Stage 1b alongside the evaluator golden-set work.

## 2. Goals

- After each session, the user receives 3–5 concrete, actionable improvements (vocab or grammar) as flashcards.
- Cards enter a spaced-repetition schedule starting the next day. The user can review them with `tutor review`.
- Review is voice-based: the user speaks their recall attempt, an LLM grades it, the SRS algorithm updates the next due date.
- Two additional scenarios (daily standup, apartment rental abroad) so the user has variety beyond tech-interview practice.
- All five high-priority polish items from the Stage 0 final review are fixed in this stage.

## 3. Non-Goals

- Postgres / DB migration. JSON files continue. Migration is Stage 1b.
- Evaluator golden-set tooling (annotation, before/after eval). Stage 1b after ~2-4 weeks of real-use data accumulates.
- Card dedup via embedding similarity. Stage 1a accepts duplicate cards as a positive signal of recurring weaknesses.
- Adaptive difficulty, content layer (podcasts), Telegram bot, PWA — all stay deferred.

## 4. Approach

**Synchronous evaluator + JSON-backed SRS.** When a session ends, a single blocking LLM call analyzes the transcript and returns 3–5 GrowthPoints. These convert directly to Cards with due dates set to tomorrow. The Cards live in a single `cards.json` file at the project root. `tutor review` loads due cards, runs each through a voice-recall loop with LLM-graded recall, updates SM-2 state, and writes back.

Alternatives considered and rejected:

- **Async evaluator (background process):** session ends immediately, evaluator runs in background. Rejected because the added complexity (process management, persistence handoff) isn't worth saving 3-5 seconds of wait time. The user gets immediate feedback this way.
- **On-demand evaluator (`tutor evaluate <session_id>`):** explicit step. Rejected because extra friction reduces the probability the user actually evaluates. Automatic is the default.
- **Per-card JSON files (`cards/{id}.json`):** mirrored Stage 0's session storage pattern. Rejected because a single `cards.json` simplifies queries (e.g., "all due today") without sacrificing anything meaningful at this scale.

## 5. Architecture

```
[ Session end ]
       │
       ▼
[ Evaluator ] ────► OpenRouter (stronger model, e.g. gemini-2.5-pro)
       │              JSON-structured output, parsed via Pydantic
       │ list[GrowthPoint]
       ▼
[ SRSEngine.create_cards ] ──► cards.json
       │ list[Card]            (due_date = today + 1)
       ▼
[ session.json ] ──► appends growth_points field for traceability


[ tutor review ]
       │
       ▼
[ SRSEngine.due_today ] ──► cards.json
       │ list[Card]
       ▼
[ ReviewOrchestrator ]
       ├─► Recorder ──► WAV
       ├─► WhisperASR ──► transcript
       ├─► LLMGrader ──► OpenRouter (gemini-flash, cheap)
       │                   prompt: "grade attempt vs target, 0-5"
       │                   parsed integer
       ├─► SRSEngine.record_review ──► cards.json (atomic write)
       └─► TTS (target version, for ear)
```

### Module boundaries

Each new module has one job and a narrow interface, so each can be tested with mocks of its neighbors. The Evaluator never touches the SRS; the SRS doesn't know what an LLM is; the Grader doesn't manage card state.

## 6. Components

### 6.1 Evaluator (`tutor/evaluator.py`)

**Responsibility:** post-session transcript analysis. Pure function across the LLM client. No I/O of its own (caller persists the result).

**Interface:**
```python
class Evaluator:
    def __init__(self, llm: LLMClient, model: str): ...
    def evaluate(self, transcript: list[dict[str, str]]) -> list[GrowthPoint]
```

`model` here may differ from the dialog model — the evaluator uses a stronger model (default `google/gemini-2.5-pro` via `OPENROUTER_EVALUATOR_MODEL` env var) for better correction quality.

**GrowthPoint schema:**
```python
class GrowthPoint(BaseModel):
    tag: Literal["vocab", "grammar"]
    user_utterance: str         # verbatim
    corrected_version: str
    explanation: str            # 1-2 sentences
    context: str | None = None  # one line of dialog before, optional
```

**LLM prompt principles:**
- Strict JSON output (`response_format={"type": "json_object"}`).
- Focus only on vocab and grammar; explicitly skip filler words, ASR mistranscriptions, idiom/register issues, minor style.
- Return 3–5 items (not more, not fewer if possible).
- Address the student as an intermediate Russian-native speaker.

**Parse safety:** invalid JSON → one retry → on second failure return empty list and log warning. The session still ends cleanly; no cards just means no learning this session, never a crash.

**Cost:** ~3–5k input + ~500 output per session = roughly $0.005–0.01 on gemini-2.5-pro. Acceptable under the daily $0.5 cap.

### 6.2 SRS Engine

**Pure SM-2 in `tutor/srs.py`:**
```python
def next_interval(quality: int, prev_interval: int, repetitions: int, ease_factor: float) -> tuple[int, int, float]
```

Deterministic, no side effects, easy to test against boundary cases.

**Storage + orchestration in `tutor/srs_engine.py`:**
```python
class SRSEngine:
    def __init__(self, path: Path, now: Callable[[], date] = date.today): ...
    def create_cards(self, growth_points: list[GrowthPoint], session_id: str) -> list[Card]
    def due_today(self, limit: int | None = None, tag: str | None = None) -> list[Card]
    def record_review(self, card_id: str, quality: int) -> None
```

**Card schema:**
```python
@dataclass
class Card:
    id: str                          # 12-hex from uuid4
    created_from_session_id: str
    tag: Literal["vocab", "grammar"]
    user_utterance: str
    corrected_version: str
    explanation: str
    context: str | None

    ease_factor: float = 2.5
    interval_days: int = 0
    repetitions: int = 0
    due_date: str                    # ISO date
    last_review_quality: int | None = None
    review_history: list[dict] = field(default_factory=list)
```

**Storage:** single `cards.json` at project root. Atomic writes (tmp + `os.replace`). Loaded once in memory per process. gitignored.

**No dedup:** repeated mistakes produce repeated cards by design in Stage 1a.

### 6.3 LLM Grader (`tutor/grader.py`)

**Responsibility:** judge whether a spoken recall attempt matches the target corrected version. Returns an integer 0–5 for SM-2 input.

**Interface:**
```python
class LLMGrader:
    def __init__(self, llm: LLMClient, model: str): ...
    def grade(self, target: str, attempt: str) -> int
```

`model` is configured via `OPENROUTER_GRADER_MODEL` env var (default: same as dialog model, gemini-flash). Cheap, fast, sufficient for binary-ish judgment.

**Prompt:**
```
You are grading an English recall practice.
TARGET: "{target}"
STUDENT ATTEMPT (transcribed from speech): "{attempt}"
Grade 0-5: 0=wrong/silence, 1=vague hint, 2=partial, 3=essentially correct meaning,
4=correct with minor variation, 5=identical.
Be lenient about word order. Focus on the key improvement (vocab word or grammar pattern)
from the target, not exact wording.
Return ONLY the integer.
```

**Parse safety:** extract the first integer 0-5 from the response. If none found, log warning and default to 3 (neutral).

**Cost:** ~200 input + 1 output per card. Trivial.

### 6.4 Review Orchestrator (`tutor/review.py`)

**Responsibility:** load due cards, run each through the voice-recall loop, update SRS state. Same adapter shape as `SessionOrchestrator` — uses LLM (via grader), ASR, TTS, Recorder.

**Interface:**
```python
class ReviewOrchestrator:
    def __init__(self, grader, asr, tts, recorder, srs, per_session_card_limit: int = 25): ...
    def run(self, limit: int | None = None, tag_filter: str | None = None) -> ReviewSummary
```

`ReviewSummary` carries: cards_reviewed, quality_distribution (count per 0-5), elapsed_seconds.

**Per-card flow:**
1. Print: card N/total, tag, context, original utterance, prompt.
2. Recorder writes WAV to `tempfile.gettempdir()`.
3. ASR transcribes.
4. Grader scores attempt vs target.
5. Print score, target, explanation.
6. TTS speaks the target version (so user hears correct pronunciation).
7. `srs.record_review(card_id, quality=score)`.
8. Clean up temp WAV.
9. Next card.

**CLI escape:** typing `skip` records quality=0 and continues; typing `quit` exits the loop cleanly.

### 6.5 CLI changes (`tutor/cli.py`)

New subcommand:
```
tutor review [--limit N] [--tag vocab|grammar]
```

Wires real adapters (same Recorder/ASR/TTS as session, plus the new Grader and SRSEngine) and runs `ReviewOrchestrator`.

Friendly error handling for `ScenarioNotFoundError` (per polish #3).

## 7. Data Flow

### 7.1 Session lifecycle with Evaluator (updated)

```
Steps 1–5 unchanged from Stage 0.

5. User taps "end" (or turn limit hit, or budget exhausted).
6. Session loop exits.
7. Evaluator runs synchronously on the full transcript.
   ├─► On success: list[GrowthPoint], persisted to session.json under "growth_points".
   └─► On failure (LLM error / parse fail twice): session.json gets "growth_points_error".
8. SRSEngine.create_cards converts each GrowthPoint to a Card with due_date = today + 1.
   ├─► Cards appended to cards.json (atomic write).
   └─► session.json gets "cards_created": ["<id1>", ...] for back-reference.
9. session.end_session marks ended_at.
10. Print summary: N growth points, N cards created, due tomorrow.
```

### 7.2 Review lifecycle (new)

```
1. tutor review [--limit N] [--tag T]
2. SRSEngine.due_today(limit, tag) → list[Card]. If empty, print "No cards due today" and exit 0.
3. For each card:
   • Show context + original utterance + prompt.
   • Recorder.record_to_wav(temp_path).
   • ASR.transcribe(temp_path) → attempt_text.
   • Grader.grade(card.corrected_version, attempt_text) → 0-5 score.
   • Print score, target, explanation.
   • TTS.speak(card.corrected_version).
   • SRSEngine.record_review(card.id, score) — recalculates due_date.
   • os.remove(temp_path).
4. Print final summary.
```

### 7.3 Persistence layout

```
project_root/
├── budget.json                      (gitignored; daily caps state)
├── cards.json                       (gitignored; all SRS cards)
└── sessions/
    └── YYYY-MM-DD/
        └── <session_id>.json        (gitignored; turns + growth_points + cards_created)
```

## 8. Error Handling

| Failure | Handling |
|---|---|
| Evaluator LLM error (any) | 1 retry, then log warning, write `growth_points_error` to session, no cards created, session still ends cleanly |
| Evaluator returns malformed JSON | Same as above |
| Evaluator returns 0 or >5 items | Use what came back, no crash. 0 items = no cards. >5 = take first 5. |
| Grader returns non-integer response | Default quality = 3, log warning |
| ASR returns empty transcript in review | Quality = 0 automatically (no attempt to grade) |
| Budget exhausted during session evaluator | Session ends cleanly without cards, `growth_points_error` logged |
| Budget exhausted during review | Print message, exit review loop after current card |
| `cards.json` corrupted on read | Log error, exit with non-zero. User must restore from git or delete and start fresh. (No auto-recovery — corruption is rare and silent recovery hides bugs.) |
| Mid-review crash | Last card before crash already persisted (one card = one atomic write). Lost: at most the in-progress card's score. |

## 9. Budget

Same caps as Stage 0 ($0.5/day USD, 200k tokens/day, hardcoded). Two new cost sources:

- **Evaluator per session:** ~$0.005-0.01 (gemini-2.5-pro). At 1 session/day this is ~$0.3/month, well within cap.
- **Grader per card:** ~$0.0001 (gemini-flash). At 10 cards/day this is ~$0.03/month.

Total expected: well under $0.5/day even with daily use.

Settings additions:
```
OPENROUTER_EVALUATOR_MODEL=google/gemini-2.5-pro
OPENROUTER_GRADER_MODEL=google/gemini-2.5-flash    # falls back to OPENROUTER_MODEL if unset
```

## 10. Testing

### Unit tests (pytest)

- **`tests/test_srs.py`** — SM-2 boundary cases: q=0 reset, q=3/4/5 progressions, ease_factor floor at 1.3, first review (interval=1), second review (interval=6).
- **`tests/test_srs_engine.py`** — create_cards, due_today (with limit + tag filter), record_review applies SM-2 correctly, atomic write doesn't corrupt on simulated crash.
- **`tests/test_evaluator.py`** — happy path with mocked LLM returning canned JSON; malformed JSON → retry → second fail → empty list; oversize result → truncate to 5; LLM raises → empty list + warning.
- **`tests/test_grader.py`** — happy path; non-integer response defaults to 3; integer-with-text response parses correctly; budget-exceeded raises through.
- **`tests/test_review.py`** — full happy-path review loop (mocks for ASR/Grader/TTS/Recorder/SRS); skip command; quit command; empty due list; budget-exceeded mid-loop.

### Integration scenarios (mocked externals)

- End-to-end session → evaluator → cards created → review → SRS state updated. Verifies the full data flow.

### Manual smoke (Stage 1a step 12)

- Real session with new scenario (daily standup). Verify growth_points produced.
- Real review session. Verify recall flow and TTS playback.

### Not in Stage 1a

- Evaluator golden-set + before/after eval. Stage 1b — need real session data first.
- Grader calibration eval. Stage 1b.

## 11. Polish Fixes (from Stage 0 final review)

Each fix gets a regression test:

| # | Fix | Test |
|---|---|---|
| 1 | `Settings.openrouter_api_key: SecretStr`; LLMClient calls `.get_secret_value()` | Assert `repr(settings)` does not contain the key value |
| 2 | Wrap opening LLM call in `try/except BudgetExceededError` in `SessionOrchestrator.run` | Assert opening-call budget error produces clean exit with summary, not traceback |
| 3 | CLI catches `ScenarioNotFoundError`, prints friendly message, exits 2 | Assert `tutor interview --scenario bad-id` exits 2 with stderr message, no traceback |
| 4 | `storage._write` uses tmp + `os.replace` | Assert simulated mid-write crash leaves either old content or new content, never partial |
| 5 | Temp WAV files removed in session.py and review.py (in `finally` per turn/card) | Assert `tempfile.gettempdir()` has no `tutor_*` files after a session/review completes |

## 12. New Scenarios

Both follow the existing YAML structure (`id`, `name`, `difficulty`, `counterpart`, `goal`, `vocab_focus`, `opening_line`, `system_prompt_template`).

### 12.1 `daily_standup.yaml`

- **Counterpart:** tech lead at a US-based team's daily standup. Brief, no smalltalk.
- **Persona:** professional, time-conscious. Cuts off rambling. Asks about yesterday/today/blockers.
- **Goal:** practice the standup structure — yesterday's progress, today's plan, blockers — in concise English.
- **Vocab focus:** time estimates ("by end of week", "rough cut"), blocker phrasing ("blocked on", "waiting on"), dependency callouts ("after the X team merges").

### 12.2 `apartment_rental_abroad.yaml`

- **Counterpart:** landlord or rental agent showing an apartment in a US or EU city.
- **Persona:** friendly but business-like. Asks about job, income, move-in date, references.
- **Goal:** practice the rental conversation — lease terms, utilities, deposit, neighbourhood.
- **Vocab focus:** rental vocabulary (`lease`, `deposit`, `utilities included`, `month-to-month`, `co-signer`), hedging when discussing finances ("competitive salary", "stable income").

Both ship with the same StrictUndefined Jinja safety as the existing scenario.

## 13. Decisions

| Decision | Choice | Why |
|---|---|---|
| Evaluator timing | Synchronous after session | Immediate feedback, no background-process complexity |
| Evaluator model | gemini-2.5-pro (configurable) | Stronger model for better corrections; cost manageable |
| Cards storage | Single `cards.json` | Simpler queries than per-card files; fine at scale |
| SRS algorithm | SM-2 | Well-understood; matches Stage 0 spec choice |
| Review style | Voice answer + LLM grade | Maximally aligned with voice-first goal |
| Grader model | gemini-flash | Cheap; binary-ish judgment doesn't need strong model |
| Dedup | None | Repeated mistakes = useful signal, not noise |
| DB migration | Deferred to Stage 1b | JSON works; Postgres premature now |
| Old session backfill | None | Past sessions stay as-is |

## 14. Open Questions / Risks

- **Whisper mistranscription in review:** if the user said the correct answer but ASR garbled it, the grader sees gibberish and scores low. Mitigation in Stage 1a: none. Observe in real use. If frequent, add a "click to type your answer instead" fallback in Stage 1b.
- **Grader calibration unknown:** no golden set yet for the grader. Initial behavior calibrated by feel. Stage 1b builds the calibration set.
- **Evaluator output quality at intermediate level:** the prompt asks for vocab/grammar only, but the LLM may still surface idiom issues. Observe and tighten prompt if needed.
- **Repeated growth points across sessions:** without dedup, the SRS may fill with near-duplicates. Track frequency. If it harms review experience, add similarity-based dedup in Stage 1b.
- **`OPENROUTER_EVALUATOR_MODEL` availability:** gemini-2.5-pro must be accessible via OpenRouter. If not, fall back to gemini-2.5-flash as default. Confirm before implementation.

## 15. Success Criteria (post-Stage 1a, after 2-3 weeks of use)

Stage 1a is considered successful if:

- ≥10 sessions completed with the new evaluator producing growth_points on each.
- ≥30 cards accumulated in `cards.json`.
- ≥5 review sessions completed using `tutor review`.
- User reports (qualitatively): at least one card they "almost forgot" that the grader's score reflected accurately (i.e., the SRS recall mechanism is genuinely teaching, not just clicking through).
- Both new scenarios used at least twice each.
- All 5 polish fixes have regression tests passing.
- `cards.json` has not been manually edited or restored — the data layer holds.

When these are true, Stage 1a is done. Stage 1b proposals (Postgres migration + golden-set tooling + dedup) can then draw from real session data.
