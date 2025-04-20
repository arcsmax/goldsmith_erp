from pydantic import BaseSettings, PostgresDsn, validator
from typing import Optional
from pathlib import Path
import os

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    APP_NAME: str = "Goldsmith ERP"
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 8  # 8 days
    
    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    
    # Database
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str
    POSTGRES_HOST: str = "db"  # Docker-Compose Service Name
    POSTGRES_PORT: str = "5432"
    DATABASE_URL: Optional[PostgresDsn] = None
    
    # CORS
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]
    
    @validator("DATABASE_URL", pre=True)
    def assemble_db_url(cls, v: Optional[str], values: dict) -> str:
        if isinstance(v, str):
            return v
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            user=values.get("POSTGRES_USER"),
            password=values.get("POSTGRES_PASSWORD"),
            host=values.get("POSTGRES_HOST"),
            port=values.get("POSTGRES_PORT"),
            path=f"/{values.get('POSTGRES_DB')}",
        )
    
    class Config:
        env_file = os.path.join(Path(__file__).parent.parent.parent.parent, ".env")
        case_sensitive = True

settings = Settings()