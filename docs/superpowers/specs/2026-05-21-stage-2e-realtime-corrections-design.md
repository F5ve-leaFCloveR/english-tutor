# Stage 2e — Real-time Per-Turn Corrections in Voice Sessions

- **Date:** 2026-05-21
- **Author:** Stas Arkhipov
- **Status:** Draft, pending implementation plan

## 1. Context

Today a voice session shows corrections only after `End` is clicked and the post-session `Evaluator` finishes processing the full transcript (~5 s). The user wants to see corrections **immediately after each utterance** — the same UX that `/chat` (Stage 2d) already provides for typed text. After `End`, the session should drop straight into `/review` with all per-turn corrections already attached, with no separate evaluator pass.

## 2. Goals

- After each user utterance in a voice session, the user sees their transcribed text, then inline `vocab`/`grammar` corrections (0–3), then the bot's reply.
- Session end no longer triggers a separate `Evaluator` call. The ended session immediately appears in `/review` with all collected corrections.
- SRS card creation continues — cards are made from the union of per-turn corrections (deduped by `user_utterance`).
- `/review` and `ReviewDetail` UI is unchanged.

## 3. Non-Goals

- Streaming TTS or word-by-word audio reveal.
- Live grammar feedback during recording (only after ASR returns).
- Per-message manual re-evaluation / editing of corrections.
- Backfilling per-turn corrections for sessions created under the old flow.

## 4. Approach

Reuse `ChatTurn` (from Stage 2d) for voice session turns. Per turn, one LLM call returns `{reply, corrections}` JSON instead of plain text. The system prompt combines the scenario's role-play instructions with the JSON-output correction instructions.

Each `turns[i]` dict in `session.json` gets a new `corrections` field. At session end, the union of those per-turn corrections (deduped by `user_utterance`) is written to the session's `growth_points` field, preserving the existing storage contract for `/review` and SRS card creation.

## 5. Architecture

```
[ Voice session turn ]
   recorder → /api/sessions/:id/turn (audio)
   backend:
     ASR → user_text
     ChatTurn.respond(history, user_text, system_prompt=scenario+correction)
       → { reply, corrections[] }
     storage.append_turn(session_id, user_text, llm_text=reply, corrections=corrections)
   response: TurnResult { user_text, assistant_text, corrections }
   frontend:
     render user_bubble → InlineCorrection cards → assistant_bubble → TTS(reply)

[ Session end ]
   /api/sessions/:id/end
   backend (BackgroundTask):
     storage.end_session(session_id)        # ended_at first (Stage 2c.2 ordering)
     turns = storage.load_session(...)["turns"]
     growth_points = dedupe_by_user_utterance([ c for t in turns for c in t.get("corrections", []) ])
     storage.set_growth_points(session_id, growth_points)
     if growth_points:
        deps.srs.create_cards(growth_points, session_id=session_id)
```

## 6. Components

### 6.1 `tutor/conversation.py` — refactor

- `ChatTurn.__init__` accepts optional `system_prompt: str | None = None`. Default falls back to the existing `_DEFAULT_CHAT_SYSTEM_PROMPT`.
- New module-level helper `build_session_chat_prompt(scenario: Scenario, user_native_language: str = "Russian") -> str`:
  - Returns the scenario role-play prompt (`scenarios.loader.build_system_prompt(...)`) concatenated with a `_CORRECTION_INSTRUCTIONS` block that asks for `{reply, corrections}` JSON output.
- `_CORRECTION_INSTRUCTIONS` extracted as a constant from the current `_SYSTEM_PROMPT` (it's the "Return STRICT JSON" portion + the per-message correction rules).

### 6.2 `tutor/storage.py` — `append_turn`

- `append_turn(session_id, user_text, llm_text, corrections: list[dict] | None = None)` — new optional parameter.
- Persists turn as `{ts, user_text, llm_text, corrections}`. If `corrections=None`, field is absent (backward compatible with old sessions / old callers).

### 6.3 `tutor/web/services.py` — `turn_service`

Rewrite:

```python
def turn_service(deps, session_id, audio_bytes):
    session_data = storage.load_session(session_id)  # 404 guard
    # ASR
    user_text = deps.asr.transcribe(audio_bytes).strip()
    if not user_text: raise NoSpeechDetectedError(...)

    scenario = load_scenario(session_data["scenario_id"])
    system_prompt = build_session_chat_prompt(scenario, user_native_language="Russian")

    # history excludes the new user message
    history = []
    if session_data.get("opening_text"):
        history.append({"role": "assistant", "content": session_data["opening_text"]})
    for t in session_data.get("turns", []):
        history.append({"role": "user", "content": t["user_text"]})
        history.append({"role": "assistant", "content": t["llm_text"]})

    chat = ChatTurn(llm=deps.llm, model=deps.dialog_model_or_chat_model, system_prompt=system_prompt)
    response = chat.respond(history=history, message=user_text)

    correction_dicts = [c.model_dump() for c in response.corrections]
    storage.append_turn(session_id, user_text=user_text, llm_text=response.reply, corrections=correction_dicts)

    return TurnResult(user_text=user_text, assistant_text=response.reply, corrections=correction_dicts)
```

Uses the existing dialog model (`settings.openrouter_model`, or whatever the deps factory currently passes for `dialog_model_or_chat_model` — confirm at implementation time which deps field is appropriate; both currently default to `openrouter_model`).

### 6.4 `tutor/web/services.py` — `end_session_service`

Simplified:

```python
def end_session_service(deps, session_id):
    session_data = storage.load_session(session_id)  # 404 guard
    storage.end_session(session_id)                  # ended_at first (Stage 2c.2)

    turns = session_data.get("turns", [])
    aggregated = _aggregate_corrections(turns)       # dedup by user_utterance, keep first occurrence

    storage.set_growth_points(session_id, aggregated)

    cards_created_ids = []
    growth_points_error = None
    if aggregated:
        try:
            # Convert dicts back to GrowthPoint-like objects for srs.create_cards
            growth_points_objs = _dicts_to_growth_points(aggregated)
            cards = deps.srs.create_cards(growth_points_objs, session_id=session_id)
            cards_created_ids = [c.id for c in cards]
            storage.set_cards_created(session_id, cards_created_ids)
        except Exception as e:
            log.warning("SRS create_cards failed: %s", e)
            growth_points_error = f"create_cards failed: {e}"
            storage.set_growth_points_error(session_id, growth_points_error)

    final = storage.load_session(session_id)
    return EndSessionResult(
        session_id=session_id,
        ended_at=final.get("ended_at"),
        growth_points=aggregated,
        cards_created=cards_created_ids,
        growth_points_error=growth_points_error,
    )
```

- `_aggregate_corrections(turns)` walks all turns, collects `t.get("corrections", [])`, dedupes by `c["user_utterance"].lower().strip()`, returns deduped list preserving original order.
- `_dicts_to_growth_points(dicts)` builds `GrowthPoint` instances (the model from `evaluator.py` — reuse) so `srs.create_cards(...)` works unchanged. `ChatCorrection` and `GrowthPoint` share the four core fields; we just add `context=None` to match `GrowthPoint`.

### 6.5 `tutor/web/schemas.py` — `TurnResult`

Add field:

```python
class TurnResult(BaseModel):
    user_text: str
    assistant_text: str
    corrections: list[ChatCorrectionDict] = []
```

`ChatCorrectionDict` exists from Stage 2d.

### 6.6 Frontend — `TurnResult` type

Add `corrections: ChatCorrectionDict[]` to `frontend/src/api/types.ts:TurnResult` (already has `user_text`, `assistant_text`).

### 6.7 Frontend — `SessionPage.tsx`

When `turnMutation.onSuccess` fires, render `InlineCorrection` cards under the user message that just landed. Storage:

- Component state already keeps a `messages` array (or equivalent). Extend each user message with optional `corrections: ChatCorrectionDict[]` (same shape used in `/chat`).
- Right after the turn response is committed to state, the inline corrections appear automatically on next render.
- TTS playback of `assistant_text` is unchanged.

### 6.8 Frontend — `ReviewDetail.tsx`

No change. Reads `growth_points` from the session JSON. New sessions populate it from aggregated per-turn corrections; old sessions still have evaluator-derived `growth_points`.

## 7. Data Flow

```
Turn:
  user_audio
    → /api/sessions/:id/turn
    → ASR → user_text
    → ChatTurn (1 LLM call) → {reply, corrections}
    → storage.append_turn(corrections=...)
    → response { user_text, assistant_text, corrections }
  frontend: render user_bubble + InlineCorrection + assistant_bubble + TTS

End:
  → /api/sessions/:id/end (202 Accepted)
  background:
    storage.end_session(id)                  # ended_at first
    aggregate per-turn corrections → growth_points
    storage.set_growth_points(id, growth_points)
    srs.create_cards(growth_points)
```

## 8. Error Handling

| Scenario | Behaviour |
|---|---|
| `ChatTurn` returns invalid JSON twice | Returns fallback `ChatResponse(reply="Sorry...", corrections=[])`. Turn still saved with empty corrections. |
| LLM API failure | `ChatTurn` already catches → fallback reply. Turn saved (degraded UX, no crash). |
| 0-turn session ends | `aggregated == []`, `set_growth_points(id, [])`, no SRS cards. Matches Stage 2c.2 behaviour. |
| Duplicate `user_utterance` across turns | Dedupe keeps first; second occurrence dropped. Prevents card duplication. |
| Existing closed sessions (pre-2e) | Untouched. They retain Evaluator-derived `growth_points`; `/review` shows them via existing substring matching. |
| Existing in-progress sessions (no `ended_at`) | New `turn_service` runs against them; their next turn produces a `corrections` field, prior turns stay correction-less. End flow still works. |

## 9. Testing

### Backend
- `ChatTurn` accepts `system_prompt=` override (1 new test).
- `build_session_chat_prompt(scenario)` produces a prompt that includes both scenario role-play text AND the correction JSON instructions (1 test).
- `storage.append_turn(corrections=...)` persists corrections; default `None` preserves old shape (2 tests).
- `turn_service` returns `corrections` in `TurnResult` and persists them per turn (2 tests).
- `end_session_service` aggregates per-turn corrections into `growth_points` (1 test); dedupes by `user_utterance` (1 test); skips SRS card creation when aggregated is empty (1 test); creates cards when non-empty (1 test); 0-turn case still works (regression).
- `end_session_service` does NOT call `Evaluator` anymore — assert via `mocker.patch("tutor.web.services.Evaluator")` confirming `evaluate` was not called (1 test).

### Frontend
- `SessionPage` renders `InlineCorrection` cards after a turn returns corrections (1 test).
- `SessionPage` skips InlineCorrection when corrections array is empty (1 test).
- `TurnResult` type compiles with `corrections` field (implicit via build).

### Manual smoke
- Run a session, say 2-3 sentences each with deliberate mistakes. After each turn, verify corrections appear inline within ~2 s.
- Click End → navigate to `/review` → ensure the same session shows corrections inline immediately (no Analyzing state, or very brief one).
- Next day check `/practice` — SRS cards appear from this session's corrections.

## 10. Decisions

| Decision | Choice | Why |
|---|---|---|
| Combined LLM call vs separate evaluator | Combined (ChatTurn) | Lower latency for voice, fewer LLM calls overall, proven in Stage 2d. |
| Drop end-of-session Evaluator | Yes | Per-turn corrections supersede; one fewer LLM call per session. |
| Keep SRS card creation | Yes | Voice = primary practice loop; cards reinforce mistakes. |
| Dedupe corrections by `user_utterance` | Yes | Avoid card duplication when the user repeats a mistake. |
| Backfill old sessions | No | Out of scope. Old sessions retain Evaluator output; new ones use per-turn pathway. |
| Model for combined call | Same as current dialog (`gemini-2.5-flash`) | Already does it for /chat. Sufficient for per-message analysis. |

## 11. Migration / Backward Compatibility

- Old sessions: `turns[]` lacks `corrections` field. `_aggregate_corrections` treats missing key as `[]`. `growth_points` already populated by Evaluator at original close time — left untouched.
- New sessions: each turn has `corrections` field; `growth_points` is aggregated at close.
- `ReviewDetail` renders whichever `growth_points` is present; both code paths produce the same JSON shape.

## 12. Success Criteria

- Run a session with 3 deliberate mistakes (e.g., "I goed", "she don't like", "more better"). After each utterance, the corresponding InlineCorrection card appears under the user bubble within 2 s.
- Click End → /review → the same session shows in the list with status `N corrections` or `Clean`, opens to a detail view with all corrections inline.
- Next day in `/practice`, the deduped corrections appear as due SRS cards.
- All current tests + new tests green.
