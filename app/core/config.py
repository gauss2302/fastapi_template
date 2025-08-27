import os
from functools import lru_cache
from typing import Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env.example",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application settings
    APP_NAME: str = "FastAPI Backend"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    API_V1_STR: str = "/api/v1"

    # Security settings
    SECRET_KEY: str = Field(min_length=32, description="JWT secret key - must be set in environment")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days
    ALGORITHM: str = "HS256"

    # Database settings
    POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER")
    POSTGRES_USER: str = os.getenv("POSTGRES_USER")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB")
    POSTGRES_PORT: int = os.getenv("POSTGRES_PORT")
    DATABASE_URL: Optional[str] = None

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: Optional[str], info) -> str:
        if isinstance(v, str) and v:
            return v

        # ИСПРАВЛЕНО: правильный доступ к данным в Pydantic v2
        values = info.data

        server = values.get('POSTGRES_SERVER', 'localhost')
        user = values.get('POSTGRES_USER', 'postgres')
        password = values.get('POSTGRES_PASSWORD', 'postgres')
        port = values.get('POSTGRES_PORT', 5432)
        db = values.get('POSTGRES_DB', 'fastapi_db')

        return (
            f"postgresql+asyncpg://"
            f"{user}:{password}@{server}:{port}/{db}"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        """Синхронная версия DATABASE_URL для Alembic"""
        return self.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg2://")

    # Redis settings
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # Google OAuth settings
    GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID")
    GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET")
    GOOGLE_REDIRECT_URI: str = os.getenv("GOOGLE_REDIRECT_URI")

    # GitHub OAuath settigns
    GITHUB_CLIENT_ID: str = os.getenv("GITHUB_CLIENT_ID", "")
    GITHUB_CLIENT_SECRET: str = os.getenv("GITHUB_CLIENT_SECRET", "")
    GITHUB_REDIRECT_URI: str = os.getenv("GITHUB_REDIRECT_URI", "")

    # CORS settings
    BACKEND_CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3000"],
        description="Allowed CORS origins"
    )

    SECURE_COOKIES: bool = Field(default=True, description="For production")
    TRUSTED_HOSTS: list[str] = Field(
        default=["localhost", "127.0.0.1"],
        description="Trusted host headers"
    )

    # Logging
    LOG_LEVEL: str = "INFO"

    PGADMIN_EMAIL: Optional[str] = None
    PGADMIN_PASSWORD: Optional[str] = None


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()