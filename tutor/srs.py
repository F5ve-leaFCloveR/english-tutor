"""Pure SM-2 spaced repetition algorithm. No I/O."""
from __future__ import annotations


_MIN_EASE_FACTOR = 1.3


def next_interval(
    quality: int,
    prev_interval: int,
    repetitions: int,
    ease_factor: float,
) -> tuple[int, int, float]:
    """Compute the next SRS state from a review.

    Args:
        quality: 0-5 score for this review (3+ = pass, <3 = fail).
        prev_interval: previous interval in days.
        repetitions: how many consecutive successful reviews so far.
        ease_factor: current ease factor (typically starts at 2.5, floor 1.3).

    Returns:
        (new_interval_days, new_repetitions, new_ease_factor)
    """
    if quality < 3:
        # Failure: reset repetitions and interval, ease factor unchanged.
        return 1, 0, ease_factor

    if repetitions == 0:
        new_interval = 1
    elif repetitions == 1:
        new_interval = 6
    else:
        new_interval = round(prev_interval * ease_factor)

    new_repetitions = repetitions + 1

    # Update ease factor.
    q = quality
    delta = 0.1 - (5 - q) * (0.08 + (5 - q) * 0.02)
    new_ease_factor = max(_MIN_EASE_FACTOR, ease_factor + delta)

    return new_interval, new_repetitions, new_ease_factor
