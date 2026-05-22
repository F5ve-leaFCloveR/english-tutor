"""Pydantic request/response models for the web API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ScenarioSummary(BaseModel):
    id: str
    name: str
    difficulty: str


class StartSessionRequest(BaseModel):
    scenario_id: str


class StartSessionResult(BaseModel):
    session_id: str
    opening_text: str


class TurnResult(BaseModel):
    user_text: str
    assistant_text: str
    corrections: list[dict] = Field(default_factory=list)


class EndSessionResult(BaseModel):
    session_id: str
    ended_at: str | None
    growth_points: list[dict] = Field(default_factory=list)
    cards_created: list[str] = Field(default_factory=list)
    growth_points_error: str | None = None


class GradeRequestSkip(BaseModel):
    skip: Literal[True]


class GradeResult(BaseModel):
    card_id: str
    user_attempt_text: str
    quality: int
    target: str
    explanation: str
    next_due: str


class DueCardsResult(BaseModel):
    cards: list[dict]
    total_due: int


class BudgetSummary(BaseModel):
    usd_today: float
    tokens_today: int
    daily_usd_cap: float
    daily_token_cap: int


class ErrorResponse(BaseModel):
    error: str
    message: str | None = None


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    voice: str | None = None


class EndSessionAccepted(BaseModel):
    session_id: str
    status: Literal["processing"] = "processing"


class SessionListResult(BaseModel):
    sessions: list[dict]


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    history: list[ChatMessage] = []
    message: str


class ChatCorrectionDict(BaseModel):
    tag: Literal["vocab", "grammar"]
    user_utterance: str
    corrected_version: str
    explanation: str


class ChatResponseDict(BaseModel):
    reply: str
    corrections: list[ChatCorrectionDict]
