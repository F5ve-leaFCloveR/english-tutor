"""Dependency container for the web layer. Holds preloaded singletons."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI

from tutor.asr import WhisperASR
from tutor.budget import BudgetTracker
from tutor.llm import LLMClient
from tutor.settings import get_settings
from tutor.srs_engine import SRSEngine
from tutor.storage import SessionStorage


@dataclass
class Dependencies:
    budget: BudgetTracker
    llm: LLMClient
    asr: WhisperASR
    storage: SessionStorage
    srs: SRSEngine
    evaluator_model: str
    grader_model: str
    tts_model: str
    tts_voice: str
    chat_model: str = ""
    custom_scenarios_path: str = "custom_scenarios.json"


def build_dependencies(project_root: Path) -> Dependencies:
    settings = get_settings()
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
    asr = WhisperASR(model_size=settings.whisper_model_size)
    storage = SessionStorage(root=project_root / "sessions")
    srs = SRSEngine(path=project_root / "cards.json")
    return Dependencies(
        budget=budget,
        llm=llm,
        asr=asr,
        storage=storage,
        srs=srs,
        evaluator_model=settings.openrouter_evaluator_model,
        grader_model=settings.openrouter_grader_model,
        tts_model=settings.tts_model,
        tts_voice=settings.tts_voice,
        # Free-chat shares the conversational model (settings.openrouter_model).
        # No separate env var: keep things lean until we need a distinct chat model.
        chat_model=settings.openrouter_model,
        custom_scenarios_path=settings.custom_scenarios_path,
    )
