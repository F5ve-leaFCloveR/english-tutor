"""Web-layer exception classes and FastAPI handlers."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from tutor.budget import BudgetExceededError
from tutor.scenarios.loader import ScenarioNotFoundError
from tutor.srs_engine import CardNotFoundError


class NoSpeechDetectedError(Exception):
    """Raised when ASR produces an empty transcript."""


class SessionNotFoundError(Exception):
    def __init__(self, session_id: str) -> None:
        super().__init__(f"session not found: {session_id}")
        self.session_id = session_id


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ScenarioNotFoundError)
    async def _scenario_not_found(request: Request, exc: ScenarioNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"error": "scenario_not_found", "message": str(exc)},
        )

    @app.exception_handler(SessionNotFoundError)
    async def _session_not_found(request: Request, exc: SessionNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"error": "session_not_found", "session_id": exc.session_id},
        )

    @app.exception_handler(CardNotFoundError)
    async def _card_not_found(request: Request, exc: CardNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"error": "card_not_found", "message": str(exc)},
        )

    @app.exception_handler(NoSpeechDetectedError)
    async def _no_speech(request: Request, exc: NoSpeechDetectedError):
        return JSONResponse(
            status_code=422,
            content={"error": "no_speech_detected", "message": str(exc)},
        )

    @app.exception_handler(BudgetExceededError)
    async def _budget(request: Request, exc: BudgetExceededError):
        return JSONResponse(
            status_code=429,
            content={"error": "budget_exhausted", "message": str(exc)},
        )
