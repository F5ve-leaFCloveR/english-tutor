from datetime import date, datetime, timedelta
from pathlib import Path
import pytest


def _make_storage_with_sessions(tmp_path, session_dates):
    """Create N sessions on the given ISO date strings.
    Returns a SessionStorage instance ready for reading."""
    from tutor.storage import SessionStorage

    for ds in session_dates:
        y, m, d = (int(x) for x in ds.split("-"))
        storage = SessionStorage(root=tmp_path, now=lambda y=y, m=m, d=d: datetime(y, m, d, 10, 0))
        storage.create_session("tech_interview_behavioral")

    return SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 12, 0))


def _make_srs_with_cards(tmp_path, configs):
    """Create cards according to configs.

    Each config is a tuple (tag, repetitions, interval_days, last_quality).
    Chunks of 5 across distinct session_ids so the per-session cap doesn't apply.
    Mutations are matched to created cards by user_utterance (engine reorders
    grammar-before-vocab internally, so positional zip is unreliable).
    """
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint

    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    if configs:
        gps = [
            GrowthPoint(tag=tag, user_utterance=f"u{i}", corrected_version=f"c{i}",
                        explanation="e", context=None)
            for i, (tag, _, _, _) in enumerate(configs)
        ]
        for chunk_idx in range(0, len(gps), 5):
            chunk = gps[chunk_idx:chunk_idx + 5]
            engine.create_cards(chunk, session_id=f"s{chunk_idx // 5}")
        # Mutate in-memory cards by user_utterance lookup (engine sorts internally).
        by_utt = {c.user_utterance: c for c in engine.all_cards()}
        for i, (_tag, reps, interval, qual) in enumerate(configs):
            card = by_utt[f"u{i}"]
            card.repetitions = reps
            card.interval_days = interval
            card.last_review_quality = qual
        engine._flush()

    # Reopen so we read the persisted state
    return SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))


def test_stats_empty_state(tmp_path):
    from tutor.stats import StatsCalculator
    from tutor.storage import SessionStorage
    from tutor.srs_engine import SRSEngine

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 10, 0))
    srs = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    calc = StatsCalculator(storage=storage, srs=srs, now=lambda: date(2026, 5, 21))

    s = calc.compute()
    assert s.streak_days == 0
    assert s.last_activity is None
    assert s.sessions_total == 0
    assert s.cards_total == 0
    assert s.retention_rate is None
    assert s.retention_sample_size == 0


def test_stats_streak_today_only(tmp_path):
    from tutor.stats import StatsCalculator
    from tutor.srs_engine import SRSEngine

    storage = _make_storage_with_sessions(tmp_path, ["2026-05-21"])
    srs = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    calc = StatsCalculator(storage=storage, srs=srs, now=lambda: date(2026, 5, 21))

    s = calc.compute()
    assert s.streak_days == 1
    assert s.last_activity == "2026-05-21"


def test_stats_streak_today_and_yesterday(tmp_path):
    from tutor.stats import StatsCalculator
    from tutor.srs_engine import SRSEngine

    storage = _make_storage_with_sessions(tmp_path, ["2026-05-20", "2026-05-21"])
    srs = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    calc = StatsCalculator(storage=storage, srs=srs, now=lambda: date(2026, 5, 21))

    assert calc.compute().streak_days == 2


def test_stats_streak_yesterday_only_falls_back(tmp_path):
    from tutor.stats import StatsCalculator
    from tutor.srs_engine import SRSEngine

    # Activity yesterday but not today — streak still counts (from yesterday)
    storage = _make_storage_with_sessions(tmp_path, ["2026-05-20"])
    srs = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    calc = StatsCalculator(storage=storage, srs=srs, now=lambda: date(2026, 5, 21))

    assert calc.compute().streak_days == 1


def test_stats_streak_broken(tmp_path):
    from tutor.stats import StatsCalculator
    from tutor.srs_engine import SRSEngine

    # Last activity was 3 days ago — streak is 0
    storage = _make_storage_with_sessions(tmp_path, ["2026-05-17", "2026-05-18"])
    srs = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    calc = StatsCalculator(storage=storage, srs=srs, now=lambda: date(2026, 5, 21))

    assert calc.compute().streak_days == 0


def test_stats_sessions_by_scenario(tmp_path):
    from tutor.stats import StatsCalculator
    from tutor.storage import SessionStorage
    from tutor.srs_engine import SRSEngine

    for sid, t in [
        ("tech_interview_behavioral", datetime(2026, 5, 21, 9)),
        ("tech_interview_behavioral", datetime(2026, 5, 21, 10)),
        ("daily_standup", datetime(2026, 5, 20, 9)),
    ]:
        storage = SessionStorage(root=tmp_path, now=lambda t=t: t)
        storage.create_session(sid)

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 12))
    srs = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    calc = StatsCalculator(storage=storage, srs=srs, now=lambda: date(2026, 5, 21))

    s = calc.compute()
    assert s.sessions_total == 3
    assert s.sessions_by_scenario == {"tech_interview_behavioral": 2, "daily_standup": 1}


def test_stats_cards_by_state(tmp_path):
    from tutor.stats import StatsCalculator
    from tutor.storage import SessionStorage

    configs = [
        ("vocab", 0, 0, None),     # new
        ("vocab", 1, 1, 3),        # learning (interval 1)
        ("vocab", 3, 6, 4),        # learning (interval 6)
        ("grammar", 4, 15, 4),     # mature (interval > 7)
        ("grammar", 5, 30, 5),     # mature
    ]
    srs = _make_srs_with_cards(tmp_path, configs)
    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 12))
    calc = StatsCalculator(storage=storage, srs=srs, now=lambda: date(2026, 5, 21))

    s = calc.compute()
    assert s.cards_total == 5
    assert s.cards_by_tag == {"vocab": 3, "grammar": 2}
    assert s.cards_by_state == {"new": 1, "learning": 2, "mature": 2}


def test_stats_retention_below_threshold_returns_none(tmp_path):
    from tutor.stats import StatsCalculator
    from tutor.storage import SessionStorage

    # Only 2 cards with repetitions >= 3 — below threshold of 5
    configs = [
        ("vocab", 3, 6, 4),
        ("vocab", 4, 15, 4),
        ("vocab", 0, 0, None),
    ]
    srs = _make_srs_with_cards(tmp_path, configs)
    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 12))
    calc = StatsCalculator(storage=storage, srs=srs, now=lambda: date(2026, 5, 21))

    s = calc.compute()
    assert s.retention_rate is None
    assert s.retention_sample_size == 2


def test_stats_retention_above_threshold(tmp_path):
    from tutor.stats import StatsCalculator
    from tutor.storage import SessionStorage

    # 6 cards with repetitions >= 3, 5 of them passing (quality >= 3)
    configs = [
        ("vocab", 3, 6, 4),
        ("vocab", 3, 6, 5),
        ("vocab", 4, 15, 3),
        ("grammar", 5, 30, 4),
        ("grammar", 3, 6, 4),
        ("grammar", 4, 15, 1),  # failed
    ]
    srs = _make_srs_with_cards(tmp_path, configs)
    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 12))
    calc = StatsCalculator(storage=storage, srs=srs, now=lambda: date(2026, 5, 21))

    s = calc.compute()
    assert s.retention_sample_size == 6
    assert s.retention_rate == pytest.approx(5 / 6, abs=0.001)


def test_stats_days_filter_applies_to_sessions_not_cards(tmp_path):
    from tutor.stats import StatsCalculator
    from tutor.storage import SessionStorage

    for t in [
        datetime(2026, 5, 21, 9),  # today
        datetime(2026, 5, 10, 9),  # 11 days ago
        datetime(2026, 5, 1, 9),   # 20 days ago
    ]:
        s = SessionStorage(root=tmp_path, now=lambda t=t: t)
        s.create_session("tech_interview_behavioral")

    configs = [("vocab", 0, 0, None), ("grammar", 0, 0, None)]
    srs = _make_srs_with_cards(tmp_path, configs)

    storage = SessionStorage(root=tmp_path, now=lambda: datetime(2026, 5, 21, 12))
    calc = StatsCalculator(storage=storage, srs=srs, now=lambda: date(2026, 5, 21))

    s = calc.compute(days=7)
    assert s.sessions_total == 1  # only today
    assert s.cards_total == 2  # all cards regardless of window
