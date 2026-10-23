from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("SMARTTT_API_KEY", "test-generator-key")
os.environ.setdefault("ALLOCATOR_API_KEY", "test-allocator-key")
os.environ.setdefault("ATTENDANCE_BASE_URL", "http://attendance.test")
os.environ.setdefault("ATTENDANCE_API_KEY", "test-attendance-key")
os.environ.setdefault("ALLOCATOR_CLIENT_KEY", "test-inbound-key")
os.environ.setdefault("RUN_INLINE", "true")
os.environ.setdefault("SOLVER_WORKERS", "2")

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app import models  # noqa: F401  (registers the tables)
from app.clients.allocator import AllocatorClient, set_allocator
from app.clients.attendance import AttendanceClient, set_attendance
from app.clients.smarttt import SmartttClient, set_smarttt
from app.config import get_settings
from app.db import Base, get_engine, get_sessionmaker
from app.services.departments import reset_sync_state
from tests.fake_allocator import FakeAllocator
from tests.fake_attendance import FakeAttendance
from tests.fake_smarttt import FakeSmarttt


@pytest.fixture(autouse=True)
def _database() -> Iterator[None]:
    os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or "sqlite://"
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def smarttt() -> Iterator[FakeSmarttt]:
    fake = FakeSmarttt()
    client = SmartttClient(get_settings(), transport=fake.transport())
    set_smarttt(client)
    yield fake
    set_smarttt(None)
    client.close()


@pytest.fixture
def attendance() -> Iterator[FakeAttendance]:
    fake = FakeAttendance()
    client = AttendanceClient(get_settings(), transport=fake.transport())
    set_attendance(client)
    reset_sync_state()
    yield fake
    set_attendance(None)
    client.close()


@pytest.fixture
def allocator() -> Iterator[FakeAllocator]:
    fake = FakeAllocator()
    client = AllocatorClient(get_settings(), transport=fake.transport())
    set_allocator(client)
    yield fake
    set_allocator(None)
    client.close()


@pytest.fixture
def db() -> Iterator[Session]:
    session = get_sessionmaker()()
    yield session
    session.close()


@pytest.fixture
def client(smarttt: FakeSmarttt, attendance: FakeAttendance) -> Iterator[TestClient]:
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def sign_in(client: TestClient, identifier: str = "director") -> TestClient:
    response = client.post("/api/auth/login", json={"identifier": identifier, "password": "right-password"})
    assert response.status_code == 200, response.text
    client.headers["X-XSRF-TOKEN"] = client.cookies["tg_xsrf"]
    return client


def departments(
    client: TestClient, settings: dict[str, dict[str, object]] | None = None
) -> dict[str, dict[str, object]]:
    """
    The departments (read from the fake Attendance), by name, after giving
    each named one the Generator's own code and lecturer count from `settings`.
    """
    found = {d["name"]: d for d in client.get("/api/departments").json()["data"]["departments"]}
    for name, fields in (settings or {}).items():
        response = client.patch(f"/api/departments/{found[name]['id']}", json=fields)
        assert response.status_code == 200, response.text
        found[name] = response.json()["data"]
    return found
