"""Application configuration. Reads .env via pydantic-settings."""
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    openrouter_api_key: SecretStr = Field(..., description="OpenRouter API key")
    openrouter_model: str = Field(default="google/gemini-2.5-flash")
    daily_usd_budget: float = Field(default=0.5, gt=0)
    daily_token_budget: int = Field(default=200_000, gt=0)
    per_session_turn_limit: int = Field(default=25, gt=0)
    whisper_model_size: str = Field(default="small")
    tts_voice: str = Field(default="Samantha", description="macOS `say` voice name (run `say -v '?'` to list)")
    tts_rate: int = Field(default=180, gt=0)

    @field_validator("openrouter_api_key", mode="before")
    @classmethod
    def reject_placeholder(cls, v):
        # v may be a string (from env) or SecretStr depending on source
        raw = v.get_secret_value() if hasattr(v, "get_secret_value") else v
        if not isinstance(raw, str):
            return v
        if "REPLACE_ME" in raw:
            raise ValueError("OPENROUTER_API_KEY still contains placeholder value")
        if not raw.startswith("sk-or-"):
            raise ValueError("OPENROUTER_API_KEY does not look like an OpenRouter key")
        return v


def get_settings() -> Settings:
    return Settings()
