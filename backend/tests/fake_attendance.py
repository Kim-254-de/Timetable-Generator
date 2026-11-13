"""An in-memory Smart Attendance: the departments administrators created there, each with its code,
and sign-in for the timetabling office it invites ("director"; anyone else is another officer)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from tests.fake_smarttt import CS, DIRECTOR, EDU, LECTURER_ACCOUNT

API_KEY = "test-attendance-key"
PREFIX = "/api/v1/integrations/generator"


def department(
    attendance_id: str, name: str, code: str | None, smarttt_id: int | None, lecturers: int = 0
) -> dict[str, Any]:
    return {
        "id": attendance_id,
        "name": name,
        "code": code,
        "smartttDepartmentId": smarttt_id,
        "lecturerCount": lecturers,
    }


class FakeAttendance:
    def __init__(self) -> None:
        # The same two departments SMARTTT's snapshot has, linked by SMARTTT's id.
        self.departments: list[dict[str, Any]] = [
            department("att-cs", "Computer Science", "DCOMP", CS, lecturers=5),
            department("att-edu", "Education", "DEDU", EDU, lecturers=9),
        ]
        self.down = False
        self.calls = 0
        # The Director's own account, as My profile changes it.
        self.password = "right-password"
        self.names: dict[str, str] = {}
        self.profile_calls = True  # False: an Attendance from before the profile calls

    def identity(self, account: str, office: bool) -> dict[str, Any]:
        default = "Dee Director" if office else "Max Manager"
        name = self.names.get(account, default)
        return {
            "account": {
                "id": account,
                "full_name": name,
                "email": f"{default.split()[0].lower()}@uni.ac.ke",
                "university_id": None,
            },
            "timetabling_office": office,
        }

    def add(self, attendance_id: str, name: str, code: str | None = None, smarttt_id: int | None = None) -> None:
        self.departments.append(department(attendance_id, name, code, smarttt_id))

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.down:
            raise httpx.ConnectError("Attendance is down", request=request)
        if request.headers.get("X-API-Key") != API_KEY:
            return httpx.Response(401, json={"success": False, "error": {"code": "INVALID_API_KEY"}})
        if request.url.path == PREFIX + "/authenticate":
            body = json.loads(request.content)
            if body.get("password") != self.password:
                return httpx.Response(200, json={"success": True, "data": {"authenticated": False}})
            office = body.get("identifier") == "director"
            data = {"authenticated": True, **self.identity(DIRECTOR if office else LECTURER_ACCOUNT, office)}
            return httpx.Response(200, json={"success": True, "data": data})
        if request.url.path == PREFIX + "/identity" and request.method == "PATCH" and self.profile_calls:
            body = json.loads(request.content)
            if body["account_id"] != DIRECTOR:
                return httpx.Response(404, json={"success": False, "error": {"code": "NOT_FOUND"}})
            self.names[DIRECTOR] = " ".join(body["full_name"].split())
            return httpx.Response(200, json={"success": True, "data": self.identity(DIRECTOR, True)})
        if request.url.path == PREFIX + "/password" and self.profile_calls:
            body = json.loads(request.content)
            if body["current_password"] != self.password:
                data: dict[str, Any] = {"changed": False, "reason": "wrong_password"}
            elif body["new_password"] == self.password:
                data = {"changed": False, "reason": "same_password"}
            else:
                self.password = body["new_password"]
                data = {"changed": True}
            return httpx.Response(200, json={"success": True, "data": data})
        if request.url.path == PREFIX + "/identity" and request.method == "GET":
            account = request.url.params["account_id"]
            return httpx.Response(200, json={"success": True, "data": self.identity(account, account == DIRECTOR)})
        if request.url.path == PREFIX + "/departments":
            return httpx.Response(200, json={"success": True, "data": {"departments": self.departments}})
        return httpx.Response(404, json={"success": False})
