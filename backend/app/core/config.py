from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

INSECURE_JWT_SECRET = "change-me-dev-secret-change-me-dev-secret"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["dev", "test", "prod"] = "dev"
    app_name: str = "Chotu-Gyani"
    database_url: str = "postgresql+asyncpg://chotu:chotu@localhost:5433/chotu"
    test_database_url: str = "postgresql+asyncpg://chotu:chotu@localhost:5433/chotu_test"
    redis_url: str = ""

    jwt_secret: str = INSECURE_JWT_SECRET
    jwt_issuer: str = "chotu-gyani"
    jwt_audience: str = "chotu-gyani-api"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    password_reset_ttl_minutes: int = 30
    invitation_ttl_days: int = 7

    frontend_origins: str = "http://localhost:3000"

    llm_provider: Literal["mock", "groq", "anthropic"] = "mock"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"
    llm_timeout_seconds: float = 30.0

    # Groq: dev/staging provider for LLM, STT and TTS (OpenAI-compatible API).
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_llm_model: str = "openai/gpt-oss-120b"
    groq_reasoning_effort: Literal["low", "medium", "high"] = "low"
    groq_stt_model: str = "whisper-large-v3"
    groq_tts_model: str = "canopylabs/orpheus-v1-english"
    groq_tts_voice: str = "troy"
    groq_max_rate_limit_wait_seconds: float = 20.0

    stt_provider: Literal["mock", "groq", "gnani"] = "mock"
    tts_provider: Literal["mock", "groq", "gnani"] = "mock"
    gnani_api_key: str = ""
    gnani_base_url: str = ""

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/integrations/google-sheets/callback"

    enable_workers: bool = True
    worker_poll_seconds: int = 30
    action_ttl_minutes: int = 15
    reminder_max_attempts: int = 5
    reminder_backoff_base_seconds: int = 60
    reminder_backoff_cap_seconds: int = 3600

    max_audio_bytes: int = 5 * 1024 * 1024
    max_audio_seconds: int = 120

    usage_limit_assistant_messages: int = 2000
    usage_limit_audio_requests: int = 500
    usage_limit_agent_generations: int = 100

    auth_rate_limit_per_minute: int = 10

    @field_validator("frontend_origins")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.frontend_origins.split(",") if o.strip()]

    def validate_for_startup(self) -> None:
        if self.app_env == "prod":
            if self.jwt_secret == INSECURE_JWT_SECRET or len(self.jwt_secret) < 32:
                raise RuntimeError("Insecure JWT_SECRET in production")
            if "*" in self.cors_origins:
                raise RuntimeError("Wildcard CORS origin is not allowed in production")


@lru_cache
def get_settings() -> Settings:
    return Settings()
