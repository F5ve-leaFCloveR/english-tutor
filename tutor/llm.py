"""OpenRouter LLM client with retry and budget enforcement."""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

import openai
from openai import OpenAI

from tutor.budget import BudgetTracker

if TYPE_CHECKING:
    from tutor.settings import Settings

log = logging.getLogger(__name__)

_RETRYABLE = (
    openai.APITimeoutError,
    openai.APIConnectionError,
    openai.InternalServerError,
    openai.RateLimitError,
)


class LLMClient:
    def __init__(
        self,
        client: OpenAI,
        model: str,
        budget: BudgetTracker,
        max_retries: int = 2,
        base_delay: float = 1.0,
    ) -> None:
        self._client = client
        self._model = model
        self._budget = budget
        self._max_retries = max_retries
        self._base_delay = base_delay

    @classmethod
    def from_settings(cls, settings: "Settings", budget: BudgetTracker) -> "LLMClient":
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openrouter_api_key.get_secret_value(),
        )
        return cls(client=client, model=settings.openrouter_model, budget=budget)

    def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        model_override: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        self._budget.check_can_spend()

        model = model_override or self._model
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                kwargs: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                }
                if max_tokens is not None:
                    kwargs["max_tokens"] = max_tokens
                response = self._client.chat.completions.create(**kwargs)
                self._record_usage(response)
                return response.choices[0].message.content or ""
            except _RETRYABLE as e:
                last_error = e
                if attempt >= self._max_retries:
                    break
                delay = self._base_delay * (2 ** attempt)
                log.warning("LLM call failed (%s); retrying in %.1fs", type(e).__name__, delay)
                time.sleep(delay)

        assert last_error is not None
        raise last_error

    def _record_usage(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        tokens_in = getattr(usage, "prompt_tokens", 0) or 0
        tokens_out = getattr(usage, "completion_tokens", 0) or 0
        cost = 0.0
        extra = getattr(usage, "model_extra", None) or {}
        if "cost" in extra:
            try:
                cost = float(extra["cost"])
            except (TypeError, ValueError):
                cost = 0.0
        self._budget.record(tokens_in=tokens_in, tokens_out=tokens_out, usd_cost=cost)
