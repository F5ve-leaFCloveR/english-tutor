# Stage 2f — Scenarios + SRS dedupe/limit + Repeat practice

- **Date:** 2026-05-22
- **Author:** Stas Arkhipov
- **Status:** Draft, pending implementation plan

## 1. Context

After several Stage 2 iterations the user wants three independent improvements:

1. **More scenarios** plus the ability to define **custom scenarios via the UI**. Only 3 built-in YAML scenarios exist today (`tech_interview_behavioral`, `apartment_rental_abroad`, `daily_standup`).
2. **SRS cleanup**. After Stage 2e (per-turn corrections + aggregation), `/practice` accumulates many cards and the same `user_utterance` can produce multiple cards with different `corrected_version` targets — the grader then expects one target while the user remembers another. Already observed: `"okay, show me it."` appears 3× in `cards.json` (25 total).
3. **"Try again"** on a card after grading — to drill a recently-reviewed item without bumping SRS scheduling.

## 2. Goals

- Ship 4 new built-in YAML scenarios that cover daily-life topics.
- Allow the user to create a custom scenario from a minimal form (name, difficulty, system prompt, optional opening line). Custom scenarios appear next to built-in ones in `/`. Users can delete their own custom scenarios.
- On session end, only create SRS cards for corrections whose `user_utterance` does not already exist in storage, and cap new-cards-per-session at **5** (grammar prioritised over vocab).
- A one-shot backfill removes the 2 existing extra `"okay, show me it."` duplicate cards from the user's `cards.json`.
- After a card is graded, the result screen offers a **Try again** button that resets the recorder so the user can practice the same target — without invoking SRS scheduling.

## 3. Non-Goals

- Editing existing built-in YAML scenarios via the UI.
- Editing custom scenarios after creation (delete + recreate is fine for MVP).
- Sharing custom scenarios across users / multi-user.
- Marking duplicates retroactively in old session JSONs.
- A "cram mode" UI separate from /practice (just a button suffices).
- Replacing the SM-2 algorithm.

## 4. Approach

### 4.1 Scenarios — built-in + custom hybrid

Built-in scenarios remain YAML files in `tutor/scenarios/`. Custom scenarios live in a single JSON file `custom_scenarios.json` at the project root (gitignored). New module `tutor/scenarios/custom_storage.py` owns CRUD. `loader.py`'s `list_scenarios()` and `load_scenario(id)` merge both sources, preferring built-in if an id clash occurs (built-ins effectively "win" — unlikely since custom ids are slugified user names).

Custom scenarios provide a free-text `system_prompt` (no Jinja templating required — `{{ user_native_language }}` is allowed if the user wants it but optional). The structured `counterpart`, `goal`, `vocab_focus` fields default to empty values to satisfy the `Scenario` dataclass.

New endpoints:
- `POST /api/scenarios/custom` body `{name, difficulty?, system_prompt, opening_line?}` → 201 `{id, name, difficulty, is_custom: true}`.
- `DELETE /api/scenarios/custom/{id}` → 204.
- `GET /api/scenarios` extended with `is_custom: bool` flag per item.

### 4.2 SRS dedupe + limit

`SRSEngine.create_cards(growth_points, session_id)` is modified:

1. **Cross-session dedupe**: build a set of existing `user_utterance.lower().strip()` across all current cards. Filter out any incoming growth_point whose key is in the set.
2. **Per-session limit**: after dedup, sort: `grammar` first, `vocab` second; preserve input order within each tag. Take first 5.
3. Create cards from the filtered+capped list as before.

If no new cards survive (all dupes or empty), return `[]`. End-of-session flow already handles empty-card case.

A one-shot Python via Bash will dedupe existing `cards.json` (remove 2 redundant `"okay, show me it."` entries, keeping the earliest by created_at if present, otherwise first by file order).

### 4.3 "Try again" button

Frontend-only change in `PracticePage.tsx`. The result screen (rendered when `lastResult !== null`) gains a second button next to "Next card":

- **Try again** — `setLastResult(null)`. The card view re-renders showing the same card. `index` doesn't advance. No API call. No SRS state mutation.

## 5. Architecture

```
[ Backend ]
   tutor/scenarios/
     custom_storage.py   (NEW: JSON CRUD)
     loader.py           (MOD: merge built-in + custom)
     casual_conversation.yaml      (NEW)
     travel_directions.yaml        (NEW)
     coffee_chat_colleague.yaml    (NEW)
     customer_service_call.yaml    (NEW)

   tutor/srs_engine.py    (MOD: create_cards dedupes + caps)

   tutor/web/
     schemas.py    (MOD: ScenarioSummary.is_custom; CustomScenarioCreate)
     services.py   (MOD: list_scenarios_service includes is_custom; new create/delete services)
     api.py        (MOD: POST /api/scenarios/custom, DELETE /api/scenarios/custom/{id})

[ Frontend ]
   api/
     types.ts    (MOD: ScenarioSummary.is_custom; CustomScenarioCreate)
     client.ts   (MOD: api.createCustomScenario, api.deleteCustomScenario)

   pages/
     ScenariosPage.tsx       (MOD: + Create button, delete on customs)
     NewScenarioPage.tsx     (NEW: form)
     PracticePage.tsx        (MOD: Try again button)

   App.tsx     (MOD: /scenarios/new route)
```

## 6. Components

### 6.1 New built-in YAML scenarios

`tutor/scenarios/casual_conversation.yaml`, `travel_directions.yaml`, `coffee_chat_colleague.yaml`, `customer_service_call.yaml`. All follow the existing structure (id, name, difficulty, counterpart{role,persona}, goal, vocab_focus, opening_line, system_prompt_template with `{{ user_native_language }}`).

Difficulty mix: 2× intermediate, 2× advanced (rough — actual choices in plan).

### 6.2 `CustomScenarioStorage` (`tutor/scenarios/custom_storage.py`)

```python
@dataclass
class CustomScenarioStorage:
    path: Path

    def list_all(self) -> list[dict]: ...
    def load(self, scenario_id: str) -> dict: ...       # raises ScenarioNotFoundError
    def create(self, name, difficulty, system_prompt, opening_line) -> dict: ...
    def delete(self, scenario_id: str) -> None: ...     # raises ScenarioNotFoundError
```

Storage file format:

```json
{
  "scenarios": [
    {
      "id": "my-restaurant-chat",
      "name": "My restaurant chat",
      "difficulty": "intermediate",
      "system_prompt": "You are a waiter at a fancy NYC restaurant...",
      "opening_line": "Good evening! Welcome.",
      "created_at": "2026-05-22T12:00:00"
    }
  ]
}
```

`create()` slugifies `name` → ASCII lowercase hyphen-separated `id`. Collision: append `-2`, `-3`, etc.

### 6.3 Loader merge (`tutor/scenarios/loader.py`)

- `list_scenarios() -> list[str]`: existing YAML stems + ids from `CustomScenarioStorage.list_all()`. Dedup if a custom id ever clashes (built-in wins).
- `load_scenario(id)`: try YAML first; on missing, look in custom storage. Build a `Scenario` from custom dict with empty structured fields:
  - `counterpart = {}`
  - `goal = ""`
  - `vocab_focus = []`
  - `system_prompt_template` = raw `system_prompt` (no jinja preprocessing needed if it lacks `{{ }}`; if user includes `{{ user_native_language }}`, it works through `Template(...).render()`).
  - `opening_line` = custom `opening_line` or sensible default (`"Hello — let's get started."`).

Loader's `load_scenario` now accepts the configured custom storage via dependency injection (a global default for backward compat in CLI, web layer overrides).

Pragmatic option: keep `load_scenario(id)` standalone (no DI), let it construct a `CustomScenarioStorage(path=os.getenv("CUSTOM_SCENARIOS_PATH", "custom_scenarios.json"))` on each call. Cheap (one JSON file read). Simpler than threading DI through.

### 6.4 Web schemas

```python
class ScenarioSummary(BaseModel):
    id: str
    name: str
    difficulty: str
    is_custom: bool = False


class CustomScenarioCreate(BaseModel):
    name: str
    difficulty: str = "intermediate"
    system_prompt: str
    opening_line: str | None = None
```

### 6.5 Web services

```python
def create_custom_scenario_service(deps, payload: CustomScenarioCreate) -> ScenarioSummary:
    storage = CustomScenarioStorage(path=settings.custom_scenarios_path)
    created = storage.create(
        name=payload.name,
        difficulty=payload.difficulty,
        system_prompt=payload.system_prompt,
        opening_line=payload.opening_line or "",
    )
    return ScenarioSummary(id=created["id"], name=created["name"], difficulty=created["difficulty"], is_custom=True)


def delete_custom_scenario_service(deps, scenario_id: str) -> None:
    storage = CustomScenarioStorage(path=settings.custom_scenarios_path)
    storage.delete(scenario_id)
```

`list_scenarios_service` extended to mark each item `is_custom`:
- Built-in: load file via existing loader path (YAML exists).
- Custom: look up id in `CustomScenarioStorage`.

### 6.6 Web API

```python
@app.post("/api/scenarios/custom", response_model=ScenarioSummary, status_code=201)
async def create_custom(req: CustomScenarioCreate, d: Dependencies = Depends(get_deps)):
    if not req.name.strip() or not req.system_prompt.strip():
        raise HTTPException(status_code=422, detail="name and system_prompt are required")
    return services.create_custom_scenario_service(d, req)


@app.delete("/api/scenarios/custom/{scenario_id}", status_code=204)
async def delete_custom(scenario_id: str, d: Dependencies = Depends(get_deps)):
    services.delete_custom_scenario_service(d, scenario_id)
    return None
```

### 6.7 Frontend

- `frontend/src/api/types.ts`:
  ```typescript
  export interface ScenarioSummary {
    id: string;
    name: string;
    difficulty: string;
    is_custom?: boolean;
  }
  export interface CustomScenarioCreate {
    name: string;
    difficulty: string;
    system_prompt: string;
    opening_line?: string;
  }
  ```
- `frontend/src/api/client.ts`: `createCustomScenario(req)`, `deleteCustomScenario(id)`.
- `frontend/src/pages/ScenariosPage.tsx`: header "+ Create scenario" → navigates to `/scenarios/new`. Each row with `is_custom` shows a small `×` button that calls `deleteCustomScenario(id)` then refetches via React Query invalidation.
- `frontend/src/pages/NewScenarioPage.tsx` (new): form with 4 fields. On submit → `createCustomScenario(...)` → navigate to `/`.
- `frontend/src/App.tsx`: `<Route path="/scenarios/new" element={<NewScenarioPage />} />`.

### 6.8 SRS engine — dedupe + cap

`SRSEngine.create_cards`:

```python
PER_SESSION_CARD_LIMIT = 5

def create_cards(self, growth_points: list[GrowthPoint], session_id: str) -> list[Card]:
    existing_keys = {c.user_utterance.lower().strip() for c in self._cards.values()}
    filtered = [gp for gp in growth_points
                if gp.user_utterance.lower().strip() not in existing_keys]
    filtered.sort(key=lambda gp: 0 if gp.tag == "grammar" else 1)
    capped = filtered[:PER_SESSION_CARD_LIMIT]
    # existing create-each-card loop, on `capped` instead of `growth_points`
```

The result list returned to `end_session_service` is the actually-created subset. SRS file write is skipped if nothing new lands.

### 6.9 Practice "Try again"

`PracticePage.tsx` result branch:

```tsx
{lastResult ? (
  <div className="...">
    {/* existing result display */}
    <div className="flex gap-3 justify-center">
      <button onClick={() => setLastResult(null)}>Try again</button>
      <button onClick={advance}>Next card</button>
    </div>
  </div>
) : ...}
```

Try-again does NOT touch `index`, recorder, or SRS. The user can record again, hit Submit, see a new result for the same card. Each repeat costs an LLM grader call but no SRS bump.

## 7. Data Flow

### 7.1 Creating a custom scenario

```
User: /scenarios/new form submit
  → POST /api/scenarios/custom {name, difficulty, system_prompt, opening_line?}
  → Service: CustomScenarioStorage.create → JSON write
  → 201 ScenarioSummary with is_custom=true
  → Frontend: navigate to / → ScenariosPage refetches /api/scenarios
```

### 7.2 SRS card creation post-session

```
end_session_service:
  aggregated = _aggregate_corrections(turns)
  srs.create_cards(aggregated_as_GrowthPoint_objs, session_id)
    # internally: dedupe vs storage, cap at 5
  → returns the actually-created N cards (could be 0-5)
```

### 7.3 Try again

```
User clicks "Try again":
  setLastResult(null)
  → renders card view again, recorder ready
User records new attempt → Submit:
  → POST /api/review/{card_id}/grade
  → returns new GradeResult, lastResult updated
  (SRS due_date already changed on FIRST submit; further attempts do bump it
   per current backend behavior — TODO: see decision below)
```

**Decision on repeat semantics**: the existing `/api/review/{card_id}/grade` endpoint calls `srs.record_review(quality)` which bumps the SRS state. If the user clicks "Try again" and re-submits, the second grade ALSO bumps SRS. To honour the "no SRS effect" decision, the simplest fix is **frontend-only**: "Try again" simply does not navigate to the next card and lets the user re-record, BUT we don't add a new "submit again" round trip — we just clear the result and let them try recording for an updated grade. Actually that's still a grade call.

Cleanest implementation: introduce a new endpoint `/api/review/{card_id}/grade?practice_only=true` (or a body flag) that grades but does NOT call `record_review`. Frontend uses it when invoked from a "Try again" attempt.

Alternative: keep `/api/review/{card_id}/grade` unchanged; "Try again" lets the user record, then sends the same endpoint; backend's `record_review` is idempotent-ish (the second `record_review` overwrites due_date based on new quality — that's "fine" but not truly no-op).

Going with the explicit flag approach: simpler semantics and easier to reason about.

### 7.4 Backfill (one-shot)

```bash
python3 -c "
import json
with open('cards.json') as f: data = json.load(f)
cards = data['cards']
seen = set()
deduped = []
for c in cards:
    key = c['user_utterance'].lower().strip()
    if key in seen:
        continue
    seen.add(key)
    deduped.append(c)
data['cards'] = deduped
print(f'before={len(cards)} after={len(deduped)} removed={len(cards)-len(deduped)}')
with open('cards.json','w') as f: json.dump(data, f, indent=2, ensure_ascii=False)
"
```

Not committed — runs once, reports count.

## 8. Error Handling

| Scenario | Behaviour |
|---|---|
| POST custom scenario with empty name or system_prompt | 422 |
| POST custom scenario with name that slugifies to existing id | Append `-2`, `-3`, ... |
| DELETE custom scenario that doesn't exist | 404 |
| DELETE built-in scenario id (not in custom storage) | 404 — built-ins not deletable via API |
| Custom scenario JSON file missing/corrupt | Treated as empty list; corrupt → backup `.broken-N` like `cards.json` |
| `create_cards` with all-duplicate growth_points | Returns `[]`, no write, no card_ids in storage |
| `create_cards` post-cap: 5 cards land, others dropped | Logged at debug |
| `/api/review/.../grade?practice_only=true` | Grades but skips SRS write |
| Try-again on first card (no prior grade) | Button not yet visible (only shown when `lastResult` set) |

## 9. Testing

### Backend
- `CustomScenarioStorage`: create/load/list/delete + collision id handling + corrupt-file backup (4-5 tests).
- `loader.load_scenario`: returns custom scenario when YAML missing; built-in wins on id clash (2 tests).
- `loader.list_scenarios`: includes both built-in + custom (1 test).
- `POST /api/scenarios/custom`: happy path, empty name 422, collision id (2-3 tests).
- `DELETE /api/scenarios/custom/{id}`: success 204, missing 404 (2 tests).
- `GET /api/scenarios`: includes `is_custom` flag (1 test).
- `SRSEngine.create_cards`: dedupes vs existing storage (1 test), caps at 5 (1 test), prioritises grammar (1 test), empty result if all dupes (1 test).
- `grade_card_service`: with `practice_only=True` flag does not call `record_review` (1 test).
- `POST /api/review/{card_id}/grade?practice_only=true`: SRS state unchanged after (1 test).

### Frontend
- `NewScenarioPage`: renders 4 form fields, submits to `api.createCustomScenario`, navigates to / (2-3 tests).
- `ScenariosPage`: shows × button only for `is_custom`, calls `api.deleteCustomScenario`, refetches (2 tests).
- `PracticePage`: result screen has "Try again" button; clicking resets `lastResult` without advancing index (1 test).

### Manual smoke
- Create a custom scenario "Talk to a cab driver" via UI → it shows up in list with `custom` badge → click → session starts with that prompt → bot replies in role.
- Delete the same scenario → disappears from list.
- Run a session and intentionally repeat the same grammatical mistake in two turns: only one card lands in /practice next day.
- Run a session with 7 distinct mistakes: max 5 cards land (top-5 by grammar-first sort).
- Backfill old `cards.json`: `"okay, show me it."` reduces from 3 to 1.
- In /practice, after grading a card and seeing the result, click "Try again" → record a different version → see new result with a new score. SRS due_date doesn't change on the second attempt.

## 10. Decisions

| Decision | Choice | Why |
|---|---|---|
| Custom scenarios storage | Single JSON file `custom_scenarios.json` (gitignored) | Simpler than DB or per-file YAML; matches `cards.json` style. |
| Edit custom scenarios | No (delete + recreate) | YAGNI for MVP. |
| Built-in deletable via API | No | Built-ins are app content, not user data. |
| Custom prompt templating | Optional `{{ user_native_language }}` Jinja support | Backward compat with existing `build_system_prompt`. Power users can use it; most won't. |
| Dedupe key for SRS | Lowercased+stripped `user_utterance` | Matches Stage 2e per-session dedupe; consistent UX. |
| Per-session card limit | 5 | Spec wording. 5 is a reasonable daily review slug. |
| Grammar > vocab priority | Yes | Grammar tends to be more impactful per the curriculum. |
| Try-again SRS effect | None (new `practice_only=true` flag) | Honours the explicit "просто тренировка" decision. |
| Backfill existing cards.json | One-shot Bash, not a CLI command | Single-user app; pragmatic. |

## 11. Migration / Backward Compatibility

- Existing YAML scenarios untouched. `custom_scenarios.json` initially absent → empty.
- `ScenarioSummary.is_custom` defaults to `False` so existing frontend code that ignores the field continues to work.
- Existing `cards.json` backfilled in one shot (3 duplicate "okay, show me it." → 1).
- Old `grade` endpoint behavior unchanged when `practice_only` is absent (defaults to false).
- CLI orchestrator unaware of custom scenarios — works with built-ins only. Not a regression; CLI is the legacy path.

## 12. Success Criteria

- 4 new built-in scenarios visible in `/`.
- User creates "Talk to a barber" custom scenario → it appears immediately → session works → tutor stays in barber role.
- User deletes a custom scenario → it disappears.
- After 3 sessions repeating the same English mistake, only 1 SRS card exists for that mistake.
- A 10-correction session produces no more than 5 new cards.
- Existing 25-card store cleaned up (after backfill): no duplicate `user_utterance`.
- In /practice, "Try again" resets the result and lets a re-record without bumping SRS scheduling.
- All current tests + new tests green. CLI flow unaffected.
