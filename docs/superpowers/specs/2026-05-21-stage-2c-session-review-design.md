# Stage 2c — Session Review (inline corrections)

- **Date:** 2026-05-21
- **Author:** Stas Arkhipov
- **Status:** Draft, pending implementation plan

## 1. Context

After ending a session the user navigates home and lands on `/review`. Today `/review` runs SRS voice-graded recall practice — useful but not what the user wants right after a session. They want to **read the conversation again** with the evaluator's corrections rendered **inline under each user message**, so context and correction are absorbed together.

The current /review (SRS practice) stays available but moves to a new `/practice` route. The /review route is repurposed for passive session review.

## 2. Goals

- After ending a session, user opens `/review` and sees the most recent ended session: chat-history with each user message followed by the growth points that came from it.
- Loading state when async evaluator is still running.
- Empty state when there are no completed sessions yet.
- Existing SRS practice flow stays intact, now under `/practice`.

## 3. Non-Goals

- Multi-session browser (list of past sessions). One latest session is enough for Stage 2c.
- Editing corrections, marking them done.
- Streaming evaluator output.
- Re-running evaluator from UI.

## 4. Approach

`/review` becomes a read-only session viewer. It fetches the latest session via `GET /api/sessions?limit=1` then renders the conversation. For each user message, it filters the session's `growth_points` by case-insensitive substring match on `user_utterance` and renders matched items inline below the bubble. Unmatched growth points (rare) render in a small "Other corrections" section at the end.

While the session has `ended_at` but no `growth_points` field yet, the page shows an "Analyzing..." state and React Query refetches every 3 seconds until `growth_points` (or `growth_points_error`) appears.

The existing `ReviewPage.tsx` is renamed to `PracticePage.tsx` — same code, new route at `/practice`. `Layout` nav adds a "Practice" link.

## 5. Architecture

```
[ Browser: /review ]
   ├─ useQuery → GET /api/sessions?limit=1
   ├─ render conversation (MessageBubble per turn)
   ├─ for each user message: filter growth_points by substring match,
   │   render InlineCorrection components under the bubble
   └─ poll every 3s while session is "analyzing"

[ Browser: /practice ]   ← renamed-from /review
   └─ SRS voice-graded recall (unchanged)

[ Backend ]
   GET /api/sessions?limit=N   (new)
       → returns array of session dicts, latest first (uses SessionStorage.list_sessions)
```

## 6. Components

### 6.1 Backend — `GET /api/sessions`

New route in `tutor/web/api.py`:

```
GET /api/sessions?limit=N
  → 200 {"sessions": [session_dict, session_dict, ...]}
```

- `limit` query param, default 10, max 50.
- Returns `SessionStorage.list_sessions()` sliced to `limit` (already sorted by `started_at` desc).
- Only sessions with `ended_at` set are returned (filter unfinished ones — they're not "reviewable" yet).

New schema in `tutor/web/schemas.py`:

```python
class SessionListResult(BaseModel):
    sessions: list[dict]
```

### 6.2 Backend — service

`tutor/web/services.py` adds:

```python
def list_sessions_service(deps: Dependencies, limit: int = 10) -> list[dict]:
    all_sessions = deps.storage.list_sessions()
    ended = [s for s in all_sessions if s.get("ended_at")]
    return ended[:limit]
```

### 6.3 Frontend — rename ReviewPage → PracticePage

- `frontend/src/pages/ReviewPage.tsx` → `frontend/src/pages/PracticePage.tsx` (same content, just rename + update internal exports)
- `frontend/src/pages/ReviewPage.test.tsx` → `frontend/src/pages/PracticePage.test.tsx` (same content)
- App.tsx route `/review` → `/practice` for the renamed component

### 6.4 Frontend — new ReviewPage

`frontend/src/pages/ReviewPage.tsx`:
- `useQuery(['sessions-latest'], () => api.getSessions(1), {refetchInterval: 3000 if analyzing else false})`
- States:
  - loading → skeleton
  - no sessions → "No sessions yet. Run one to get your review."
  - session.ended_at set, no growth_points field AND no growth_points_error → "Analyzing your session…" + spinner
  - growth_points_error → red banner with the error message
  - growth_points: [] → "No corrections found — clean session!"
  - growth_points present → render conversation
- Render conversation: opening assistant bubble (if any), then alternating user/assistant turns. After each user bubble, inline corrections.

### 6.5 Frontend — InlineCorrection component

`frontend/src/components/InlineCorrection.tsx`:
- Props: `growth_point: GrowthPointDict`
- Visual: small card under the bubble. Tag chip (vocab/grammar). Strikethrough `user_utterance` → corrected `corrected_version`. Italic explanation below.
- Uses Tailwind for styling.

### 6.6 Frontend — API client

`frontend/src/api/client.ts` adds:

```typescript
getSessions(limit: number = 10): Promise<SessionData[]> {
    const qs = `?limit=${limit}`;
    return request<{sessions: SessionData[]}>(`/api/sessions${qs}`).then(r => r.sessions);
}
```

### 6.7 Frontend — Layout nav

`Layout.tsx` updates: existing "Review" link → keep as "Review", new "Practice" link added.

Order in header: Scenarios | Review | Practice | Stats.

### 6.8 App routing

`App.tsx`:

```typescript
<Route path="/" element={<ScenariosPage />} />
<Route path="/session/:id" element={<SessionPage />} />
<Route path="/review" element={<ReviewPage />} />        // NEW: passive
<Route path="/practice" element={<PracticePage />} />    // RENAMED: SRS voice
<Route path="/stats" element={<StatsPage />} />
```

## 7. Matching Logic

For a user message text `m` and growth point `gp`:
```python
match = gp.user_utterance.lower().strip() in m.lower()
```

If match, render `gp` below message `m`. Each gp matches at most one message (first match wins — gp removed from pool to avoid duplicate render).

Growth points with no match → rendered in "Other corrections" panel at end of conversation.

## 8. Data Flow

```
1. User ends session → navigate to /
2. User clicks "Review" in nav → /review
3. GET /api/sessions?limit=1
4. If session.ended_at && !growth_points && !growth_points_error → poll every 3s
5. When growth_points arrives → render conversation + inline corrections
6. User reads, navigates away when done
```

## 9. Error Handling

| Scenario | UI |
|---|---|
| No sessions in store | "No sessions yet. Run one to see your review." + link to / |
| Latest session not ended (in progress) | "Your last session is still running" + link to /session/{id} |
| Session ended, evaluator analyzing | "Analyzing your session…" + spinner + auto-refetch |
| growth_points_error set | Red banner with the error text; conversation still renders |
| growth_points: [] | "No corrections found — clean session!" + conversation rendered |
| Network failure on fetch | React Query default retry; toast on persistent failure |

## 10. Testing

### Backend
- `GET /api/sessions?limit=N` returns sessions filtered to `ended_at` set, sorted desc, capped at limit.
- Service skips non-ended sessions.

### Frontend
- ReviewPage: mocks api.getSessions → shows conversation + InlineCorrection for matching growth points.
- ReviewPage: empty state when sessions list is empty.
- ReviewPage: "analyzing" state when session has ended_at but no growth_points field.
- ReviewPage: error banner when growth_points_error is set.
- InlineCorrection: renders strikethrough, arrow, corrected version, explanation.
- Practice page (renamed): unchanged behavior verified.

### Manual smoke
- Run a session, end it, navigate /review → see "Analyzing..." → after ~5s see conversation + inline corrections.
- Click "Practice" → SRS due cards (no regression).

## 11. Decisions

| Decision | Choice | Why |
|---|---|---|
| Multi-session list | No — only latest | Simpler MVP; history page later |
| Matching algorithm | Case-insensitive substring | Evaluator emits verbatim quotes; substring catches most cases |
| Polling interval | 3 seconds | Evaluator completes in ~5s typically |
| /practice rename | Move existing ReviewPage to PracticePage | Preserves SRS flow code unchanged |
| Inline vs separate growth points section | Inline under each user message | Matches user request "сочетается в UI" |

## 12. Success Criteria

- User ends a session, opens /review within 10s, sees "Analyzing…", then conversation + inline corrections.
- User clicks "Practice" → SRS due cards flow works as before.
- Tests green: backend (~172) + frontend.
