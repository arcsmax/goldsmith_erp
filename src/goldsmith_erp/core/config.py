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
        Validate that SECRET_KEY is secure and not using default/insecure values.

        Security requirements:
        - Minimum 32 characters
        - Not a common insecure default value
        - High entropy (for production)
        """
        # List of known insecure default values
        insecure_values = [
            "change_this_to_a_secure_random_string",
            "CHANGE_THIS_TO_A_SECURE_RANDOM_STRING_AT_LEAST_32_CHARS",
            "secret",
            "secretkey",
            "your-secret-key",
            "mysecretkey",
            "changeme",
            "password",
            "secret123",
            "supersecret",
        ]

        # Check for exact matches (case-insensitive)
        if v.lower() in [s.lower() for s in insecure_values]:
            raise ValueError(
                "SECRET_KEY is using an insecure default value! "
                "Generate a secure key with:\n"
                "  python3 -c \"import secrets; print(secrets.token_urlsafe(64))\"\n"
                "Then set it in your .env file."
            )

        # Check minimum length
        if len(v) < 32:
            raise ValueError(
                f"SECRET_KEY must be at least 32 characters for security. "
                f"Current length: {len(v)}. "
                f"Generate a secure key with:\n"
                f"  python3 -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )

        # Warning for low entropy (optional, but helpful)
        # Check if key has good character diversity
        if len(set(v)) < 16:  # Less than 16 unique characters
            import warnings
            warnings.warn(
                f"SECRET_KEY has low entropy ({len(set(v))} unique characters). "
                f"Consider generating a more random key.",
                UserWarning
            )

        return v

# Instantiate once per process
settings = Settings()