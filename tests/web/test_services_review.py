from datetime import date, datetime
from unittest.mock import MagicMock
import pytest


def _deps(tmp_path):
    from tutor.web.deps import Dependencies
    from tutor.budget import BudgetTracker
    from tutor.storage import SessionStorage
    from tutor.srs_engine import SRSEngine

    return Dependencies(
        budget=BudgetTracker(
            path=tmp_path / "b.json", daily_usd_cap=1.0,
            daily_token_cap=1_000_000,
            now=lambda: datetime(2026, 5, 22, 10, 0),
        ),
        llm=MagicMock(), asr=MagicMock(),
        storage=SessionStorage(root=tmp_path / "sessions"),
        srs=SRSEngine(path=tmp_path / "cards.json",
                      now=lambda: date(2026, 5, 22)),
        evaluator_model="m1", grader_model="m2",
    )


def _seed_cards(tmp_path, configs):
    """configs: list of (tag, repetitions, interval_days, last_quality)."""
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint
    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    gps = [
        GrowthPoint(tag=tag, user_utterance=f"u{i}", corrected_version=f"c{i}",
                    explanation="why", context=None)
        for i, (tag, _, _, _) in enumerate(configs)
    ]
    if gps:
        engine.create_cards(gps, session_id="s1")
        for (tag, reps, interval, qual), card in zip(configs, engine.all_cards()):
            card.repetitions = reps
            card.interval_days = interval
            card.last_review_quality = qual
        engine._flush()


def test_review_due_service_returns_dicts(tmp_path):
    from tutor.web.services import review_due_service
    _seed_cards(tmp_path, [("vocab", 0, 0, None), ("grammar", 0, 0, None)])
    deps = _deps(tmp_path)
    result = review_due_service(deps, limit=None, tag=None)
    assert result.total_due == 2
    assert len(result.cards) == 2
    assert all(isinstance(c, dict) for c in result.cards)


def test_review_due_service_respects_filter(tmp_path):
    from tutor.web.services import review_due_service
    _seed_cards(tmp_path, [("vocab", 0, 0, None), ("grammar", 0, 0, None),
                            ("vocab", 0, 0, None)])
    deps = _deps(tmp_path)
    result = review_due_service(deps, limit=10, tag="vocab")
    assert result.total_due == 2  # 2 vocab cards


def test_grade_card_service_audio_path(tmp_path, mocker):
    from tutor.web.services import grade_card_service
    _seed_cards(tmp_path, [("vocab", 0, 0, None)])
    deps = _deps(tmp_path)
    deps.asr.transcribe.return_value = "I led a project"
    fake_grader = MagicMock()
    fake_grader.grade.return_value = 4
    mocker.patch("tutor.web.services.LLMGrader", return_value=fake_grader)

    card_id = deps.srs.all_cards()[0].id
    result = grade_card_service(deps, card_id=card_id, audio_bytes=b"audio",
                                 skip=False)
    assert result.quality == 4
    assert result.user_attempt_text == "I led a project"


def test_grade_card_service_skip_path(tmp_path):
    from tutor.web.services import grade_card_service
    _seed_cards(tmp_path, [("vocab", 0, 0, None)])
    deps = _deps(tmp_path)
    card_id = deps.srs.all_cards()[0].id
    result = grade_card_service(deps, card_id=card_id, audio_bytes=None, skip=True)
    assert result.quality == 0
    assert result.user_attempt_text == "(skipped)"


def test_grade_card_service_raises_on_unknown_card(tmp_path):
    from tutor.web.services import grade_card_service
    from tutor.srs_engine import CardNotFoundError
    deps = _deps(tmp_path)
    with pytest.raises(CardNotFoundError):
        grade_card_service(deps, card_id="does_not_exist", audio_bytes=b"x", skip=False)
