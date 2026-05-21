from datetime import date
from pathlib import Path
import json
import pytest


def test_srs_engine_create_cards_persists_to_disk(tmp_path):
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint

    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    gps = [
        GrowthPoint(tag="vocab", user_utterance="I made a project", corrected_version="I led a project", explanation="Led signals ownership.", context=None),
        GrowthPoint(tag="grammar", user_utterance="I working", corrected_version="I'm working", explanation="Missing auxiliary.", context=None),
    ]
    cards = engine.create_cards(gps, session_id="sess_xyz")
    assert len(cards) == 2
    assert cards[0].tag == "vocab"
    assert cards[0].due_date == "2026-05-22"
    assert cards[0].created_from_session_id == "sess_xyz"
    assert cards[0].repetitions == 0
    assert cards[0].ease_factor == 2.5

    raw = json.loads((tmp_path / "cards.json").read_text())
    assert len(raw["cards"]) == 2


def test_srs_engine_due_today_filters_by_date(tmp_path):
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint

    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    gps = [GrowthPoint(tag="vocab", user_utterance="x", corrected_version="y", explanation="z", context=None)]
    engine.create_cards(gps, session_id="s1")

    # Card is due tomorrow, not today
    assert engine.due_today() == []

    engine2 = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 22))
    due = engine2.due_today()
    assert len(due) == 1


def test_srs_engine_due_today_respects_limit(tmp_path):
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint

    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    gps = [
        GrowthPoint(tag="vocab", user_utterance=f"u{i}", corrected_version=f"c{i}", explanation="e", context=None)
        for i in range(5)
    ]
    engine.create_cards(gps, session_id="s1")

    engine2 = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 22))
    due = engine2.due_today(limit=3)
    assert len(due) == 3


def test_srs_engine_due_today_filters_by_tag(tmp_path):
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint

    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    gps = [
        GrowthPoint(tag="vocab", user_utterance="u1", corrected_version="c1", explanation="e", context=None),
        GrowthPoint(tag="grammar", user_utterance="u2", corrected_version="c2", explanation="e", context=None),
    ]
    engine.create_cards(gps, session_id="s1")

    engine2 = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 22))
    due_vocab = engine2.due_today(tag="vocab")
    assert len(due_vocab) == 1
    assert due_vocab[0].tag == "vocab"


def test_srs_engine_record_review_updates_state(tmp_path):
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint

    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    gps = [GrowthPoint(tag="vocab", user_utterance="x", corrected_version="y", explanation="z", context=None)]
    engine.create_cards(gps, session_id="s1")

    # Reopen with now=tomorrow so the just-created card is due.
    engine2 = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 22))
    cards = engine2.due_today()
    card_id = cards[0].id

    engine2.record_review(card_id, quality=4)
    updated = engine2.load_card(card_id)
    assert updated.repetitions == 1
    assert updated.interval_days == 1
    assert updated.due_date == "2026-05-23"
    assert updated.last_review_quality == 4
    assert len(updated.review_history) == 1


def test_srs_engine_record_review_quality_below_3_resets(tmp_path):
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint

    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    gps = [GrowthPoint(tag="vocab", user_utterance="x", corrected_version="y", explanation="z", context=None)]
    engine.create_cards(gps, session_id="s1")

    engine2 = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 22))
    card_id = engine2.due_today()[0].id

    engine2.record_review(card_id, quality=4)
    engine2.record_review(card_id, quality=4)
    engine2.record_review(card_id, quality=1)
    updated = engine2.load_card(card_id)
    assert updated.repetitions == 0
    assert updated.interval_days == 1


def test_srs_engine_record_review_unknown_card_raises(tmp_path):
    from tutor.srs_engine import SRSEngine, CardNotFoundError

    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 22))
    with pytest.raises(CardNotFoundError):
        engine.record_review("does_not_exist", quality=3)


def test_srs_engine_corrupt_cards_json_backs_up_and_raises(tmp_path):
    """Regression P2: corrupt cards.json must NOT silently destroy data.
    Engine raises RuntimeError; the bad file is renamed to .broken-<ts>."""
    from tutor.srs_engine import SRSEngine
    import pytest as _pytest

    cards_path = tmp_path / "cards.json"
    cards_path.write_text("{ this is not valid json")

    with _pytest.raises(RuntimeError, match="corrupt"):
        SRSEngine(path=cards_path, now=lambda: date(2026, 5, 21))

    # Original file was renamed to a .broken-* sibling
    backups = list(tmp_path.glob("cards.broken-*"))
    assert len(backups) == 1, f"expected exactly one backup, got {backups}"
    # Original path no longer exists (was renamed away)
    assert not cards_path.exists()


def test_srs_engine_all_cards_returns_list_snapshot(tmp_path):
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint

    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    gps = [
        GrowthPoint(tag="vocab", user_utterance="u1", corrected_version="c1",
                    explanation="e", context=None),
        GrowthPoint(tag="grammar", user_utterance="u2", corrected_version="c2",
                    explanation="e", context=None),
    ]
    engine.create_cards(gps, session_id="s1")

    all_cards = engine.all_cards()
    assert len(all_cards) == 2
    tags = sorted(c.tag for c in all_cards)
    assert tags == ["grammar", "vocab"]


def test_srs_engine_all_cards_empty_when_no_cards(tmp_path):
    from tutor.srs_engine import SRSEngine

    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    assert engine.all_cards() == []
