"""A stand-in for the Timetable Allocator's /api/integrations/generator endpoint."""

from __future__ import annotations

import copy
from typing import Any

import httpx

KEY = "test-inbound-key"


def course(cid: str, department: str, programme: str, students: int, year: int = 1) -> dict[str, Any]:
    return {
        "id": cid,
        "department_code": department,
        "programme": programme,
        "year": year,
        "semester": 1,
        "sub_class": "",
        "label": f"{programme} Y{year}S1",
        "students": students,
    }


def group(
    gid: str, label: str, members: list[tuple[str, int]], staff: str | None, name: str = "", **hours: float
) -> dict[str, Any]:
    return {
        "id": gid,
        "key": "",
        "label": label,
        "members": [{"course_id": c, "students": n} for c, n in members],
        "students": sum(n for _c, n in members),
        "lecturer": {"staff_number": staff, "name": name or f"Dr. {staff}", "employment_type": "full_time"}
        if staff
        else None,
        "lecture_hours": hours.get("lecture_hours"),
        "practical_hours": hours.get("practical_hours"),
        "cf_hours": hours.get("cf_hours"),
    }


def unit(
    uid: str, code: str, courses: list[str], groups: list[dict[str, Any]], hours: int = 3, length: int = 3
) -> dict[str, Any]:
    return {
        "id": uid,
        "code": code,
        "title": f"{code} title",
        "weekly_hours": hours,
        "class_length": length,
        "room_type": "lecture_hall",
        "course_ids": courses,
        "groups": groups,
    }


class FakeAllocator:
    """Departments' published teaching for any term; tests change `published` and `not_published`."""

    def __init__(self) -> None:
        self.courses: list[dict[str, Any]] = []
        self.published: list[dict[str, Any]] = []
        self.not_published: list[dict[str, Any]] = []
        self.calls: list[str] = []

    def publish(self, code: str, name: str, units: list[dict[str, Any]], at: str = "2026-10-20T08:00:00+00:00") -> None:
        self.not_published = [d for d in self.not_published if d["code"] != code]
        self.published = [d for d in self.published if d["code"] != code] + [
            {"code": code, "name": name, "published_at": at, "published_by": "A Cod (STF/1)", "units": units}
        ]

    def waiting(self, code: str, name: str) -> None:
        self.published = [d for d in self.published if d["code"] != code]
        self.not_published.append(
            {"code": code, "name": name, "reopened_at": None, "last_published_at": None, "changed_units": []}
        )

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("X-API-Key") != KEY:
            return httpx.Response(401, json={"success": False})
        path = request.url.path.removeprefix("/api/integrations/generator")
        self.calls.append(path)
        if path.startswith("/terms/") and path.endswith("/submissions"):
            data = {
                "term_id": path.split("/")[2],
                "courses": copy.deepcopy(self.courses),
                "published": copy.deepcopy(self.published),
                "not_published": copy.deepcopy(self.not_published),
            }
            return httpx.Response(200, json={"success": True, "data": data})
        return httpx.Response(404, json={"success": False})
