"""Orchestration layer for the web API. Reuses existing modules."""
from __future__ import annotations

import logging
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from tutor.evaluator import Evaluator
from tutor.grader import LLMGrader
from tutor.scenarios.loader import (
    Scenario,
    ScenarioNotFoundError,
    build_system_prompt,
    list_scenarios,
    load_scenario,
)
from tutor.stats import StatsCalculator, StatsSummary
from tutor.web.deps import Dependencies
from tutor.web.errors import NoSpeechDetectedError, SessionNotFoundError
from tutor.web.schemas import (
    BudgetSummary,
    DueCardsResult,
    EndSessionResult,
    GradeResult,
    ScenarioSummary,
    StartSessionResult,
    TurnResult,
)

log = logging.getLogger(__name__)


def list_scenarios_service(deps: Dependencies) -> list[ScenarioSummary]:
    summaries: list[ScenarioSummary] = []
    for sid in list_scenarios():
        sc = load_scenario(sid)
        summaries.append(ScenarioSummary(id=sc.id, name=sc.name, difficulty=sc.difficulty))
    return summaries


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

        # 3. Build messages
        scenario = load_scenario(session_data["scenario_id"])
        system_prompt = build_system_prompt(scenario, user_native_language="Russian")
        messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if session_data.get("opening_text"):
            messages.append({"role": "assistant", "content": session_data["opening_text"]})
        for turn in session_data.get("turns", []):
            messages.append({"role": "user", "content": turn["user_text"]})
            messages.append({"role": "assistant", "content": turn["llm_text"]})
        messages.append({"role": "user", "content": user_text})

        # 4. LLM call
        assistant_text = deps.llm.complete(messages=messages)

        # 5. Persist
        deps.storage.append_turn(session_id, user_text=user_text, llm_text=assistant_text)
        return TurnResult(user_text=user_text, assistant_text=assistant_text)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def end_session_service(deps: Dependencies, session_id: str) -> EndSessionResult:
    try:
        session_data = deps.storage.load_session(session_id)
    except FileNotFoundError as e:
        raise SessionNotFoundError(session_id) from e

    turns = session_data.get("turns", [])
    growth_points_dicts: list[dict] = []
    cards_created_ids: list[str] = []
    growth_points_error: str | None = None

    if turns:
        scenario = load_scenario(session_data["scenario_id"])
        system_prompt = build_system_prompt(scenario, user_native_language="Russian")
        history: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
        if session_data.get("opening_text"):
            history.append({"role": "assistant", "content": session_data["opening_text"]})
        for turn in turns:
            history.append({"role": "user", "content": turn["user_text"]})
            history.append({"role": "assistant", "content": turn["llm_text"]})

        try:
            evaluator = Evaluator(llm=deps.llm, model=deps.evaluator_model)
            growth_points = evaluator.evaluate(transcript=history)
        except Exception as e:
            log.warning("Evaluator raised: %s", e)
            growth_points = []
            growth_points_error = f"evaluator failed: {e}"
            deps.storage.set_growth_points_error(session_id, growth_points_error)

        if growth_points:
            growth_points_dicts = [
                gp.model_dump() if hasattr(gp, "model_dump") else asdict(gp)
                for gp in growth_points
            ]
            deps.storage.set_growth_points(session_id, growth_points_dicts)
            try:
                cards = deps.srs.create_cards(growth_points, session_id=session_id)
                cards_created_ids = [c.id for c in cards]
                deps.storage.set_cards_created(session_id, cards_created_ids)
            except Exception as e:
                log.warning("SRS create_cards failed: %s", e)
                growth_points_error = f"create_cards failed: {e}"
                deps.storage.set_growth_points_error(session_id, growth_points_error)

    deps.storage.end_session(session_id)
    final = deps.storage.load_session(session_id)

    return EndSessionResult(
        session_id=session_id,
        ended_at=final.get("ended_at"),
        growth_points=growth_points_dicts,
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
