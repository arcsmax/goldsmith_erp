# src/goldsmith_erp/core/config.py

import secrets
from pathlib import Path
from typing import Any, Optional

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    """

    # ── Tell Pydantic to read `/app/.env` at runtime ───────────────────────────
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parents[4] / ".env",  # project root/.env
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    # ── App basics ─────────────────────────────────────────────────────────────
    APP_NAME: str = "Goldsmith ERP"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description="JWT secret key - MUST be set in production via SECRET_KEY env variable"
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days

    # ── Server ─────────────────────────────────────────────────────────────────
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False

    # ── PostgreSQL ──────────────────────────────────────────────────────────────
    POSTGRES_USER: str = "user"
    POSTGRES_PASSWORD: str = "pass"
    POSTGRES_DB: str = "goldsmith"
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: Optional[PostgresDsn] = None

    # ── Redis ───────────────────────────────────────────────────────────────────
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_URL: Optional[RedisDsn] = None
    # ── CORS ─────────────────────────────────────────────────────────────────────
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
    ]

    @classmethod
    @field_validator("DATABASE_URL", mode="before")
    def assemble_db_url(
        cls, value: Optional[str], info: Any
    ) -> str:
        """
        Build a Postgres DSN if DATABASE_URL was not provided.
        """
        if isinstance(value, str):
            return value

        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=info.data["POSTGRES_USER"],
            password=info.data["POSTGRES_PASSWORD"],
            host=info.data["POSTGRES_HOST"],
            port=info.data["POSTGRES_PORT"],
            path=f"/{info.data['POSTGRES_DB']}",
        )

    @classmethod
    @field_validator("REDIS_URL", mode="before")
    def assemble_redis_url(cls, value, info):
        """
        Build a Redis DSN if REDIS_URL was not provided.
        """
        if isinstance(value, str):
            return value
        return RedisDsn.build(
            scheme="redis",
            host=info.data["REDIS_HOST"],
            port=str(info.data["REDIS_PORT"]),
            path=f"/{info.data['REDIS_DB']}",
        )

    @field_validator("SECRET_KEY")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """
        Validate that SECRET_KEY is secure and not using default value.
        """
        if v == "change_this_to_a_secure_random_string":
            raise ValueError(
                "SECRET_KEY must be changed from default! "
                "Set SECRET_KEY environment variable with a secure random string."
            )
        if len(v) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters long for security. "
                f"Current length: {len(v)}"
            )
        return v

# Instantiate once per process
settings = Settings()