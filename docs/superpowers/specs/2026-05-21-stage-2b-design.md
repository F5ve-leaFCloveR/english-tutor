# Stage 2b — Backend TTS + Async Evaluator + Voice Picker

- **Date:** 2026-05-21
- **Author:** Stas Arkhipov
- **Status:** Draft, pending implementation plan

## 1. Context

Stage 2a shipped a working browser UI on 2026-05-21. Real-use smoke surfaced four issues:

1. Browser TTS quality (SpeechSynthesis) is poor in both Chrome and Safari even with Siri Voice 2 downloaded — Apple's premium Siri voices are not exposed to the Web Speech API, leaving only basic compact voices.
2. The session's opening assistant message is rendered as a bubble but never spoken aloud. The TTS call was deliberately gated on a "user gesture" per iOS Safari, but the gate is never released.
3. End-of-session waits 3–5 seconds for evaluator + SRS card creation before navigation. The user stares at a spinner.
4. User wants the ability to choose among several TTS voices, not just one hard-coded default.

A POC (`scripts/poc_tts.py`) confirmed:

- Gemini TTS is **not** available via OpenRouter (verified across all 358 catalog models).
- OpenAI's `openai/gpt-audio-mini` works via OpenRouter using the existing API key. Quality is good (validated with sample). Cost is ~$0.00022 per short sentence — well under the $0.5/day cap (~200 sessions/day before hitting the cap).
- 13 voices are accessible: `alloy`, `echo`, `fable`, `onyx`, `nova`, `shimmer`, `ash`, `ballad`, `coral`, `sage`, `verse`, `marin`, `cedar`.

Stage 2b addresses all four issues. The "reading list" feature (item 4 from the original feedback list, not addressed here) is deferred to Stage 3 — it needs its own brainstorm.

## 2. Goals

- Replace browser SpeechSynthesis with backend-generated TTS via OpenRouter (`openai/gpt-audio-mini`). Quality must be perceptibly better than current.
- The session opening assistant message plays aloud automatically when the session screen mounts.
- Ending a session navigates back to home immediately; evaluator and SRS card creation run in the background.
- The user can choose among the 13 available voices via a small picker in the app header, with a "Test voice" sample. Selection persists across reloads.
- All existing CLI paths (`tutor interview`, `tutor review`, `tutor stats`) continue to work without changes.

## 3. Non-Goals

- Streaming TTS playback (chunked audio while still being generated). Current full-sentence-then-play latency (~3s for a 3s utterance) is acceptable for MVP.
- Persistent server-side TTS cache (file or DB). In-memory LRU is sufficient.
- Voice cloning, custom voice training.
- Reading list / article ingestion. Stage 3.
- Session history detail page (where past growth points are reviewable). Stage 2c.
- Session-end summary modal. Acceptable trade-off for async end.

## 4. Approach

**Backend TTS as a thin proxy with caching.** A new `TTSService` wraps the OpenRouter chat-completions call (with `modalities=["text","audio"]`, `audio.format="pcm16"`, `stream=True`), assembles PCM chunks into a WAV blob, returns bytes. An in-memory LRU caches by `sha256(text + voice)` so the opening line and review targets aren't regenerated within a process lifetime.

**Async session-end via FastAPI BackgroundTasks.** The `/api/sessions/{id}/end` route is the entrypoint that schedules the heavy work (`end_session_service`) as a background task. It returns HTTP 202 with `{session_id, status: "processing"}` immediately. The existing service is reused unchanged — only the route changes.

**Frontend voice abstraction.** `useTTS` is rewritten to call the backend first (fetch `/api/tts`, decode WAV, `<audio>` element plays). On network/budget/server error, it falls back to `window.speechSynthesis` so the app degrades gracefully instead of going silent. The hook's interface (`speak(text)`) is unchanged — `SessionPage` and `ReviewPage` need no logic edits beyond the opening-playback fix.

**Voice picker as a header dropdown.** A new `VoicePicker` component sits in `Layout` next to `BudgetIndicator`. It shows the 13 voices, persists the choice to `localStorage["ttsVoice"]`, and offers a "Test" button that plays a short sample sentence in the chosen voice. `useTTS` reads `localStorage["ttsVoice"]` on every call (no React re-render needed for value to take effect on next speech).

Alternatives considered:

- **OpenAI direct (not via OpenRouter):** would mean a new API key, separate budget tracking, separate billing. OpenRouter works fine — skip.
- **ElevenLabs:** higher quality but $5/mo and another key. Defer until OpenAI quality proves insufficient.
- **WebSocket / SSE for async end notification:** overkill for "no summary" UX choice. User goes home, cards appear on next review. No real-time updates needed.
- **Streaming TTS chunks to browser:** lower TTFB but adds complexity (range requests, MediaSource API). Defer.
- **Persistent file cache for TTS:** in-memory LRU is enough for typical usage patterns (opening + review target repetition). Process restart loses cache, regenerates first call. Cost is negligible.

## 5. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Browser                                                         │
│                                                                  │
│  SessionPage / ReviewPage / VoicePicker                          │
│       │  (uses) ─────────► useTTS                                │
│                                │                                 │
│                                ▼                                 │
│                       POST /api/tts {text, voice}                │
│                                │                                 │
│                                ▼                                 │
│                       <audio> plays returned WAV                 │
│                                │                                 │
│       fallback on error: window.speechSynthesis.speak            │
│                                                                  │
│  Voice picker in Layout header → localStorage["ttsVoice"]        │
│                                                                  │
│  End session: POST /api/sessions/{id}/end                        │
│       → 202 {status: "processing"}  → navigate("/")              │
└──────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│  FastAPI                                                         │
│                                                                  │
│  POST /api/tts ──► TTSService.synthesize(text, voice)            │
│                          │                                       │
│                          ├─ cache hit? return WAV bytes          │
│                          │                                       │
│                          └─ miss:                                │
│                                ├─ OpenRouter chat completions    │
│                                │    stream PCM16                 │
│                                ├─ assemble WAV header + data     │
│                                ├─ store in LRU                   │
│                                └─ return bytes                   │
│                                                                  │
│  POST /api/sessions/{id}/end                                     │
│       └─ background_tasks.add_task(end_session_service, id)      │
│       └─ return {session_id, status: "processing"} (202)         │
│                                                                  │
│  Existing routes unchanged.                                      │
└──────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│  Existing modules unchanged: SessionStorage, SRSEngine,          │
│  Evaluator, LLMClient, BudgetTracker.                            │
│  end_session_service unchanged — invoked via BackgroundTasks.    │
└──────────────────────────────────────────────────────────────────┘
```

## 6. Components

### 6.1 `tutor/web/tts.py` (NEW)

`TTSService` orchestrates the OpenRouter call and caches results.

```python
class TTSService:
    def __init__(
        self,
        client: OpenAI,           # OpenRouter-pointed
        model: str,               # "openai/gpt-audio-mini"
        default_voice: str,       # "alloy"
        budget: BudgetTracker,
        cache_capacity: int = 64,
    ) -> None: ...

    def synthesize(self, text: str, voice: str | None = None) -> bytes:
        """Return WAV bytes. Uses cache if available."""
```

Internals:
- Pre-call: `budget.check_can_spend()`. Post-call: record cost from `usage` (if present).
- Cache key: `hashlib.sha256(f"{voice}|{text}".encode()).hexdigest()`.
- Cache: `collections.OrderedDict` for LRU (max 64 entries; pop oldest on overflow).
- OpenRouter call shape (per POC):
  ```python
  stream = client.chat.completions.create(
      model=self._model,
      messages=[{"role": "user", "content": f"Say exactly this sentence: {text}"}],
      modalities=["text", "audio"],
      audio={"voice": voice, "format": "pcm16"},
      stream=True,
      stream_options={"include_usage": True},
  )
  ```
- PCM assembly: iterate `chunk.choices[0].delta.audio.data` (base64), decode, concatenate; wrap with WAV header (24000 Hz, mono, 16-bit signed LE) using `wave` stdlib.

Error handling:
- `BudgetExceededError` propagates (already handled by exception_handlers → 429).
- Network/API errors raise a new `TTSGenerationError`. Frontend will catch via 5xx → fallback to SpeechSynthesis.

### 6.2 `tutor/web/api.py` modifications

**New route:**

```
POST /api/tts
  body: {"text": str, "voice"?: str}
  → 200 audio/wav binary (Content-Type: audio/wav)
  → 422 if text empty
  → 429 if budget exhausted
  → 502 if TTSGenerationError (transient OpenRouter failure)
```

`Content-Disposition: inline` so browsers play it without download prompt.

**Modified route:**

```
POST /api/sessions/{id}/end
  → 202 {"session_id": str, "status": "processing"}
  → 404 if session not found (synchronously, before scheduling)
```

The route validates the session exists synchronously (avoid scheduling a no-op task), then `background_tasks.add_task(services.end_session_service, deps, session_id)`. Return immediately.

Note: BackgroundTasks run after the response is sent but before the worker is fully free. For a single-user CLI/web app, that's fine. If we ever serve multiple users, this changes (need a real task queue), but that's out of Stage 2b's scope.

### 6.3 `tutor/web/services.py` modifications

`end_session_service` itself is unchanged — it stays a synchronous Python function. The change is purely at the route layer.

One new tiny helper added:

```python
def get_session_or_raise(deps: Dependencies, session_id: str) -> dict:
    """Same as get_session_service but explicit name for the validate-then-schedule path."""
    return get_session_service(deps, session_id)
```

(Or we just call `get_session_service` directly from the route — same thing. Whichever the implementer finds cleaner.)

### 6.4 `tutor/web/schemas.py` additions

```python
class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    voice: str | None = None

class EndSessionAccepted(BaseModel):
    session_id: str
    status: Literal["processing"] = "processing"
```

### 6.5 `tutor/settings.py` additions

```python
tts_model: str = Field(default="openai/gpt-audio-mini",
                       description="OpenRouter TTS model")
tts_voice: str = Field(default="alloy",
                       description="Default TTS voice (overridable per request)")
```

`.env.example` gets two new lines.

### 6.6 `tutor/web/deps.py` modifications

`Dependencies` dataclass gets two new fields and `build_dependencies` populates them:

```python
@dataclass
class Dependencies:
    # ... existing ...
    tts_model: str
    tts_voice: str

def build_dependencies(project_root: Path) -> Dependencies:
    # ... existing ...
    return Dependencies(
        # ...
        tts_model=settings.tts_model,
        tts_voice=settings.tts_voice,
    )
```

In production, `create_app` instantiates `TTSService` from `deps.llm._client` (reuse the same OpenAI/OpenRouter HTTP client), `deps.tts_model`, `deps.tts_voice`, `deps.budget`. The route handler holds a closure over this single instance.

### 6.7 `frontend/src/api/client.ts` additions

```typescript
synthesizeTTS(text: string, voice?: string): Promise<Blob> {
    // POST /api/tts with JSON body, expect audio/wav back
    return fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, voice }),
    }).then(r => {
        if (!r.ok) { /* throw ApiError */ }
        return r.blob();
    });
}
```

`endSession` return type narrows to the new accepted shape:

```typescript
endSession(session_id: string): Promise<{ session_id: string; status: "processing" }>
```

### 6.8 `frontend/src/hooks/useTTS.ts` rewrite

Same interface (`speak(text) → Promise<void>`, `isSpeaking`, `voices`), new internals:

```typescript
function useTTS() {
    const [isSpeaking, setIsSpeaking] = useState(false);
    const audioRef = useRef<HTMLAudioElement | null>(null);

    const speak = async (text: string): Promise<void> => {
        if (!text.trim()) return;
        const voice = localStorage.getItem("ttsVoice") || undefined;
        setIsSpeaking(true);
        try {
            const blob = await api.synthesizeTTS(text, voice);
            const url = URL.createObjectURL(blob);
            const audio = new Audio(url);
            audioRef.current = audio;
            await new Promise<void>((resolve, reject) => {
                audio.onended = () => { URL.revokeObjectURL(url); resolve(); };
                audio.onerror = () => { URL.revokeObjectURL(url); reject(); };
                audio.play().catch(reject);
            });
        } catch (e) {
            // Fallback to SpeechSynthesis
            await speakWithBrowser(text, voice);
        } finally {
            setIsSpeaking(false);
        }
    };

    // voices array: hardcoded list of 13 OpenAI voices (no need to fetch from backend)
    const voices = OPENAI_TTS_VOICES;

    return { speak, isSpeaking, voices };
}
```

`speakWithBrowser` is the previous SpeechSynthesis logic, retained as a fallback path.

`voices` is now a static array of the 13 voice names (`alloy`, `echo`, ..., `cedar`) — consumed by `VoicePicker`.

### 6.9 `frontend/src/components/VoicePicker.tsx` (NEW)

Small dropdown rendered in `Layout` header next to `BudgetIndicator`:

```typescript
function VoicePicker() {
    const tts = useTTS();
    const [selected, setSelected] = useState(
        () => localStorage.getItem("ttsVoice") || "alloy"
    );

    const change = (voice: string) => {
        localStorage.setItem("ttsVoice", voice);
        setSelected(voice);
    };

    const testSample = "This is a sample of the selected voice.";

    return (
        <div className="flex items-center gap-2">
            <select value={selected} onChange={(e) => change(e.target.value)}
                    className="text-xs border rounded px-2 py-1 bg-white">
                {OPENAI_TTS_VOICES.map(v => <option key={v} value={v}>{v}</option>)}
            </select>
            <button onClick={() => tts.speak(testSample)}
                    disabled={tts.isSpeaking}
                    className="text-xs px-2 py-1 border rounded hover:bg-slate-100 disabled:opacity-50">
                Test
            </button>
        </div>
    );
}
```

Component is placed in `Layout` header immediately before `BudgetIndicator`. On mobile widths, the dropdown shrinks but stays usable.

### 6.10 `frontend/src/pages/SessionPage.tsx` modifications

Two changes:

**a) Opening auto-playback fix.** Add a `useEffect` that fires once when the session loads:

```typescript
const playedOpeningRef = useRef(false);

useEffect(() => {
    if (playedOpeningRef.current) return;
    const opening = messages.find(m => m.role === "assistant")?.text;
    if (opening) {
        playedOpeningRef.current = true;
        tts.speak(opening).catch(() => {/* non-fatal */});
    }
}, [messages]);
```

The ref ensures we only speak once even on re-renders.

**b) Async end — no summary.** `endMutation.onSuccess` becomes:

```typescript
onSuccess: () => {
    navigate("/");
}
```

`SessionSummary` import and rendering are removed (component file stays in the tree, just unused). The route immediately navigates away; the user does not see a spinner.

### 6.11 `frontend/src/components/Layout.tsx` modifications

Add `<VoicePicker />` immediately before `<BudgetIndicator />` in the header bar. Both wrapped in a flex container so they sit side-by-side on desktop, stack vertically on mobile if needed.

### 6.12 `frontend/src/components/SessionSummary.tsx`

Unchanged. Stays in the tree unused, ready for re-introduction in Stage 2c (session history page).

## 7. Data Flow

### 7.1 TTS request lifecycle

```
1. SessionPage / ReviewPage / VoicePicker calls tts.speak(text)
2. useTTS reads localStorage["ttsVoice"]
3. POST /api/tts {text, voice}
4. Backend: TTSService.synthesize
     ├─ check cache (sha256(voice|text)) — hit? return cached bytes
     └─ miss:
          ├─ budget.check_can_spend()
          ├─ OpenRouter stream PCM16
          ├─ concat → WAV header + data
          ├─ store in LRU
          ├─ budget.record(...)
          └─ return bytes
5. Browser receives audio/wav, plays via <audio>
6. On error: fallback to window.speechSynthesis with same text
```

### 7.2 Async session-end lifecycle

```
1. User clicks "End session" in SessionPage
2. POST /api/sessions/{id}/end
3. Backend: route validates session exists synchronously
4. background_tasks.add_task(end_session_service, deps, session_id)
5. Return 202 {session_id, status: "processing"}
6. Frontend: navigate("/") immediately
7. Background: evaluator → set_growth_points → SRS.create_cards → end_session
8. User next time visits /review or /stats → sees new cards/numbers
```

### 7.3 Voice picker lifecycle

```
1. VoicePicker mounts, reads localStorage["ttsVoice"] (default "alloy")
2. User changes select → localStorage updated + local state updated
3. User clicks "Test" → tts.speak("This is a sample…") with chosen voice
4. Sample plays from backend or fallback
5. Subsequent session/review TTS uses the chosen voice (read from localStorage on each call)
```

## 8. Error Handling

| Failure | Backend handling | Frontend handling |
|---|---|---|
| OpenRouter timeout / 5xx during TTS | Raise `TTSGenerationError` → 502 | Catch in useTTS, fallback to SpeechSynthesis |
| OpenRouter 429 (rate limit) | Existing LLMClient retry — pass through | Same |
| Budget exhausted | `BudgetExceededError` → 429 | Toast "Budget cap reached"; fallback to SpeechSynthesis briefly until cap resets |
| Empty TTS text | 422 `{"error": "no_text"}` | useTTS short-circuits before request anyway |
| Session not found at /end | 404 (synchronous) | Toast "Session not found"; stay on session screen |
| BackgroundTask throws inside end_session_service | Existing internal error handling (`growth_points_error` persisted to session JSON) — task itself returns silently | Frontend never sees; user sees the error if they navigate to a future session-history view (Stage 2c) |
| WAV decode fails in browser | `<audio>` `onerror` | Fallback to SpeechSynthesis |
| `localStorage` unavailable (private browsing) | N/A | Falls back to default voice ("alloy"), VoicePicker is read-only |
| Voice picker selects invalid voice (manual localStorage edit) | OpenRouter returns 400 | useTTS catches, falls back to SpeechSynthesis with no voice override |

## 9. Budget

Backend TTS adds a new spend source:

- Per request: ~200–800 chars → roughly $0.00005–0.0002 per call (per POC).
- Per session: 1 opening + ~15 assistant replies = 16 TTS calls, ~$0.001–0.003 per session.
- Per review session: ~10 target replays = ~$0.0005 per review session.
- Daily total at typical use: well under $0.05/day. The existing $0.50/day cap remains generous.

The existing `BudgetTracker.check_can_spend()` and `record(tokens, cost)` are reused inside `TTSService`. Cost is read from `usage.cost` in the streamed final chunk (per POC), with a 0.0 fallback if missing.

In-memory LRU cache means the opening line is generated once per process lifetime, regenerated on uvicorn restart. Worst case: same opening cached across users — fine for single-user.

## 10. Testing

### Backend

- **`tutor/web/tts.py`** unit tests: mocked OpenRouter stream returns canned PCM bytes; assert WAV header is correctly formed (RIFF magic, 24kHz, mono, 16-bit), assert cache hit returns identical bytes without second OpenRouter call, assert cache eviction at capacity, assert budget cost is recorded.
- **`tutor/web/api.py`** integration tests via TestClient:
  - `POST /api/tts` happy path returns 200 audio/wav with non-empty body.
  - Empty text → 422.
  - Mocked `TTSService` raising `TTSGenerationError` → 502.
  - Mocked budget exhausted → 429.
  - `POST /api/sessions/{id}/end` now returns 202 with the new schema; background task runs (use `BackgroundTasks` patching to assert the right service was scheduled).
  - `/end` on unknown session still returns 404 synchronously.

### Frontend

- **`useTTS`** tests: backend success path (mocked `api.synthesizeTTS` returns a Blob, audio.play stubbed), fallback path (api throws → SpeechSynthesis invoked).
- **`VoicePicker`** tests: renders 13 options; change updates localStorage; Test button calls tts.speak.
- **`SessionPage`** test extension: opening TTS auto-plays on mount; endMutation success navigates to `/` (no summary modal).
- **`ReviewPage`**: existing tests unchanged — useTTS interface is the same.

### Integration / manual smoke

After implementation:
- Visit `/`, change voice to `nova` via header picker, click "Test" → hear sample.
- Start a session, hear opening play automatically.
- Have a turn, hear reply.
- Click "End session" — page returns to `/` instantly.
- Wait ~5s, navigate to `/review` — new cards appear.

## 11. Decisions

| Decision | Choice | Why |
|---|---|---|
| TTS provider | OpenAI gpt-audio-mini via OpenRouter | Existing key, validated quality, cheap |
| Voice options | All 13 OpenAI voices | Static list, no need to fetch |
| Default voice | `alloy` | Validated in POC |
| Streaming TTS to browser | No, full sentence then play | Simpler, 3s latency acceptable |
| TTS cache | In-memory LRU, 64 entries | Process-lifetime sufficient |
| Async end | FastAPI `BackgroundTasks` | Native, no infra; single-user OK |
| End UX | Immediate navigate, no summary | Spec; user explicitly chose simplest path |
| Voice picker location | Layout header | Always accessible; doesn't need settings page |
| Voice persistence | `localStorage["ttsVoice"]` | Simple, no backend state |
| Voice picker default | `alloy` | Matches backend default |
| Fallback to SpeechSynthesis | Yes, on any backend TTS error | Graceful degradation |
| Backend TTS endpoint format | POST JSON, return raw audio/wav | Simplest contract; no base64 overhead |

## 12. Open Questions / Risks

- **TTS quality across all 13 voices is not verified.** POC tested only `alloy`. If some voices sound bad, that's acceptable — user picks what they like.
- **PCM-to-WAV header generation is one-off code in `TTSService`.** Standard Python `wave` module handles it. Risk is minor (well-defined format).
- **BackgroundTask exception swallowing:** if `end_session_service` raises something unexpected (not caught internally), the user never knows. Stage 2c may add a session-history page; until then, the failure mode is "session has no growth points and the user wonders why." Existing internal try/except catches evaluator + create_cards failures and writes `growth_points_error` — so the failure IS recorded, just invisible until we have a UI to surface it.
- **Process restart loses TTS cache.** Acceptable; the cache rebuilds on next access.
- **OpenRouter rate limit during a session:** the existing `LLMClient` retry logic also applies via the shared `OpenAI` client. If we exceed retries, request fails → frontend falls back to SpeechSynthesis for that one phrase.
- **`localStorage` size limit (typically 5MB):** we store only a small string key. No risk.
- **Voice picker on mobile screen widths:** the header may get crowded with logo + nav + picker + budget. CSS will need responsive handling. Acceptable to test and adjust during implementation.

## 13. Success Criteria

Stage 2b is successful when:

- A real session in the browser plays the opening line automatically through the backend-generated TTS, in a voice that sounds natural (not robotic).
- Changing the voice in the header picker is reflected on the next utterance.
- Clicking "End session" navigates to `/` within ~200ms, regardless of how long evaluator + SRS take.
- Within ~5–10 seconds of ending a session, new cards become available in `/review`.
- Full `pytest` suite green (~155+ tests after Stage 2b additions).
- `npm test` green.
- CLI commands continue to work (regression check).
- Daily budget after a typical use day stays well under $0.50.
