"""Settings, read once from the environment (and `.env` in development)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: Literal["development", "test", "production"] = "development"

    database_url: str = "postgresql+psycopg://generator:generator@localhost:5432/generator"
    redis_url: str = "redis://localhost:6379/0"
    # Solver runs go to the RQ worker; true runs them in the web process
    # (tests and single-machine development only).
    run_inline: bool = False
    run_queue: str = "generator-runs"
    # The longest run the Director may ask for, and the default.
    max_time_limit_seconds: int = 3600
    default_time_limit_seconds: int = 600
    solver_workers: int = Field(default=8, ge=1, le=64)

    # SMARTTT, the only system the Generator talks to.
    smarttt_base_url: str = "http://localhost:8000"
    smarttt_api_key: str = ""
    smarttt_timeout_seconds: float = 60.0  # a publish writes the whole term

    # The Timetable Allocator reads units, groups and published meetings with
    # this key (X-API-Key); it must equal GENERATOR_API_KEY in the Allocator.
    # Unset = the Allocator can't connect.
    allocator_api_key: str = ""

    session_cookie_name: str = "tg_session"
    csrf_cookie_name: str = "XSRF-TOKEN"
    csrf_header_name: str = "X-XSRF-TOKEN"
    session_idle_minutes: int = 120
    session_absolute_hours: int = 12
    identity_refresh_seconds: int = 300
    cookie_secure: bool = True
    cookie_domain: str | None = None

    cors_origins: list[str] = Field(default_factory=list)

    login_max_attempts: int = 10
    login_window_seconds: int = 900

    log_level: str = "INFO"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _production_requirements(self) -> Settings:
        if self.environment == "production":
            if not self.smarttt_api_key:
                raise ValueError("Missing required setting in production: SMARTTT_API_KEY")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production.")
            if self.run_inline:
                raise ValueError("RUN_INLINE must be false in production; solver runs belong on the worker.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
