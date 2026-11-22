from functools import lru_cache
from typing import List
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_NAME: str = "Splitzy"
    APP_ENV: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"

    # Database connection string (supports asyncpg)
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/splitzy",
        validation_alias="DATABASE_URL",
    )

    # JWT Security settings
    JWT_SECRET: str = Field(
        default="splitzy-super-secret-jwt-key-minimum-32-chars-long",
        validation_alias="JWT_SECRET",
    )
    JWT_ALGORITHM: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, validation_alias="ACCESS_TOKEN_EXPIRE_MINUTES")

    # Optional Gemini API Key for financial intelligence
    GEMINI_API_KEY: str | None = Field(default=None, validation_alias="GEMINI_API_KEY")

    # Allowed CORS Origins for React Native, Expo, and Web
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:8081",
        "http://localhost:19000",
        "http://localhost:19006",
        "exp://",
        "*",
    ]

    @property
    def async_database_url(self) -> str:
        """Ensure the database URL has the postgresql+asyncpg:// scheme."""
        url = self.DATABASE_URL
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        if url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
