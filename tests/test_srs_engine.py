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
    # Grammar is prioritized over vocab in create_cards' output order.
    vocab_card = next(c for c in cards if c.tag == "vocab")
    assert vocab_card.due_date == "2026-05-22"
    assert vocab_card.created_from_session_id == "sess_xyz"
    assert vocab_card.repetitions == 0
    assert vocab_card.ease_factor == 2.5

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


def test_create_cards_skips_duplicates_by_user_utterance(tmp_path):
    """Cross-session: a growth_point whose user_utterance matches an existing card is skipped."""
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint
    engine = SRSEngine(path=tmp_path / "cards.json")
    # First create one card
    gp1 = GrowthPoint(tag="grammar", user_utterance="I goed",
                     corrected_version="I went", explanation="Past tense.", context=None)
    engine.create_cards([gp1], session_id="s1")
    # Now try to create another with same user_utterance
    gp2 = GrowthPoint(tag="grammar", user_utterance="I goed",
                     corrected_version="I went home", explanation="Better.", context=None)
    new_cards = engine.create_cards([gp2], session_id="s2")
    assert new_cards == []
    assert len(engine.all_cards()) == 1


def test_create_cards_dedupe_is_case_insensitive(tmp_path):
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint
    engine = SRSEngine(path=tmp_path / "cards.json")
    gp1 = GrowthPoint(tag="grammar", user_utterance="  I Goed  ",
                     corrected_version="I went", explanation="X", context=None)
    engine.create_cards([gp1], session_id="s1")
    gp2 = GrowthPoint(tag="vocab", user_utterance="i goed",
                     corrected_version="i went", explanation="Y", context=None)
    new_cards = engine.create_cards([gp2], session_id="s2")
    assert new_cards == []


def test_create_cards_caps_at_5_per_session(tmp_path):
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint
    engine = SRSEngine(path=tmp_path / "cards.json")
    gps = [
        GrowthPoint(tag="grammar", user_utterance=f"sentence number {i}",
                    corrected_version="x", explanation="y", context=None)
        for i in range(8)
    ]
    new_cards = engine.create_cards(gps, session_id="s1")
    assert len(new_cards) == 5


def test_create_cards_prioritizes_grammar_over_vocab(tmp_path):
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint
    engine = SRSEngine(path=tmp_path / "cards.json")
    gps = (
        [GrowthPoint(tag="vocab", user_utterance=f"vocab {i}", corrected_version="c",
                     explanation="e", context=None) for i in range(4)]
        + [GrowthPoint(tag="grammar", user_utterance=f"grammar {i}", corrected_version="c",
                       explanation="e", context=None) for i in range(4)]
    )
    new_cards = engine.create_cards(gps, session_id="s1")
    assert len(new_cards) == 5
    tags = [c.tag for c in new_cards]
    # All 4 grammars should make it; one vocab too
    assert tags.count("grammar") == 4
    assert tags.count("vocab") == 1


def test_create_cards_all_duplicates_returns_empty(tmp_path):
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint
    engine = SRSEngine(path=tmp_path / "cards.json")
    gp = GrowthPoint(tag="grammar", user_utterance="I goed",
                    corrected_version="I went", explanation="x", context=None)
    engine.create_cards([gp], session_id="s1")
    # Second call: all dupes
    result = engine.create_cards([gp, gp], session_id="s2")
    assert result == []
