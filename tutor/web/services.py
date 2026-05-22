"""Orchestration layer for the web API. Reuses existing modules."""
from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from tutor.conversation import ChatTurn, build_session_chat_prompt
from tutor.evaluator import Evaluator, GrowthPoint
from tutor.grader import LLMGrader
from tutor.scenarios.loader import (
    Scenario,
    ScenarioNotFoundError,
    build_system_prompt,
    load_scenario,
)
from tutor.stats import StatsCalculator, StatsSummary
from tutor.web.deps import Dependencies
from tutor.web.errors import NoSpeechDetectedError, SessionNotFoundError
from tutor.web.schemas import (
    BudgetSummary,
    CustomScenarioCreate,
    DueCardsResult,
    EndSessionResult,
    GradeResult,
    ScenarioSummary,
    StartSessionResult,
    TurnResult,
)

log = logging.getLogger(__name__)


def list_scenarios_service(deps: Dependencies) -> list[ScenarioSummary]:
    """Built-in YAML scenarios + custom JSON scenarios; mark each with is_custom."""
    from tutor.scenarios.custom_storage import CustomScenarioStorage
    from tutor.scenarios.loader import SCENARIOS_DIR

    storage = CustomScenarioStorage(path=Path(deps.custom_scenarios_path))
    custom_scenarios = storage.list_all()
    builtin_ids = sorted({p.stem for p in SCENARIOS_DIR.glob("*.yaml")})

    summaries: list[ScenarioSummary] = []
    # Built-in (always first, sorted)
    for sid in builtin_ids:
        sc = load_scenario(sid)
        summaries.append(ScenarioSummary(
            id=sc.id, name=sc.name, difficulty=sc.difficulty, is_custom=False,
        ))
    # Custom (only those NOT shadowed by built-in id)
    for c in custom_scenarios:
        if c["id"] in builtin_ids:
            continue
        summaries.append(ScenarioSummary(
            id=c["id"], name=c["name"], difficulty=c["difficulty"], is_custom=True,
        ))
    return summaries


def create_custom_scenario_service(
    deps: Dependencies, payload: CustomScenarioCreate
) -> ScenarioSummary:
    from tutor.scenarios.custom_storage import CustomScenarioStorage

    storage = CustomScenarioStorage(path=Path(deps.custom_scenarios_path))
    created = storage.create(
        name=payload.name.strip(),
        difficulty=payload.difficulty,
        system_prompt=payload.system_prompt.strip(),
        opening_line=(payload.opening_line or "").strip(),
    )
    return ScenarioSummary(
        id=created["id"],
        name=created["name"],
        difficulty=created["difficulty"],
        is_custom=True,
    )


def delete_custom_scenario_service(deps: Dependencies, scenario_id: str) -> None:
    from tutor.scenarios.custom_storage import CustomScenarioStorage

    storage = CustomScenarioStorage(path=Path(deps.custom_scenarios_path))
    storage.delete(scenario_id)  # raises ScenarioNotFoundError → 404


def start_session_service(deps: Dependencies, scenario_id: str) -> StartSessionResult:
    scenario = load_scenario(scenario_id)  # raises ScenarioNotFoundError
    session_id = deps.storage.create_session(scenario_id=scenario.id)

    system_prompt = build_system_prompt(scenario, user_native_language="Russian")
    opening = deps.llm.complete(
        messages=[{"role": "system", "content": system_prompt}],
    )
    deps.storage.set_opening_text(session_id, opening)
    return StartSessionResult(session_id=session_id, opening_text=opening)


def get_session_service(deps: Dependencies, session_id: str) -> dict:
    try:
        return deps.storage.load_session(session_id)
    except FileNotFoundError as e:
        raise SessionNotFoundError(session_id) from e


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

    # Set ended_at FIRST so the session immediately appears in /review.
    deps.storage.end_session(session_id)

    turns = session_data.get("turns", [])
    aggregated = _aggregate_corrections(turns)

    deps.storage.set_growth_points(session_id, aggregated)

    cards_created_ids: list[str] = []
    growth_points_error: str | None = None
    if aggregated:
        try:
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


def review_due_service(
    deps: Dependencies, limit: int | None, tag: str | None
) -> DueCardsResult:
    cards = deps.srs.due_today(limit=limit, tag=tag)
    return DueCardsResult(
        cards=[asdict(c) for c in cards],
        total_due=len(cards),
    )


def grade_card_service(
    deps: Dependencies, card_id: str, audio_bytes: bytes | None, skip: bool
) -> GradeResult:
    card = deps.srs.load_card(card_id)  # raises CardNotFoundError

    if skip:
        quality = 0
        user_attempt_text = "(skipped)"
    else:
        if audio_bytes is None:
            raise NoSpeechDetectedError("no audio submitted")
        tmp = Path(tempfile.gettempdir()) / f"web_grade_{card_id}_{os.getpid()}.bin"
        tmp.write_bytes(audio_bytes)
        try:
            user_attempt_text = deps.asr.transcribe(tmp).strip()
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
        if not user_attempt_text:
            quality = 0
        else:
            grader = LLMGrader(llm=deps.llm, model=deps.grader_model)
            quality = grader.grade(target=card.corrected_version, attempt=user_attempt_text)

    deps.srs.record_review(card_id, quality=quality)
    updated = deps.srs.load_card(card_id)
    return GradeResult(
        card_id=card_id,
        user_attempt_text=user_attempt_text,
        quality=quality,
        target=card.corrected_version,
        explanation=card.explanation,
        next_due=updated.due_date,
    )


def stats_service(deps: Dependencies, days: int | None) -> StatsSummary:
    calc = StatsCalculator(storage=deps.storage, srs=deps.srs)
    return calc.compute(days=days)


def budget_service(deps: Dependencies) -> BudgetSummary:
    return BudgetSummary(
        usd_today=deps.budget.usd_today,
        tokens_today=deps.budget.tokens_today,
        daily_usd_cap=deps.budget.daily_usd_cap,
        daily_token_cap=deps.budget.daily_token_cap,
    )


def list_sessions_service(deps: Dependencies, limit: int = 10) -> list[dict]:
    """Return up to `limit` ended sessions, latest first."""
    all_sessions = deps.storage.list_sessions()
    ended = [s for s in all_sessions if s.get("ended_at")]
    return ended[:limit]


def chat_service(
    deps: Dependencies,
    history: list[dict[str, str]],
    message: str,
) -> dict:
    """Stateless free-chat turn: returns {reply, corrections} via one LLM call."""
    from tutor.conversation import ChatTurn

    chat = ChatTurn(llm=deps.llm, model=deps.chat_model)
    response = chat.respond(history=history, message=message)
    return response.model_dump()
