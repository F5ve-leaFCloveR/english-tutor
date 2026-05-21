# Stage 2a — Browser UI (Backend API + React Frontend) Design

- **Date:** 2026-05-21
- **Author:** Stas Arkhipov
- **Status:** Draft, pending implementation plan

## 1. Context

Stages 0, 1a, and 1b shipped a working CLI tutor on `main`: voice-loop sessions, SRS-scheduled review, polish-grade error handling, and a `tutor stats` command. The CLI is functional but cumbersome for daily use — pressing Enter twice to record, reading growth points in a terminal, no visible streak indicator.

Stage 2a converts the four CLI flows (session, review, stats, scenario picker) into a browser UI: a FastAPI backend wrapping the existing modules, and a React + Vite frontend with chat-style session screen and push-to-talk voice loop. The CLI continues to work unchanged.

This is Stage 2 broken into three: Stage 2a (this spec) ships the working UI for localhost daily use. Stage 2b adds polish (settings page, history view, charts, mobile-network access). Stage 2c adds PWA features and proper deploy.

## 2. Goals

- All four core flows (browse scenarios, run session, review cards, view stats) work end-to-end in the browser.
- Voice loop in browser feels at least as natural as Telegram/WhatsApp voice messages: hold the mic button, release to send, hear the reply.
- The existing CLI commands continue to work without regressions — they share the same storage and Python modules.
- The full app runs on `localhost:8000` from a single command, no auth, no external deploy.

## 3. Non-Goals

- PWA features (manifest, service worker, offline tolerance, mobile install). Stage 2c.
- Mobile network access (opening from phone over local WiFi). Stage 2c.
- VPS deploy or hosting. Stage 2c.
- Settings page (TTS voice picker, theme, budget caps UI). Stage 2b.
- History browser, past sessions list, edit/delete operations. Stage 2b.
- Stats charts / visualization. Stage 2b — plain text+numbers in 2a.
- Auth / multi-user. Possibly never; this is solo.
- Streaming ASR (live partial transcripts during recording). Stage 2b if desired.
- Backend TTS (ElevenLabs etc.). Browser SpeechSynthesis only in 2a.
- Cross-browser perfection. Chrome + Safari on macOS must work; Firefox/Edge as bonus.

## 4. Approach

**Stateless API + persist-everything-immediately.** Backend does not hold long-lived session orchestrator objects. Each `/turn` call loads the session JSON from disk, builds the LLM context from stored utterances, runs LLM/ASR, persists the new turn, returns the reply. No in-memory session manager. Backend restart never loses state.

**Single FastAPI process serves API and built frontend.** After `npm run build`, Vite outputs to `tutor/web/static/` and FastAPI mounts it. No separate dev server in production. Localhost only — FastAPI binds `127.0.0.1` with no auth.

Alternatives considered:

- **Server-side stateful session manager:** more efficient (no per-turn storage reads), but memory leaks if sessions don't end, backend restart loses state, harder to test. Rejected.
- **Mostly client-side state:** frontend keeps history, sends full conversation with each request. Bloated payloads, history-state confusion. Rejected.
- **HTMX + Jinja2 templates instead of React:** voice recording still requires JS, so the "minimum JS" advantage is small. Chat-style UI with reactive state is easier in React. Rejected.

## 5. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser (React + Vite + Tailwind)                              │
│                                                                 │
│  Pages: /              → ScenariosPage (list, click to start)   │
│         /session/:id   → SessionPage (chat-style + voice loop)  │
│         /review        → ReviewPage (card flip + voice grade)   │
│         /stats         → StatsPage (text dashboard)             │
│                                                                 │
│  State: React Query (server), useState (UI), no Redux/Zustand   │
│  Voice: MediaRecorder (push-to-talk), SpeechSynthesis (TTS)     │
└─────────────────────────────────────────────────────────────────┘
                            │ HTTP/JSON + multipart audio
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  FastAPI (127.0.0.1:8000)                                       │
│                                                                 │
│  /api/scenarios            GET                                  │
│  /api/sessions             POST (start)                         │
│  /api/sessions/{id}/turn   POST (multipart audio → reply)       │
│  /api/sessions/{id}/end    POST (eval + cards)                  │
│  /api/review/due           GET                                  │
│  /api/review/{cid}/grade   POST (multipart audio | skip)        │
│  /api/stats                GET                                  │
│  /api/budget               GET                                  │
│  /                         GET (built React index.html)         │
│  /static/*                 GET (Vite assets)                    │
│                                                                 │
│  tutor/web/api.py       — FastAPI app, routes (thin layer)      │
│  tutor/web/services.py  — orchestration (reuses Stage 1 modules)│
│  tutor/web/schemas.py   — Pydantic request/response models      │
│  tutor/web/errors.py    — exception → JSON mappers              │
│                                                                 │
│  Whisper preloaded at startup (lifespan).                       │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│  Existing storage and modules (no changes)                      │
│    sessions/{date}/{id}.json   cards.json   budget.json         │
│    SessionStorage, SRSEngine, Evaluator, LLMGrader,             │
│    StatsCalculator, scenarios loader, BudgetTracker             │
└─────────────────────────────────────────────────────────────────┘
```

### Design principles

- **Reuse, don't duplicate.** `services.py` orchestrates existing modules instead of reimplementing the loops.
- **CLI stays alive.** `tutor interview` / `tutor review` / `tutor stats` continue to work. No regressions to their tests.
- **Each Python module has one job.** `api.py` is thin route handlers, `services.py` is orchestration, `schemas.py` is data shapes, `errors.py` is exception mapping.
- **Frontend pages are thin too.** Pages compose hooks + components. Hooks own the side-effect logic (recording, TTS, fetch).

## 6. Components

### 6.1 Backend — `tutor/web/api.py`

FastAPI app with lifespan that preloads Whisper. Catches all custom exceptions and maps them to JSON responses via handlers registered in `errors.py`. Mounts `static/` for frontend assets and adds a catch-all for non-`/api` routes to serve `index.html` (so React Router deep links work on reload).

Routes are thin: parse request → call service function → return response.

### 6.2 Backend — `tutor/web/services.py`

Pure-Python functions, no HTTP knowledge. Each function takes typed args, returns typed result, raises typed exceptions.

```python
def list_scenarios_service() -> list[ScenarioSummary]: ...

def start_session_service(scenario_id: str, settings, deps) -> StartSessionResult:
    # creates session, calls LLM for opening, persists, returns id+opening_text

def turn_service(session_id: str, audio_bytes: bytes, deps) -> TurnResult:
    # ASR → load session → build messages → LLM → persist turn → return texts

def end_session_service(session_id: str, deps) -> EndSessionResult:
    # evaluator → growth_points persist → SRS create_cards → end_session

def review_due_service(limit, tag, deps) -> list[Card]: ...

def grade_card_service(card_id, audio_bytes_or_skip, deps) -> GradeResult:
    # ASR (if audio) → grader → SRS.record_review → return result

def stats_service(days, deps) -> StatsSummary: ...

def budget_service(deps) -> BudgetSummary: ...
```

`deps` is a small struct of preloaded singletons (Whisper, LLMClient, BudgetTracker, paths). FastAPI dependency injection assembles it.

### 6.3 Backend — `tutor/web/schemas.py`

Pydantic models mirroring the API contract from section §6.5. Used both for request validation and response serialization.

### 6.4 Backend — `tutor/web/errors.py`

Custom exceptions raised by services + FastAPI handlers that map them to HTTP responses with structured JSON. Mapping in §6.5.

### 6.5 API contract

```
GET  /api/scenarios
  → 200 {"scenarios": [{"id": str, "name": str, "difficulty": str}, ...]}

POST /api/sessions
  body: {"scenario_id": str}
  → 200 {"session_id": str, "opening_text": str}
  → 404 {"error": "scenario_not_found", "scenario_id": str}
  → 429 {"error": "budget_exhausted", "message": str}

GET  /api/sessions/{id}
  → 200 {full session JSON: scenario_id, started_at, ended_at, turns,
         opening_text, growth_points?, cards_created?, growth_points_error?}
  → 404 {"error": "session_not_found"}
  Used for page reload to reconstruct conversation state.

POST /api/sessions/{id}/turn
  body: multipart/form-data audio file
  → 200 {"user_text": str, "assistant_text": str}
  → 404 {"error": "session_not_found"}
  → 422 {"error": "no_speech_detected"}
  → 429 {"error": "budget_exhausted"}

POST /api/sessions/{id}/end
  → 200 {"session_id": str, "ended_at": str,
         "growth_points": list[dict], "cards_created": list[str],
         "growth_points_error": str | null}
  → 404 {"error": "session_not_found"}

GET  /api/review/due?limit=N&tag=vocab|grammar
  → 200 {"cards": list[Card], "total_due": int}

POST /api/review/{card_id}/grade
  body: multipart audio OR JSON {"skip": true}
  → 200 {"card_id": str, "user_attempt_text": str,
         "quality": 0..5, "target": str, "explanation": str,
         "next_due": str}
  → 404 {"error": "card_not_found"}
  → 429 {"error": "budget_exhausted"}

GET  /api/stats?days=N           # days optional
  → 200 <StatsSummary as JSON>

GET  /api/budget
  → 200 {"usd_today": float, "tokens_today": int,
         "daily_usd_cap": float, "daily_token_cap": int}
```

Exception → HTTP map: `ScenarioNotFoundError`→404, `CardNotFoundError`→404, `BudgetExceededError`→429, session `FileNotFoundError`→404, empty Whisper transcript→422, Pydantic validation→422 (default).

### 6.6 Frontend project layout

```
frontend/
├── package.json
├── vite.config.ts          # proxy /api → :8000 in dev
├── tsconfig.json
├── tailwind.config.js
├── postcss.config.js
├── index.html
└── src/
    ├── main.tsx
    ├── App.tsx                       # BrowserRouter + Layout + Routes
    ├── api/
    │   ├── client.ts                 # typed fetch wrappers
    │   └── types.ts                  # mirror of backend schemas
    ├── hooks/
    │   ├── useRecorder.ts            # MediaRecorder + push-to-talk
    │   └── useTTS.ts                 # SpeechSynthesis wrapper
    ├── components/
    │   ├── Layout.tsx                # header (budget, nav) + outlet
    │   ├── BudgetIndicator.tsx
    │   ├── MessageBubble.tsx
    │   ├── PushToTalkButton.tsx
    │   ├── ReviewCard.tsx
    │   └── SessionSummary.tsx        # end-of-session growth_points display
    └── pages/
        ├── ScenariosPage.tsx
        ├── SessionPage.tsx
        ├── ReviewPage.tsx
        └── StatsPage.tsx
```

### 6.7 Frontend stack and patterns

- **React 18 + TypeScript** — typed components, strict mode.
- **Vite** — dev server + production bundler.
- **Tailwind CSS** — utility classes, mobile-first responsive.
- **React Router v6** — client routing, BrowserRouter.
- **@tanstack/react-query** — server state for scenarios, due cards, stats, budget.
- **Native `fetch`** in `api/client.ts` — no axios.
- **lucide-react** — icon library.

State management:
- Server data → React Query (refetch on focus, cache by query key)
- Session conversation → local React state for the message array, persisted server-side via `/turn`
- UI state → `useState` per component

### 6.8 `useRecorder` hook

```typescript
function useRecorder(): {
  isRecording: boolean;
  durationMs: number;        // for visual timer
  startRecording: () => Promise<void>;
  stopRecording: () => Promise<Blob | null>;  // null if too short
  cancelRecording: () => void;
} { /* MediaRecorder + state machine */ }
```

- `getUserMedia({audio: true})` on first start, stream cached.
- MIME type fallback chain: `audio/webm;codecs=opus` → `audio/mp4` → `audio/wav` (whichever is supported).
- Hard cap 60 seconds; auto-stop with `tooLong` flag.
- Min duration 500ms; below that → returns `null` (treat as accidental tap).
- Cancel: discards current MediaRecorder, no upload.

### 6.9 `useTTS` hook

```typescript
function useTTS(): {
  speak: (text: string) => Promise<void>;
  isSpeaking: boolean;
  voices: SpeechSynthesisVoice[];      // for future settings page
} { /* SpeechSynthesis wrapper */ }
```

- Waits for `voiceschanged` event on first mount; caches voice list.
- `speak()` returns a Promise resolved on `utterance.onend`.
- Voice selection: defaults to OS default. Stage 2a uses `localStorage.getItem('ttsVoice')` if set; settings UI in 2b.
- iOS Safari requires user gesture for first `.speak()` — opening line of a session is triggered only after the user clicks "Start session," not on route mount.

### 6.10 PushToTalkButton component

- Big circular button (min 80×80px).
- Binds `onPointerDown` / `onPointerUp` / `onPointerLeave` (handles both mouse and touch).
- Visual states: idle → pressed (pulsing red) → uploading (spinner) → idle.
- Shows recording duration as a small chip overlaying the button.
- Error states render as a subtle red border + tooltip.

### 6.11 MessageBubble component

- Variants: `user` (right-aligned, blue) | `assistant` (left-aligned, gray).
- Shows speaking indicator (📢 icon) on assistant bubbles while TTS is playing.
- Long-press / right-click → menu with "Replay" (re-trigger TTS) and "Copy text".

### 6.12 SessionPage

Composition:

1. Header: scenario name + budget indicator.
2. Scrollable message list (Tailwind `overflow-y-auto`).
3. Footer with PushToTalkButton + EndSession button.
4. On `/end` response: SessionSummary modal displays growth_points + cards_created, then routes back to `/`.

Flow:
- Mount with `:id` → call `/api/sessions` already done? Or page receives session_id from ScenariosPage navigation. ScenariosPage calls `POST /api/sessions` then navigates to `/session/:id` with state containing the opening text.
- PushToTalkButton hold → record → release → POST `/turn` → append both bubbles to local state → TTS plays assistant text.
- End button → POST `/end` → show summary modal.

### 6.13 ReviewPage

Composition:

1. Progress indicator at top ("Card 3/8 — vocab").
2. Card front: original utterance + prompt "How would you say it more precisely?"
3. PushToTalkButton + Skip + Quit buttons.
4. After grade: show score (1-5), target version, explanation. Auto-play TTS of target.
5. Auto-advance to next card after 3 seconds OR user clicks "Next".

### 6.14 StatsPage

Plain text panels (no charts in 2a):
- Streak section with last-activity date
- Sessions panel (total / last 7d / last 30d / by scenario)
- Cards panel (total / by tag / by state)
- Retention section

Optional query param `?days=N` filters session counts.

### 6.15 ScenariosPage

List of clickable cards. Each shows scenario name + difficulty. On click → POST `/api/sessions` → navigate to `/session/:id`.

## 7. Data Flow

### 7.1 Session lifecycle (browser-driven)

```
1. User on / → clicks scenario card
2. POST /api/sessions {scenario_id}
     ├─ services.start_session: storage.create_session
     ├─ load scenario, build system prompt
     ├─ LLM.complete for opening line
     └─ returns {session_id, opening_text}
3. Frontend navigates to /session/:id with opening_text in route state
4. SessionPage mounts:
     ├─ adds opening_text as first assistant bubble
     ├─ on user gesture (intro modal "Tap to start"), TTS speaks opening
5. Per turn:
     ├─ User holds mic button
     ├─ MediaRecorder records → Blob on release
     ├─ POST /api/sessions/:id/turn (multipart audio)
     │    ├─ services.turn: temp file, ASR, load session, build messages,
     │    │  LLM.complete, storage.append_turn
     │    └─ returns {user_text, assistant_text}
     ├─ Frontend appends user bubble + assistant bubble
     └─ TTS plays assistant_text
6. End:
     ├─ User clicks End
     ├─ POST /api/sessions/:id/end
     │    ├─ services.end_session: evaluator, set_growth_points or _error,
     │    │  SRS.create_cards, set_cards_created, end_session
     │    └─ returns {growth_points, cards_created, growth_points_error}
     ├─ SessionSummary modal shows growth points
     └─ Navigate to /
```

### 7.2 Review lifecycle

```
1. /review mounts → GET /api/review/due
2. For each card:
     ├─ Card front shown
     ├─ User records OR skips
     ├─ If audio: POST /api/review/:cid/grade (multipart audio)
     │   ├─ services.grade_card: ASR → grader → SRS.record_review
     │   └─ returns {quality, target, explanation, next_due}
     ├─ If skip: POST /api/review/:cid/grade {"skip": true}
     ├─ Card back shown with score
     ├─ TTS plays target
     └─ Next card after 3s or click
3. Done → show summary (cards reviewed, quality distribution).
```

### 7.3 Stats / Budget

Read-only fetches on page mount. `BudgetIndicator` in header polls `/api/budget` every 30 seconds while on session/review pages, on-mount otherwise.

## 8. Error Handling

### Backend → response shape

Already covered in §6.5.

### Frontend handling

| Error | UI behavior |
|---|---|
| Network error (fetch fails) | Toast: "Connection issue, retry?" with retry button. Recorded blob preserved in memory if turn. |
| `no_speech_detected` 422 | Toast: "Didn't catch that — try again." Button re-armed, no bubble appended. |
| `budget_exhausted` 429 | Modal: "Daily budget cap reached ($X.XX / $0.50). Resets at midnight." Session disabled until next day. |
| `scenario_not_found` 404 | Toast on ScenariosPage, list reloads. |
| `session_not_found` 404 | Toast + navigate to /. |
| `card_not_found` 404 | Toast + advance to next card. |
| Mic permission denied | Modal: "Mic permission required. Enable in browser settings." Recording controls disabled. |
| TTS failure | Silent — assistant bubble still shows text. No retry. |
| iOS Safari first-call quirk | Opening TTS gated behind explicit "Start session" click. |
| MediaRecorder unsupported | Modal: "Your browser doesn't support audio recording. Try Chrome or Safari." |

## 9. Budget

Inherited unchanged from Stage 1b ($0.5/day USD, 200k tokens/day). New LLM call sources:

- `/api/sessions` opening line — 1 LLM call (~500 tok)
- `/api/sessions/turn` — 1 LLM call per turn (~1-2k tok)
- `/api/sessions/end` — 1 evaluator call (~3-5k tok)
- `/api/review/grade` — 1 grader call per card (~200 tok)

Same caps and `BudgetExceededError` propagation. The `/api/budget` endpoint exposes current state for `BudgetIndicator`.

## 10. Testing

### Backend

- **Unit tests for `services.py`** — mocked LLM/ASR/Storage/SRS; one happy-path test per service function + one error-path test per defined exception.
- **API tests via `fastapi.testclient.TestClient`** — one test per endpoint covering 200 + dominant error paths; e.g. `/sessions/turn` covers 200, 404, 422, 429.
- **Existing tests stay green** — no edits to `tests/test_session.py`, `test_review.py`, etc.

### Frontend

- **Vitest + @testing-library/react** for component tests.
- 1 smoke test per page (renders without crash, key elements present).
- Targeted tests for `useRecorder` and `useTTS` state machines (mock `MediaRecorder` and `speechSynthesis`).
- API client: mocked `fetch`, verify request shapes.
- No Playwright/E2E in 2a — manual smoke fills that gap.

### Integration / manual smoke

- `scripts/build_and_serve.sh` succeeds.
- One real session end-to-end in browser (record voice, hear reply, see growth points).
- One real review session in browser.
- Stats page displays current state.
- CLI commands still work: `tutor interview`, `tutor review`, `tutor stats`.

## 11. Decisions

| Decision | Choice | Why |
|---|---|---|
| State management on backend | Stateless API + reload from storage each turn | Simpler, no memory leaks, restart-safe |
| Frontend framework | React + Vite | Industry standard, user picked it |
| Styling | Tailwind CSS | Fast iteration, mobile-responsive utilities |
| Routing | React Router v6 | Standard, deep-link friendly |
| Server state | React Query | Cache + refetch built-in |
| Voice recording UX | Push-to-talk (hold) | Mobile-native, Telegram/WhatsApp-familiar |
| TTS | Browser SpeechSynthesis | Free, no backend audio plumbing, uses OS voice |
| ASR | Backend Whisper (preload) | Already integrated, reliable |
| Auth | None | Localhost only |
| Build / deploy | Single FastAPI serves static + API | One process, no CORS, no proxy |
| Audio format | Whatever browser provides | Whisper via FFmpeg handles webm/mp4/wav |
| Charts in stats | None — plain text | Stage 2a focus on functional, not visual polish |
| E2E tests | None — manual smoke | Stage 2a not yet stable enough to lock down behavior |

## 12. Open Questions / Risks

- **SpeechSynthesis voice availability varies by browser/OS.** On Mac Safari with downloaded Siri Voice 2, sounds great. On other browsers, default voices may be robotic. Mitigation: settings page (Stage 2b) will let user pick from `voices[]`.
- **iOS Safari permissions for audio.** MediaRecorder + getUserMedia work, but require HTTPS for non-localhost. Localhost is allowed. Stage 2c with VPS deploy will need TLS.
- **Whisper preload memory footprint.** Loading the model at startup costs ~500MB RAM. Acceptable for a single-user local app. If this becomes a problem, fall back to lazy load (slower first turn).
- **React Query and conversation history sync.** Local message array is the source of truth during a session. If user reloads the page mid-session, the array is rebuilt from `GET /api/sessions/{id}` — which requires storing `opening_text` in the session JSON (extend `start_session_service` to persist it).
- **Frontend bundle size.** React + Router + Query + Tailwind + lucide ≈ 200-300KB gzipped. Fine for localhost. Stage 2c can add code-splitting if mobile network is added.
- **Microphone format mismatch.** Some browser/OS combinations may produce audio Whisper struggles with. If we see frequent `no_speech_detected` 422s, add server-side conversion step using FFmpeg. Out of scope unless observed.

## 13. Success Criteria

Stage 2a is successful when:

- All 4 screens load without errors in Chrome and Safari on macOS.
- A full session goes end-to-end in the browser: pick scenario → hold mic → speak → hear reply → repeat → end → see growth points.
- A review session goes end-to-end: due cards load → hold mic → speak target → see score → next card.
- Stats page shows the same numbers as `tutor stats` for the same data.
- `pytest` is green across the suite (existing + new API/services tests, ~110+ tests).
- `npm test` is green in `frontend/`.
- `scripts/build_and_serve.sh` produces a working app on `localhost:8000` with one command.
- CLI commands (`tutor interview`, `tutor review`, `tutor stats`) work unchanged.
- The user uses the browser UI instead of the CLI for at least one full week without reverting.
