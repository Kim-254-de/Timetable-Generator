"""Settings, read once from the environment (and `.env` in development)."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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

    # Smart Attendance, where administrators create the departments the
    # Generator plans against (GET /api/v1/integrations/generator/departments)
    # and where departments enter and publish their teaching, which "Import
    # published departments" reads (.../terms/{id}/submissions). One shared
    # key both ways: it must equal GENERATOR_API_KEY there, and Attendance
    # sends it to read the terms and published times here. Unset URL =
    # departments stay as last read and nothing can be imported.
    attendance_base_url: str = ""
    attendance_api_key: str = ""
    attendance_timeout_seconds: float = 15.0
    # Departments are re-read from Attendance at most this often when listed.
    department_sync_seconds: int = 60

    session_cookie_name: str = "tg_session"
    # Distinct from other apps' on the same host, so each keeps its own sign-in.
    csrf_cookie_name: str = "tg_xsrf"
    csrf_header_name: str = "X-XSRF-TOKEN"
    session_idle_minutes: int = 120
    session_absolute_hours: int = 12
    identity_refresh_seconds: int = 300
    cookie_secure: bool = True
    cookie_domain: str | None = None

    # NoDecode: the raw string reaches _split_origins, which takes a comma-separated
    # list (or JSON). Without it pydantic-settings parses the value as JSON first,
    # and a plain origin, or CORS_ORIGINS= left empty, stops the app starting.
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=list)

    login_max_attempts: int = 10
    login_window_seconds: int = 900

    log_level: str = "INFO"

    @field_validator("smarttt_api_key", "attendance_api_key", mode="before")
    @classmethod
    def _clean_key(cls, value: object) -> object:
        # Compared byte for byte by the other system: spaces, line breaks or
        # quotes pasted into a hosting dashboard would make an equal key differ.
        if isinstance(value, str):
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1].strip()
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            if value.strip().startswith("["):
                return json.loads(value)
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _production_requirements(self) -> Settings:
        if self.environment == "production":
            # The defaults point at a developer's machine; production must say where things are.
            missing = [
                name.upper()
                for name in ("database_url", "redis_url", "smarttt_base_url")
                if name not in self.model_fields_set
            ]
            if not self.smarttt_api_key:
                missing.append("SMARTTT_API_KEY")
            if missing:
                raise ValueError(f"Missing required settings in production: {', '.join(missing)}")
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production.")
            if self.run_inline:
                raise ValueError("RUN_INLINE must be false in production; solver runs belong on the worker.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
