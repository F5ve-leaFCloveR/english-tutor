# Stage 2e — Real-time Per-Turn Corrections in Voice Sessions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** During a voice session, after each user utterance the UI immediately shows `InlineCorrection` cards (vocab/grammar) under the user bubble — same UX as `/chat`. Session end no longer triggers a separate `Evaluator` pass; the closed session enters `/review` with all per-turn corrections aggregated into `growth_points`.

**Architecture:** Reuse `ChatTurn` (Stage 2d). Per turn, one LLM call returns `{reply, corrections}` JSON. The system prompt combines the scenario role-play prompt with the chat correction instructions. Each `turns[i]` gets a `corrections` field in storage. At session end, aggregate per-turn corrections (deduped by `user_utterance`) into `growth_points` so `/review` + SRS card creation work unchanged.

**Tech Stack:** Same as Stage 2d. No new deps.

**Prerequisites:**
- Stage 2d on `main` (`a12881b` or later).
- All current tests green: 190 pytest, 48 vitest, build succeeds.

---

## File Structure

```
tutor/
├── conversation.py            (MODIFY: ChatTurn accepts system_prompt; new build_session_chat_prompt)
└── web/
    ├── schemas.py             (MODIFY: TurnResult.corrections)
    ├── services.py            (MODIFY: turn_service rewrite, end_session_service simplification)
    └── deps.py                (no change — uses existing chat_model)

tutor/storage.py               (MODIFY: append_turn accepts corrections)

tests/
├── test_conversation.py       (MODIFY: + build_session_chat_prompt + system_prompt override tests)
├── test_storage.py            (MODIFY: + append_turn with corrections)
└── web/
    ├── test_services_session.py  (MODIFY: + end_session aggregation/dedup tests, drop-Evaluator regression)
    ├── test_services_turn.py     (MODIFY: + turn_service corrections-in-result)
    └── test_api.py               (MODIFY: + /turn returns corrections in TurnResult)

frontend/src/
├── api/types.ts               (MODIFY: TurnResult.corrections)
└── pages/
    ├── SessionPage.tsx        (MODIFY: render InlineCorrection under user bubbles)
    └── SessionPage.test.tsx   (MODIFY: + corrections rendering)
```

---

## Task 1: `ChatTurn` accepts `system_prompt` + `build_session_chat_prompt` helper

**Files:**
- Modify: `tutor/conversation.py`
- Modify: `tests/test_conversation.py`

- [ ] **Step 1: Append failing tests** to `tests/test_conversation.py`:

```python
def test_chat_turn_accepts_custom_system_prompt():
    from tutor.conversation import ChatTurn
    import json
    from unittest.mock import MagicMock

    llm = MagicMock()
    llm.complete.return_value = json.dumps({"reply": "ok", "corrections": []})
    custom_prompt = "You are a strict English teacher. Respond curtly."
    chat = ChatTurn(llm=llm, model="m", system_prompt=custom_prompt)
    chat.respond(history=[], message="hi")
    sent_messages = llm.complete.call_args.kwargs["messages"]
    assert sent_messages[0]["role"] == "system"
    assert sent_messages[0]["content"] == custom_prompt


def test_chat_turn_default_system_prompt_unchanged():
    """Default prompt path remains the friendly-partner chat prompt."""
    from tutor.conversation import ChatTurn
    import json
    from unittest.mock import MagicMock

    llm = MagicMock()
    llm.complete.return_value = json.dumps({"reply": "ok", "corrections": []})
    chat = ChatTurn(llm=llm, model="m")
    chat.respond(history=[], message="hi")
    sent_messages = llm.complete.call_args.kwargs["messages"]
    assert "friendly English conversational partner" in sent_messages[0]["content"]


def test_build_session_chat_prompt_combines_scenario_and_corrections():
    from tutor.conversation import build_session_chat_prompt
    from tutor.scenarios.loader import load_scenario

    scenario = load_scenario("tech_interview_behavioral")
    prompt = build_session_chat_prompt(scenario, user_native_language="Russian")
    # Scenario role-play content present
    assert "tech_interview_behavioral" in prompt or "interview" in prompt.lower()
    # Correction-output JSON instructions present
    assert "STRICT JSON" in prompt
    assert "\"corrections\"" in prompt
    assert "vocab" in prompt
    assert "grammar" in prompt
```

- [ ] **Step 2: Run** `cd /Users/sarkhipov/Work/Personal/english-tutor && source .venv/bin/activate && pytest tests/test_conversation.py -v` → 3 new fails.

- [ ] **Step 3: Refactor `tutor/conversation.py`**:

Replace the current contents of `_SYSTEM_PROMPT` with a split: `_CORRECTION_INSTRUCTIONS` (the JSON output rules) + `_DEFAULT_CHAT_INTRO` (the friendly-partner persona). The combined default `_DEFAULT_CHAT_SYSTEM_PROMPT` joins them.

Modify `ChatTurn.__init__` to accept `system_prompt: str | None = None`, store on instance, and use in `.respond()`.

Add module-level helper `build_session_chat_prompt(scenario, user_native_language="Russian")` that uses `tutor.scenarios.loader.build_system_prompt(scenario, user_native_language)` (existing helper) then appends `_CORRECTION_INSTRUCTIONS`.

Full file:

```python
"""Free-chat LLM turn: reply + per-message corrections in one structured call."""
from __future__ import annotations

import json
import logging
from typing import Literal

from pydantic import BaseModel, ValidationError

from tutor.llm import LLMClient
from tutor.scenarios.loader import Scenario, build_system_prompt

log = logging.getLogger(__name__)


_DEFAULT_CHAT_INTRO = """You are a friendly English conversational partner for a Russian-native intermediate student.

Reply naturally and conversationally in 2-4 sentences. Match the user's tone. Ask follow-up questions when natural.
"""


_CORRECTION_INSTRUCTIONS = """In the SAME response, identify up to 3 corrections to the user's MOST RECENT message only. Focus on:
  - vocab: word choice that's correct but weak/generic. Suggest a stronger, more precise word.
  - grammar: tense, articles, prepositions, word order errors.
Skip filler words, typos, idiom/register issues, minor style preferences. If the message is clean, return an empty list.

Return STRICT JSON, no commentary:
{
  "reply": "<your conversational reply>",
  "corrections": [
    {
      "tag": "vocab" | "grammar",
      "user_utterance": "<verbatim what the user wrote>",
      "corrected_version": "<your improved version>",
      "explanation": "<1-2 sentences why the correction is better>"
    }
  ]
}
"""


_DEFAULT_CHAT_SYSTEM_PROMPT = _DEFAULT_CHAT_INTRO + "\n" + _CORRECTION_INSTRUCTIONS


_FALLBACK_REPLY = "Sorry, I had trouble responding. Could you say that again?"


class ChatCorrection(BaseModel):
    tag: Literal["vocab", "grammar"]
    user_utterance: str
    corrected_version: str
    explanation: str


class ChatResponse(BaseModel):
    reply: str
    corrections: list[ChatCorrection]


def build_session_chat_prompt(scenario: Scenario, user_native_language: str = "Russian") -> str:
    """System prompt for a voice session: scenario role-play + JSON correction rules."""
    role_play = build_system_prompt(scenario, user_native_language=user_native_language)
    return role_play + "\n\n" + _CORRECTION_INSTRUCTIONS


class ChatTurn:
    def __init__(
        self,
        llm: LLMClient,
        model: str,
        system_prompt: str | None = None,
    ) -> None:
        self._llm = llm
        self._model = model
        self._system_prompt = system_prompt or _DEFAULT_CHAT_SYSTEM_PROMPT

    def respond(
        self,
        history: list[dict[str, str]],
        message: str,
    ) -> ChatResponse:
        """One turn: LLM replies AND returns corrections for the latest user message."""
        messages = [{"role": "system", "content": self._system_prompt}]
        for h in history:
            messages.append({"role": h["role"], "content": h["content"]})
        messages.append({"role": "user", "content": message})

        reminder = {
            "role": "user",
            "content": (
                "Your previous response was not valid JSON. Return STRICT JSON only, "
                "no commentary, no markdown fences. Just the {\"reply\": ..., \"corrections\": [...]} object."
            ),
        }

        last_error: Exception | None = None
        for attempt in range(2):
            call_messages = messages if attempt == 0 else messages + [reminder]
            try:
                raw = self._llm.complete(
                    messages=call_messages,
                    temperature=0.7,
                    model_override=self._model,
                    max_tokens=1024,
                )
            except Exception as e:
                log.warning("Chat LLM call failed: %s", e)
                return ChatResponse(reply=_FALLBACK_REPLY, corrections=[])
            try:
                parsed = ChatResponse.model_validate_json(_strip_code_fences(raw))
                parsed.corrections = parsed.corrections[:3]
                return parsed
            except (ValidationError, ValueError, json.JSONDecodeError) as e:
                last_error = e
                log.warning("Chat returned invalid JSON (attempt %d): %s", attempt + 1, e)
                continue

        log.warning("Chat exhausted retries: %s", last_error)
        return ChatResponse(reply=_FALLBACK_REPLY, corrections=[])


def _strip_code_fences(text: str) -> str:
    """LLMs sometimes wrap JSON in ```json ... ```. Strip if present."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/test_conversation.py -v
pytest 2>&1 | tail -5
```

→ 10 green in test_conversation.py (7 existing + 3 new), full suite ~193 green.

```bash
git add tutor/conversation.py tests/test_conversation.py
git commit -m "refactor(chat): ChatTurn accepts system_prompt + build_session_chat_prompt helper"
```

## Context

- Branch: `main`. Previous: `a8fe26d` (Stage 2e spec).
- Task 1 of 6.

---

## Task 2: `storage.append_turn` accepts `corrections`

**Files:**
- Modify: `tutor/storage.py`
- Modify: `tests/test_storage.py`

- [ ] **Step 1: Append failing tests** to `tests/test_storage.py`:

```python
def test_append_turn_persists_corrections(tmp_path):
    from tutor.storage import SessionStorage
    storage = SessionStorage(root=tmp_path)
    sid = storage.create_session(scenario_id="tech_interview_behavioral")
    storage.append_turn(
        sid,
        user_text="I goed there",
        llm_text="Interesting!",
        corrections=[{
            "tag": "grammar",
            "user_utterance": "I goed",
            "corrected_version": "I went",
            "explanation": "Past tense of 'go' is 'went'.",
        }],
    )
    data = storage.load_session(sid)
    assert len(data["turns"]) == 1
    turn = data["turns"][0]
    assert turn["user_text"] == "I goed there"
    assert turn["llm_text"] == "Interesting!"
    assert turn["corrections"] == [{
        "tag": "grammar",
        "user_utterance": "I goed",
        "corrected_version": "I went",
        "explanation": "Past tense of 'go' is 'went'.",
    }]


def test_append_turn_without_corrections_omits_field(tmp_path):
    """Backward compat: callers that don't pass corrections produce the legacy turn shape."""
    from tutor.storage import SessionStorage
    storage = SessionStorage(root=tmp_path)
    sid = storage.create_session(scenario_id="tech_interview_behavioral")
    storage.append_turn(sid, user_text="hi", llm_text="hello")
    data = storage.load_session(sid)
    assert "corrections" not in data["turns"][0]
```

- [ ] **Step 2: Run** `pytest tests/test_storage.py -v 2>&1 | tail -20` → 2 new fails (TypeError: unexpected kwarg `corrections`).

- [ ] **Step 3: Modify `tutor/storage.py`** — change `append_turn`:

Replace the existing method:

```python
    def append_turn(
        self,
        session_id: str,
        user_text: str,
        llm_text: str,
        corrections: list[dict] | None = None,
    ) -> None:
        path = self._find_session_path(session_id)
        data = json.loads(path.read_text())
        turn: dict = {
            "ts": self.now().isoformat(),
            "user_text": user_text,
            "llm_text": llm_text,
        }
        if corrections is not None:
            turn["corrections"] = corrections
        data["turns"].append(turn)
        self._write(path, data)
```

- [ ] **Step 4: Run + commit**

```bash
pytest tests/test_storage.py -v 2>&1 | tail -10
pytest 2>&1 | tail -5
```

→ all green.

```bash
git add tutor/storage.py tests/test_storage.py
git commit -m "feat(storage): append_turn accepts optional corrections"
```

## Context

- Branch: `main`. Previous: T1 commit.
- Task 2 of 6.

---

## Task 3: `turn_service` uses `ChatTurn` + `TurnResult.corrections`

**Files:**
- Modify: `tutor/web/schemas.py`
- Modify: `tutor/web/services.py`
- Modify: `tests/web/test_services_turn.py` (file may not exist yet — if not, append to `tests/web/test_services_session.py` or create new)

- [ ] **Step 1: Update `tutor/web/schemas.py`** — extend `TurnResult`

Find `TurnResult` (existing). Add `corrections` field. Use `ChatCorrectionDict` already defined (from Stage 2d).

Replace `TurnResult`:

```python
class TurnResult(BaseModel):
    user_text: str
    assistant_text: str
    corrections: list[ChatCorrectionDict] = []
```

Ensure `ChatCorrectionDict` is defined earlier in the file (it is, from Stage 2d).

- [ ] **Step 2: Append failing tests** to `tests/web/test_services_session.py`:

```python
def test_turn_service_returns_corrections_in_result(tmp_path, mocker):
    """turn_service now uses ChatTurn — TurnResult includes per-turn corrections."""
    import json
    from tutor.web.services import turn_service, start_session_service
    deps = _make_deps(tmp_path)
    # Initial start_session_service uses plain LLM (returns string)
    deps.llm.complete.return_value = "Opening."
    s = start_session_service(deps, scenario_id="tech_interview_behavioral")

    # Now configure LLM to return ChatTurn JSON for the turn
    deps.asr.transcribe.return_value = "I goed there"
    deps.llm.complete.return_value = json.dumps({
        "reply": "Where did you go?",
        "corrections": [{
            "tag": "grammar",
            "user_utterance": "I goed",
            "corrected_version": "I went",
            "explanation": "Past tense of 'go' is 'went'.",
        }],
    })
    result = turn_service(deps, session_id=s.session_id, audio_bytes=b"...")
    assert result.user_text == "I goed there"
    assert result.assistant_text == "Where did you go?"
    assert len(result.corrections) == 1
    assert result.corrections[0]["tag"] == "grammar"
    assert result.corrections[0]["corrected_version"] == "I went"


def test_turn_service_persists_corrections_in_storage(tmp_path, mocker):
    """The turn dict in session.json has a corrections field after the turn."""
    import json
    from tutor.web.services import turn_service, start_session_service
    deps = _make_deps(tmp_path)
    deps.llm.complete.return_value = "Opening."
    s = start_session_service(deps, scenario_id="tech_interview_behavioral")

    deps.asr.transcribe.return_value = "I goed"
    deps.llm.complete.return_value = json.dumps({
        "reply": "Where?",
        "corrections": [{
            "tag": "grammar",
            "user_utterance": "I goed",
            "corrected_version": "I went",
            "explanation": "Past tense.",
        }],
    })
    turn_service(deps, session_id=s.session_id, audio_bytes=b"...")
    data = deps.storage.load_session(s.session_id)
    assert len(data["turns"]) == 1
    assert data["turns"][0]["corrections"][0]["corrected_version"] == "I went"


def test_turn_service_handles_empty_corrections(tmp_path, mocker):
    """Clean message: LLM returns []. Turn still saves, corrections stored as empty list."""
    import json
    from tutor.web.services import turn_service, start_session_service
    deps = _make_deps(tmp_path)
    deps.llm.complete.return_value = "Opening."
    s = start_session_service(deps, scenario_id="tech_interview_behavioral")

    deps.asr.transcribe.return_value = "I went to the store."
    deps.llm.complete.return_value = json.dumps({
        "reply": "What did you buy?",
        "corrections": [],
    })
    result = turn_service(deps, session_id=s.session_id, audio_bytes=b"...")
    assert result.corrections == []
    data = deps.storage.load_session(s.session_id)
    assert data["turns"][0]["corrections"] == []
```

- [ ] **Step 3: Run** `pytest tests/web/test_services_session.py -v 2>&1 | tail -20` → 3 new fails.

- [ ] **Step 4: Modify `tutor/web/services.py`** — rewrite `turn_service`

At top of file, add to imports:

```python
from tutor.conversation import ChatTurn, build_session_chat_prompt
```

Replace `turn_service` (currently at lines 62–98) with:

```python
def turn_service(deps: Dependencies, session_id: str, audio_bytes: bytes) -> TurnResult:
    # 1. Load session first (cheap, fails fast on bad id)
    try:
        session_data = deps.storage.load_session(session_id)
    except FileNotFoundError as e:
        raise SessionNotFoundError(session_id) from e

    # 2. Save audio + ASR
    tmp = Path(tempfile.gettempdir()) / f"web_turn_{session_id}_{os.getpid()}.bin"
    tmp.write_bytes(audio_bytes)
    try:
        user_text = deps.asr.transcribe(tmp).strip()
        if not user_text:
            raise NoSpeechDetectedError(f"empty transcript for session {session_id}")

        # 3. Build chat history (excludes the new user message)
        scenario = load_scenario(session_data["scenario_id"])
        system_prompt = build_session_chat_prompt(scenario, user_native_language="Russian")
        history: list[dict[str, str]] = []
        if session_data.get("opening_text"):
            history.append({"role": "assistant", "content": session_data["opening_text"]})
        for turn in session_data.get("turns", []):
            history.append({"role": "user", "content": turn["user_text"]})
            history.append({"role": "assistant", "content": turn["llm_text"]})

        # 4. ChatTurn call: reply + corrections in one shot
        chat = ChatTurn(llm=deps.llm, model=deps.chat_model, system_prompt=system_prompt)
        response = chat.respond(history=history, message=user_text)
        correction_dicts = [c.model_dump() for c in response.corrections]

        # 5. Persist turn (with corrections)
        deps.storage.append_turn(
            session_id,
            user_text=user_text,
            llm_text=response.reply,
            corrections=correction_dicts,
        )
        return TurnResult(
            user_text=user_text,
            assistant_text=response.reply,
            corrections=correction_dicts,
        )
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
```

Note: `deps.chat_model` was added in Stage 2d T2; it defaults to `settings.openrouter_model`. Same model that previously did plain-text dialog, now used for JSON output.

- [ ] **Step 5: Run + commit**

```bash
pytest tests/web/test_services_session.py -v 2>&1 | tail -20
pytest 2>&1 | tail -5
```

Expected: existing turn tests may need adjustment (they previously mocked `llm.complete` to return plain text — now they need JSON). Read the failing tests and update mocks accordingly. The mock format change is mechanical:

```python
# before
deps.llm.complete.return_value = "Some reply."
# after
deps.llm.complete.return_value = json.dumps({"reply": "Some reply.", "corrections": []})
```

Walk through `test_services_session.py` and update any existing turn-related test (look for tests that call `turn_service` and configure `deps.llm.complete`). Do NOT modify tests of `end_session_service` or `start_session_service` — those still use plain `llm.complete` calls for opening/evaluator paths.

Run again until green. Full suite ~196 (190 + 6 new + adjusted existing).

```bash
git add tutor/web/schemas.py tutor/web/services.py tests/web/test_services_session.py
git commit -m "feat(web): turn_service returns per-turn corrections via ChatTurn"
```

## Context

- Branch: `main`. Previous: T2 commit.
- Task 3 of 6.

---

## Task 4: `end_session_service` aggregates from turns (drops Evaluator)

**Files:**
- Modify: `tutor/web/services.py`
- Modify: `tests/web/test_services_session.py`

- [ ] **Step 1: Append failing tests** to `tests/web/test_services_session.py`:

```python
def test_end_session_aggregates_per_turn_corrections(tmp_path, mocker):
    """End simply unions per-turn corrections into growth_points (no Evaluator call)."""
    import json
    from tutor.web.services import end_session_service, start_session_service, turn_service
    deps = _make_deps(tmp_path)
    deps.llm.complete.return_value = "Opening."
    s = start_session_service(deps, scenario_id="tech_interview_behavioral")

    # Turn 1: 1 correction
    deps.asr.transcribe.return_value = "I goed"
    deps.llm.complete.return_value = json.dumps({
        "reply": "Where?",
        "corrections": [{
            "tag": "grammar", "user_utterance": "I goed",
            "corrected_version": "I went", "explanation": "Past tense.",
        }],
    })
    turn_service(deps, session_id=s.session_id, audio_bytes=b"...")

    # Turn 2: 1 different correction
    deps.asr.transcribe.return_value = "more better"
    deps.llm.complete.return_value = json.dumps({
        "reply": "Interesting.",
        "corrections": [{
            "tag": "grammar", "user_utterance": "more better",
            "corrected_version": "better", "explanation": "'More' redundant with comparative.",
        }],
    })
    turn_service(deps, session_id=s.session_id, audio_bytes=b"...")

    result = end_session_service(deps, session_id=s.session_id)
    assert len(result.growth_points) == 2
    user_utts = [gp["user_utterance"] for gp in result.growth_points]
    assert "I goed" in user_utts
    assert "more better" in user_utts


def test_end_session_dedupes_corrections_by_user_utterance(tmp_path, mocker):
    """Same user_utterance across turns dedupes to one growth_point."""
    import json
    from tutor.web.services import end_session_service, start_session_service, turn_service
    deps = _make_deps(tmp_path)
    deps.llm.complete.return_value = "Opening."
    s = start_session_service(deps, scenario_id="tech_interview_behavioral")

    # Two turns, BOTH flag "I goed"
    correction = {
        "tag": "grammar", "user_utterance": "I goed",
        "corrected_version": "I went", "explanation": "Past tense.",
    }
    deps.asr.transcribe.return_value = "I goed there"
    deps.llm.complete.return_value = json.dumps({"reply": "ok", "corrections": [correction]})
    turn_service(deps, session_id=s.session_id, audio_bytes=b"...")

    deps.asr.transcribe.return_value = "I goed home"
    deps.llm.complete.return_value = json.dumps({"reply": "ok", "corrections": [correction]})
    turn_service(deps, session_id=s.session_id, audio_bytes=b"...")

    result = end_session_service(deps, session_id=s.session_id)
    assert len(result.growth_points) == 1


def test_end_session_does_not_call_evaluator(tmp_path, mocker):
    """Regression: Stage 2e drops the separate Evaluator pass."""
    import json
    from tutor.web.services import end_session_service, start_session_service, turn_service
    deps = _make_deps(tmp_path)
    deps.llm.complete.return_value = "Opening."
    s = start_session_service(deps, scenario_id="tech_interview_behavioral")
    deps.asr.transcribe.return_value = "I goed"
    deps.llm.complete.return_value = json.dumps({"reply": "ok", "corrections": []})
    turn_service(deps, session_id=s.session_id, audio_bytes=b"...")

    evaluator_mock = mocker.patch("tutor.web.services.Evaluator")
    end_session_service(deps, session_id=s.session_id)
    evaluator_mock.return_value.evaluate.assert_not_called()


def test_end_session_creates_srs_cards_from_aggregated(tmp_path, mocker):
    """SRS cards created from aggregated per-turn corrections (deduped)."""
    import json
    from tutor.web.services import end_session_service, start_session_service, turn_service
    deps = _make_deps(tmp_path)
    deps.llm.complete.return_value = "Opening."
    s = start_session_service(deps, scenario_id="tech_interview_behavioral")
    deps.asr.transcribe.return_value = "I goed"
    deps.llm.complete.return_value = json.dumps({
        "reply": "ok",
        "corrections": [{
            "tag": "grammar", "user_utterance": "I goed",
            "corrected_version": "I went", "explanation": "Past tense.",
        }],
    })
    turn_service(deps, session_id=s.session_id, audio_bytes=b"...")

    end_session_service(deps, session_id=s.session_id)
    deps.srs.create_cards.assert_called_once()
    args, kwargs = deps.srs.create_cards.call_args
    growth_points_passed = args[0] if args else kwargs.get("growth_points") or kwargs.get("growth_points", [])
    # Argument is a list of GrowthPoint instances (or similar dataclass) — verify content
    # Be lenient about whether positional or keyword
    if isinstance(growth_points_passed, list) and growth_points_passed:
        gp = growth_points_passed[0]
        # gp could be a Pydantic model or dataclass — check via getattr
        assert getattr(gp, "user_utterance", None) == "I goed" or gp.get("user_utterance") == "I goed"


def test_end_session_no_cards_when_no_corrections(tmp_path, mocker):
    """Clean session (no per-turn corrections) → no SRS card creation."""
    import json
    from tutor.web.services import end_session_service, start_session_service, turn_service
    deps = _make_deps(tmp_path)
    deps.llm.complete.return_value = "Opening."
    s = start_session_service(deps, scenario_id="tech_interview_behavioral")
    deps.asr.transcribe.return_value = "I went to the store."
    deps.llm.complete.return_value = json.dumps({"reply": "Nice.", "corrections": []})
    turn_service(deps, session_id=s.session_id, audio_bytes=b"...")

    end_session_service(deps, session_id=s.session_id)
    deps.srs.create_cards.assert_not_called()
```

- [ ] **Step 2: Run** `pytest tests/web/test_services_session.py -v 2>&1 | tail -20` → 5 new fails.

Also: the **existing** `test_end_session_persists_empty_growth_points_when_evaluator_returns_empty` (from Stage 2c.2) patches `Evaluator` and expects it to be called. That test becomes obsolete. **Delete it** in this task. Same for `test_end_session_writes_error_when_setup_raises` — it patches `load_scenario` to fail mid-evaluator. With the new flow `load_scenario` isn't called in `end_session_service` anymore. **Delete it**. Replace with the 5 new tests above. (Search for both test function names in the file and remove them — they're no longer meaningful.)

The `test_end_session_persists_empty_growth_points_for_zero_turn_session` regression test (0-turn case) IS still relevant — keep it, but the implementation will satisfy it through the aggregator returning `[]`.

The `test_end_session_sets_ended_at_before_evaluator_runs` regression — also keep, but adapt: it currently patches `Evaluator` and asserts `ended_at` is set when evaluator runs. Since we no longer call Evaluator, replace the test with a simpler version that asserts `ended_at` is set as the first storage write after `load_session`:

```python
def test_end_session_sets_ended_at_first(tmp_path, mocker):
    """Regression: ended_at must be set before SRS card creation so /review shows
    the session as Analyzing immediately."""
    from tutor.web.services import end_session_service, start_session_service
    deps = _make_deps(tmp_path)
    deps.llm.complete.return_value = "Opening."
    s = start_session_service(deps, scenario_id="tech_interview_behavioral")

    # Capture session state at the moment SRS card creation runs
    captured = {}
    def fake_create_cards(growth_points, session_id):
        snapshot = deps.storage.load_session(session_id)
        captured["ended_at"] = snapshot.get("ended_at")
        return []
    deps.srs.create_cards.side_effect = fake_create_cards

    # Need at least one correction so create_cards is invoked
    import json
    deps.asr.transcribe.return_value = "I goed"
    deps.llm.complete.return_value = json.dumps({
        "reply": "ok",
        "corrections": [{"tag": "grammar", "user_utterance": "I goed",
                         "corrected_version": "I went", "explanation": "Past tense."}],
    })
    from tutor.web.services import turn_service
    turn_service(deps, session_id=s.session_id, audio_bytes=b"...")
    end_session_service(deps, session_id=s.session_id)
    assert captured["ended_at"], "ended_at must be set before create_cards runs"
```

Replace the old `test_end_session_sets_ended_at_before_evaluator_runs` with this one.

- [ ] **Step 3: Modify `tutor/web/services.py`** — simplify `end_session_service`

Replace `end_session_service` (currently lines 101–163) with the version below. Also delete the now-unused import of `Evaluator` if no other function in the file uses it (search first — `evaluator.py` is still used by the CLI orchestrator in `tutor/session.py` so we keep the module, just drop the unused import from `tutor/web/services.py`).

Top of file: also add helper imports if needed (`from tutor.evaluator import GrowthPoint` — we reuse the schema for SRS).

```python
def _aggregate_corrections(turns: list[dict]) -> list[dict]:
    """Union per-turn corrections, dedupe by lowercased+stripped user_utterance.
    Preserves first-occurrence order."""
    seen: set[str] = set()
    out: list[dict] = []
    for t in turns:
        for c in t.get("corrections", []) or []:
            key = c.get("user_utterance", "").strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(c)
    return out


def end_session_service(deps: Dependencies, session_id: str) -> EndSessionResult:
    try:
        session_data = deps.storage.load_session(session_id)
    except FileNotFoundError as e:
        raise SessionNotFoundError(session_id) from e

    # Set ended_at FIRST so the session immediately appears in /review (as Analyzing,
    # then quickly becomes ready once growth_points is written below).
    deps.storage.end_session(session_id)

    turns = session_data.get("turns", [])
    aggregated = _aggregate_corrections(turns)

    deps.storage.set_growth_points(session_id, aggregated)

    cards_created_ids: list[str] = []
    growth_points_error: str | None = None
    if aggregated:
        try:
            # SRSEngine.create_cards expects a list of GrowthPoint-like objects with
            # `tag, user_utterance, corrected_version, explanation, context` attributes.
            # Construct GrowthPoint instances from the dicts. context defaults to None.
            growth_point_objs = [
                GrowthPoint(
                    tag=c["tag"],
                    user_utterance=c["user_utterance"],
                    corrected_version=c["corrected_version"],
                    explanation=c["explanation"],
                    context=c.get("context"),
                )
                for c in aggregated
            ]
            cards = deps.srs.create_cards(growth_point_objs, session_id=session_id)
            cards_created_ids = [c.id for c in cards]
            deps.storage.set_cards_created(session_id, cards_created_ids)
        except Exception as e:
            log.warning("SRS create_cards failed: %s", e)
            growth_points_error = f"create_cards failed: {e}"
            deps.storage.set_growth_points_error(session_id, growth_points_error)

    final = deps.storage.load_session(session_id)
    return EndSessionResult(
        session_id=session_id,
        ended_at=final.get("ended_at"),
        growth_points=aggregated,
        cards_created=cards_created_ids,
        growth_points_error=growth_points_error,
    )
```

Update imports at top of `tutor/web/services.py`:

```python
from tutor.evaluator import Evaluator, GrowthPoint
```

(Keep `Evaluator` import only if other helpers reference it. After this task it can be removed unless CLI integration needs it. Search the file for `Evaluator` — if it's not referenced elsewhere in `tutor/web/services.py`, remove the symbol from the import. `GrowthPoint` IS needed.)

- [ ] **Step 4: Run + commit**

```bash
pytest tests/web/test_services_session.py -v 2>&1 | tail -30
pytest 2>&1 | tail -5
```

Expected: all green. Full suite ~200.

```bash
git add tutor/web/services.py tests/web/test_services_session.py
git commit -m "feat(web): end_session aggregates per-turn corrections (drops Evaluator)"
```

## Context

- Branch: `main`. Previous: T3 commit.
- Task 4 of 6.

---

## Task 5: Frontend — `TurnResult.corrections` type + `SessionPage` inline corrections

**Files:**
- Modify: `frontend/src/api/types.ts`
- Modify: `frontend/src/pages/SessionPage.tsx`
- Modify: `frontend/src/pages/SessionPage.test.tsx`

- [ ] **Step 1: Update `frontend/src/api/types.ts`** — extend `TurnResult`

Find:

```typescript
export interface TurnResult {
  user_text: string;
  assistant_text: string;
}
```

Replace with:

```typescript
export interface TurnResult {
  user_text: string;
  assistant_text: string;
  corrections: ChatCorrectionDict[];
}
```

`ChatCorrectionDict` already exists from Stage 2d.

- [ ] **Step 2: Append failing test** to `frontend/src/pages/SessionPage.test.tsx`

Read the existing test file first to see the mock pattern. The new test extends the existing `useTTS` / `useRecorder` mocks. Add this test (adapt to match the existing pattern's mocking style):

```typescript
it("renders inline corrections under user message after a turn", async () => {
  // Reuse the existing test's mock pattern. Here's a self-contained variant
  // using vi.resetModules + vi.doMock — mirror whatever pattern the existing
  // empty-state / smoke tests use.
  vi.resetModules();
  vi.doMock("../api/client", () => ({
    api: {
      getSession: vi.fn().mockResolvedValue({
        session_id: "s1",
        scenario_id: "tech_interview_behavioral",
        started_at: "2026-05-21T10:00:00",
        ended_at: null,
        opening_text: "Hi, candidate.",
        turns: [],
      }),
      submitTurn: vi.fn().mockResolvedValue({
        user_text: "I goed there",
        assistant_text: "Where?",
        corrections: [{
          tag: "grammar",
          user_utterance: "I goed",
          corrected_version: "I went",
          explanation: "Past tense of 'go' is 'went'.",
        }],
      }),
      endSession: vi.fn(),
    },
    ApiError: class extends Error {},
  }));
  vi.doMock("../hooks/useTTS", () => ({
    useTTS: () => ({ speak: vi.fn().mockResolvedValue(undefined), isSpeaking: false, voices: [], lastError: null }),
  }));
  vi.doMock("../hooks/useRecorder", () => ({
    useRecorder: () => ({
      startRecording: vi.fn().mockResolvedValue(undefined),
      stopRecording: vi.fn().mockResolvedValue(new Blob(["x"], { type: "audio/webm" })),
      isRecording: false,
    }),
  }));

  const { SessionPage } = await import("./SessionPage");
  // The existing test file already has a `wrap(node)` helper — reuse it.
  render(wrap(<SessionPage />, "/session/s1"));

  // Simulate push-to-talk start+stop. The exact event sequence depends on PushToTalkButton —
  // either fire pointerdown/pointerup on the button, or call the recorder.stopRecording
  // mock to trigger turnMutation. The simplest robust path: find the push-to-talk button
  // (likely role="button" with aria-label or similar text "Hold to talk"), fire pointerDown
  // and pointerUp.
  const pttButton = await screen.findByRole("button", { name: /talk|record|speak/i });
  fireEvent.pointerDown(pttButton);
  fireEvent.pointerUp(pttButton);

  await waitFor(() => {
    expect(screen.getByText("I goed there")).toBeInTheDocument();
    expect(screen.getByText("I went")).toBeInTheDocument();
    expect(screen.getByText("Past tense of 'go' is 'went'.")).toBeInTheDocument();
    expect(screen.getByText("Where?")).toBeInTheDocument();
  });
});
```

If the existing `SessionPage.test.tsx` does NOT have a `wrap()` helper or a similar testing pattern, look at the imports / setup in the file and mirror what's there. The test file already has at least one test that successfully renders the page — copy its setup wholesale and add the new assertions.

- [ ] **Step 3: Run** `cd /Users/sarkhipov/Work/Personal/english-tutor/frontend && npm test SessionPage 2>&1 | tail -20` → new test fails (corrections not rendered).

- [ ] **Step 4: Modify `frontend/src/pages/SessionPage.tsx`**

Extend the `ChatMessage` interface and the `onSuccess` handler to attach corrections to the user message:

Replace the `ChatMessage` interface and the `turnMutation` block. Concretely:

```typescript
import { useEffect, useRef, useState } from "react";
import { useParams, useLocation, useNavigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { api, ApiError } from "../api/client";
import type { ChatCorrectionDict } from "../api/types";
import { MessageBubble } from "../components/MessageBubble";
import { InlineCorrection } from "../components/InlineCorrection";
import { PushToTalkButton } from "../components/PushToTalkButton";
import { useRecorder } from "../hooks/useRecorder";
import { useTTS } from "../hooks/useTTS";

interface ChatMessage {
  role: "user" | "assistant";
  text: string;
  corrections?: ChatCorrectionDict[];
}
```

Update the `useQuery` callback that builds initial messages — when reading existing turns from a session, include any per-turn corrections that were already stored:

```typescript
  useQuery({
    queryKey: ["session", id],
    queryFn: async () => {
      const data = await api.getSession(id!);
      const msgs: ChatMessage[] = [];
      if (data.opening_text) msgs.push({ role: "assistant", text: data.opening_text });
      for (const t of data.turns) {
        const turnCorrections = (t as unknown as { corrections?: ChatCorrectionDict[] }).corrections;
        msgs.push({ role: "user", text: t.user_text, corrections: turnCorrections ?? [] });
        msgs.push({ role: "assistant", text: t.llm_text });
      }
      setMessages(msgs);
      return data;
    },
    enabled: !!id,
  });
```

Note: this requires `SessionData.turns[i]` to optionally have `corrections`. Update the type in `frontend/src/api/types.ts` too:

```typescript
export interface SessionData {
  session_id: string;
  scenario_id: string;
  started_at: string;
  ended_at: string | null;
  opening_text: string | null;
  turns: Array<{ ts: string; user_text: string; llm_text: string; corrections?: ChatCorrectionDict[] }>;
  growth_points?: GrowthPointDict[];
  cards_created?: string[];
  growth_points_error?: string | null;
}
```

Update the `turnMutation.onSuccess` to push a user message with corrections + an assistant message:

```typescript
  const turnMutation = useMutation({
    mutationFn: async (audio: Blob) => api.submitTurn(id!, audio),
    onSuccess: async (result) => {
      setMessages((prev) => [
        ...prev,
        { role: "user", text: result.user_text, corrections: result.corrections },
        { role: "assistant", text: result.assistant_text },
      ]);
      try {
        await tts.speak(result.assistant_text);
      } catch {
        /* TTS failure non-fatal */
      }
    },
    onError: (err) => {
      // ... existing error handling unchanged ...
    },
  });
```

Update the messages-render loop to render `InlineCorrection` under each user message:

```tsx
        {messages.map((m, i) => (
          <div key={i}>
            <MessageBubble
              role={m.role}
              text={m.text}
              isSpeaking={m.role === "assistant" && tts.isSpeaking && i === messages.length - 1}
            />
            {m.role === "user" && m.corrections && m.corrections.length > 0 && (
              <div>
                {m.corrections.map((c, j) => (
                  <InlineCorrection
                    key={j}
                    growth_point={{ ...c, context: null }}
                  />
                ))}
              </div>
            )}
          </div>
        ))}
```

- [ ] **Step 5: Run + build + commit**

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor/frontend
npm test 2>&1 | tail -15
npm run build 2>&1 | tail -5
```

Expected: ~50 tests green (48 existing + new).

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor
git add frontend/src/api/types.ts frontend/src/pages/SessionPage.tsx frontend/src/pages/SessionPage.test.tsx
git commit -m "feat(session): render inline corrections under user messages"
```

## Context

- Branch: `main`. Previous: T4 commit.
- Task 5 of 6.

---

## Task 6: Manual smoke

- [ ] **Step 1: Run all suites + build + push**

```bash
cd /Users/sarkhipov/Work/Personal/english-tutor && source .venv/bin/activate && pytest 2>&1 | tail -5
cd frontend && npm test 2>&1 | tail -10
npm run build 2>&1 | tail -5

cd /Users/sarkhipov/Work/Personal/english-tutor
git push origin main
```

Expected: pytest ~200 green, npm test ~50 green, build clean.

- [ ] **Step 2: Run web UI**

`./scripts/build_and_serve.sh` → `http://127.0.0.1:8000`

Checks:

1. Click Scenarios → pick "tech_interview_behavioral" (or any) → starts a session.
2. Hold push-to-talk, say a deliberate-mistake sentence ("I goed to the store yesterday"). Release.
3. Within 2-3 s:
   - Your transcribed text appears in a user bubble.
   - Below it: an InlineCorrection card showing "I goed" → "I went" with explanation.
   - Then the assistant's reply in a bubble (TTS plays).
4. Continue 2 more turns with various mistakes. Each user message gets its own inline corrections (or none if the turn is clean).
5. Click End session → navigate to /. Click Review → the just-ended session appears in the list with status `N corrections` (not Analyzing — it's already ready).
6. Click into the session → review-detail view shows all corrections inline, identical to chat-mode.
7. Next day: open /practice → SRS cards from this session's corrections are due (test logic: should appear with `due_date == today`).

- [ ] **Step 3: Report findings**

If anything regresses (especially: dialog reply quality, latency, JSON parse failures producing fallback replies), file follow-up. Otherwise Stage 2e done.

## Context

- Branch: `main`. Previous: T5 commit.
- Task 6 of 6.

---

## Self-review

1. **Spec coverage:**
   - ChatTurn accepts custom system prompt → T1 ✓
   - `build_session_chat_prompt(scenario)` helper → T1 ✓
   - `storage.append_turn` persists corrections → T2 ✓
   - `turn_service` uses ChatTurn + returns corrections → T3 ✓
   - `end_session_service` drops Evaluator, aggregates from turns, dedupes → T4 ✓
   - SRS card creation preserved at session end → T4 ✓
   - `TurnResult.corrections` schema field → T3 + T5 (backend + frontend) ✓
   - Frontend renders inline corrections after each turn → T5 ✓
   - Backward compat: existing closed sessions unchanged → relies on storage shape; no migration needed ✓
   - 0-turn case: aggregator returns [], still writes growth_points: [] → T4 implementation ✓

2. **Placeholder scan:** no TBD / TODO / placeholder strings.

3. **Type consistency:**
   - `ChatCorrectionDict` (backend Pydantic + frontend TS) — same shape, 4 fields.
   - `ChatCorrection` (Python class from conversation.py) — same 4 fields.
   - `GrowthPoint` (from evaluator.py) — 5 fields (adds `context: str | None`). T4 builds these from dict via explicit constructor.
   - `SessionData.turns[i].corrections` is optional in TS — backend writes the field only when ChatTurn returned a list (even empty), so older turns lack it.
   - `TurnResult.corrections` defaults to `[]` in Pydantic and is non-optional in TS — backend always sends a list now.

4. **Failure modes covered:**
   - ChatTurn JSON parse failure → fallback reply, empty corrections, turn still saved (existing behaviour from Stage 2d, no new test needed in 2e).
   - 0-turn end: aggregator handles empty list correctly.
   - Duplicate user_utterance across turns: dedupe in `_aggregate_corrections`.
   - SRS card creation failure: existing try/except catches, sets `growth_points_error`.

---

## Definition of Done

- 5 task commits + manual smoke on `origin/main`.
- pytest ~200 green.
- npm test ~50 green.
- npm run build succeeds.
- Voice session shows inline corrections within 2 s of finishing each utterance.
- Ended session lands in /review immediately as ready (no Analyzing phase).
- SRS cards still created from corrections at session end.
- No regressions in /chat, /review, /practice, /stats, /scenarios.
