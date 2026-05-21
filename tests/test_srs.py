import pytest


def test_srs_first_review_quality_3_or_higher_sets_interval_1():
    from tutor.srs import next_interval
    new_interval, new_repetitions, new_ef = next_interval(
        quality=3, prev_interval=0, repetitions=0, ease_factor=2.5
    )
    assert new_interval == 1
    assert new_repetitions == 1
    assert new_ef == pytest.approx(2.36, abs=0.01)


def test_srs_second_review_sets_interval_6():
    from tutor.srs import next_interval
    new_interval, new_repetitions, _ = next_interval(
        quality=4, prev_interval=1, repetitions=1, ease_factor=2.5
    )
    assert new_interval == 6
    assert new_repetitions == 2


def test_srs_third_review_multiplies_by_ease_factor():
    from tutor.srs import next_interval
    new_interval, new_repetitions, _ = next_interval(
        quality=4, prev_interval=6, repetitions=2, ease_factor=2.5
    )
    assert new_interval == 15  # round(6 * 2.5)
    assert new_repetitions == 3


def test_srs_failure_resets_repetitions_and_interval():
    from tutor.srs import next_interval
    new_interval, new_repetitions, new_ef = next_interval(
        quality=1, prev_interval=15, repetitions=3, ease_factor=2.6
    )
    assert new_interval == 1
    assert new_repetitions == 0
    # ease factor does NOT reset on failure (SM-2 standard)
    assert new_ef == 2.6


def test_srs_ease_factor_floor_is_1_3():
    from tutor.srs import next_interval
    # Many quality=3 reviews should drive ease factor toward 1.3 but not below
    ef = 1.35
    for _ in range(20):
        _, _, ef = next_interval(quality=3, prev_interval=1, repetitions=0, ease_factor=ef)
    assert ef >= 1.3


def test_srs_ease_factor_increases_on_quality_5():
    from tutor.srs import next_interval
    _, _, new_ef = next_interval(quality=5, prev_interval=6, repetitions=2, ease_factor=2.5)
    # quality=5: ef + 0.1 - 0 * (0.08 + 0 * 0.02) = ef + 0.1
    assert new_ef == pytest.approx(2.6, abs=0.01)


def test_srs_ease_factor_unchanged_at_quality_4():
    from tutor.srs import next_interval
    _, _, new_ef = next_interval(quality=4, prev_interval=6, repetitions=2, ease_factor=2.5)
    # quality=4: ef + 0.1 - 1 * (0.08 + 1 * 0.02) = ef + 0.1 - 0.10 = ef
    assert new_ef == pytest.approx(2.5, abs=0.01)
