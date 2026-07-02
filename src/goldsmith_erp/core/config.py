# src/goldsmith_erp/core/config.py

import logging
import secrets
from pathlib import Path
from typing import Any, Optional

from pydantic import Field, PostgresDsn, RedisDsn, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    """

    # ── Tell Pydantic to read `/app/.env` at runtime ───────────────────────────
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parents[3]
        / ".env",  # project root/.env  (src/goldsmith_erp/core/config.py → parents[3])
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # .env carries compose-only vars (DB_PORT, REDIS_EXT_PORT, BACKEND_PORT); ignore them at the Settings layer
    )

    # ── App basics ─────────────────────────────────────────────────────────────
    APP_NAME: str = "Goldsmith ERP"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description="JWT secret key - MUST be set in production via SECRET_KEY env variable",
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
    def assemble_db_url(cls, value: Optional[str], info: Any) -> str:
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

    # ── Connection Pooling ───────────────────────────────────────────────────────
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800  # 30 minutes — recycle stale connections

    # ── Workshop / Application identity ──────────────────────────────────────────
    WORKSHOP_NAME: str = "Goldschmiede"
    APP_VERSION: str = "1.0.0"

    # ── Backup ───────────────────────────────────────────────────────────────────
    BACKUP_DIR: str = "~/goldsmith-backups"
    BACKUP_CLOUD_URL: Optional[str] = None

    # ── Email / SMTP ─────────────────────────────────────────────────────────────
    # All fields are optional — the email service degrades gracefully when unset.
    # Set EMAIL_NOTIFICATIONS_ENABLED=true and the SMTP_* fields to activate.
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM: Optional[str] = None
    EMAIL_NOTIFICATIONS_ENABLED: bool = False

    # ── Encryption ───────────────────────────────────────────────────────────────
    # Fernet key for PII field encryption at rest. Generate with setup.sh.
    # Optional: app starts without it but PII fields will not be encrypted.
    ENCRYPTION_KEY: Optional[str] = None

    # ── Anonymization (GDPR Art. 17) ─────────────────────────────────────────────
    # Salt used by `anonymize_user()` to derive the per-erasure HMAC tracking
    # token written to `gdpr_requests.notes`. The token is an internal
    # correlation aid only — it is not exposed to end users and is not stored
    # in any FK column (the global sentinel user carries all anonymised FKs).
    #
    # Generate with: python3 -c "import secrets; print(secrets.token_urlsafe(64))"
    #
    # CRITICAL — DO NOT ROTATE POST-FIRST-ERASURE.
    # Rotating the salt after anonymisation has occurred orphans previously
    # emitted tracking HMACs (they can no longer be regenerated for audit
    # lookup). Production rotation must be coordinated with DPO sign-off and
    # a one-off archive of the old salt. See V1.1-ANONYMIZE-USER-CONTRACT §4.
    ANONYMIZATION_SALT: Optional[str] = None

    # ── Cookie security ──────────────────────────────────────────────────────────
    # Set True in production when TLS is terminated at the load balancer or
    # reverse proxy (HTTPS). Keep False for local network / dev environments.
    COOKIE_SECURE: bool = False

    @model_validator(mode="after")
    def _check_encryption_key(self) -> "Settings":
        """Fail-fast in production if ENCRYPTION_KEY is not set."""
        if not self.ENCRYPTION_KEY:
            if not self.DEBUG:
                raise ValueError(
                    "ENCRYPTION_KEY must be set in production (DEBUG=False). "
                    'Generate with: python -c "from cryptography.fernet import Fernet; '
                    'print(Fernet.generate_key().decode())"'
                )
            else:
                logging.getLogger(__name__).warning(
                    "ENCRYPTION_KEY not set — PII fields will NOT be encrypted. "
                    "This is only acceptable in development."
                )
        return self

    @model_validator(mode="after")
    def _check_anonymization_salt(self) -> "Settings":
        """Fail-fast in production if ANONYMIZATION_SALT is not set.

        In dev (DEBUG=True) the service falls back to a deterministic but
        obviously-insecure placeholder so tests and first-run setup work.
        Any production deployment MUST provide its own salt; rotating it
        post-first-erasure is forbidden (see field docstring).
        """
        if not self.ANONYMIZATION_SALT:
            if not self.DEBUG:
                raise ValueError(
                    "ANONYMIZATION_SALT must be set in production (DEBUG=False). "
                    'Generate with: python3 -c "import secrets; '
                    'print(secrets.token_urlsafe(64))"'
                )
            else:
                logging.getLogger(__name__).warning(
                    "ANONYMIZATION_SALT not set — anonymize_user() will use a "
                    "dev-only fallback salt. Acceptable only in development."
                )
        return self

    # ── Photo Upload ─────────────────────────────────────────────────────────────
    # Directory where uploaded order photos and thumbnails are stored.
    # Relative paths are resolved from the project root at runtime.
    PHOTO_STORAGE_PATH: str = "./uploads/photos"
    PHOTO_MAX_SIZE_MB: int = 8

    # ── Repair Intake Checklist (V1.1) ───────────────────────────────────────────
    # Seeded onto every new RepairJob.intake_checklist at creation (one item
    # per label, see RepairService.create_repair). Each item is satisfied by
    # an INTAKE-phase photo or an explicit "nicht zutreffend" + reason —
    # dispute-protection mirroring insurance-industry intake practice.
    REPAIR_INTAKE_CHECKLIST: list[str] = [
        "Krappen/Fassungen",
        "Pavé-Besatz",
        "Gravuren",
        "Punzen/Stempel",
        "Vorhandene Tragespuren und Schäden",
    ]

    # ── File Storage Root (GDPR Art. 17 file erasure) ────────────────────────────
    # Root directory containing every filesystem artefact referenced by DB path
    # columns — generated PDFs, uploaded photos, scrap-gold receipts. When a
    # customer exercises Art. 17 erasure, the ``FileErasureService`` deletes
    # every file referenced by a row linked to that customer.
    #
    # CRITICAL — path-traversal boundary.
    # The service resolves each candidate path and refuses to delete any file
    # that escapes this root (e.g. a malicious ``../../../etc/passwd`` value
    # in a DB column). Every deployment MUST set this to a path that contains
    # ONLY the uploaded / generated artefact tree; siblings to this directory
    # MUST NOT contain data the service is not entitled to delete on Art. 17
    # request.
    #
    # Default points to ``./uploads`` relative to CWD — suitable for local
    # dev and the existing ``PHOTO_STORAGE_PATH`` layout, but production
    # deployments should override with an absolute path.
    FILE_STORAGE_ROOT: str = "./uploads"

    # ── Metal Price Service ──────────────────────────────────────────────────────
    # Optional external API for live spot prices.
    # When unset the service falls back to DB history then hardcoded defaults.
    METAL_PRICE_API_URL: Optional[str] = None

    # How long (seconds) a fetched price set is kept in Redis before re-fetching.
    METAL_PRICE_CACHE_TTL: int = 3600  # 1 hour

    # EUR per gram fallback prices used only when Redis AND the API AND the DB
    # all fail to provide a price.  Values reflect mid-2026 typical spot rates.
    METAL_PRICE_FALLBACK_GOLD: float = 75.0  # 24K / fine gold
    METAL_PRICE_FALLBACK_SILVER: float = 0.85  # 999 fine silver
    METAL_PRICE_FALLBACK_PLATINUM: float = 30.0  # pure platinum

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
                '  python3 -c "import secrets; print(secrets.token_urlsafe(64))"\n'
                "Then set it in your .env file."
            )

        # Check minimum length
        if len(v) < 32:
            raise ValueError(
                f"SECRET_KEY must be at least 32 characters for security. "
                f"Current length: {len(v)}. "
                f"Generate a secure key with:\n"
                f'  python3 -c "import secrets; print(secrets.token_urlsafe(64))"'
            )

        # Warning for low entropy (optional, but helpful)
        # Check if key has good character diversity
        if len(set(v)) < 16:  # Less than 16 unique characters
            import warnings

            warnings.warn(
                f"SECRET_KEY has low entropy ({len(set(v))} unique characters). "
                f"Consider generating a more random key.",
                UserWarning,
            )

        return v


# Instantiate once per process
settings = Settings()
