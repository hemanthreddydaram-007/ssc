from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    """Application configuration loaded from environment variables and `.env`."""

    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), str(BACKEND_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AI Exam Coach"
    app_version: str = "0.1.0"
    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"

    database_url: str = f"sqlite:///{(REPO_ROOT / 'storage' / 'dev.db').as_posix()}"

    auth_mode: Literal["dev_header", "single_user", "jwt"] = "dev_header"
    local_default_user_id: UUID = UUID("00000000-0000-0000-0000-000000000001")
    local_default_user_name: str = "Local Student"
    jwt_secret_key: SecretStr | None = None
    jwt_expire_minutes: int = 60 * 24 * 7

    rate_limit_enabled: bool = False
    rate_limit_auth_per_minute: int = 20
    rate_limit_ai_per_minute: int = 15

    cors_origins: list[str] | str = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )

    storage_root: Path = REPO_ROOT / "storage"
    max_upload_mb: int = 50
    max_pdf_pages: int = 250

    gemini_api_key: SecretStr | None = None
    gemini_api_keys: str = ""
    gemini_model_fast: str = "gemini-2.5-flash"
    gemini_model_standard: str = "gemini-2.5-flash"
    gemini_model_vision: str = "gemini-2.5-flash"
    gemini_fallback_models: str = (
        "gemini-3.5-flash-lite,gemini-2.5-flash-lite,gemini-3-flash-preview"
    )

    @property
    def effective_auth_mode(self) -> Literal["dev_header", "single_user", "jwt"]:
        """Enforce JWT authentication whenever running in production."""
        if self.app_env == "production":
            return "jwt"
        return self.auth_mode

    @property
    def effective_rate_limit_enabled(self) -> bool:
        """Enable rate limiting automatically in production unless configured."""
        return self.rate_limit_enabled or self.app_env == "production"

    @field_validator("database_url", mode="before")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        if isinstance(value, str):
            if value.startswith("postgres://"):
                return "postgresql+psycopg://" + value[len("postgres://") :]
            if value.startswith("postgresql://"):
                return "postgresql+psycopg://" + value[len("postgresql://") :]
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator("storage_root", mode="before")
    @classmethod
    def _resolve_storage_root(cls, value: str | Path) -> Path:
        path = Path(value)
        if not path.is_absolute():
            path = (BACKEND_DIR / path).resolve()
        return path


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
