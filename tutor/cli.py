"""CLI entry point. Wires real adapters and runs a session or review."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from openai import OpenAI

from tutor.asr import WhisperASR
from tutor.audio import AudioRecorder
from tutor.budget import BudgetTracker
from tutor.evaluator import Evaluator
from tutor.grader import LLMGrader
from tutor.llm import LLMClient
from tutor.review import ReviewOrchestrator
from tutor.scenarios.loader import ScenarioNotFoundError, list_scenarios, load_scenario
from tutor.session import SessionOrchestrator
from tutor.settings import get_settings
from tutor.srs_engine import SRSEngine
from tutor.stats import StatsCalculator, format_summary
from tutor.storage import SessionStorage
from tutor.tts import MacSayTTS


def _positive_int(value: str) -> int:
    iv = int(value)
    if iv < 1:
        raise argparse.ArgumentTypeError("--days must be >= 1")
    return iv


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tutor", description="English speaking practice CLI")
    sub = p.add_subparsers(dest="command", required=True)

    sub_interview = sub.add_parser("interview", help="Run a behavioral session")
    sub_interview.add_argument("--scenario", default="tech_interview_behavioral",
                                help="Scenario id (default: tech_interview_behavioral)")

    sub.add_parser("list-scenarios", help="List available scenarios")

    sub_review = sub.add_parser("review", help="Review due SRS cards")
    sub_review.add_argument("--limit", type=int, default=None, help="Max cards to review")
    sub_review.add_argument("--tag", choices=["vocab", "grammar"], default=None,
                             help="Filter cards by tag")

    sub_stats = sub.add_parser("stats", help="Show progress stats")
    sub_stats.add_argument(
        "--days",
        type=_positive_int,
        default=None,
        help="Window for session counts (sessions only, not cards). Must be >= 1.",
    )

    return p


def _build_common_clients(settings):
    project_root = _project_root()
    budget = BudgetTracker(
        path=project_root / "budget.json",
        daily_usd_cap=settings.daily_usd_budget,
        daily_token_cap=settings.daily_token_budget,
    )
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=settings.openrouter_api_key.get_secret_value(),
    )
    llm = LLMClient(client=client, model=settings.openrouter_model, budget=budget)
    return budget, llm


def _run_interview(scenario_id: str) -> int:
    try:
        scenario = load_scenario(scenario_id)
    except ScenarioNotFoundError:
        available = ", ".join(list_scenarios())
        print(f"error: scenario '{scenario_id}' not found. Available: {available}", file=sys.stderr)
        return 2

    settings = get_settings()
    project_root = _project_root()
    budget, llm = _build_common_clients(settings)

    asr = WhisperASR(model_size=settings.whisper_model_size)
    tts = MacSayTTS(voice=settings.macos_say_voice, rate=settings.tts_rate)
    recorder = AudioRecorder()
    storage = SessionStorage(root=project_root / "sessions")

    evaluator = Evaluator(llm=llm, model=settings.openrouter_evaluator_model)
    srs_engine = SRSEngine(path=project_root / "cards.json")

    print(f"\n=== {scenario.name} ===")
    print(f"Budget today: ${budget.usd_today:.4f} / ${settings.daily_usd_budget}")
    print(f"Press Enter to start each turn. Type 'end' to finish.\n")

    orch = SessionOrchestrator(
        llm=llm, asr=asr, tts=tts, recorder=recorder, storage=storage,
        scenario=scenario,
        per_session_turn_limit=settings.per_session_turn_limit,
        evaluator=evaluator,
        srs_engine=srs_engine,
    )
    session_id = orch.run()
    print(f"\nSession {session_id} saved. Budget after: ${budget.usd_today:.4f}")
    return 0


def _run_review(limit: int | None, tag: str | None) -> int:
    settings = get_settings()
    project_root = _project_root()
    budget, llm = _build_common_clients(settings)

    asr = WhisperASR(model_size=settings.whisper_model_size)
    tts = MacSayTTS(voice=settings.macos_say_voice, rate=settings.tts_rate)
    recorder = AudioRecorder()
    grader = LLMGrader(llm=llm, model=settings.openrouter_grader_model)
    srs = SRSEngine(path=project_root / "cards.json")

    print(f"Budget today: ${budget.usd_today:.4f} / ${settings.daily_usd_budget}")

    orch = ReviewOrchestrator(grader=grader, asr=asr, tts=tts, recorder=recorder, srs=srs)
    summary = orch.run(limit=limit, tag_filter=tag)
    print(f"Budget after: ${budget.usd_today:.4f}")
    print(f"Cards reviewed: {summary.cards_reviewed}; distribution: {summary.quality_distribution}")
    return 0


def _run_stats(days: int | None) -> int:
    project_root = _project_root()
    storage = SessionStorage(root=project_root / "sessions")
    srs = SRSEngine(path=project_root / "cards.json")
    calc = StatsCalculator(storage=storage, srs=srs)
    summary = calc.compute(days=days)
    print(format_summary(summary, days=days))
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "interview":
        return _run_interview(args.scenario)
    if args.command == "list-scenarios":
        for sid in list_scenarios():
            print(sid)
        return 0
    if args.command == "review":
        return _run_review(args.limit, args.tag)
    if args.command == "stats":
        return _run_stats(args.days)
    return 1


if __name__ == "__main__":
    sys.exit(main())
