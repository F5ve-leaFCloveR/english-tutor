from datetime import date
from pathlib import Path
from unittest.mock import MagicMock
import pytest


def _stub_review_adapters(transcripts, grader_scores):
    """Mocks for asr/tts/recorder/grader."""
    asr = MagicMock()
    asr.transcribe.side_effect = transcripts
    tts = MagicMock()
    recorder = MagicMock()
    recorder.record_to_wav.side_effect = [Path(f"/tmp/fake_{i}.wav") for i in range(50)]
    grader = MagicMock()
    grader.grade.side_effect = grader_scores
    return asr, tts, recorder, grader


def _make_srs_with_cards(tmp_path, n_cards):
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint

    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    gps = [
        GrowthPoint(tag="vocab", user_utterance=f"u{i}", corrected_version=f"c{i}",
                     explanation="e", context=None)
        for i in range(n_cards)
    ]
    engine.create_cards(gps, session_id="s1")
    # Reopen on the next day so cards are due
    return SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 22))


def test_review_processes_due_cards(tmp_path, mocker):
    from tutor.review import ReviewOrchestrator

    mocker.patch("builtins.input", side_effect=["", "", "", ""])  # 3 cards × 1 input each
    srs = _make_srs_with_cards(tmp_path, n_cards=3)
    asr, tts, recorder, grader = _stub_review_adapters(
        transcripts=["c0", "c1", "c2"],
        grader_scores=[3, 4, 5],
    )

    orch = ReviewOrchestrator(grader=grader, asr=asr, tts=tts, recorder=recorder, srs=srs)
    summary = orch.run()
    assert summary.cards_reviewed == 3
    assert summary.quality_distribution == {3: 1, 4: 1, 5: 1}
    assert grader.grade.call_count == 3
    assert tts.speak.call_count == 3  # speaks the target after each grade


def test_review_no_due_cards(tmp_path, mocker, capsys):
    from tutor.review import ReviewOrchestrator
    from tutor.srs_engine import SRSEngine

    srs = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    asr, tts, recorder, grader = _stub_review_adapters([], [])

    orch = ReviewOrchestrator(grader=grader, asr=asr, tts=tts, recorder=recorder, srs=srs)
    summary = orch.run()
    assert summary.cards_reviewed == 0


def test_review_skip_command_records_zero(tmp_path, mocker):
    from tutor.review import ReviewOrchestrator

    mocker.patch("builtins.input", side_effect=["skip", ""])
    srs = _make_srs_with_cards(tmp_path, n_cards=2)
    asr, tts, recorder, grader = _stub_review_adapters(
        transcripts=["c1"],
        grader_scores=[4],
    )

    orch = ReviewOrchestrator(grader=grader, asr=asr, tts=tts, recorder=recorder, srs=srs)
    summary = orch.run()
    assert summary.cards_reviewed == 2
    # First card was skipped → quality 0
    assert summary.quality_distribution.get(0) == 1
    assert grader.grade.call_count == 1  # only called for non-skipped


def test_review_quit_command_ends_early(tmp_path, mocker):
    from tutor.review import ReviewOrchestrator

    mocker.patch("builtins.input", side_effect=["", "quit"])
    srs = _make_srs_with_cards(tmp_path, n_cards=3)
    asr, tts, recorder, grader = _stub_review_adapters(
        transcripts=["c0"],
        grader_scores=[3],
    )

    orch = ReviewOrchestrator(grader=grader, asr=asr, tts=tts, recorder=recorder, srs=srs)
    summary = orch.run()
    assert summary.cards_reviewed == 1


def test_review_respects_limit_and_tag(tmp_path, mocker):
    from tutor.review import ReviewOrchestrator
    from tutor.srs_engine import SRSEngine
    from tutor.evaluator import GrowthPoint

    engine = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 21))
    gps = [
        GrowthPoint(tag="vocab", user_utterance="u1", corrected_version="c1", explanation="e", context=None),
        GrowthPoint(tag="grammar", user_utterance="u2", corrected_version="c2", explanation="e", context=None),
        GrowthPoint(tag="vocab", user_utterance="u3", corrected_version="c3", explanation="e", context=None),
    ]
    engine.create_cards(gps, session_id="s1")
    srs = SRSEngine(path=tmp_path / "cards.json", now=lambda: date(2026, 5, 22))

    mocker.patch("builtins.input", side_effect=[""])
    asr, tts, recorder, grader = _stub_review_adapters(
        transcripts=["c1"],
        grader_scores=[3],
    )

    orch = ReviewOrchestrator(grader=grader, asr=asr, tts=tts, recorder=recorder, srs=srs)
    summary = orch.run(limit=1, tag_filter="vocab")
    assert summary.cards_reviewed == 1
