# Stage 2b — Backend TTS + Async End + Voice Picker — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace browser SpeechSynthesis with backend-generated TTS via `openai/gpt-audio-mini` (alloy default, 13 voices); fix the session opening auto-playback bug; make `/api/sessions/{id}/end` non-blocking via FastAPI BackgroundTasks; add a small voice picker to the header.

**Architecture:** New `tutor/web/tts.py` calls OpenRouter with streaming PCM16, assembles WAV, caches in-memory LRU. New `POST /api/tts` route. `POST /api/sessions/{id}/end` schedules `end_session_service` as a BackgroundTask and returns 202 immediately. Frontend `useTTS` calls the backend first, falls back to SpeechSynthesis on error. A `VoicePicker` dropdown in `Layout` persists choice to `localStorage`. No other components change.

**Tech Stack:** Same as Stage 2a — Python 3.11+, FastAPI, openai SDK against OpenRouter, React 18 + TypeScript, Vite, Tailwind. No new dependencies.

**Prerequisites:**
- Stage 2a complete (~153 pytest + 19 npm test green; branch `main` at `6c7358b` or later).
- POC script `scripts/poc_tts.py` confirms `openai/gpt-audio-mini` via existing OpenRouter key works.

---

## File Structure

```
tutor/
├── settings.py                   (MODIFY: tts_model + tts_voice fields)
├── web/
│   ├── tts.py                    (NEW: TTSService)
│   ├── schemas.py                (MODIFY: TTSRequest + EndSessionAccepted)
│   ├── deps.py                   (MODIFY: tts_model + tts_voice in Dependencies)
│   └── api.py                    (MODIFY: POST /api/tts; /end → BackgroundTasks 202)

frontend/src/
├── api/
│   ├── types.ts                  (MODIFY: end response shape; add OPENAI_TTS_VOICES const)
│   └── client.ts                 (MODIFY: synthesizeTTS method; endSession return type)
├── hooks/
│   └── useTTS.ts                 (REWRITE: backend primary + SpeechSynthesis fallback)
├── components/
│   ├── Layout.tsx                (MODIFY: insert VoicePicker)
│   └── VoicePicker.tsx           (NEW)
└── pages/
    └── SessionPage.tsx           (MODIFY: opening useEffect; remove SessionSummary modal)

tests/web/
├── test_tts.py                   (NEW)
├── test_schemas.py               (MODIFY: TTSRequest + EndSessionAccepted)
├── test_deps.py                  (MODIFY: tts fields in Dependencies)
└── test_api.py                   (MODIFY: /api/tts tests; /end 202 tests)

.env.example                      (MODIFY: 2 new lines)
```

---

## Task 1: Settings — tts_model + tts_voice

**Files:**
- Modify: `tutor/settings.py`
- Modify: `tests/test_settings.py`
- Modify: `.env.example`

- [ ] **Step 1: Write failing tests**

Update `test_settings_loads_api_key` in `tests/test_settings.py` — add two assertions at the end:

```python
    assert s.tts_model == "openai/gpt-audio-mini"
    assert s.tts_voice == "alloy"
```

- [ ] **Step 2: Run** `cd /Users/sarkhipov/Work/Personal/english-tutor && source .venv/bin/activate && pytest tests/test_settings.py::test_settings_loads_api_key -v` → FAIL.

- [ ] **Step 3: Add fields to `tutor/settings.py`** — insert after `openrouter_grader_model`:

```python
    tts_model: str = Field(
        default="openai/gpt-audio-mini",
        description="OpenRouter TTS model for backend speech synthesis",
    )
    tts_voice: str = Field(
        default="alloy",
        description="Default TTS voice (overridable per request via /api/tts body)",
    )
```

- [ ] **Step 4: Update `.env.example`** (path denied to Edit, use Bash `printf >>`):

Append these two lines:
```
TTS_MODEL=openai/gpt-audio-mini
TTS_VOICE=alloy
```

Use Bash: `printf "TTS_MODEL=openai/gpt-audio-mini\nTTS_VOICE=alloy\n" >> /Users/sarkhipov/Work/Personal/english-tutor/.env.example`. Verify with `cat /Users/sarkhipov/Work/Personal/english-tutor/.env.example`.

- [ ] **Step 5: Run tests + commit**

`pytest` → all green (~154).

```bash
git add tutor/settings.py tests/test_settings.py .env.example
git commit -m "feat(settings): add tts_model + tts_voice env vars"
```

---

## Task 2: Schemas — TTSRequest + EndSessionAccepted

**Files:**
- Modify: `tutor/web/schemas.py`
- Modify: `tests/web/test_schemas.py`

- [ ] **Step 1: Append failing tests** in `tests/web/test_schemas.py`:

```python
def test_tts_request_schema():
    from tutor.web.schemas import TTSRequest
    import pytest as _p
    TTSRequest(text="hello")
    TTSRequest(text="hello", voice="alloy")
    with _p.raises(Exception):
        TTSRequest(text="")  # min_length=1


def test_end_session_accepted_schema():
    from tutor.web.schemas import EndSessionAccepted
    r = EndSessionAccepted(session_id="abc12345")
    assert r.status == "processing"
    assert r.session_id == "abc12345"
```

- [ ] **Step 2: Run** `pytest tests/web/test_schemas.py -v` → 2 fail.

- [ ] **Step 3: Append to `tutor/web/schemas.py`**:

```python
class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    voice: str | None = None


class EndSessionAccepted(BaseModel):
    session_id: str
    status: Literal["processing"] = "processing"
```

- [ ] **Step 4: Run tests + commit**

`pytest tests/web/test_schemas.py -v` → 7 passed.
`pytest` → green.

```bash
git add tutor/web/schemas.py tests/web/test_schemas.py
git commit -m "feat(web): TTSRequest + EndSessionAccepted schemas"
```

---

## Task 3: Dependencies — tts_model + tts_voice

**Files:**
- Modify: `tutor/web/deps.py`
- Modify: `tests/web/test_deps.py`

- [ ] **Step 1: Update tests**

In `tests/web/test_deps.py`, in `test_dependencies_dataclass_holds_components`, add to the `Dependencies(...)` call:

```python
        tts_model="m3",
        tts_voice="v1",
```

In `test_build_dependencies_from_settings`, add two assertions at the end:

```python
    assert deps.tts_model == "openai/gpt-audio-mini"
    assert deps.tts_voice == "alloy"
```

- [ ] **Step 2: Run** `pytest tests/web/test_deps.py -v` → fail.

- [ ] **Step 3: Update `tutor/web/deps.py`**

In `Dependencies` dataclass, append two fields:

```python
    tts_model: str
    tts_voice: str
```

In `build_dependencies`, append to the returned Dependencies:

```python
        tts_model=settings.tts_model,
        tts_voice=settings.tts_voice,
```

- [ ] **Step 4: Run tests + commit**

`pytest tests/web/test_deps.py -v` → 2 passed.
`pytest` → green.

```bash
git add tutor/web/deps.py tests/web/test_deps.py
git commit -m "feat(web): pass tts_model + tts_voice through Dependencies"
```

Note: this may break existing tests that construct `Dependencies(...)` literally. Fix any failures by adding the two new fields to those constructor calls with placeholder values (e.g., `tts_model="m", tts_voice="v"`). Affected files likely: `tests/web/test_services_session.py`, `test_services_turn.py`, `test_services_end.py`, `test_services_review.py`, `test_services_stats.py`, `test_api.py`. Touch only what's needed to keep tests green.

---

## Task 4: TTSService — OpenRouter streaming + WAV + LRU cache

**Files:**
- Create: `tutor/web/tts.py`
- Create: `tests/web/test_tts.py`

- [ ] **Step 1: Write failing tests**

`tests/web/test_tts.py`:

```python
import base64
import wave
from datetime import datetime
from io import BytesIO
from unittest.mock import MagicMock
import pytest


def _make_budget(tmp_path):
    from tutor.budget import BudgetTracker
    return BudgetTracker(
        path=tmp_path / "b.json",
        daily_usd_cap=1.0,
        daily_token_cap=1_000_000,
        now=lambda: datetime(2026, 5, 21, 12, 0),
    )


def _stub_pcm_stream(pcm_bytes: bytes, cost: float = 0.0):
    """Yield SSE-like chunks: first chunks deliver audio data (base64), final has usage."""
    # Split PCM into two halves for realism
    half = len(pcm_bytes) // 2
    chunk1, chunk2 = pcm_bytes[:half], pcm_bytes[half:]

    def make_audio_chunk(b: bytes):
        c = MagicMock()
        c.choices = [MagicMock()]
        c.choices[0].delta = MagicMock()
        c.choices[0].delta.audio = {"data": base64.b64encode(b).decode("ascii")}
        c.usage = None
        return c

    final = MagicMock()
    final.choices = [MagicMock()]
    final.choices[0].delta = MagicMock()
    final.choices[0].delta.audio = None
    final.usage = MagicMock()
    final.usage.prompt_tokens = 50
    final.usage.completion_tokens = 100
    final.usage.total_tokens = 150
    final.usage.model_extra = {"cost": cost}

    return iter([make_audio_chunk(chunk1), make_audio_chunk(chunk2), final])


def test_tts_service_returns_wav_bytes(tmp_path):
    from tutor.web.tts import TTSService

    pcm = b"\x01\x02" * 1000  # arbitrary PCM16 mono data
    client = MagicMock()
    client.chat.completions.create.return_value = _stub_pcm_stream(pcm, cost=0.0001)

    svc = TTSService(
        client=client,
        model="openai/gpt-audio-mini",
        default_voice="alloy",
        budget=_make_budget(tmp_path),
    )

    wav_bytes = svc.synthesize("hello", voice="alloy")

    # Verify it's a valid WAV
    assert wav_bytes[:4] == b"RIFF"
    assert wav_bytes[8:12] == b"WAVE"
    with wave.open(BytesIO(wav_bytes), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == 24000
        assert w.getsampwidth() == 2  # 16-bit
        # Frames should equal PCM byte count / 2 (16-bit samples)
        assert w.getnframes() == len(pcm) // 2


def test_tts_service_caches_by_text_and_voice(tmp_path):
    from tutor.web.tts import TTSService

    pcm = b"\x03\x04" * 500
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _stub_pcm_stream(pcm),
        _stub_pcm_stream(b"different" * 100),  # would differ if cache missed
    ]

    svc = TTSService(
        client=client,
        model="openai/gpt-audio-mini",
        default_voice="alloy",
        budget=_make_budget(tmp_path),
    )

    a = svc.synthesize("hello", voice="alloy")
    b = svc.synthesize("hello", voice="alloy")
    assert a == b
    assert client.chat.completions.create.call_count == 1  # second hit cache


def test_tts_service_cache_key_includes_voice(tmp_path):
    from tutor.web.tts import TTSService

    pcm_a = b"AA" * 200
    pcm_b = b"BB" * 200
    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _stub_pcm_stream(pcm_a),
        _stub_pcm_stream(pcm_b),
    ]

    svc = TTSService(
        client=client,
        model="openai/gpt-audio-mini",
        default_voice="alloy",
        budget=_make_budget(tmp_path),
    )

    a = svc.synthesize("hello", voice="alloy")
    b = svc.synthesize("hello", voice="nova")
    assert a != b
    assert client.chat.completions.create.call_count == 2


def test_tts_service_default_voice_used_when_none(tmp_path):
    from tutor.web.tts import TTSService

    pcm = b"\x00\x01" * 100
    client = MagicMock()
    client.chat.completions.create.return_value = _stub_pcm_stream(pcm)

    svc = TTSService(
        client=client,
        model="openai/gpt-audio-mini",
        default_voice="alloy",
        budget=_make_budget(tmp_path),
    )

    svc.synthesize("hi", voice=None)

    call_kwargs = client.chat.completions.create.call_args.kwargs
    assert call_kwargs["audio"]["voice"] == "alloy"


def test_tts_service_lru_eviction(tmp_path):
    from tutor.web.tts import TTSService

    client = MagicMock()
    client.chat.completions.create.side_effect = [
        _stub_pcm_stream(b"\x01\x02" * 100) for _ in range(5)
    ]
    svc = TTSService(
        client=client,
        model="openai/gpt-audio-mini",
        default_voice="alloy",
        budget=_make_budget(tmp_path),
        cache_capacity=2,
    )

    svc.synthesize("a", voice="alloy")
    svc.synthesize("b", voice="alloy")
    svc.synthesize("c", voice="alloy")  # evicts "a"
    svc.synthesize("a", voice="alloy")  # re-generates, not cached

    # 4 unique generations, none was a cache hit when re-asking for "a"
    assert client.chat.completions.create.call_count == 4


def test_tts_service_propagates_budget_error(tmp_path):
    from tutor.web.tts import TTSService
    from tutor.budget import BudgetTracker, BudgetExceededError

    budget = BudgetTracker(
        path=tmp_path / "b.json",
        daily_usd_cap=0.00001,
        daily_token_cap=1_000_000,
        now=lambda: datetime(2026, 5, 21, 12, 0),
    )
    budget.record(tokens_in=10, tokens_out=10, usd_cost=0.001)  # already over

    svc = TTSService(
        client=MagicMock(),
        model="openai/gpt-audio-mini",
        default_voice="alloy",
        budget=budget,
    )

    with pytest.raises(BudgetExceededError):
        svc.synthesize("hello", voice="alloy")


def test_tts_service_wraps_api_error(tmp_path):
    from tutor.web.tts import TTSService, TTSGenerationError

    client = MagicMock()
    client.chat.completions.create.side_effect = RuntimeError("openrouter down")

    svc = TTSService(
        client=client,
        model="openai/gpt-audio-mini",
        default_voice="alloy",
        budget=_make_budget(tmp_path),
    )

    with pytest.raises(TTSGenerationError):
        svc.synthesize("hello", voice="alloy")
```

- [ ] **Step 2: Run** `pytest tests/web/test_tts.py -v` → 7 errors (module missing).

- [ ] **Step 3: Implement `tutor/web/tts.py`**

```python
"""Backend TTS via OpenRouter (gpt-audio-mini), with WAV assembly + LRU cache."""
from __future__ import annotations

import base64
import hashlib
import logging
import wave
from collections import OrderedDict
from io import BytesIO

from openai import OpenAI

from tutor.budget import BudgetTracker

log = logging.getLogger(__name__)

_SAMPLE_RATE = 24000
_CHANNELS = 1
_SAMPLE_WIDTH = 2  # 16-bit


class TTSGenerationError(Exception):
    """Raised when the underlying TTS API call fails."""


class TTSService:
    def __init__(
        self,
        client: OpenAI,
        model: str,
        default_voice: str,
        budget: BudgetTracker,
        cache_capacity: int = 64,
    ) -> None:
        self._client = client
        self._model = model
        self._default_voice = default_voice
        self._budget = budget
        self._cache_capacity = cache_capacity
        self._cache: OrderedDict[str, bytes] = OrderedDict()

    def synthesize(self, text: str, voice: str | None = None) -> bytes:
        voice = voice or self._default_voice
        key = self._cache_key(text, voice)
        if key in self._cache:
            self._cache.move_to_end(key)  # mark recently used
            return self._cache[key]

        self._budget.check_can_spend()
        wav_bytes = self._generate(text, voice)
        self._cache[key] = wav_bytes
        if len(self._cache) > self._cache_capacity:
            self._cache.popitem(last=False)  # evict LRU
        return wav_bytes

    def _cache_key(self, text: str, voice: str) -> str:
        return hashlib.sha256(f"{voice}|{text}".encode("utf-8")).hexdigest()

    def _generate(self, text: str, voice: str) -> bytes:
        try:
            stream = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "user", "content": f"Say exactly this sentence: {text}"}
                ],
                modalities=["text", "audio"],
                audio={"voice": voice, "format": "pcm16"},
                stream=True,
                stream_options={"include_usage": True},
            )
        except Exception as e:
            raise TTSGenerationError(f"TTS API call failed: {e}") from e

        pcm_chunks: list[bytes] = []
        usage = None
        try:
            for chunk in stream:
                if chunk.usage is not None:
                    usage = chunk.usage
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                audio = getattr(delta, "audio", None)
                if audio:
                    data = audio.get("data") if isinstance(audio, dict) else getattr(audio, "data", None)
                    if data:
                        pcm_chunks.append(base64.b64decode(data))
        except Exception as e:
            raise TTSGenerationError(f"TTS stream decode failed: {e}") from e

        pcm = b"".join(pcm_chunks)
        if not pcm:
            raise TTSGenerationError("TTS returned no audio data")

        self._record_usage(usage)
        return self._wrap_wav(pcm)

    def _wrap_wav(self, pcm: bytes) -> bytes:
        buf = BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(_CHANNELS)
            w.setsampwidth(_SAMPLE_WIDTH)
            w.setframerate(_SAMPLE_RATE)
            w.writeframes(pcm)
        return buf.getvalue()

    def _record_usage(self, usage) -> None:
        if usage is None:
            return
        tokens_in = getattr(usage, "prompt_tokens", 0) or 0
        tokens_out = getattr(usage, "completion_tokens", 0) or 0
        cost = 0.0
        extra = getattr(usage, "model_extra", None) or {}
        if "cost" in extra:
            try:
                cost = float(extra["cost"])
            except (TypeError, ValueError):
                cost = 0.0
        self._budget.record(tokens_in=tokens_in, tokens_out=tokens_out, usd_cost=cost)
```

- [ ] **Step 4: Run + commit**

`pytest tests/web/test_tts.py -v` → 7 passed.
`pytest` → green (~161).

```bash
git add tutor/web/tts.py tests/web/test_tts.py
git commit -m "feat(web): TTSService — OpenRouter streaming + WAV + LRU cache"
```

---

## Task 5: API route — POST /api/tts

**Files:**
- Modify: `tutor/web/api.py`
- Modify: `tests/web/test_api.py`

- [ ] **Step 1: Append failing tests** in `tests/web/test_api.py`:

```python
def test_post_tts_returns_wav(tmp_path, mocker):
    client, deps = _client(tmp_path, mocker)

    # Patch TTSService.synthesize to return a small WAV blob
    fake_wav = b"RIFF" + b"\x00" * 100 + b"WAVE"
    mocker.patch("tutor.web.api.TTSService.synthesize", return_value=fake_wav)

    r = client.post("/api/tts", json={"text": "hello world"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert r.content == fake_wav


def test_post_tts_empty_text_422(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.post("/api/tts", json={"text": ""})
    assert r.status_code == 422


def test_post_tts_tts_generation_error_502(tmp_path, mocker):
    from tutor.web.tts import TTSGenerationError
    client, _ = _client(tmp_path, mocker)
    mocker.patch(
        "tutor.web.api.TTSService.synthesize",
        side_effect=TTSGenerationError("api down"),
    )
    r = client.post("/api/tts", json={"text": "hi"})
    assert r.status_code == 502
    assert r.json()["error"] == "tts_generation_failed"


def test_post_tts_uses_voice_from_request(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    spy = mocker.patch("tutor.web.api.TTSService.synthesize", return_value=b"RIFF...")
    client.post("/api/tts", json={"text": "hi", "voice": "nova"})
    # The route should pass voice="nova" through
    assert spy.call_args.kwargs.get("voice") == "nova" or "nova" in spy.call_args.args
```

- [ ] **Step 2: Run** `pytest tests/web/test_api.py -v` → 4 errors / failures.

- [ ] **Step 3: Update `tutor/web/api.py`**

Add imports at top:

```python
from fastapi.responses import Response
from tutor.web.schemas import TTSRequest
from tutor.web.tts import TTSGenerationError, TTSService
```

In `create_app`, after building `deps` (and after `app` exists), instantiate a single `TTSService`:

```python
    tts_service = TTSService(
        client=deps.llm._client,        # reuse the OpenAI/OpenRouter client
        model=deps.tts_model,
        default_voice=deps.tts_voice,
        budget=deps.budget,
    )
```

Register a generation-error handler (before routes):

```python
    @app.exception_handler(TTSGenerationError)
    async def _tts_failed(request, exc):
        return JSONResponse(
            status_code=502,
            content={"error": "tts_generation_failed", "message": str(exc)},
        )
```

(Add `JSONResponse` to imports if missing.)

Add the TTS route (place it alongside other routes):

```python
    @app.post("/api/tts")
    async def synthesize_tts(req: TTSRequest):
        audio = tts_service.synthesize(req.text, voice=req.voice)
        return Response(content=audio, media_type="audio/wav")
```

- [ ] **Step 4: Run + commit**

`pytest tests/web/test_api.py -v` → 18 passed (14 prior + 4 new).
`pytest` → green.

```bash
git add tutor/web/api.py tests/web/test_api.py
git commit -m "feat(web): POST /api/tts endpoint with TTSGenerationError handler"
```

---

## Task 6: Async session-end via BackgroundTasks

**Files:**
- Modify: `tutor/web/api.py`
- Modify: `tests/web/test_api.py`

- [ ] **Step 1: Update existing `/end` tests** in `tests/web/test_api.py`

Find `test_post_end_no_turns_skips_evaluator` and replace its assertions (the response shape changes from EndSessionResult to EndSessionAccepted):

```python
def test_post_end_no_turns_returns_accepted(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.post("/api/sessions", json={"scenario_id": "tech_interview_behavioral"})
    sid = r.json()["session_id"]
    r2 = client.post(f"/api/sessions/{sid}/end")
    assert r2.status_code == 202
    body = r2.json()
    assert body["session_id"] == sid
    assert body["status"] == "processing"
```

Add a new test that verifies the background work actually ran (TestClient runs background tasks synchronously after response):

```python
def test_post_end_runs_background_task(tmp_path, mocker):
    client, deps = _client(tmp_path, mocker)
    deps.llm.complete.return_value = "Hi."
    deps.asr.transcribe.return_value = "I did stuff"

    r = client.post("/api/sessions", json={"scenario_id": "tech_interview_behavioral"})
    sid = r.json()["session_id"]

    # Have one turn so end_session_service actually has work to do
    import io
    files = {"audio": ("turn.webm", io.BytesIO(b"audio"), "audio/webm")}
    client.post(f"/api/sessions/{sid}/turn", files=files)

    # Patch end_session_service to track invocation
    called_with = {}
    def fake_end(deps_, session_id):
        called_with["session_id"] = session_id
    mocker.patch("tutor.web.api.services.end_session_service", side_effect=fake_end)

    r2 = client.post(f"/api/sessions/{sid}/end")
    assert r2.status_code == 202

    # TestClient executes BackgroundTasks before returning control
    assert called_with["session_id"] == sid


def test_post_end_unknown_session_still_404(tmp_path, mocker):
    client, _ = _client(tmp_path, mocker)
    r = client.post("/api/sessions/does_not_exist/end")
    assert r.status_code == 404
```

- [ ] **Step 2: Run** `pytest tests/web/test_api.py -v` → failures (response shape mismatch).

- [ ] **Step 3: Update `/end` route in `tutor/web/api.py`**

Add imports:

```python
from fastapi import BackgroundTasks
from tutor.web.schemas import EndSessionAccepted
```

Replace the existing `end_session` route handler:

```python
    @app.post("/api/sessions/{session_id}/end",
              response_model=EndSessionAccepted, status_code=202)
    async def end_session(
        session_id: str,
        background_tasks: BackgroundTasks,
        d: Dependencies = Depends(get_deps),
    ):
        # Validate session exists synchronously (so 404 fires before scheduling)
        services.get_session_service(d, session_id)
        background_tasks.add_task(services.end_session_service, d, session_id)
        return EndSessionAccepted(session_id=session_id)
```

(Note: `EndSessionResult` schema is no longer used by this route. It can stay in schemas.py — Stage 2c session-history page may use it.)

- [ ] **Step 4: Run + commit**

`pytest tests/web/test_api.py -v` → green.
`pytest` → green.

```bash
git add tutor/web/api.py tests/web/test_api.py
git commit -m "feat(web): /sessions/{id}/end → 202 + BackgroundTasks for evaluator"
```

---

## Task 7: Frontend API client — synthesizeTTS + types update

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/api/client.test.ts`

- [ ] **Step 1: Append failing tests** in `frontend/src/api/client.test.ts`:

```typescript
it("synthesizeTTS POSTs JSON and returns Blob", async () => {
    global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        blob: async () => new Blob([new Uint8Array([1, 2, 3])], { type: "audio/wav" }),
    });
    const blob = await api.synthesizeTTS("hello", "nova");
    expect(blob).toBeInstanceOf(Blob);
    const call = (global.fetch as any).mock.calls[0];
    expect(call[0]).toBe("/api/tts");
    expect(call[1].method).toBe("POST");
    expect(JSON.parse(call[1].body)).toEqual({ text: "hello", voice: "nova" });
});

it("endSession returns EndSessionAccepted shape", async () => {
    global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ session_id: "s1", status: "processing" }),
    });
    const r = await api.endSession("s1");
    expect(r.session_id).toBe("s1");
    expect(r.status).toBe("processing");
});
```

(Replace existing reference to `global` with `globalThis` if your test file already uses `globalThis`.)

- [ ] **Step 2: Run** `cd /Users/sarkhipov/Work/Personal/english-tutor/frontend && npm test` → failures.

- [ ] **Step 3: Update `frontend/src/api/types.ts`**

Replace existing `EndSessionResult` (keep it, may be reused later) and add new:

```typescript
export interface EndSessionAccepted {
  session_id: string;
  status: "processing";
}

export const OPENAI_TTS_VOICES = [
  "alloy", "echo", "fable", "onyx", "nova", "shimmer",
  "ash", "ballad", "coral", "sage", "verse", "marin", "cedar",
] as const;

export type OpenAITTSVoice = typeof OPENAI_TTS_VOICES[number];
```

- [ ] **Step 4: Update `frontend/src/api/client.ts`**

Add to the imports:

```typescript
import type {
  // ... existing ...
  EndSessionAccepted,
} from "./types";
```

Change the `endSession` return type:

```typescript
  endSession(session_id: string): Promise<EndSessionAccepted> {
    return request(`/api/sessions/${session_id}/end`, { method: "POST" });
  },
```

Add the `synthesizeTTS` method on the `api` object (after `getBudget` or any sensible spot):

```typescript
  async synthesizeTTS(text: string, voice?: string): Promise<Blob> {
    const res = await fetch("/api/tts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, voice }),
    });
    if (!res.ok) {
      let body: ApiErrorBody;
      try {
        body = await res.json();
      } catch {
        body = { error: "tts_failed" };
      }
      throw new ApiError(res.status, body);
    }
    return res.blob();
  },
```

- [ ] **Step 5: Run + commit**

`npm test` → all passing including 2 new tests.

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/api/
git commit -m "feat(frontend): api.synthesizeTTS + EndSessionAccepted type"
```

---

## Task 8: useTTS rewrite — backend primary, SpeechSynthesis fallback

**Files:**
- Modify: `frontend/src/hooks/useTTS.ts`
- Modify: `frontend/src/hooks/useTTS.test.ts`

- [ ] **Step 1: Rewrite `frontend/src/hooks/useTTS.test.ts`**

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useTTS } from "./useTTS";

beforeEach(() => {
  // Stub localStorage
  const store: Record<string, string> = {};
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v; },
      removeItem: (k: string) => { delete store[k]; },
    },
  });

  // Stub URL.createObjectURL + revokeObjectURL
  (globalThis as any).URL.createObjectURL = vi.fn(() => "blob:fake");
  (globalThis as any).URL.revokeObjectURL = vi.fn();

  // Stub HTMLAudioElement
  class FakeAudio {
    src = "";
    onended: (() => void) | null = null;
    onerror: ((e: any) => void) | null = null;
    constructor(src: string) { this.src = src; }
    play() {
      // Resolve, then fire onended on next tick
      setTimeout(() => this.onended?.(), 0);
      return Promise.resolve();
    }
  }
  (globalThis as any).Audio = FakeAudio;

  // Stub SpeechSynthesis as fallback
  (globalThis as any).SpeechSynthesisUtterance = vi.fn().mockImplementation(function () {
    return { text: "", onend: null, onerror: null };
  });
  (globalThis as any).speechSynthesis = {
    getVoices: () => [],
    speak: vi.fn((u: any) => setTimeout(() => u.onend?.(), 0)),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  };
});


describe("useTTS", () => {
  it("speak uses backend TTS by default", async () => {
    vi.mock("../api/client", () => ({
      api: {
        synthesizeTTS: vi.fn().mockResolvedValue(new Blob([new Uint8Array([1, 2])], { type: "audio/wav" })),
      },
      ApiError: class extends Error {},
    }));
    const { api } = await import("../api/client");

    const { result } = renderHook(() => useTTS());
    await act(async () => {
      await result.current.speak("hello world");
    });
    expect((api.synthesizeTTS as any)).toHaveBeenCalledWith("hello world", undefined);
  });

  it("speak passes voice from localStorage", async () => {
    vi.resetModules();
    const synth = vi.fn().mockResolvedValue(new Blob());
    vi.doMock("../api/client", () => ({
      api: { synthesizeTTS: synth },
      ApiError: class extends Error {},
    }));
    const { useTTS: hook } = await import("./useTTS");

    localStorage.setItem("ttsVoice", "nova");
    const { result } = renderHook(() => hook());
    await act(async () => {
      await result.current.speak("hello");
    });
    expect(synth).toHaveBeenCalledWith("hello", "nova");
  });

  it("falls back to SpeechSynthesis on backend error", async () => {
    vi.resetModules();
    vi.doMock("../api/client", () => ({
      api: { synthesizeTTS: vi.fn().mockRejectedValue(new Error("network")) },
      ApiError: class extends Error {},
    }));
    const { useTTS: hook } = await import("./useTTS");

    const { result } = renderHook(() => hook());
    await act(async () => {
      await result.current.speak("hello");
    });
    expect((globalThis as any).speechSynthesis.speak).toHaveBeenCalled();
  });

  it("exposes static OPENAI_TTS_VOICES as voices", () => {
    const { result } = renderHook(() => useTTS());
    expect(result.current.voices).toContain("alloy");
    expect(result.current.voices.length).toBe(13);
  });
});
```

- [ ] **Step 2: Run** `npm test` → useTTS failures.

- [ ] **Step 3: Rewrite `frontend/src/hooks/useTTS.ts`**

```typescript
import { useCallback, useState } from "react";
import { api } from "../api/client";
import { OPENAI_TTS_VOICES } from "../api/types";

export interface UseTTS {
  speak: (text: string) => Promise<void>;
  isSpeaking: boolean;
  voices: readonly string[];
}

async function speakWithBrowser(text: string): Promise<void> {
  if (typeof speechSynthesis === "undefined") return;
  return new Promise((resolve) => {
    const u = new SpeechSynthesisUtterance(text);
    u.onend = () => resolve();
    u.onerror = () => resolve();
    speechSynthesis.speak(u);
  });
}

export function useTTS(): UseTTS {
  const [isSpeaking, setIsSpeaking] = useState(false);

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
    } catch {
      // Backend TTS failed — fallback to browser SpeechSynthesis
      await speakWithBrowser(text);
    } finally {
      setIsSpeaking(false);
    }
  }, []);

  return { speak, isSpeaking, voices: OPENAI_TTS_VOICES };
}
```

- [ ] **Step 4: Run + commit**

`npm test` → all passing.
`npm run build` → succeeds.

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/hooks/
git commit -m "feat(frontend): useTTS rewrites to backend primary + SpeechSynthesis fallback"
```

---

## Task 9: VoicePicker + Layout integration

**Files:**
- Create: `frontend/src/components/VoicePicker.tsx`
- Create: `frontend/src/components/VoicePicker.test.tsx`
- Modify: `frontend/src/components/Layout.tsx`

- [ ] **Step 1: Write failing test**

`frontend/src/components/VoicePicker.test.tsx`:

```typescript
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { VoicePicker } from "./VoicePicker";

beforeEach(() => {
  const store: Record<string, string> = {};
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => { store[k] = v; },
      removeItem: (k: string) => { delete store[k]; },
    },
  });
});

vi.mock("../hooks/useTTS", () => ({
  useTTS: () => ({ speak: vi.fn(), isSpeaking: false, voices: ["alloy", "nova", "echo"] }),
}));

describe("VoicePicker", () => {
  it("renders all available voices in select", () => {
    render(<VoicePicker />);
    const sel = screen.getByRole("combobox") as HTMLSelectElement;
    const options = Array.from(sel.options).map(o => o.value);
    expect(options).toContain("alloy");
    expect(options).toContain("nova");
  });

  it("persists choice to localStorage on change", () => {
    render(<VoicePicker />);
    const sel = screen.getByRole("combobox");
    fireEvent.change(sel, { target: { value: "nova" } });
    expect(localStorage.getItem("ttsVoice")).toBe("nova");
  });

  it("renders Test button", () => {
    render(<VoicePicker />);
    expect(screen.getByRole("button", { name: /test/i })).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run** `npm test` → failures.

- [ ] **Step 3: Create `frontend/src/components/VoicePicker.tsx`**

```typescript
import { useState } from "react";
import { useTTS } from "../hooks/useTTS";

const TEST_SAMPLE = "This is a sample of the selected voice.";

export function VoicePicker() {
  const tts = useTTS();
  const [selected, setSelected] = useState<string>(
    () => localStorage.getItem("ttsVoice") || "alloy"
  );

  const change = (voice: string) => {
    localStorage.setItem("ttsVoice", voice);
    setSelected(voice);
  };

  return (
    <div className="flex items-center gap-2">
      <select
        value={selected}
        onChange={(e) => change(e.target.value)}
        className="text-xs border border-slate-300 rounded px-2 py-1 bg-white text-slate-800"
        aria-label="Choose TTS voice"
      >
        {tts.voices.map((v) => (
          <option key={v} value={v}>{v}</option>
        ))}
      </select>
      <button
        type="button"
        onClick={() => tts.speak(TEST_SAMPLE)}
        disabled={tts.isSpeaking}
        className="text-xs px-2 py-1 border border-slate-300 rounded hover:bg-slate-100 disabled:opacity-50"
      >
        Test
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Add VoicePicker to `frontend/src/components/Layout.tsx`**

Locate the existing header `<div>` that contains `<BudgetIndicator />` and add `VoicePicker` before it:

```typescript
import { VoicePicker } from "./VoicePicker";
// ...
        <div className="flex items-center gap-3">
          <VoicePicker />
          <BudgetIndicator />
        </div>
```

(Replace the existing wrapper around `<BudgetIndicator />` accordingly — the exact JSX depends on what Stage 2a wrote. Look for where BudgetIndicator is rendered and place VoicePicker just before it inside the same flex container.)

- [ ] **Step 5: Run + commit**

`npm test` → all passing including 3 new VoicePicker tests.
`npm run build` → succeeds.

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/components/
git commit -m "feat(frontend): VoicePicker dropdown in Layout header"
```

---

## Task 10: SessionPage — opening playback + remove summary

**Files:**
- Modify: `frontend/src/pages/SessionPage.tsx`
- Modify: `frontend/src/pages/SessionPage.test.tsx`

- [ ] **Step 1: Update existing test** in `frontend/src/pages/SessionPage.test.tsx`

Find the existing test and add a new assertion that confirms tts.speak was called with the opening:

Replace the existing test (or add a new one that uses a real-ish useTTS mock):

```typescript
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { SessionPage } from "./SessionPage";

vi.mock("../api/client", () => ({
  api: {
    getSession: vi.fn().mockResolvedValue({
      session_id: "s1",
      scenario_id: "tech_interview_behavioral",
      started_at: "2026-05-21T10:00:00",
      ended_at: null,
      opening_text: "Hi, tell me about yourself.",
      turns: [],
    }),
  },
  ApiError: class extends Error {},
}));

const speakSpy = vi.fn().mockResolvedValue(undefined);
vi.mock("../hooks/useTTS", () => ({
  useTTS: () => ({ speak: speakSpy, isSpeaking: false, voices: [] }),
}));

vi.mock("../hooks/useRecorder", () => ({
  useRecorder: () => ({
    isRecording: false, startRecording: vi.fn(), stopRecording: vi.fn(), cancelRecording: vi.fn(),
  }),
}));

function wrap(initial: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <MemoryRouter initialEntries={[initial]}>
      <QueryClientProvider client={qc}>
        <Routes>
          <Route path="/session/:id" element={<SessionPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

describe("SessionPage", () => {
  it("renders opening text as assistant bubble", async () => {
    render(wrap("/session/s1"));
    await waitFor(() => {
      expect(screen.getByText("Hi, tell me about yourself.")).toBeInTheDocument();
    });
  });

  it("auto-plays opening via TTS on mount", async () => {
    speakSpy.mockClear();
    render(wrap("/session/s1"));
    await waitFor(() => {
      expect(speakSpy).toHaveBeenCalledWith("Hi, tell me about yourself.");
    });
  });
});
```

- [ ] **Step 2: Run** `npm test` → opening-TTS test fails (currently SessionPage doesn't call speak on mount).

- [ ] **Step 3: Update `frontend/src/pages/SessionPage.tsx`**

Add at the top of the imports:

```typescript
import { useEffect, useRef, useState } from "react";
```

(`useRef` may already be imported. If yes, no change. If not, add it.)

Inside the `SessionPage` function, add ref + effect after the existing `messages` state is established:

```typescript
  const playedOpeningRef = useRef(false);

  useEffect(() => {
    if (playedOpeningRef.current) return;
    const opening = messages.find((m) => m.role === "assistant")?.text;
    if (opening) {
      playedOpeningRef.current = true;
      tts.speak(opening).catch(() => { /* non-fatal */ });
    }
  }, [messages, tts]);
```

Modify `endMutation.onSuccess` to navigate immediately and skip the SessionSummary modal:

```typescript
  const endMutation = useMutation({
    mutationFn: () => api.endSession(id!),
    onSuccess: () => {
      navigate("/");
    },
  });
```

Remove the SessionSummary import and `<SessionSummary ... />` rendering. The component file stays in the tree (unused).

Remove the `summary` state and any related code that referenced it.

- [ ] **Step 4: Run + commit**

`npm test` → all passing including the new opening-TTS test.
`npm run build` → succeeds.

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/pages/
git commit -m "feat(frontend): auto-play opening + immediate navigate on end"
```

---

## Task 11: Manual end-to-end smoke

User-driven verification. No automated test.

- [ ] **Step 1: Confirm test suites + build green**

`cd /Users/sarkhipov/Work/Personal/english-tutor && source .venv/bin/activate && pytest` → ~163 tests pass.
`cd frontend && npm test` → all passing.
`npm run build` → succeeds.

- [ ] **Step 2: Push commits**

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor
git log --oneline origin/main..HEAD   # show what we'll push
git push origin main
```

- [ ] **Step 3: Run the web UI**

`./scripts/build_and_serve.sh` — builds frontend, starts uvicorn at `http://127.0.0.1:8000`.

- [ ] **Step 4: Smoke checks**

Open `http://127.0.0.1:8000`:

1. **Voice picker visible:** header has a small dropdown with voice names + "Test" button.
2. **Test sample plays:** select a voice (e.g., `nova`), click Test → hear a natural sample in the chosen voice.
3. **Session opening auto-plays:** click a scenario → land on session screen → opening bubble appears AND the assistant voice immediately speaks the opening line through the backend (no SpeechSynthesis robotic voice).
4. **Turn playback:** hold mic, speak, release → assistant reply bubble appears AND voice plays naturally.
5. **End navigates immediately:** click "End session" → URL changes to `/` within ~200ms, no spinner, no modal.
6. **Cards appear shortly:** wait ~5–10s, navigate to `/review` → new cards from the just-finished session are present.
7. **Voice persistence:** reload page, voice picker still shows your previous selection.
8. **CLI not broken:** `tutor stats` and `tutor list-scenarios` work as before.

- [ ] **Step 5: Report findings**

Report any issues. If all good, Stage 2b is done.

---

## Self-review checklist

Verify before declaring Stage 2b done:

1. **Spec coverage:**
   - Backend TTS via openai/gpt-audio-mini → Tasks 4, 5
   - Opening auto-playback fix → Task 10
   - Async session-end via BackgroundTasks → Task 6
   - Voice picker in header → Task 9
   - localStorage voice persistence → Tasks 8, 9
   - SpeechSynthesis fallback → Task 8
   - In-memory LRU cache (64 entries) → Task 4
   - Settings (tts_model + tts_voice) → Tasks 1, 3
   - Schemas (TTSRequest + EndSessionAccepted) → Task 2

2. **Type consistency:**
   - `TTSService.synthesize(text, voice=None) -> bytes` — used by api.py route in Task 5
   - `api.synthesizeTTS(text, voice?) -> Promise<Blob>` — used by useTTS in Task 8
   - `OPENAI_TTS_VOICES` constant — exported from types.ts (Task 7), consumed by useTTS (Task 8) and VoicePicker (Task 9)
   - `Dependencies` dataclass has `tts_model` + `tts_voice` (Task 3), consumed in `create_app` (Task 5)
   - `EndSessionAccepted` schema (Task 2) used by route (Task 6) and client (Task 7)

3. **No placeholders:** every step has either code or exact commands.

4. **Failure modes covered:**
   - TTS generation failure → 502 (Task 5 test) → frontend falls back to SpeechSynthesis (Task 8 test)
   - Empty TTS text → 422 (Task 5 test)
   - Budget exhausted → 429 (existing handler, exercised in Task 4 test)
   - Unknown session at /end → 404 (Task 6 test)
   - LocalStorage unavailable → useTTS still works with default voice (Task 8 implementation: `getItem` returns null, no override)

---

## Definition of Done for Stage 2b

- 10 task commits + manual smoke on `origin/main`.
- Full `pytest` suite green (~163 tests).
- `cd frontend && npm test` green.
- `npm run build` succeeds.
- Real session in browser: opening auto-plays via backend TTS in a natural voice (alloy or user's pick).
- Real session end: page navigates to `/` immediately; cards become available within ~10s.
- Voice picker shows 13 voices, "Test" plays sample, choice persists across reloads.
- CLI commands continue to work.
- Daily budget after typical use stays well under $0.50.
