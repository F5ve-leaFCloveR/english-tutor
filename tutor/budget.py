"""Daily USD + token budget tracker. Persists across process restarts."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Callable


class BudgetExceededError(Exception):
    """Raised when continuing would exceed the daily budget."""


@dataclass
class _DailyState:
    day: str  # ISO date
    tokens: int
    usd: float


class BudgetTracker:
    def __init__(
        self,
        path: Path,
        daily_usd_cap: float,
        daily_token_cap: int,
        now: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.path = Path(path)
        self.daily_usd_cap = daily_usd_cap
        self.daily_token_cap = daily_token_cap
        self._now = now
        self._state = self._load_or_init()

    def _today_iso(self) -> str:
        return self._now().date().isoformat()

    def _load_or_init(self) -> _DailyState:
        if not self.path.exists():
            return _DailyState(day=self._today_iso(), tokens=0, usd=0.0)
        try:
            data = json.loads(self.path.read_text())
        except (json.JSONDecodeError, OSError):
            return _DailyState(day=self._today_iso(), tokens=0, usd=0.0)
        if data.get("day") != self._today_iso():
            return _DailyState(day=self._today_iso(), tokens=0, usd=0.0)
        return _DailyState(
            day=data["day"],
            tokens=int(data.get("tokens", 0)),
            usd=float(data.get("usd", 0.0)),
        )

    def _flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({
            "day": self._state.day,
            "tokens": self._state.tokens,
            "usd": self._state.usd,
        }))

    @property
    def tokens_today(self) -> int:
        return self._state.tokens

    @property
    def usd_today(self) -> float:
        return self._state.usd

    def record(self, tokens_in: int, tokens_out: int, usd_cost: float) -> None:
        self._state.tokens += tokens_in + tokens_out
        self._state.usd += usd_cost
        self._flush()

    def check_can_spend(self) -> None:
        """Raise BudgetExceededError if either cap has been reached."""
        if self._state.usd >= self.daily_usd_cap:
            raise BudgetExceededError(
                f"Daily USD cap reached ({self._state.usd:.4f} >= {self.daily_usd_cap})"
            )
        if self._state.tokens >= self.daily_token_cap:
            raise BudgetExceededError(
                f"Daily token cap reached ({self._state.tokens} >= {self.daily_token_cap})"
            )
