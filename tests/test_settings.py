import os
import pytest
from pydantic import ValidationError


def test_settings_loads_api_key(monkeypatch):
    from tutor.settings import Settings
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    s = Settings()
    assert s.openrouter_api_key == "sk-or-v1-test"
    assert s.openrouter_model == "google/gemini-2.5-flash"
    assert s.daily_usd_budget == 0.5
    assert s.daily_token_budget == 200_000
    assert s.per_session_turn_limit == 25
    assert s.whisper_model_size == "small"


def test_settings_raises_without_api_key(monkeypatch):
    from tutor.settings import Settings
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    # disable .env file loading for this test
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_rejects_placeholder_key(monkeypatch):
    from tutor.settings import Settings
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-REPLACE_ME")
    with pytest.raises(ValidationError):
        Settings()
