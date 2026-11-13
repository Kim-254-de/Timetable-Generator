"""My profile: the Director's name and password, both kept in Smart Attendance."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.clients import attendance as attendance_module
from tests.conftest import sign_in


def test_the_director_renames_themselves_and_every_session_shows_it(client, attendance):
    sign_in(client)
    me = client.get("/api/auth/me").json()["data"]
    assert (me["full_name"], me["email"]) == ("Dee Director", "dee@uni.ac.ke")

    response = client.patch("/api/auth/me", json={"full_name": "  Dr.  Dee   Mwangi "})
    assert response.status_code == 200, response.text
    assert response.json()["data"]["full_name"] == "Dr. Dee Mwangi"
    assert attendance.names
    assert client.get("/api/auth/me").json()["data"]["full_name"] == "Dr. Dee Mwangi"


def test_a_name_attendance_would_refuse_is_refused_here(client, attendance):
    sign_in(client)
    for bad in ("Dr", "<script>", "9 Lives"):
        response = client.patch("/api/auth/me", json={"full_name": bad})
        assert response.status_code == 422, bad
        assert response.json()["error"]["code"] == "INVALID_NAME"
    assert not attendance.names


def test_renaming_needs_the_csrf_token(client, attendance):
    sign_in(client)
    del client.headers["X-XSRF-TOKEN"]
    assert client.patch("/api/auth/me", json={"full_name": "Dee Mwangi"}).status_code == 403


def test_an_attendance_without_profile_calls_says_so_and_keeps_the_session(client, attendance):
    sign_in(client)
    attendance.profile_calls = False
    response = client.patch("/api/auth/me", json={"full_name": "Dee Mwangi"})
    assert response.status_code == 503
    assert response.json()["error"]["message"] == attendance_module.PROFILE_NOT_SUPPORTED
    assert client.get("/api/auth/me").status_code == 200


def test_the_director_changes_their_password_and_other_sessions_end(client, attendance):
    from app.main import create_app

    with TestClient(create_app()) as other:
        sign_in(other)
        sign_in(client)

        weak = client.post("/api/auth/password", json={"current_password": "right-password", "new_password": "simple"})
        assert (weak.status_code, weak.json()["error"]["code"]) == (422, "WEAK_PASSWORD")
        wrong = client.post("/api/auth/password", json={"current_password": "nope", "new_password": "New-Pass-2027"})
        assert (wrong.status_code, wrong.json()["error"]["code"]) == (400, "WRONG_PASSWORD")
        same = client.post(
            "/api/auth/password", json={"current_password": "right-password", "new_password": "right-password"}
        )
        assert same.status_code == 422  # no uppercase or digit: caught here before Attendance is asked

        done = client.post(
            "/api/auth/password", json={"current_password": "right-password", "new_password": "New-Pass-2027"}
        )
        assert done.status_code == 200, done.text
        assert attendance.password == "New-Pass-2027"
        assert client.get("/api/auth/me").status_code == 200
        assert other.get("/api/auth/me").status_code == 401
