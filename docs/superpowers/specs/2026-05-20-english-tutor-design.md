# English Tutor — Design Document

- **Date:** 2026-05-20
- **Author:** Stas Arkhipov
- **Status:** Draft, pending implementation plan

## 1. Context

Personal English learning app for the author, who is preparing to move abroad in ~12 months and find remote work in foreign currency. The brainstorm established these constraints and motivations:

- **Author profile:** ML/AI engineer at Grand Line, Russian native, school-level English foundation. Comfortable reading technical English (docs, papers), but weak in real-time listening and speaking.
- **Time budget:** 15–30 minutes per day, realistically. The design must work at the low end of this range.
- **Timeline:** 12 months to be operational across four scenario classes — tech interviews, daily remote work, life-abroad practical situations, casual smalltalk / networking.
- **Past failure modes:** Duolingo-style apps (boring grind, no concrete utility), watching series in English (motivation died without active link to real life). The bottleneck is motivation and habit, not access to content.

**Core hypothesis:** a voice-first AI tutor focused on concrete scenarios will solve the motivation problem because each session yields visible utility for a specific real-world situation the user will face within months.

## 2. Goals

- Visible speaking and listening progress across the four scenario classes.
- Habit-forming UX: short sessions, near-zero friction to start, daily streak that's easy to maintain on a busy day.
- Each session produces concrete, persistent artifacts (vocab cards, growth points) so progress is felt week-over-week, not just claimed.

## 3. Non-Goals

- Multi-user / multi-tenant. Single user (the author) for the foreseeable future.
- General English curriculum or "Unit N of 30" structure. Scenarios only.
- Phoneme-level pronunciation scoring (V2+ at earliest).
- Standardized exam prep (IELTS / TOEFL).

## 4. Approach

**AI dialogue partner.** A voice-first app where the user picks a scenario, has a 10–15 minute voice conversation with an LLM playing the counterpart (recruiter, teammate, landlord, …). After the session, an evaluator LLM produces 3–5 "growth points" — places where the user's English was wrong, awkward, or unnatural — and turns them into vocab cards. Cards enter a spaced-repetition schedule starting the next day.

### Alternatives considered

- **Content-driven (podcasts / articles + AI questions):** rejected as the primary approach because the user's gap is output (speaking), not input. A content layer may be added later as a supplementary listening source.
- **Telegram-native ambient tutor:** rejected as primary because rich voice scenarios need a better UI than Telegram provides. TG may be added later as a low-friction entry point and reminder layer.

## 5. Architecture

```
[ Client: CLI (Stages 0–1) → React PWA (Stage 2) ]
            │ HTTPS / local socket
            ▼
[ FastAPI backend ]
  • Session orchestrator (Voice Loop)
  • LLM client → OpenRouter
       - gemini-3-flash for in-session counterpart
       - a stronger model (gemini-3-pro or similar) for evaluator
  • ASR adapter → Whisper large-v3 on Mac MPS (already installed for transcribing meetings)
  • TTS adapter → macOS `say` (Stage 0) / browser SpeechSynthesis (Stage 2) / ElevenLabs (later, if needed)
  • Evaluator
  • SRS Engine (SM-2 algorithm)
            │
            ▼
[ Persistence ]
  • Stage 0: JSON files on disk (sessions/{date}.json)
  • Stage 1+: PostgreSQL via docker-compose, schema: users, scenarios, sessions, utterances, vocab_cards, card_reviews
```

### Design principle: component isolation

Scenario Library, Voice Loop, Evaluator, and SRS Engine are independent units with explicit interfaces. Replacing Whisper with another ASR must not break the SRS Engine. Replacing SM-2 with FSRS must not affect the dialog loop. This makes future experiments cheap and lets us evolve each part without cascade rewrites.

## 6. Components

### 6.1 Scenario Library

- **Responsibility:** stores scenarios as YAML, builds the system prompt for a given scenario at session start.
- **Interface:**
  - `get_scenarios(level, tags) -> list[Scenario]`
  - `build_system_prompt(scenario_id, user_profile) -> str`
- **Storage:** YAML files in `scenarios/`. Each file: setting, counterpart role, persona, difficulty, goal of dialog, vocab focus tags.
- **Dependencies:** none (Jinja2 for templating).
- **MVP scenarios** (Stage 0: 1; Stage 1: 3):
  1. Tech interview, behavioral (Stage 0)
  2. Daily standup with US-based team (Stage 1)
  3. Apartment rental conversation abroad (Stage 1)

### 6.2 Voice Loop (Session Orchestrator)

- **Responsibility:** runs a live session — user audio → ASR → LLM → TTS → user audio, looping until session ends.
- **Interface:**
  - `start_session(scenario_id) -> session_id`
  - `submit_audio(session_id, audio_blob) -> (audio_response, transcript_user, transcript_llm)`
  - `end_session(session_id) -> full_transcript`
- **State:** in-process conversation history, plus per-turn checkpoint to disk/DB.
- **Dependencies:** LLM client, ASR client, TTS client, persistence layer.
- **Behavior on crash:** if the orchestrator dies mid-session, the session is marked `incomplete` and not sent to the Evaluator. Acceptable risk for MVP — we don't persist conversation history to Redis or similar.

### 6.3 Evaluator

- **Responsibility:** post-session analysis. Receives the full transcript, returns 3–5 GrowthPoint objects.
- **GrowthPoint structure:**
  - `user_utterance`: what the user actually said
  - `natural_version`: how a fluent speaker would say it
  - `explanation`: why the natural version is better (grammar, idiom, register, vocabulary)
  - `tag`: one of `grammar | vocab | idiom | register | clarity`
- **Interface:** `evaluate(transcript) -> list[GrowthPoint]`
- **Why separate from the dialog LLM:** different prompt, different model (stronger, a stronger one), can be A/B-tested independently, easier to eval against a golden set.

### 6.4 SRS Engine

- **Responsibility:** creates vocab cards from GrowthPoints, schedules reviews using SM-2, returns due cards for today.
- **Interface:**
  - `create_cards(growth_points) -> list[Card]`
  - `due_today(user_id) -> list[Card]`
  - `record_review(card_id, quality: 0..5) -> next_due`
- **Card structure:**
  - `front`: user's original phrase + context (1 line from the dialog before)
  - `back`: natural version + explanation
  - `audio_back`: TTS of natural version (cached)
- **Review format:** show front + ask "how would a fluent speaker say this?" → user attempts (typed or voiced) → reveal back → self-grade quality 0–5.
- **Dependencies:** persistence layer only.

### 6.5 Session API (thin layer)

FastAPI endpoints that compose the four components into HTTP routes. Contains no business logic — pure dispatcher. Keeps the components testable in isolation.

## 7. Data Flow

### 7.1 Session lifecycle

```
1. Client opens app
   GET /today → { due_cards: N, suggested_scenario: id }

2. (Optional) SRS review, 3–5 min
   For each card: show front → user attempts → POST /review {card_id, quality}

3. User starts scenario
   POST /sessions {scenario_id}
     backend:
       • INSERT row in sessions
       • build system prompt from Scenario Library
       • LLM generates opening line as counterpart
       • TTS → audio blob
     ← { session_id, first_audio, first_text }

4. Voice loop (repeats):
   • UI: user holds mic, speaks, releases
   • POST /sessions/{id}/turn (multipart: audio_blob)
     backend:
       • Whisper STT → user_text
       • append to conversation history
       • LLM call with full history → counterpart reply
       • TTS → audio blob
       • INSERT into utterances (user_audio_path, user_text, llm_text, llm_audio_path, timestamps)
     ← { llm_audio, llm_text, user_text }
   • UI plays llm_audio, shows both texts under reveal

5. User taps "End"
   POST /sessions/{id}/end
     backend (async, doesn't block UI):
       • Evaluator gets transcript
       • LLM call → 3–5 GrowthPoints
       • SRS Engine: create_cards(growth_points), due = tomorrow
       • UPDATE sessions {ended_at, growth_points_json}
     ← { summary, cards_created }

6. UI shows summary:
   for each growth point: user's phrase → natural version → explanation
```

### 7.2 Daily cycle

- **On app open:** streak count, "N cards due today", scenario recommendation (round-robin by tags so the user doesn't stagnate in one).
- **Throughout the day:** SRS cards can be reviewed independently of a session (micro-mode, ~30 seconds each).
- **Weekly:** progress digest — sessions completed, retention rate of cards at N days, which tags are tanking.
- **Monthly:** LLM-judged speaking-confidence delta — 10 random utterances from the last week vs 10 from the first week, judge LLM rates improvement.

### 7.3 Persistence checkpoints

| When | Table | Why |
|---|---|---|
| Each turn | `utterances` | replay, debug, future audio analytics |
| End of session | `sessions.growth_points_json` | post-hoc review |
| Card created | `vocab_cards` (due = now + 1 day) | SRS scheduler |
| Each review | `card_reviews` (quality, interval_after) | recompute next due |

### 7.4 Intentional non-persistence

- LLM conversation history lives in process memory between turns. If the backend dies mid-session, the session ends. Cheaper than Redis. Acceptable for MVP.
- Audio blobs are kept 7 days, then auto-deleted (a placeholder in the transcript remains).

## 8. Error Handling

### 8.1 External services

| Failure | Handling |
|---|---|
| OpenRouter 5xx / timeout on turn | 1 retry with 1s jitter, then surface "connection issue, tap to retry"; turn is not recorded |
| OpenRouter 429 (rate limit) | Exponential backoff, UI shows "API congestion, waiting…" |
| Whisper OOM on MPS | Fallback to browser Web Speech API (worse for Russian accents, but session survives) |
| TTS fails | Fallback to browser SpeechSynthesis with a "fallback voice" badge |
| OpenRouter account out of credit | Hard stop: "Top up account" message, session cannot start |

### 8.2 Quality issues (caught via logging / eval, not runtime)

- **ASR misrecognition:** user can tap their own transcribed line and edit before submitting the turn. This is also a learning signal — if Whisper consistently mistranscribes a sound, the user knows to work on it.
- **LLM breaks role** (responds as "AI assistant" instead of the counterpart): detected via the Evaluator stage rules, session flagged for prompt-tuning review.
- **Robotic TTS:** not blocking in MVP. Tolerable. Switch to ElevenLabs / OpenRouter TTS later if it actively kills motivation.

### 8.3 User-side

- **Network drop mid-turn:** audio blob saved to localStorage, retried when network returns.
- **App closed mid-session:** session is marked `incomplete`, evaluator skipped. On restart, user is offered "resume" or "start fresh".
- **Mic permission denied:** onboarding flow explains how to enable it. App is unusable without mic — this is core.

## 9. Budget Discipline

The user's work-issued aitunnel.ru token (with a ~2000 ₽/day company-set cap) is **for Grand Line tasks only**. This project uses a separate personal OpenRouter account.

### 9.1 OpenRouter-side limits

- Daily soft cap: $0.5, configured in the OpenRouter dashboard.
- Account holds a small prepaid balance (e.g., $5–10) so even a runaway bug can't drain a credit card.

### 9.2 Application-side hard caps

```python
DAILY_TOKEN_BUDGET = 200_000      # tokens, tracked via response metadata
MONTHLY_USD_BUDGET = 5            # USD, tracked via response cost field
PER_SESSION_TURN_LIMIT = 25       # prevents one runaway session from eating the day
```

When any limit is hit, the app soft-blocks new sessions with a "Today's quota done, come back tomorrow" message.

### 9.3 Expected actual cost

A 15-minute session is roughly 15k input + 2.5k output tokens for the dialog, plus ~3k + 800 for the evaluator. On gemini-3-flash with OpenRouter markup: **under $0.02 per session**. The $0.5/day cap is a safety net, not an expected daily spend.

### 9.4 Secrets handling

- API key lives in a `.env` file in the project root. `.env` is in `.gitignore` from the first commit.
- Loaded via `pydantic-settings`, accessed in code as `settings.openrouter_api_key`. Never hardcoded. Never logged. Never pasted into chat or commit messages.
- If the key is ever exposed (e.g., accidentally shown in a screenshot or chat log), the response is: revoke immediately on OpenRouter, generate a new one, update `.env`.

## 10. Testing

### 10.1 Unit tests (deterministic)

- **SRS algorithm (SM-2):** boundary cases — first card, complete failure, perfect recall, failure streaks. Pure function `next_interval(quality, prev_interval, ease_factor)`, trivial to test.
- **Budget tracker:** token accumulation, hard cutoff at threshold, daily/monthly reset behavior.
- **Scenario template rendering:** Jinja substitutions, required-field validation.
- **Card deduplication:** when a new GrowthPoint resembles an existing card (embedding similarity > threshold), it's merged, not duplicated.

Pytest, no network, runs on every commit.

### 10.2 Integration tests (with mocked externals)

| Scenario | Mocks |
|---|---|
| Happy-path session (5 turns + end) | OpenRouter → canned responses, Whisper → fixed transcript, TTS → silent mp3 |
| Session with retry after OpenRouter 500 | First call returns 500, second call OK |
| Rate limit (429) | Verify backoff timing |
| Budget exceeded mid-session | Returns budget error, turn not recorded |

Mocks are built via interface classes (`LLMClient`, `ASRClient`, `TTSClient`) with test implementations. Tests don't break when signatures evolve.

### 10.3 LLM eval (golden-set)

Mirrors the eval discipline used at Grand Line — no prompt change is merged without before/after on the golden set.

**Voice Loop counterpart eval:**

- Golden set: 20 mini-scenarios, each with a fixed system prompt + 5 pre-recorded user turns.
- Run, capture LLM responses, score with metrics:
  - `in_role`: LLM didn't break character ("As an AI…"). Judged via a second LLM call or rule-based heuristics.
  - `language_consistency`: response is in English (no Russian leak).
  - `length_in_bounds`: 1–3 sentences. No graphomania.
- Run before/after on every system-prompt change.

**Evaluator eval:**

- Golden set: 15 transcripts (collected during Stage 1 from real sessions) annotated with ground-truth growth points.
- Metric `recall@5`: of the ground-truth errors, how many did the evaluator catch in its 5 suggestions?
- Metric `precision`: of the 5 suggestions, how many are real errors (not false positives)?
- No evaluator prompt change merged without a non-regression on these metrics.

### 10.4 Manual smoke + telemetry

- Before each "release" to the personal install: one full session per scenario, by hand.
- Lightweight telemetry: SQL queries in a Jupyter notebook once a week — `sessions.completed_rate`, `cards.retention_at_7d`, `avg_session_turns`. No Grafana / Sentry in MVP.

### 10.5 Not in MVP

- Browser E2E tests (Playwright). Too expensive for the value.
- Load testing. One user.
- Mutation testing.

## 11. MVP Scope

### Stage 0 — CLI prototype (~1 week focused, or 2–3 weeks at 30 min/day)

**Goal:** validate that the core voice loop works AND that talking to the LLM in role feels good to the user. The unknowns we're de-risking are technical (does the loop run end-to-end?) and human (does the user actually want to do this every day?).

Included:

- Python CLI: `python tutor.py interview`.
- Single scenario: **tech interview, behavioral**.
- Voice loop: microphone → Whisper → OpenRouter LLM → macOS `say` → speakers.
- Session transcript saved to `sessions/{date}.json`.
- Budget tracker with hard stop at $0.5/day.
- Secrets in `.env`, `.env` gitignored from first commit.

Excluded (deliberately):

- No UI beyond the CLI.
- No vocab cards, no SRS, no Evaluator.
- No database (JSON files are enough).
- No additional scenarios.

### Stage 1 — Full backend MVP (still CLI, no web)

Added:

- PostgreSQL via docker-compose, schema: users, sessions, utterances, vocab_cards, card_reviews.
- Evaluator producing 3–5 GrowthPoints per session.
- SRS Engine (SM-2) generating and scheduling cards.
- Two more scenarios: "daily standup" and "apartment rental abroad".
- CLI review command: `python tutor.py review`.

Stays in CLI for 2–4 weeks to collect data and build the evaluator golden set from real sessions. Catching UX issues in CLI is much faster than in a PWA.

### Stage 2 — PWA frontend

Only after Stage 1 is in active daily use:

- React PWA on top of the existing backend.
- Voice loop via WebAudio + MediaRecorder.
- SRS review screen, progress dashboard.
- Scenarios expanded to 8–10.
- Optional content layer (podcast / article + AI questions) if a listening gap remains.

### Out of scope across all MVP stages

| Feature | Why deferred |
|---|---|
| Telegram bot entry point | Validate core first; TG is an optimization |
| Phoneme-level pronunciation scoring | Heavy pipeline, low value relative to MVP cost |
| ElevenLabs TTS | macOS `say` and browser SpeechSynthesis are good enough to start |
| Multi-user / auth | Single user for now |
| Adaptive difficulty in real time | Fix a level first, tune empirically |
| Speaking-confidence score visualization | Need data first; add after Stage 1 |
| Fancy SRS variants (FSRS, etc.) | SM-2 is well-understood, MVP-sufficient |

## 12. Decisions

| Decision | Choice | Why |
|---|---|---|
| Implementation language | Python | Consistent with GL stack; Whisper/aitunnel patterns reusable |
| First scenario | Tech interview, behavioral | Concrete pre-move utility; well-defined turn structure |
| Path | CLI-first (Stage 0) before any PWA | De-risk core loop before investing in UI |
| LLM access | Personal OpenRouter account, separate from work aitunnel | Ethical, operational, and privacy separation |
| SRS algorithm | SM-2 | Simple, well-understood; upgrade to FSRS later if needed |
| ASR | Whisper large-v3 on MPS (locally installed) | Already in user's stack, no cost, good quality |
| TTS | macOS `say` (Stage 0) | Free, zero setup, "good enough" to validate the loop |

## 13. Open Questions

- **Whisper integration model:** load once at backend start (memory cost) or subprocess per request (latency cost)? Decide during Stage 0 implementation, measure both.
- **TTS endurance:** is macOS `say` actually tolerable for daily 15-minute sessions, or annoying enough to motivate switching to ElevenLabs in Stage 1? Validate by use, not by guessing.
- **Counterpart LLM choice:** start with gemini-3-flash; if roleplay quality is weak (breaks role, robotic, off-topic), evaluate alternatives (e.g. gpt-4o-mini) before Stage 1.
- **Evaluator LLM choice:** needs to be stronger than the counterpart model. Candidates: gemini-3-pro or similar. Cost trade-off determined empirically when the evaluator golden set exists.
- **Audio retention period:** 7 days assumed for blob retention. Revisit if the user actively wants to re-listen to older sessions.

## 14. Success Criteria (post-Stage 1)

The MVP is considered successful if, after 4 weeks of Stage 1 use:

- The user has completed ≥ 20 sessions (≈ daily, with normal misses).
- Cards `retention_at_7d ≥ 60%` — the user is genuinely learning, not just clicking.
- The user reports (qualitatively) at least one moment where something learned in a session helped in a real interaction (work standup, conversation, etc.).
- The evaluator golden set exists (≥ 15 annotated transcripts), and at least one before/after eval has been run on a prompt change.
