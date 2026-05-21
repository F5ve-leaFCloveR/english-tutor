import os
import pytest
from pydantic import ValidationError


def test_settings_loads_api_key(monkeypatch):
    from tutor.settings import Settings
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-test")
    s = Settings()
    assert s.openrouter_api_key.get_secret_value() == "sk-or-v1-test"
    assert s.openrouter_model == "google/gemini-2.5-flash"
    assert s.openrouter_evaluator_model == "google/gemini-2.5-pro"
    assert s.openrouter_grader_model == "google/gemini-2.5-flash"
    assert s.daily_usd_budget == 0.5
    assert s.daily_token_budget == 200_000
    assert s.per_session_turn_limit == 25
    assert s.whisper_model_size == "small"
    assert s.macos_say_voice == "Samantha"
    assert s.tts_rate == 180
    assert s.tts_model == "openai/gpt-audio-mini"
    assert s.tts_voice == "alloy"


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


def test_settings_api_key_is_not_in_repr(monkeypatch):
    """Regression: SecretStr ensures repr() doesn't leak the API key."""
    from tutor.settings import Settings
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-supersecret123")
    s = Settings()
    r = repr(s)
    assert "sk-or-v1-supersecret123" not in r
    assert "supersecret123" not in r
    # the value is still retrievable via get_secret_value
    assert s.openrouter_api_key.get_secret_value() == "sk-or-v1-supersecret123"
