"""A stand-in for Smart Attendance's /api/v1/integrations/generator/terms/{term}/submissions endpoint."""

from __future__ import annotations

import base64
import copy
import json
from typing import Any

import httpx

KEY = "test-attendance-key"


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


class FakeTeaching:
    """Departments' published teaching for any term; tests change `published` and `not_published`."""

    def __init__(self) -> None:
        self.courses: list[dict[str, Any]] = []
        self.published: list[dict[str, Any]] = []
        self.not_published: list[dict[str, Any]] = []
        self.calls: list[str] = []
        # Exams: published papers per department, and the invigilators named on the shared draft.
        self.exam_courses: list[dict[str, Any]] = []
        self.exam_published: list[dict[str, Any]] = []
        self.exam_not_published: list[dict[str, Any]] = []
        self.invigilators: dict[str, dict[str, dict[str, str]]] = {}
        # Moderation letters the Director uploads: what was read, and what was saved (published at once).
        self.letters_read: list[dict[str, Any]] = []
        self.letters_saved: list[dict[str, Any]] = []

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
        path = request.url.path.removeprefix("/api/v1/integrations/generator")
        self.calls.append(path)
        if path.startswith("/terms/") and path.endswith("/submissions"):
            data = {
                "term_id": path.split("/")[2],
                "courses": copy.deepcopy(self.courses),
                "published": copy.deepcopy(self.published),
                "not_published": copy.deepcopy(self.not_published),
            }
            return httpx.Response(200, json={"success": True, "data": data})
        if path.startswith("/terms/") and path.endswith("/exams"):
            data = {
                "term_id": path.split("/")[2],
                "courses": copy.deepcopy(self.exam_courses),
                "published": copy.deepcopy(self.exam_published),
                "not_published": copy.deepcopy(self.exam_not_published),
            }
            return httpx.Response(200, json={"success": True, "data": data})
        if path.startswith("/terms/") and path.endswith("/exam-list/read"):
            body = json.loads(request.content)
            self.letters_read.append(body)
            if base64.b64decode(body["file"])[:2] != b"PK":
                error = {"code": "VALIDATION_FAILED", "message": "This file is not a Word document (.docx)."}
                return httpx.Response(422, json={"success": False, "error": error})
            entry = {"line": 1, "codes": ["HRIM 111"], "title": "Records", "section": "", "sitting": "regular"}
            review = {"entries": [entry], "classes": [], "summary": {"papers": 1}}
            return httpx.Response(200, json={"success": True, "data": review})
        if path.startswith("/terms/") and path.endswith("/exam-list"):
            body = json.loads(request.content)
            self.letters_saved.append(body)
            if body["department_code"] != "DHRM":
                error = {"code": "NOT_FOUND", "message": f"No department has the code {body['department_code']}."}
                return httpx.Response(404, json={"success": False, "error": error})
            rows = [("hrm-y1", 3, "regular")]
            papers = [paper(f"letter-{i}", p["codes"], rows) for i, p in enumerate(body["papers"])]
            self.exam_courses = [c for c in self.exam_courses if c["id"] != "hrm-y1"] + [
                course("hrm-y1", "DHRM", "BSC.HRIM", 3)
            ]
            self.exam_published = [d for d in self.exam_published if d["code"] != "DHRM"] + [
                {
                    "code": "DHRM",
                    "name": "Health Records",
                    "published_at": "2026-11-13T09:00:00+00:00",
                    "papers": papers,
                }
            ]
            data = {"created": len(papers), "updated": 0, "switched": 0, "published": len(papers)}
            return httpx.Response(200, json={"success": True, "data": data})
        if path.startswith("/terms/") and path.endswith("/invigilators"):
            return httpx.Response(200, json={"success": True, "data": copy.deepcopy(self.invigilators)})
        return httpx.Response(404, json={"success": False})


def paper(pid: str, codes: list[str], rows: list[tuple[str, int, str]], staff: str = "STF/9") -> dict[str, Any]:
    """A published exam paper; rows are (course id, students, mode)."""
    return {
        "id": pid,
        "codes": codes,
        "title": f"{codes[0]} paper",
        "examiner": {"staff_number": staff, "name": f"Dr. {staff}"},
        "notes": "",
        "rows": [{"course_id": c, "students": n, "mode": m} for c, n, m in rows],
        "students": sum(n for _c, n, _m in rows),
    }
