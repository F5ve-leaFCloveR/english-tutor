"""Storage + scheduling layer on top of the pure SM-2 algorithm."""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Literal

from tutor.evaluator import GrowthPoint
from tutor.srs import next_interval


class CardNotFoundError(Exception):
    pass


@dataclass
class Card:
    id: str
    created_from_session_id: str
    tag: Literal["vocab", "grammar"]
    user_utterance: str
    corrected_version: str
    explanation: str
    context: str | None
    due_date: str
    ease_factor: float = 2.5
    interval_days: int = 0
    repetitions: int = 0
    last_review_quality: int | None = None
    review_history: list[dict] = field(default_factory=list)


class SRSEngine:
    def __init__(self, path: Path, now: Callable[[], date] = date.today) -> None:
        self._path = Path(path)
        self._now = now
        self._cards: dict[str, Card] = self._load()

    def _load(self) -> dict[str, Card]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            backup = self._path.with_suffix(f".broken-{int(time.time())}")
            try:
                self._path.rename(backup)
            except OSError:
                pass
            raise RuntimeError(
                f"cards.json is corrupt. Backed up to {backup}. "
                f"Inspect or delete to start fresh. Error: {e}"
            )
        cards: dict[str, Card] = {}
        for c in raw.get("cards", []):
            card = Card(**c)
            cards[card.id] = card
        return cards

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        payload = {"cards": [asdict(c) for c in self._cards.values()]}
        try:
            tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
            os.replace(str(tmp), str(self._path))
        except Exception:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def create_cards(self, growth_points: list[GrowthPoint], session_id: str) -> list[Card]:
        today = self._now()
        tomorrow = (today + timedelta(days=1)).isoformat()
        new_cards: list[Card] = []
        for gp in growth_points:
            card = Card(
                id=uuid.uuid4().hex[:12],
                created_from_session_id=session_id,
                tag=gp.tag,
                user_utterance=gp.user_utterance,
                corrected_version=gp.corrected_version,
                explanation=gp.explanation,
                context=gp.context,
                due_date=tomorrow,
            )
            self._cards[card.id] = card
            new_cards.append(card)
        self._flush()
        return new_cards

    def due_today(self, limit: int | None = None, tag: str | None = None) -> list[Card]:
        today_iso = self._now().isoformat()
        result = [c for c in self._cards.values() if c.due_date <= today_iso]
        if tag is not None:
            result = [c for c in result if c.tag == tag]
        result.sort(key=lambda c: c.due_date)
        if limit is not None:
            result = result[:limit]
        return result

    def record_review(self, card_id: str, quality: int) -> None:
        card = self._cards.get(card_id)
        if card is None:
            raise CardNotFoundError(f"No card with id {card_id}")
        new_interval, new_repetitions, new_ef = next_interval(
            quality=quality,
            prev_interval=card.interval_days,
            repetitions=card.repetitions,
            ease_factor=card.ease_factor,
        )
        today = self._now()
        new_due = (today + timedelta(days=new_interval)).isoformat()
        card.interval_days = new_interval
        card.repetitions = new_repetitions
        card.ease_factor = new_ef
        card.due_date = new_due
        card.last_review_quality = quality
        card.review_history.append({"date": today.isoformat(), "quality": quality})
        self._flush()

    def load_card(self, card_id: str) -> Card:
        card = self._cards.get(card_id)
        if card is None:
            raise CardNotFoundError(f"No card with id {card_id}")
        return card

    def all_cards(self) -> list[Card]:
        """Return a snapshot of all cards. Read-only; mutations don't propagate
        back unless callers use record_review/create_cards."""
        return list(self._cards.values())
