"""An in-memory Smart Attendance: the departments administrators created there, each with its code."""

from __future__ import annotations

from typing import Any

import httpx

from tests.fake_smarttt import CS, EDU

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
        if request.url.path == PREFIX + "/departments":
            return httpx.Response(200, json={"success": True, "data": {"departments": self.departments}})
        return httpx.Response(404, json={"success": False})
