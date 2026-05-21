"""FastAPI app + routes. Thin layer over services.py."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from tutor.web import services
from tutor.web.deps import Dependencies, build_dependencies
from tutor.web.errors import register_exception_handlers
from tutor.web.schemas import (
    BudgetSummary,
    DueCardsResult,
    EndSessionResult,
    GradeResult,
    StartSessionRequest,
    StartSessionResult,
    TurnResult,
)

log = logging.getLogger(__name__)


def _default_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def create_app(deps: Dependencies | None = None) -> FastAPI:
    if deps is None:
        # Real run: build dependencies from project root + preload Whisper
        deps = build_dependencies(project_root=_default_project_root())
        log.info("Preloading Whisper model: %s", deps.asr._model_size)
        deps.asr._ensure_model()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(title="English Tutor API", lifespan=lifespan)
    register_exception_handlers(app)

    def get_deps() -> Dependencies:
        return deps

    @app.get("/api/scenarios")
    async def list_scenarios(d: Dependencies = Depends(get_deps)):
        result = services.list_scenarios_service(d)
        return {"scenarios": [s.model_dump() for s in result]}

    @app.post("/api/sessions", response_model=StartSessionResult)
    async def start_session(req: StartSessionRequest, d: Dependencies = Depends(get_deps)):
        return services.start_session_service(d, scenario_id=req.scenario_id)

    @app.get("/api/sessions/{session_id}")
    async def get_session(session_id: str, d: Dependencies = Depends(get_deps)):
        return services.get_session_service(d, session_id)

    @app.post("/api/sessions/{session_id}/turn", response_model=TurnResult)
    async def submit_turn(
        session_id: str,
        audio: UploadFile = File(...),
        d: Dependencies = Depends(get_deps),
    ):
        audio_bytes = await audio.read()
        return services.turn_service(d, session_id=session_id, audio_bytes=audio_bytes)

    @app.post("/api/sessions/{session_id}/end", response_model=EndSessionResult)
    async def end_session(session_id: str, d: Dependencies = Depends(get_deps)):
        return services.end_session_service(d, session_id=session_id)

    @app.get("/api/review/due", response_model=DueCardsResult)
    async def review_due(
        limit: int | None = None,
        tag: str | None = None,
        d: Dependencies = Depends(get_deps),
    ):
        return services.review_due_service(d, limit=limit, tag=tag)

    @app.post("/api/review/{card_id}/grade", response_model=GradeResult)
    async def grade_card(
        card_id: str,
        audio: UploadFile | None = File(None),
        skip: bool = False,
        d: Dependencies = Depends(get_deps),
    ):
        audio_bytes = await audio.read() if audio is not None else None
        return services.grade_card_service(
            d, card_id=card_id, audio_bytes=audio_bytes, skip=skip
        )

    @app.get("/api/stats")
    async def stats(days: int | None = None, d: Dependencies = Depends(get_deps)):
        s = services.stats_service(d, days=days)
        return asdict(s)

    @app.get("/api/budget", response_model=BudgetSummary)
    async def budget(d: Dependencies = Depends(get_deps)):
        return services.budget_service(d)

    return app
