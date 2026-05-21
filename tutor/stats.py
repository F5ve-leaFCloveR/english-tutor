"""Aggregate sessions + cards into a StatsSummary for `tutor stats`."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Callable

from tutor.srs_engine import SRSEngine
from tutor.storage import SessionStorage


_RETENTION_MIN_REPS = 3
_RETENTION_PASS_QUALITY = 3
_RETENTION_MIN_SAMPLE = 5
_MATURE_INTERVAL_DAYS = 7


@dataclass
class StatsSummary:
    today: str
    streak_days: int
    last_activity: str | None
    sessions_total: int
    sessions_last_7d: int
    sessions_last_30d: int
    sessions_by_scenario: dict[str, int] = field(default_factory=dict)
    cards_total: int = 0
    cards_by_tag: dict[str, int] = field(default_factory=dict)
    cards_by_state: dict[str, int] = field(default_factory=dict)
    retention_rate: float | None = None
    retention_sample_size: int = 0


class StatsCalculator:
    def __init__(
        self,
        storage: SessionStorage,
        srs: SRSEngine,
        now: Callable[[], date] = date.today,
    ) -> None:
        self._storage = storage
        self._srs = srs
        self._now = now

    def compute(self, days: int | None = None) -> StatsSummary:
        today = self._now()
        all_sessions = self._storage.list_sessions()
        sessions_in_window = _filter_sessions(all_sessions, today, days)

        # Streak uses ALL sessions, not the windowed slice
        session_date_set = {s.get("started_at", "")[:10] for s in all_sessions if s.get("started_at")}
        streak = _compute_streak(session_date_set, today)
        last_activity = max(session_date_set) if session_date_set else None

        last_7d = _filter_sessions(all_sessions, today, 7)
        last_30d = _filter_sessions(all_sessions, today, 30)

        by_scenario = Counter(s.get("scenario_id", "?") for s in sessions_in_window)

        # Cards are NOT filtered by the days window
        cards = self._srs.all_cards()
        by_tag = Counter(c.tag for c in cards)
        by_state = Counter(_card_state(c) for c in cards)

        # Retention
        pool = [c for c in cards if c.repetitions >= _RETENTION_MIN_REPS]
        if len(pool) >= _RETENTION_MIN_SAMPLE:
            passing = sum(1 for c in pool if (c.last_review_quality or 0) >= _RETENTION_PASS_QUALITY)
            retention = passing / len(pool)
        else:
            retention = None

        return StatsSummary(
            today=today.isoformat(),
            streak_days=streak,
            last_activity=last_activity,
            sessions_total=len(sessions_in_window),
            sessions_last_7d=len(last_7d),
            sessions_last_30d=len(last_30d),
            sessions_by_scenario=dict(by_scenario),
            cards_total=len(cards),
            cards_by_tag=dict(by_tag),
            cards_by_state=dict(by_state),
            retention_rate=retention,
            retention_sample_size=len(pool),
        )


def _filter_sessions(sessions: list[dict], today: date, days: int | None) -> list[dict]:
    if days is None:
        return list(sessions)
    cutoff = today - timedelta(days=days - 1)  # inclusive: last N days incl. today
    cutoff_iso = cutoff.isoformat()
    return [s for s in sessions if s.get("started_at", "")[:10] >= cutoff_iso]


def _compute_streak(session_dates: set[str], today: date) -> int:
    cursor = today
    if cursor.isoformat() not in session_dates:
        cursor = today - timedelta(days=1)
        if cursor.isoformat() not in session_dates:
            return 0
    n = 0
    while cursor.isoformat() in session_dates:
        n += 1
        cursor -= timedelta(days=1)
    return n


def _card_state(card) -> str:
    if card.repetitions == 0:
        return "new"
    if card.interval_days <= _MATURE_INTERVAL_DAYS:
        return "learning"
    return "mature"


def format_summary(s: StatsSummary, days: int | None = None) -> str:
    """Render StatsSummary as scannable plain text for CLI output."""
    header = "=== English Tutor Stats ==="
    if days is not None:
        header = f"=== English Tutor Stats (last {days} days) ==="

    if s.sessions_total == 0 and s.cards_total == 0 and days is None:
        return header + "\n\nNo sessions yet. Run `tutor interview` to get started.\n"

    lines = [header, ""]

    if s.last_activity:
        lines.append(f"Streak: {s.streak_days} days  (last activity: {s.last_activity})")
    else:
        lines.append(f"Streak: {s.streak_days} days")
    lines.append("")

    lines.append("Sessions")
    lines.append(f"  Total:        {s.sessions_total}")
    lines.append(f"  Last 7 days:  {s.sessions_last_7d}")
    lines.append(f"  Last 30 days: {s.sessions_last_30d}")
    if s.sessions_by_scenario:
        lines.append("  By scenario:")
        width = max(len(k) for k in s.sessions_by_scenario)
        for sid, count in sorted(s.sessions_by_scenario.items(), key=lambda kv: -kv[1]):
            lines.append(f"    {sid.ljust(width)}: {count}")
    lines.append("")

    lines.append("Cards")
    lines.append(f"  Total:    {s.cards_total}")
    if s.cards_by_tag:
        tag_str = " | ".join(f"{tag} {count}" for tag, count in sorted(s.cards_by_tag.items()))
        lines.append(f"  By tag:   {tag_str}")
    if s.cards_by_state:
        state_order = ["new", "learning", "mature"]
        state_str = " | ".join(
            f"{state} {s.cards_by_state.get(state, 0)}" for state in state_order
        )
        lines.append(f"  By state: {state_str}")
    lines.append("")

    if s.retention_rate is not None:
        passing = round(s.retention_rate * s.retention_sample_size)
        pct = round(s.retention_rate * 100)
        lines.append(f"Retention: {pct}% ({passing} of {s.retention_sample_size} mature cards passing)")
    else:
        if s.retention_sample_size == 0:
            lines.append("Retention: N/A (no cards reviewed yet)")
        else:
            lines.append(
                f"Retention: N/A (insufficient data — {s.retention_sample_size} cards with "
                f"≥3 reviews, need ≥{_RETENTION_MIN_SAMPLE})"
            )

    return "\n".join(lines) + "\n"
