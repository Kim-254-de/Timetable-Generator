"""Why sign-in could not ask Smart Attendance is said on the sign-in screen, one reason each."""

from __future__ import annotations

import httpx
import pytest

from app.clients import attendance as attendance_module
from app.clients.attendance import AttendanceClient, AttendanceSignInError
from app.config import get_settings
from tests.fake_attendance import FakeAttendance


def _client(handler, base_url: str = "http://attendance.test", key: str = "test-attendance-key") -> AttendanceClient:
    settings = get_settings().model_copy(update={"attendance_base_url": base_url, "attendance_api_key": key})
    return AttendanceClient(settings, transport=httpx.MockTransport(handler))


def _login(client):
    return client.post("/api/auth/login", json={"identifier": "director", "password": "right-password"})


def test_an_address_ending_in_api_v1_still_reaches_attendance():
    fake = FakeAttendance()
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return fake.handle(request)

    for base in ("http://attendance.test/api/v1", "http://attendance.test/api/v1/", " http://attendance.test/ "):
        assert _client(handler, base).authenticate("director", "right-password")["timetabling_office"] is True
    assert set(seen) == {"/api/v1/integrations/generator/authenticate"}


@pytest.mark.parametrize(
    ("handler", "base_url", "key", "expected"),
    [
        (FakeAttendance().handle, "", "test-attendance-key", attendance_module.SIGN_IN_NOT_SET_UP),
        (FakeAttendance().handle, "http://attendance.test", "wrong-key", attendance_module.SIGN_IN_KEY_REFUSED),
        (
            lambda r: httpx.Response(404, json={}),
            "http://attendance.test",
            "k",
            attendance_module.SIGN_IN_WRONG_ADDRESS,
        ),
        (
            lambda r: httpx.Response(502, text="Bad gateway"),
            "http://attendance.test",
            "k",
            attendance_module.SIGN_IN_FAILED,
        ),
        (lambda r: httpx.Response(400, json={}), "http://attendance.test", "k", attendance_module.SIGN_IN_FAILED),
    ],
)
def test_each_failure_has_its_own_reason(handler, base_url, key, expected):
    with pytest.raises(AttendanceSignInError) as caught:
        _client(handler, base_url, key).authenticate("director", "right-password")
    assert caught.value.message == expected


def test_attendance_down_is_said_on_the_sign_in_screen(client, attendance):
    attendance.down = True
    response = _login(client)
    assert response.status_code == 503
    error = response.json()["error"]
    assert (error["code"], error["message"]) == ("ATTENDANCE_UNAVAILABLE", attendance_module.SIGN_IN_UNREACHABLE)


def test_a_refused_key_is_said_on_the_sign_in_screen(client):
    attendance_module.set_attendance(_client(FakeAttendance().handle, key="wrong-key"))
    response = _login(client)
    assert response.status_code == 503
    assert "ATTENDANCE_API_KEY" in response.json()["error"]["message"]


def test_keys_pasted_with_spaces_or_quotes_are_cleaned():
    from app.config import Settings

    for raw in ("  abc123\n", '"abc123"', "'abc123' ", "abc123"):
        settings = Settings(attendance_api_key=raw, smarttt_api_key=raw)
        assert (settings.attendance_api_key, settings.smarttt_api_key) == ("abc123", "abc123")
