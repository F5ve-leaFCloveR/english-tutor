# Stage 2c — Session Review (inline corrections) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/review` becomes a passive read view of the latest ended session: chat-history with each user message followed by inline corrections (growth points). The current SRS practice flow moves to `/practice`.

**Architecture:** New `GET /api/sessions?limit=N` returns ended sessions (latest first). Frontend `/review` fetches `limit=1`, polls every 3s while session is still being analyzed, then renders conversation with inline growth_points matched by substring on `user_utterance`. The existing ReviewPage is renamed to PracticePage; the route `/review` is rewritten.

**Tech Stack:** Same as Stage 2b. No new deps.

**Prerequisites:**
- Stage 2b + the max_tokens fix on `main` (commit `24ed512` or later).
- All current tests green: 170 pytest, 27 npm test, `npm run build` succeeds.

---

## File Structure

```
tutor/web/
├── services.py         (MODIFY: + list_sessions_service)
├── api.py              (MODIFY: + GET /api/sessions)
└── schemas.py          (MODIFY: + SessionListResult)

frontend/src/
├── api/
│   ├── client.ts       (MODIFY: + getSessions)
│   └── types.ts        (already has SessionData; no change)
├── pages/
│   ├── ReviewPage.tsx          (REWRITE — passive viewer)
│   ├── ReviewPage.test.tsx     (REWRITE)
│   ├── PracticePage.tsx        (NEW — copy of old ReviewPage logic)
│   └── PracticePage.test.tsx   (NEW — copy of old ReviewPage tests)
├── components/
│   ├── InlineCorrection.tsx        (NEW)
│   ├── InlineCorrection.test.tsx   (NEW)
│   └── Layout.tsx                  (MODIFY: + Practice link)
└── App.tsx             (MODIFY: route rewiring)

tests/web/
├── test_services_session.py    (MODIFY: + list_sessions_service tests)
└── test_api.py                 (MODIFY: + GET /api/sessions tests)
```

---

## Task 1: Backend service — `list_sessions_service`

**Files:**
- Modify: `tutor/web/services.py`
- Modify: `tests/web/test_services_session.py`

- [ ] **Step 1: Append failing tests** to `tests/web/test_services_session.py`:

```python
def test_list_sessions_service_returns_ended_only(tmp_path):
    from tutor.web.services import list_sessions_service, start_session_service, end_session_service
    deps = _make_deps(tmp_path)
    deps.llm.complete.return_value = "Hi."

    s1 = start_session_service(deps, scenario_id="tech_interview_behavioral")
    # Note: end_session_service requires evaluator dependency; we just call
    # storage.end_session directly to simulate "ended" without evaluator side-effects
    deps.storage.end_session(s1.session_id)

    # Second session — NOT ended
    s2 = start_session_service(deps, scenario_id="tech_interview_behavioral")

    result = list_sessions_service(deps, limit=10)
    ids = [s["session_id"] for s in result]
    assert s1.session_id in ids
    assert s2.session_id not in ids


def test_list_sessions_service_respects_limit(tmp_path):
    from tutor.web.services import list_sessions_service, start_session_service
    deps = _make_deps(tmp_path)
    deps.llm.complete.return_value = "Hi."

    ids = []
    for _ in range(5):
        s = start_session_service(deps, scenario_id="tech_interview_behavioral")
        deps.storage.end_session(s.session_id)
        ids.append(s.session_id)

    result = list_sessions_service(deps, limit=2)
    assert len(result) == 2


def test_list_sessions_service_empty_when_none(tmp_path):
    from tutor.web.services import list_sessions_service
    deps = _make_deps(tmp_path)
    assert list_sessions_service(deps, limit=10) == []
```

- [ ] **Step 2: Run** `cd /Users/sarkhipov/Work/Personal/english-tutor && source .venv/bin/activate && pytest tests/web/test_services_session.py -v` → 3 fails.

- [ ] **Step 3: Append to `tutor/web/services.py`**:

```python
def list_sessions_service(deps: Dependencies, limit: int = 10) -> list[dict]:
    """Return up to `limit` ended sessions, latest first."""
    all_sessions = deps.storage.list_sessions()
    ended = [s for s in all_sessions if s.get("ended_at")]
    return ended[:limit]
```

- [ ] **Step 4: Run + commit**

`pytest` → all green.

```bash
git add tutor/web/services.py tests/web/test_services_session.py
git commit -m "feat(web): list_sessions_service — ended-only, limited"
```

## Context

- Branch: `main`. Previous: `24ed512`.
- Task 1 of 7.

---

## Task 2: Backend route — `GET /api/sessions`

**Files:**
- Modify: `tutor/web/api.py`
- Modify: `tutor/web/schemas.py`
- Modify: `tests/web/test_api.py`

- [ ] **Step 1: Append schema** in `tutor/web/schemas.py`:

```python
class SessionListResult(BaseModel):
    sessions: list[dict]
```

- [ ] **Step 2: Append failing tests** in `tests/web/test_api.py`:

```python
def test_get_sessions_returns_ended_only(tmp_path, mocker):
    client, deps = _client(tmp_path, mocker)
    deps.llm.complete.return_value = "Hi."

    # Start two sessions, end only the first
    r1 = client.post("/api/sessions", json={"scenario_id": "tech_interview_behavioral"})
    sid1 = r1.json()["session_id"]
    client.post(f"/api/sessions/{sid1}/end")

    r2 = client.post("/api/sessions", json={"scenario_id": "tech_interview_behavioral"})
    sid2 = r2.json()["session_id"]
    # do NOT end sid2

    r = client.get("/api/sessions?limit=10")
    assert r.status_code == 200
    ids = [s["session_id"] for s in r.json()["sessions"]]
    assert sid1 in ids
    assert sid2 not in ids


def test_get_sessions_default_limit(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.get("/api/sessions")
    assert r.status_code == 200
    # default limit is 10; empty store yields 0
    assert r.json()["sessions"] == []


def test_get_sessions_limit_clamped_to_50(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.get("/api/sessions?limit=999")
    assert r.status_code == 422  # pydantic validation rejects >50
```

- [ ] **Step 3: Run** `pytest tests/web/test_api.py -v` → 3 fail.

- [ ] **Step 4: Update `tutor/web/api.py`** — add to imports:

```python
from fastapi import Query
from tutor.web.schemas import SessionListResult
```

Add route alongside other sessions routes:

```python
    @app.get("/api/sessions", response_model=SessionListResult)
    async def list_sessions(
        limit: int = Query(default=10, ge=1, le=50),
        d: Dependencies = Depends(get_deps),
    ):
        return SessionListResult(sessions=services.list_sessions_service(d, limit=limit))
```

- [ ] **Step 5: Run + commit**

`pytest tests/web/test_api.py -v` → 17+3 passed.
`pytest` → ~173 green.

```bash
git add tutor/web/api.py tutor/web/schemas.py tests/web/test_api.py
git commit -m "feat(web): GET /api/sessions?limit=N route"
```

## Context

- Branch: `main`. Previous: T1 commit.
- Task 2 of 7.

---

## Task 3: Frontend API client — `getSessions`

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/api/client.test.ts`

- [ ] **Step 1: Append failing test** in `frontend/src/api/client.test.ts`:

```typescript
it("getSessions returns array of sessions", async () => {
    (globalThis as any).fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ sessions: [{ session_id: "s1", turns: [] }] }),
    });
    const sessions = await api.getSessions(5);
    expect(sessions).toHaveLength(1);
    expect(sessions[0].session_id).toBe("s1");
    const call = ((globalThis as any).fetch as any).mock.calls[0];
    expect(call[0]).toBe("/api/sessions?limit=5");
});
```

- [ ] **Step 2: Run** `cd /Users/sarkhipov/Work/Personal/english-tutor/frontend && npm test` → fail.

- [ ] **Step 3: Update `frontend/src/api/client.ts`** — append on the `api` object:

```typescript
  async getSessions(limit: number = 10): Promise<SessionData[]> {
    const data = await request<{ sessions: SessionData[] }>(`/api/sessions?limit=${limit}`);
    return data.sessions;
  },
```

(The `SessionData` type already exists in `types.ts`.)

- [ ] **Step 4: Run + commit**

`npm test` → green.
`npm run build` → succeeds.

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/api/
git commit -m "feat(frontend): api.getSessions(limit)"
```

## Context

- Branch: `main`. Previous: T2 commit.
- Task 3 of 7.

---

## Task 4: Rename `ReviewPage` → `PracticePage`

**Files:**
- Move: `frontend/src/pages/ReviewPage.tsx` → `frontend/src/pages/PracticePage.tsx`
- Move: `frontend/src/pages/ReviewPage.test.tsx` → `frontend/src/pages/PracticePage.test.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Move files via git**

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor/frontend/src/pages
git mv ReviewPage.tsx PracticePage.tsx
git mv ReviewPage.test.tsx PracticePage.test.tsx
```

- [ ] **Step 2: Rename the exported component** inside `PracticePage.tsx`:

Replace all occurrences of `ReviewPage` with `PracticePage`:

```bash
sed -i.bak 's/ReviewPage/PracticePage/g' /Users/sarkhipov/Work/Personal/english-tutor/frontend/src/pages/PracticePage.tsx
rm /Users/sarkhipov/Work/Personal/english-tutor/frontend/src/pages/PracticePage.tsx.bak
```

- [ ] **Step 3: Update the test file** the same way:

```bash
sed -i.bak 's/ReviewPage/PracticePage/g' /Users/sarkhipov/Work/Personal/english-tutor/frontend/src/pages/PracticePage.test.tsx
rm /Users/sarkhipov/Work/Personal/english-tutor/frontend/src/pages/PracticePage.test.tsx.bak
```

- [ ] **Step 4: Update `frontend/src/App.tsx`**

Find:
```typescript
import { ReviewPage } from "./pages/ReviewPage";
```

Replace with:
```typescript
import { PracticePage } from "./pages/PracticePage";
```

Find the route:
```typescript
<Route path="/review" element={<ReviewPage />} />
```

Replace with:
```typescript
<Route path="/practice" element={<PracticePage />} />
```

- [ ] **Step 5: Run + commit**

`cd /Users/sarkhipov/Work/Personal/english-tutor/frontend && npm test` → green (existing test now under PracticePage name).
`npm run build` → succeeds.

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/
git commit -m "refactor(frontend): rename ReviewPage → PracticePage at /practice"
```

## Context

- Branch: `main`. Previous: T3 commit.
- Task 4 of 7.

---

## Task 5: `InlineCorrection` component

**Files:**
- Create: `frontend/src/components/InlineCorrection.tsx`
- Create: `frontend/src/components/InlineCorrection.test.tsx`

- [ ] **Step 1: Write failing test** `frontend/src/components/InlineCorrection.test.tsx`:

```typescript
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { InlineCorrection } from "./InlineCorrection";

describe("InlineCorrection", () => {
  const gp = {
    tag: "vocab" as const,
    user_utterance: "I made a project",
    corrected_version: "I led a project",
    explanation: "Led signals ownership.",
    context: null,
  };

  it("renders tag, original, corrected, explanation", () => {
    render(<InlineCorrection growth_point={gp} />);
    expect(screen.getByText(/vocab/i)).toBeInTheDocument();
    expect(screen.getByText("I made a project")).toBeInTheDocument();
    expect(screen.getByText("I led a project")).toBeInTheDocument();
    expect(screen.getByText("Led signals ownership.")).toBeInTheDocument();
  });

  it("renders strikethrough on original utterance", () => {
    render(<InlineCorrection growth_point={gp} />);
    const orig = screen.getByText("I made a project");
    expect(orig.tagName.toLowerCase()).toBe("s");
  });
});
```

- [ ] **Step 2: Run** `cd /Users/sarkhipov/Work/Personal/english-tutor/frontend && npm test` → fail.

- [ ] **Step 3: Implement `frontend/src/components/InlineCorrection.tsx`**:

```typescript
import type { GrowthPointDict } from "../api/types";

interface Props {
  growth_point: GrowthPointDict;
}

export function InlineCorrection({ growth_point: gp }: Props) {
  const tagColor =
    gp.tag === "vocab" ? "bg-blue-100 text-blue-800" : "bg-amber-100 text-amber-800";
  return (
    <div className="ml-4 mt-1 mb-3 border-l-2 border-slate-300 pl-3 text-sm">
      <span className={`inline-block text-xs uppercase font-semibold rounded px-1.5 py-0.5 mr-2 ${tagColor}`}>
        {gp.tag}
      </span>
      <s className="text-slate-500">{gp.user_utterance}</s>
      <span className="text-slate-400 mx-2">→</span>
      <span className="text-slate-900 font-medium">{gp.corrected_version}</span>
      <div className="text-slate-600 italic mt-1 text-xs">{gp.explanation}</div>
    </div>
  );
}
```

- [ ] **Step 4: Run + commit**

`npm test` → green (2 new).
`npm run build` → succeeds.

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/components/
git commit -m "feat(frontend): InlineCorrection component"
```

## Context

- Branch: `main`. Previous: T4 commit.
- Task 5 of 7.

---

## Task 6: New `ReviewPage` (passive viewer) + Layout nav

**Files:**
- Create: `frontend/src/pages/ReviewPage.tsx`
- Create: `frontend/src/pages/ReviewPage.test.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Layout.tsx`

- [ ] **Step 1: Write failing tests** `frontend/src/pages/ReviewPage.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReviewPage } from "./ReviewPage";

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <BrowserRouter>
      <QueryClientProvider client={qc}>{node}</QueryClientProvider>
    </BrowserRouter>
  );
}

describe("ReviewPage", () => {
  it("shows empty state when no sessions", async () => {
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: { getSessions: vi.fn().mockResolvedValue([]) },
      ApiError: class extends Error {},
    }));
    const { ReviewPage: Page } = await import("./ReviewPage");
    render(wrap(<Page />));
    await waitFor(() => {
      expect(screen.getByText(/no sessions yet/i)).toBeInTheDocument();
    });
  });

  it("renders conversation with inline corrections", async () => {
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: {
        getSessions: vi.fn().mockResolvedValue([{
          session_id: "s1",
          scenario_id: "x",
          started_at: "2026-05-21T10:00:00",
          ended_at: "2026-05-21T10:15:00",
          opening_text: "Hi.",
          turns: [
            { ts: "...", user_text: "I made a project yesterday",
              llm_text: "What kind of project?" },
          ],
          growth_points: [{
            tag: "vocab",
            user_utterance: "I made a project",
            corrected_version: "I led a project",
            explanation: "Led signals ownership.",
            context: null,
          }],
        }]),
      },
      ApiError: class extends Error {},
    }));
    const { ReviewPage: Page } = await import("./ReviewPage");
    render(wrap(<Page />));
    await waitFor(() => {
      expect(screen.getByText("I made a project yesterday")).toBeInTheDocument();
      expect(screen.getByText("I led a project")).toBeInTheDocument();
      expect(screen.getByText("Led signals ownership.")).toBeInTheDocument();
    });
  });

  it("shows analyzing state when growth_points missing", async () => {
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: {
        getSessions: vi.fn().mockResolvedValue([{
          session_id: "s1",
          scenario_id: "x",
          started_at: "2026-05-21T10:00:00",
          ended_at: "2026-05-21T10:15:00",
          opening_text: "Hi.",
          turns: [{ ts: "...", user_text: "hello", llm_text: "hi" }],
        }]),
      },
      ApiError: class extends Error {},
    }));
    const { ReviewPage: Page } = await import("./ReviewPage");
    render(wrap(<Page />));
    await waitFor(() => {
      expect(screen.getByText(/analyzing/i)).toBeInTheDocument();
    });
  });

  it("shows clean session message when growth_points is empty", async () => {
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: {
        getSessions: vi.fn().mockResolvedValue([{
          session_id: "s1",
          scenario_id: "x",
          started_at: "2026-05-21T10:00:00",
          ended_at: "2026-05-21T10:15:00",
          opening_text: "Hi.",
          turns: [{ ts: "...", user_text: "hello", llm_text: "hi" }],
          growth_points: [],
          cards_created: [],
        }]),
      },
      ApiError: class extends Error {},
    }));
    const { ReviewPage: Page } = await import("./ReviewPage");
    render(wrap(<Page />));
    await waitFor(() => {
      expect(screen.getByText(/no corrections found/i)).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 2: Run** `cd /Users/sarkhipov/Work/Personal/english-tutor/frontend && npm test` → 4 fail (no module).

- [ ] **Step 3: Implement `frontend/src/pages/ReviewPage.tsx`**:

```typescript
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { GrowthPointDict, SessionData } from "../api/types";
import { MessageBubble } from "../components/MessageBubble";
import { InlineCorrection } from "../components/InlineCorrection";

function isAnalyzing(s: SessionData): boolean {
  return !!s.ended_at && !s.growth_points && !s.growth_points_error;
}

function matchGrowthPoints(
  messageText: string,
  pool: GrowthPointDict[],
): { matched: GrowthPointDict[]; remaining: GrowthPointDict[] } {
  const lower = messageText.toLowerCase();
  const matched: GrowthPointDict[] = [];
  const remaining: GrowthPointDict[] = [];
  for (const gp of pool) {
    if (gp.user_utterance.toLowerCase().trim() && lower.includes(gp.user_utterance.toLowerCase().trim())) {
      matched.push(gp);
    } else {
      remaining.push(gp);
    }
  }
  return { matched, remaining };
}

export function ReviewPage() {
  const { data: sessions, isLoading } = useQuery({
    queryKey: ["sessions-latest"],
    queryFn: () => api.getSessions(1),
    refetchInterval: (q) => {
      const data = q.state.data as SessionData[] | undefined;
      return data && data[0] && isAnalyzing(data[0]) ? 3000 : false;
    },
  });

  if (isLoading) {
    return <div className="p-8 text-slate-600">Loading…</div>;
  }

  const session = sessions?.[0];
  if (!session) {
    return (
      <div className="p-8 text-center text-slate-600">
        No sessions yet. <Link to="/" className="text-blue-600 underline">Run one</Link> to see your review.
      </div>
    );
  }

  if (isAnalyzing(session)) {
    return (
      <div className="p-8 text-center text-slate-600">
        Analyzing your session…
        <div className="mt-3 inline-block w-6 h-6 border-2 border-slate-300 border-t-blue-600 rounded-full animate-spin"></div>
      </div>
    );
  }

  const growthPoints = (session.growth_points ?? []) as GrowthPointDict[];
  const errorMessage = session.growth_points_error;
  let pool = [...growthPoints];

  return (
    <div className="max-w-3xl mx-auto p-6 w-full">
      <h1 className="text-2xl font-semibold mb-4 text-slate-900">Session review</h1>

      {errorMessage && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded text-sm text-red-800">
          Analysis failed: {errorMessage}
        </div>
      )}

      {growthPoints.length === 0 && !errorMessage && (
        <div className="mb-4 p-3 bg-emerald-50 border border-emerald-200 rounded text-sm text-emerald-800">
          No corrections found — clean session!
        </div>
      )}

      <div>
        {session.opening_text && (
          <MessageBubble role="assistant" text={session.opening_text} />
        )}
        {session.turns.map((t, i) => {
          const { matched, remaining } = matchGrowthPoints(t.user_text, pool);
          pool = remaining;
          return (
            <div key={i}>
              <MessageBubble role="user" text={t.user_text} />
              {matched.map((gp, j) => (
                <InlineCorrection key={j} growth_point={gp} />
              ))}
              <MessageBubble role="assistant" text={t.llm_text} />
            </div>
          );
        })}
      </div>

      {pool.length > 0 && (
        <div className="mt-6 border-t pt-4">
          <h2 className="text-sm font-semibold text-slate-700 mb-2">Other corrections</h2>
          {pool.map((gp, i) => <InlineCorrection key={i} growth_point={gp} />)}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Update `frontend/src/App.tsx`**

Add import:
```typescript
import { ReviewPage } from "./pages/ReviewPage";
```

Add route alongside PracticePage:
```typescript
<Route path="/review" element={<ReviewPage />} />
```

Routes block should look like:
```typescript
<Routes>
  <Route path="/" element={<ScenariosPage />} />
  <Route path="/session/:id" element={<SessionPage />} />
  <Route path="/review" element={<ReviewPage />} />
  <Route path="/practice" element={<PracticePage />} />
  <Route path="/stats" element={<StatsPage />} />
</Routes>
```

- [ ] **Step 5: Update `frontend/src/components/Layout.tsx`** — add Practice nav link

Find the nav block (something like):
```typescript
<Link to="/review" className="hover:text-slate-900">Review</Link>
<Link to="/stats" className="hover:text-slate-900">Stats</Link>
```

Replace with:
```typescript
<Link to="/review" className="hover:text-slate-900">Review</Link>
<Link to="/practice" className="hover:text-slate-900">Practice</Link>
<Link to="/stats" className="hover:text-slate-900">Stats</Link>
```

- [ ] **Step 6: Run + commit**

`npm test` → all green.
`npm run build` → succeeds.

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/
git commit -m "feat(frontend): /review = passive session viewer with inline corrections"
```

## Context

- Branch: `main`. Previous: T5 commit.
- Task 6 of 7.

---

## Task 7: Manual end-to-end smoke

- [ ] **Step 1: Run suites**

`cd /Users/sarkhipov/Work/Personal/english-tutor && source .venv/bin/activate && pytest` → ~173 pass.
`cd frontend && npm test` → all green.
`npm run build` → succeeds.

- [ ] **Step 2: Push**

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor
git push origin main
```

- [ ] **Step 3: Run web UI + verify**

`./scripts/build_and_serve.sh` — opens `http://127.0.0.1:8000`.

Checks:
1. Header nav shows: Scenarios | Review | Practice | Stats. Click each — all 4 work.
2. Run a fresh session, end it, immediately click "Review":
   - Initial state: "Analyzing your session..." with spinner
   - After ~5s: conversation appears with InlineCorrection blocks under user messages
3. Click "Practice": SRS due cards screen works (no regression from rename).
4. Empty store: rename `sessions/` away temporarily → /review shows "No sessions yet". Restore after check.

- [ ] **Step 4: Report findings**

If all checks pass — Stage 2c done.

---

## Self-review

1. **Spec coverage:**
   - GET /api/sessions endpoint → T2 ✓
   - service for sessions list → T1 ✓
   - InlineCorrection component → T5 ✓
   - New ReviewPage with 4 states (loading, empty, analyzing, normal, error) → T6 ✓
   - Polling every 3s while analyzing → T6 ✓
   - Substring matching of growth_points to messages → T6 ✓
   - "Other corrections" section for unmatched → T6 ✓
   - PracticePage rename + /practice route → T4 ✓
   - Layout nav update → T6 ✓

2. **Type consistency:**
   - `SessionData` from types.ts already has `growth_points`, `growth_points_error`, `ended_at`, `opening_text`, `turns`
   - `GrowthPointDict` already exported from types.ts
   - `api.getSessions(limit)` returns `SessionData[]` consistently used in T6
   - `InlineCorrection` props (`growth_point: GrowthPointDict`) match T5 and T6 usage

3. **No placeholders:** all code shown; rename via `sed`/`git mv` is concrete.

4. **Failure modes:**
   - Backend skips non-ended sessions → T1 + T2 tests
   - Limit clamp 1..50 → T2 test
   - Frontend states: loading, empty, analyzing, error, clean, normal → T6 tests cover most
   - Match function handles empty user_utterance gracefully (skips) → T6 code

---

## Definition of Done

- 6 task commits + manual smoke on `origin/main`.
- `pytest` ~173 green.
- `npm test` all green.
- `npm run build` succeeds.
- `/review` shows latest session with inline corrections, polls during analyzing, handles all states.
- `/practice` works exactly like the old `/review` did.
- CLI unchanged.
