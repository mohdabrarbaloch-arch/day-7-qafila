"""Application settings, loaded from the environment only.

Nothing here has a production-safe default. The JWT secret falls back to a
development value so `uvicorn app.main:app` works out of the box, but
`Settings.is_production` is used to refuse that fallback in prod.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-only-insecure-secret-change-me"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Qafila"
    environment: str = "development"
    database_url: str = "sqlite:///./qafila.db"

    jwt_secret: str = DEV_SECRET
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 24

    cors_origins: str = "*"
    rate_limit_per_minute: int = 240

    seed_demo_data: bool = True

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def validate_for_runtime(self) -> None:
        """Fail loudly rather than run production on a known secret."""
        if self.is_production and self.jwt_secret == DEV_SECRET:
            raise RuntimeError(
                "JWT_SECRET is still the development default. Set a real secret "
                "before running with ENVIRONMENT=production."
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
