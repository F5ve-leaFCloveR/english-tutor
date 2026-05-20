"""Shared pytest fixtures."""
import pytest


@pytest.fixture
def fixed_now():
    """Deterministic 'now' for budget reset tests."""
    from datetime import datetime
    return datetime(2026, 5, 20, 12, 0, 0)
