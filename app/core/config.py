"""Application configuration — all values come from the environment, never hardcoded secrets."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Qafila — Logistics AI Agent Platform"
    app_version: str = "1.0.0"
    environment: str = "development"
    api_prefix: str = "/api"

    # Security
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60 * 24  # 24h
    algorithm: str = "HS256"
    bcrypt_rounds: int = 12

    # Database
    database_url: str = "sqlite:///./qafila.db"

    # CORS
    cors_origins: str = "*"

    # Rate limiting
    rate_limit_per_minute: int = 120

    # Seed
    seed_demo_data: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
