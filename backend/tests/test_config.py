from __future__ import annotations

import pytest

from app.config import Settings

PRODUCTION = {
    "ENVIRONMENT": "production",
    "DATABASE_URL": "postgresql+psycopg://generator:secret@db:5432/generator",
    "REDIS_URL": "redis://redis:6379/0",
    "SMARTTT_BASE_URL": "https://api.nextup.co.ke",
    "SMARTTT_API_KEY": "s" * 48,
    "COOKIE_SECURE": "true",
    "RUN_INLINE": "false",
}


def test_production_starts_with_everything_set(monkeypatch):
    for name, value in PRODUCTION.items():
        monkeypatch.setenv(name, value)
    assert Settings(_env_file=None).redis_url == "redis://redis:6379/0"  # type: ignore[call-arg]


@pytest.mark.parametrize("unset", ["DATABASE_URL", "REDIS_URL", "SMARTTT_BASE_URL", "SMARTTT_API_KEY"])
def test_production_refuses_to_start_without(monkeypatch, unset):
    for name, value in PRODUCTION.items():
        if name != unset:
            monkeypatch.setenv(name, value)
    monkeypatch.delenv(unset, raising=False)
    with pytest.raises(ValueError, match=unset):
        Settings(_env_file=None)  # type: ignore[call-arg]
