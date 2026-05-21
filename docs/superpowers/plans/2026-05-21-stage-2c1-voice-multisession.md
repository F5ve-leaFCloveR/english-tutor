# Stage 2c.1 — Voice fixes + Multi-session Review — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two issues found during Stage 2c smoke: (1) voice picker silently falls back to browser default voice when backend `/api/tts` fails; (2) `/review` shows only the latest session — user wants a 7-day list and click-through detail.

**Architecture:** Three small voice-side fixes (prune unsupported voices, surface backend errors, match picked voice in browser fallback). Then split `/review` into a list view + detail view (`/review/:sessionId`) — no backend changes, frontend filters last-7-days client-side.

**Tech Stack:** Same as Stage 2c. No new deps.

**Prerequisites:**
- Stage 2c (commit `5ac4441` or later, pushed to `main`).
- OpenRouter API-key daily limit ≥ $1 (verified: now $2/day, fine for audio reservation of $0.50).
- All current tests green: 178 pytest, 35 vitest, `npm run build` succeeds.

---

## File Structure

```
frontend/src/
├── api/
│   └── types.ts                  (MODIFY: prune OPENAI_TTS_VOICES)
├── hooks/
│   ├── useTTS.ts                 (MODIFY: expose lastError, voice-aware browser fallback)
│   └── useTTS.test.ts            (NEW or MODIFY: cover error state + fallback)
├── components/
│   ├── VoicePicker.test.tsx      (MODIFY: assert pruned voice set)
│   └── Layout.tsx                (no change in this stage)
├── pages/
│   ├── ReviewPage.tsx            (REWRITE: list of last-7-days sessions)
│   ├── ReviewPage.test.tsx       (REWRITE: cover list view)
│   ├── ReviewDetail.tsx          (NEW: extracted from old ReviewPage)
│   ├── ReviewDetail.test.tsx     (NEW: 5 states)
│   └── SessionPage.tsx           (MODIFY: render TTS error banner)
├── components/
│   └── (none new)
└── App.tsx                       (MODIFY: add /review/:sessionId route)
```

---

## Task 1: Prune `OPENAI_TTS_VOICES` to actually-supported voices

`gpt-4o-mini-audio-preview` (model behind `openai/gpt-audio-mini`) does NOT support `fable`, `onyx`, `nova`. Selecting them triggers backend 400 → silent fallback.

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/components/VoicePicker.test.tsx` (if it asserts the full set; just verify after change)

- [ ] **Step 1: Locate the constant**

Read `frontend/src/api/types.ts:108-111`:
```typescript
export const OPENAI_TTS_VOICES = [
  "alloy", "echo", "fable", "onyx", "nova", "shimmer",
  "ash", "ballad", "coral", "sage", "verse", "marin", "cedar",
] as const;
```

- [ ] **Step 2: Replace with supported-only set (10 voices)**

```typescript
export const OPENAI_TTS_VOICES = [
  "alloy", "ash", "ballad", "coral", "echo", "sage", "shimmer", "verse", "marin", "cedar",
] as const;
```

- [ ] **Step 3: Run tests + build**

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor/frontend
npm test 2>&1 | tail -10
npm run build 2>&1 | tail -5
```

If any test asserts the presence of `fable` / `onyx` / `nova`, update the assertion (only the count or the explicit absence).

- [ ] **Step 4: Commit**

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/api/types.ts frontend/src/components/VoicePicker.test.tsx
git commit -m "fix(tts): drop fable/onyx/nova — unsupported by gpt-4o-mini-audio-preview"
```

## Context

- Branch: `main`. Previous commit: `5ac4441` (Stage 2c end).
- Task 1 of 6 in Stage 2c.1.

---

## Task 2: Expose TTS error state from `useTTS` + render banner in `SessionPage`

When `/api/tts` returns 4xx/5xx, frontend should:
1. Still play the audio via browser fallback so the session doesn't break.
2. Capture the error message into `useTTS.lastError` and clear it on next successful call.
3. `SessionPage` renders a small banner ("TTS error: <msg> — using browser voice") so the user knows.

**Files:**
- Modify: `frontend/src/hooks/useTTS.ts`
- Create: `frontend/src/hooks/useTTS.test.ts` (if not present)
- Modify: `frontend/src/pages/SessionPage.tsx`
- Modify: `frontend/src/pages/SessionPage.test.tsx`

- [ ] **Step 1: Write failing test** `frontend/src/hooks/useTTS.test.ts` (create if missing, append otherwise):

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";

describe("useTTS lastError", () => {
  beforeEach(() => {
    (globalThis as any).fetch = vi.fn();
    localStorage.clear();
    // Stub Audio so .play() resolves immediately
    (globalThis as any).Audio = class {
      onended?: () => void;
      onerror?: () => void;
      play() { setTimeout(() => this.onended?.(), 0); return Promise.resolve(); }
    };
    (globalThis as any).speechSynthesis = { speak: vi.fn(), getVoices: vi.fn().mockReturnValue([]) };
    (globalThis as any).SpeechSynthesisUtterance = class { onend?: () => void; onerror?: () => void; };
  });

  afterEach(() => { vi.restoreAllMocks(); });

  it("sets lastError when backend returns 4xx", async () => {
    (globalThis as any).fetch = vi.fn().mockResolvedValue({
      ok: false, status: 402,
      json: async () => ({ error: "payment_required", message: "Audio reservation $0.50 required" }),
    });
    const { useTTS } = await import("./useTTS");
    const { result } = renderHook(() => useTTS());
    await act(async () => { await result.current.speak("hi"); });
    expect(result.current.lastError).toMatch(/0\.50|payment|required/i);
  });

  it("clears lastError on subsequent successful call", async () => {
    const { useTTS } = await import("./useTTS");
    const { result } = renderHook(() => useTTS());
    // 1) fail
    (globalThis as any).fetch = vi.fn().mockResolvedValue({
      ok: false, status: 500,
      json: async () => ({ error: "bad" }),
    });
    await act(async () => { await result.current.speak("hi"); });
    expect(result.current.lastError).not.toBeNull();
    // 2) succeed
    (globalThis as any).fetch = vi.fn().mockResolvedValue({
      ok: true, status: 200,
      blob: async () => new Blob(["audio"]),
    });
    await act(async () => { await result.current.speak("hi"); });
    expect(result.current.lastError).toBeNull();
  });
});
```

- [ ] **Step 2: Run** `cd /Users/sarkhipov/Work/Personal/english-tutor/frontend && npm test useTTS` → 2 fail (no `lastError`).

- [ ] **Step 3: Rewrite `frontend/src/hooks/useTTS.ts`**:

```typescript
import { useCallback, useState } from "react";
import { api } from "../api/client";
import { ApiError } from "../api/client";
import { OPENAI_TTS_VOICES } from "../api/types";

export interface UseTTS {
  speak: (text: string) => Promise<void>;
  isSpeaking: boolean;
  voices: readonly string[];
  lastError: string | null;
}

function findBrowserVoice(picked: string | undefined): SpeechSynthesisVoice | null {
  if (!picked || typeof speechSynthesis === "undefined") return null;
  const all = speechSynthesis.getVoices();
  const target = picked.toLowerCase();
  return (
    all.find((v) => v.name.toLowerCase().includes(target)) ||
    all.find((v) => v.name.toLowerCase().includes("english")) ||
    null
  );
}

async function speakWithBrowser(text: string, picked: string | undefined): Promise<void> {
  if (typeof speechSynthesis === "undefined") return;
  return new Promise((resolve) => {
    const u = new SpeechSynthesisUtterance(text);
    const voice = findBrowserVoice(picked);
    if (voice) u.voice = voice;
    u.onend = () => resolve();
    u.onerror = () => resolve();
    speechSynthesis.speak(u);
  });
}

export function useTTS(): UseTTS {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [lastError, setLastError] = useState<string | null>(null);

  const speak = useCallback(async (text: string): Promise<void> => {
    if (!text.trim()) return;
    const voice = localStorage.getItem("ttsVoice") || undefined;
    setIsSpeaking(true);
    try {
      const blob = await api.synthesizeTTS(text, voice);
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      await new Promise<void>((resolve, reject) => {
        audio.onended = () => { URL.revokeObjectURL(url); resolve(); };
        audio.onerror = () => { URL.revokeObjectURL(url); reject(); };
        audio.play().catch(reject);
      });
      setLastError(null);
    } catch (e) {
      const msg =
        e instanceof ApiError
          ? e.body?.message || e.body?.error || `HTTP ${e.status}`
          : e instanceof Error
          ? e.message
          : "TTS failed";
      setLastError(msg);
      await speakWithBrowser(text, voice);
    } finally {
      setIsSpeaking(false);
    }
  }, []);

  return { speak, isSpeaking, voices: OPENAI_TTS_VOICES, lastError };
}
```

- [ ] **Step 4: Run** `npm test useTTS` → all green.

- [ ] **Step 5: Update `frontend/src/pages/SessionPage.tsx`** — render the TTS error banner

Find where `useTTS()` is called and add a banner that shows when `tts.lastError` is set. Example placement near the top of the page body:

```typescript
{tts.lastError && (
  <div className="mb-3 p-2 bg-amber-50 border border-amber-200 rounded text-xs text-amber-800">
    TTS error: {tts.lastError}. Using browser voice.
  </div>
)}
```

If `tts` is currently destructured as `{ speak, isSpeaking }`, expand to include `lastError`.

- [ ] **Step 6: Update `frontend/src/pages/SessionPage.test.tsx`** — add one test

Add a test that mocks `useTTS` to return `lastError: "Audio reservation $0.50 required"` and asserts the banner is visible. Pattern: look at existing SessionPage tests to see how they mock hooks/api — follow the same approach.

If the existing test already mocks `useTTS`, extend the mock to include `lastError: null` by default and add one new test with `lastError` set.

- [ ] **Step 7: Run + build + commit**

```bash
npm test 2>&1 | tail -10
npm run build 2>&1 | tail -5
cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/hooks/ frontend/src/pages/SessionPage.tsx frontend/src/pages/SessionPage.test.tsx
git commit -m "feat(tts): expose lastError + voice-aware browser fallback in useTTS"
```

## Context

- Branch: `main`. Previous: T1 commit.
- Task 2 of 6.

---

## Task 3: Extract `ReviewDetail` component from current `ReviewPage`

Pull the current passive-viewer logic out of `ReviewPage.tsx` into a reusable `ReviewDetail` that takes a session-id from the URL.

**Files:**
- Create: `frontend/src/pages/ReviewDetail.tsx`
- Create: `frontend/src/pages/ReviewDetail.test.tsx`

- [ ] **Step 1: Write failing tests** `frontend/src/pages/ReviewDetail.test.tsx`:

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

function wrap(node: React.ReactNode, initialPath = "/review/s1") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/review/:sessionId" element={node} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("ReviewDetail", () => {
  it("renders conversation with inline corrections", async () => {
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: {
        getSession: vi.fn().mockResolvedValue({
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
        }),
      },
      ApiError: class extends Error {},
    }));
    const { ReviewDetail } = await import("./ReviewDetail");
    render(wrap(<ReviewDetail />));
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
        getSession: vi.fn().mockResolvedValue({
          session_id: "s1",
          scenario_id: "x",
          started_at: "2026-05-21T10:00:00",
          ended_at: "2026-05-21T10:15:00",
          opening_text: "Hi.",
          turns: [{ ts: "...", user_text: "hello", llm_text: "hi" }],
        }),
      },
      ApiError: class extends Error {},
    }));
    const { ReviewDetail } = await import("./ReviewDetail");
    render(wrap(<ReviewDetail />));
    await waitFor(() => {
      expect(screen.getByText(/analyzing/i)).toBeInTheDocument();
    });
  });

  it("shows clean session message when growth_points is empty", async () => {
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: {
        getSession: vi.fn().mockResolvedValue({
          session_id: "s1",
          scenario_id: "x",
          started_at: "2026-05-21T10:00:00",
          ended_at: "2026-05-21T10:15:00",
          opening_text: "Hi.",
          turns: [{ ts: "...", user_text: "hello", llm_text: "hi" }],
          growth_points: [],
        }),
      },
      ApiError: class extends Error {},
    }));
    const { ReviewDetail } = await import("./ReviewDetail");
    render(wrap(<ReviewDetail />));
    await waitFor(() => {
      expect(screen.getByText(/no corrections found/i)).toBeInTheDocument();
    });
  });

  it("shows error banner when growth_points_error is set", async () => {
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: {
        getSession: vi.fn().mockResolvedValue({
          session_id: "s1",
          scenario_id: "x",
          started_at: "2026-05-21T10:00:00",
          ended_at: "2026-05-21T10:15:00",
          opening_text: "Hi.",
          turns: [{ ts: "...", user_text: "hello", llm_text: "hi" }],
          growth_points_error: "rate_limit",
        }),
      },
      ApiError: class extends Error {},
    }));
    const { ReviewDetail } = await import("./ReviewDetail");
    render(wrap(<ReviewDetail />));
    await waitFor(() => {
      expect(screen.getByText(/analysis failed: rate_limit/i)).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 2: Run** `npm test ReviewDetail` → 4 fail.

- [ ] **Step 3: Implement `frontend/src/pages/ReviewDetail.tsx`**:

```typescript
import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
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
    const needle = gp.user_utterance.toLowerCase().trim();
    if (needle && lower.includes(needle)) {
      matched.push(gp);
    } else {
      remaining.push(gp);
    }
  }
  return { matched, remaining };
}

export function ReviewDetail() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const { data: session, isLoading, error } = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => api.getSession(sessionId!),
    enabled: !!sessionId,
    refetchInterval: (q) => {
      const data = q.state.data as SessionData | undefined;
      return data && isAnalyzing(data) ? 3000 : false;
    },
  });

  if (isLoading) {
    return <div className="p-8 text-slate-600">Loading…</div>;
  }
  if (error || !session) {
    return (
      <div className="p-8 text-center text-slate-600">
        Session not found. <Link to="/review" className="text-blue-600 underline">Back to list</Link>.
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
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-slate-900">Session review</h1>
        <Link to="/review" className="text-sm text-blue-600 hover:underline">← Back to list</Link>
      </div>

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

- [ ] **Step 4: Run + commit**

```bash
npm test 2>&1 | tail -10
npm run build 2>&1 | tail -5
cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/pages/ReviewDetail.tsx frontend/src/pages/ReviewDetail.test.tsx
git commit -m "feat(review): ReviewDetail component (session viewer at /review/:id)"
```

## Context

- Branch: `main`. Previous: T2 commit.
- Task 3 of 6.

---

## Task 4: Rewrite `ReviewPage` as 7-day session list

**Files:**
- Modify: `frontend/src/pages/ReviewPage.tsx` (full rewrite)
- Modify: `frontend/src/pages/ReviewPage.test.tsx` (full rewrite)

- [ ] **Step 1: Write failing tests** `frontend/src/pages/ReviewPage.test.tsx` (replace existing):

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <BrowserRouter>
      <QueryClientProvider client={qc}>{node}</QueryClientProvider>
    </BrowserRouter>
  );
}

describe("ReviewPage (list)", () => {
  it("shows empty state when no sessions in 7 days", async () => {
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: {
        getSessions: vi.fn().mockResolvedValue([]),
        getScenarios: vi.fn().mockResolvedValue([]),
      },
      ApiError: class extends Error {},
    }));
    const { ReviewPage } = await import("./ReviewPage");
    render(wrap(<ReviewPage />));
    await waitFor(() => {
      expect(screen.getByText(/no sessions in the last 7 days/i)).toBeInTheDocument();
    });
  });

  it("filters out sessions older than 7 days", async () => {
    vi.resetModules();
    const now = new Date();
    const today = now.toISOString();
    const tenDaysAgo = new Date(now.getTime() - 10 * 86400000).toISOString();
    vi.doMock("../api/client", () => ({
      api: {
        getSessions: vi.fn().mockResolvedValue([
          {
            session_id: "recent", scenario_id: "tech_interview_behavioral",
            started_at: today, ended_at: today,
            opening_text: "Hi.", turns: [], growth_points: [],
          },
          {
            session_id: "old", scenario_id: "tech_interview_behavioral",
            started_at: tenDaysAgo, ended_at: tenDaysAgo,
            opening_text: "Hi.", turns: [], growth_points: [],
          },
        ]),
        getScenarios: vi.fn().mockResolvedValue([
          { id: "tech_interview_behavioral", name: "Behavioral", difficulty: "easy" },
        ]),
      },
      ApiError: class extends Error {},
    }));
    const { ReviewPage } = await import("./ReviewPage");
    render(wrap(<ReviewPage />));
    await waitFor(() => {
      expect(screen.getByText(/behavioral/i)).toBeInTheDocument();
    });
    // The old session shouldn't appear — assert by looking for a link to its id
    expect(screen.queryByRole("link", { name: /old/i })).not.toBeInTheDocument();
  });

  it("renders each session row with scenario name and status pill", async () => {
    vi.resetModules();
    const today = new Date().toISOString();
    vi.doMock("../api/client", () => ({
      api: {
        getSessions: vi.fn().mockResolvedValue([
          {
            session_id: "s1", scenario_id: "tech_interview_behavioral",
            started_at: today, ended_at: today,
            opening_text: "Hi.", turns: [],
            growth_points: [{ tag: "vocab", user_utterance: "x", corrected_version: "y", explanation: "z", context: null }],
          },
          {
            session_id: "s2", scenario_id: "tech_interview_behavioral",
            started_at: today, ended_at: today,
            opening_text: "Hi.", turns: [],
            growth_points: [],
          },
          {
            session_id: "s3", scenario_id: "tech_interview_behavioral",
            started_at: today, ended_at: today,
            opening_text: "Hi.", turns: [],
            // no growth_points → analyzing
          },
        ]),
        getScenarios: vi.fn().mockResolvedValue([
          { id: "tech_interview_behavioral", name: "Behavioral", difficulty: "easy" },
        ]),
      },
      ApiError: class extends Error {},
    }));
    const { ReviewPage } = await import("./ReviewPage");
    render(wrap(<ReviewPage />));
    await waitFor(() => {
      expect(screen.getByText("1 correction")).toBeInTheDocument(); // s1
      expect(screen.getByText("Clean")).toBeInTheDocument();         // s2
      expect(screen.getByText("Analyzing")).toBeInTheDocument();     // s3
    });
  });
});
```

- [ ] **Step 2: Run** `npm test ReviewPage` → fail (current ReviewPage exports passive viewer, not list).

- [ ] **Step 3: Rewrite `frontend/src/pages/ReviewPage.tsx`**:

```typescript
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { ScenarioSummary, SessionData } from "../api/types";

const SEVEN_DAYS_MS = 7 * 24 * 60 * 60 * 1000;

function formatWhen(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  const yesterday = new Date(now.getTime() - 86400000);
  const isYesterday = d.toDateString() === yesterday.toDateString();
  const hh = String(d.getHours()).padStart(2, "0");
  const mm = String(d.getMinutes()).padStart(2, "0");
  if (sameDay) return `Today ${hh}:${mm}`;
  if (isYesterday) return `Yesterday ${hh}:${mm}`;
  const wd = d.toLocaleDateString("en-US", { weekday: "short" });
  const day = d.getDate();
  const month = d.toLocaleDateString("en-US", { month: "short" });
  return `${wd} ${day} ${month} ${hh}:${mm}`;
}

type Status = { label: string; cls: string };

function statusFor(s: SessionData): Status {
  if (s.growth_points_error) return { label: "Error", cls: "bg-red-100 text-red-800" };
  if (!s.growth_points) return { label: "Analyzing", cls: "bg-slate-100 text-slate-700" };
  if (s.growth_points.length === 0) return { label: "Clean", cls: "bg-emerald-100 text-emerald-800" };
  const n = s.growth_points.length;
  return { label: `${n} correction${n === 1 ? "" : "s"}`, cls: "bg-blue-100 text-blue-800" };
}

export function ReviewPage() {
  const { data: sessions, isLoading } = useQuery({
    queryKey: ["sessions-7d"],
    queryFn: () => api.getSessions(50),
  });
  const { data: scenarios } = useQuery({
    queryKey: ["scenarios"],
    queryFn: () => api.getScenarios(),
    staleTime: Infinity,
  });

  if (isLoading) {
    return <div className="p-8 text-slate-600">Loading…</div>;
  }

  const cutoff = Date.now() - SEVEN_DAYS_MS;
  const recent = (sessions ?? []).filter(
    (s) => new Date(s.started_at).getTime() >= cutoff,
  );

  if (recent.length === 0) {
    return (
      <div className="p-8 text-center text-slate-600">
        No sessions in the last 7 days. <Link to="/" className="text-blue-600 underline">Run one</Link>.
      </div>
    );
  }

  const scenarioName = (id: string) =>
    scenarios?.find((sc: ScenarioSummary) => sc.id === id)?.name ?? id;

  return (
    <div className="max-w-3xl mx-auto p-6 w-full">
      <h1 className="text-2xl font-semibold mb-4 text-slate-900">Recent sessions</h1>
      <ul className="space-y-2">
        {recent.map((s) => {
          const st = statusFor(s);
          return (
            <li key={s.session_id}>
              <Link
                to={`/review/${s.session_id}`}
                className="block p-3 border border-slate-200 rounded hover:bg-slate-50 transition"
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="text-sm font-medium text-slate-900 truncate">
                      {scenarioName(s.scenario_id)}
                    </div>
                    <div className="text-xs text-slate-500">{formatWhen(s.started_at)}</div>
                  </div>
                  <span className={`text-xs font-semibold rounded px-2 py-1 whitespace-nowrap ${st.cls}`}>
                    {st.label}
                  </span>
                </div>
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
```

- [ ] **Step 4: Run + commit**

```bash
npm test 2>&1 | tail -10
npm run build 2>&1 | tail -5
cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/pages/ReviewPage.tsx frontend/src/pages/ReviewPage.test.tsx
git commit -m "feat(review): /review = list of sessions from last 7 days"
```

## Context

- Branch: `main`. Previous: T3 commit.
- Task 4 of 6.

---

## Task 5: Wire `/review/:sessionId` route in `App.tsx`

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Add import + route**

Read `frontend/src/App.tsx`. Add:
```typescript
import { ReviewDetail } from "./pages/ReviewDetail";
```

Add a new route alongside the existing routes block:
```typescript
<Route path="/review/:sessionId" element={<ReviewDetail />} />
```

The Routes block should end up looking like:
```typescript
<Routes>
  <Route path="/" element={<ScenariosPage />} />
  <Route path="/session/:id" element={<SessionPage />} />
  <Route path="/review" element={<ReviewPage />} />
  <Route path="/review/:sessionId" element={<ReviewDetail />} />
  <Route path="/practice" element={<PracticePage />} />
  <Route path="/stats" element={<StatsPage />} />
</Routes>
```

- [ ] **Step 2: Run + commit**

```bash
npm test 2>&1 | tail -10
npm run build 2>&1 | tail -5
cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/App.tsx
git commit -m "feat(review): wire /review/:sessionId route"
```

## Context

- Branch: `main`. Previous: T4 commit.
- Task 5 of 6.

---

## Task 6: Manual end-to-end smoke

- [ ] **Step 1: Suites + build**

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor && source .venv/bin/activate && pytest 2>&1 | tail -5
cd frontend && npm test 2>&1 | tail -10
npm run build 2>&1 | tail -5
```

All green.

- [ ] **Step 2: Push**

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor
git push origin main
```

- [ ] **Step 3: Run web UI**

`./scripts/build_and_serve.sh` → opens `http://127.0.0.1:8000`.

Checks:

**Voice picker:**
1. Open session, dropdown shows 10 voices, NO `fable` / `onyx` / `nova`.
2. Pick e.g. `coral` → click Test → coral plays back from OpenAI.
3. Pick e.g. `verse` → Test → different voice plays.
4. Temporarily lower API key limit < $0.50 (via dashboard) → Test → amber banner "TTS error: …. Using browser voice." Some browser voice plays. Restore limit.

**Multi-session review:**
1. Click "Review" → see list of recent sessions (last 7 days only). Older sessions absent.
2. Each row: scenario name + relative time + status pill.
3. Click a row → `/review/:sessionId` → see conversation with inline corrections (T6 behavior).
4. Click "← Back to list" → list view.
5. Browser back/forward works between list and detail.
6. Empty state: rename `sessions/` temporarily → list shows "No sessions in the last 7 days." Restore.

**Practice page:** still works at `/practice` (SRS recall flow).

- [ ] **Step 4: Report**

If anything regresses or behaves unexpectedly, file a follow-up. Otherwise Stage 2c.1 done.

## Context

- Branch: `main`. Previous: T5 commit.
- Task 6 of 6.

---

## Self-review

1. **Spec coverage:**
   - Voice list pruned to supported set → T1 ✓
   - TTS errors visible to user → T2 ✓
   - Browser fallback picks matching voice → T2 ✓
   - Multi-session list (7 days) → T4 ✓
   - Click-through detail view → T3 + T5 ✓
   - Layout nav unchanged (still points to /review, which is now list) ✓

2. **Type consistency:**
   - `SessionData` already has `started_at`, `growth_points`, `growth_points_error` — used identically by ReviewPage list (status pill) and ReviewDetail (banner/render).
   - `ScenarioSummary` already exported from `types.ts` — used by ReviewPage for id→name lookup.
   - `useTTS` interface gains `lastError: string | null`. Any consumer (`SessionPage`, `VoicePicker`) reads it via destructure — VoicePicker doesn't need it.

3. **No placeholders:** all code shown.

4. **Failure modes:**
   - Backend TTS fail → banner visible + browser fallback with matching voice → T2 tests
   - Session ended but analyzing → "Analyzing" pill in list, polling in detail → T3 + T4 tests
   - Empty sessions list → "No sessions in the last 7 days" → T4 test
   - Bad session id in URL → "Session not found" → T3 implementation (not tested explicitly; future)

---

## Definition of Done

- 5 task commits + manual smoke on `origin/main`.
- pytest 178 green.
- npm test ~42 green (35 + ~7 new across T2 + T3 + T4).
- npm run build succeeds.
- `/review` shows last-7-days session list with status pills.
- `/review/:sessionId` shows the detail view (conversation + inline corrections).
- Voice picker drops fable/onyx/nova; TTS errors visible; browser fallback respects picked voice.
- CLI unchanged.
