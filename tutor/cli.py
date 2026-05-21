"""CLI entry point. Wires real adapters and runs a session."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from openai import OpenAI

from tutor.asr import WhisperASR
from tutor.audio import AudioRecorder
from tutor.budget import BudgetTracker
from tutor.llm import LLMClient
from tutor.scenarios.loader import load_scenario, list_scenarios
from tutor.session import SessionOrchestrator
from tutor.settings import get_settings
from tutor.storage import SessionStorage
from tutor.tts import MacSayTTS


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tutor", description="English speaking practice CLI")
    sub = p.add_subparsers(dest="command", required=True)

    sub_interview = sub.add_parser("interview", help="Run a tech interview behavioral session")
    sub_interview.add_argument("--scenario", default="tech_interview_behavioral",
                                help="Scenario id (default: tech_interview_behavioral)")

    sub.add_parser("list-scenarios", help="List available scenarios")

    return p


def _run_interview(scenario_id: str) -> int:
    settings = get_settings()
    project_root = Path(__file__).resolve().parents[1]

    budget = BudgetTracker(
        path=project_root / "budget.json",
        daily_usd_cap=settings.daily_usd_budget,
        daily_token_cap=settings.daily_token_budget,
    )

    client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=settings.openrouter_api_key)
    llm = LLMClient(client=client, model=settings.openrouter_model, budget=budget)
    asr = WhisperASR(model_size=settings.whisper_model_size)
    tts = MacSayTTS(voice=settings.tts_voice, rate=settings.tts_rate)
    recorder = AudioRecorder()
    storage = SessionStorage(root=project_root / "sessions")
    scenario = load_scenario(scenario_id)

    print(f"\n=== {scenario.name} ===")
    print(f"Budget today: ${budget.usd_today:.4f} / ${settings.daily_usd_budget}")
    print(f"Press Enter to start each turn. Type 'end' to finish the session.\n")

    orch = SessionOrchestrator(
        llm=llm, asr=asr, tts=tts, recorder=recorder, storage=storage,
        scenario=scenario,
        per_session_turn_limit=settings.per_session_turn_limit,
    )
    session_id = orch.run()
    print(f"\nSession {session_id} saved. Budget after: ${budget.usd_today:.4f}")
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
    return 1


if __name__ == "__main__":
    sys.exit(main())
