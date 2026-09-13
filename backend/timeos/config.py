"""Application settings, loaded from environment variables / .env.

No secrets ever have a hardcoded default that looks production-usable. See
docs/TIMEOS_ENGINEERING_SPEC.md §28 (Secrets) and §12 (Backend Architecture).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="TIMEOS_", extra="ignore")

    database_url: str = "postgresql+asyncpg://timeos:timeos@localhost:5432/timeos"
    environment: str = "development"

    # AI provider config (Phase 7/8). Absent by default -> NullProvider is used everywhere.
    ai_provider: str = "null"
    ai_api_key: str | None = None
    ai_monthly_budget_usd: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
