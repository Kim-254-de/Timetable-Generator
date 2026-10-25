"""An in-memory SMARTTT speaking the Generator integration contract (/api/v1/integrations/generator/)."""

from __future__ import annotations

import copy
import json
from typing import Any

import httpx

PREFIX = "/api/v1/integrations/generator"
API_KEY = "test-generator-key"
TERM = {
    "id": "22222222-2222-2222-2222-222222222222",
    "academic_year": "2026/2027",
    "semester": 1,
    "start_date": "2026-09-21",
    "end_date": "2026-12-18",
    "is_current": True,
}
DIRECTOR = "dddddddd-0000-0000-0000-000000000001"
LECTURER_ACCOUNT = "dddddddd-0000-0000-0000-000000000002"
JANE = "aaaaaaaa-0000-0000-0000-000000000001"

CS, EDU = 1, 2
ROOMS = [
    {
        "id": "r-hall-1",
        "code": "STB 1",
        "name": "STB 1",
        "building": "STB",
        "capacity": 120,
        "capacity_confirmed": True,
        "room_type": "lecture_hall",
        "status": "active",
    },
    {
        "id": "r-hall-2",
        "code": "STB 2",
        "name": "STB 2",
        "building": "STB",
        "capacity": 120,
        "capacity_confirmed": True,
        "room_type": "lecture_hall",
        "status": "active",
    },
    {
        "id": "r-utc-1",
        "code": "UTC 1",
        "name": "UTC 1",
        "building": "UTC",
        "capacity": 200,
        "capacity_confirmed": True,
        "room_type": "lecture_hall",
        "status": "active",
    },
    {
        "id": "r-lab-1",
        "code": "LAB 1",
        "name": "LAB 1",
        "building": "STB",
        "capacity": 40,
        "capacity_confirmed": True,
        "room_type": "lab",
        "status": "active",
    },
    {
        "id": "r-closed",
        "code": "OLD 1",
        "name": "OLD 1",
        "building": "OLD",
        "capacity": 500,
        "capacity_confirmed": True,
        "room_type": "lecture_hall",
        "status": "closed",
    },
]


def snapshot_data(published: list[dict[str, Any]] | None = None, version: int | None = None) -> dict[str, Any]:
    return {
        "term": TERM,
        "taken_at": "2026-09-01T00:00:00+03:00",
        "teaching_week": {"days": ["MON", "TUE", "WED", "THU", "FRI"], "start": "07:00", "end": "19:00"},
        "departments": [
            {
                "id": CS,
                "code": "CS",
                "name": "Computer Science",
                "faculty": "Science",
                "lecturers": {"full_time": 3, "part_time": 1},
            },
            {
                "id": EDU,
                "code": "ED",
                "name": "Education",
                "faculty": "Education",
                "lecturers": {"full_time": 4, "part_time": 0},
            },
        ],
        "lecturers": [],
        "rooms": ROOMS,
        "programs": [
            {
                "id": 10,
                "code": "BSC.COMP SCI",
                "name": "BSc Computer Science",
                "department_id": CS,
                "duration_years": 4,
            },
            {"id": 20, "code": "BED.MATH/CHEM", "name": "BEd Maths/Chem", "department_id": EDU, "duration_years": 4},
        ],
        "units": [
            {"id": 101, "code": "COSC 103", "name": "Intro to Computing", "department_id": CS, "credit_hours": 3},
            {"id": 102, "code": "COSC 110", "name": "Programming", "department_id": CS, "credit_hours": 3},
            {"id": 201, "code": "EDFO 111", "name": "Foundations", "department_id": EDU, "credit_hours": 3},
            {"id": 202, "code": "SMED 100", "name": "Science lab", "department_id": EDU, "credit_hours": 3},
        ],
        "curricula": [
            {
                "program_id": 10,
                "study_year": 1,
                "study_semester": 1,
                "units": [
                    {"unit_id": 101, "is_core": True, "is_elective": False, "credit_hours": 3},
                    {"unit_id": 102, "is_core": True, "is_elective": False, "credit_hours": 3},
                ],
            },
            {
                "program_id": 20,
                "study_year": 1,
                "study_semester": 1,
                "units": [
                    {"unit_id": 101, "is_core": True, "is_elective": False, "credit_hours": 3},
                    {"unit_id": 201, "is_core": True, "is_elective": False, "credit_hours": 3},
                    {"unit_id": 202, "is_core": True, "is_elective": False, "credit_hours": 3},
                ],
            },
        ],
        "class_sizes": [
            {"program_id": 10, "study_year": 1, "study_semester": 1, "students": 90},
            {"program_id": 20, "study_year": 1, "study_semester": 1, "students": 150},
        ],
        "registrations": [],
        "published": {"version": version, "sessions": published or []},
        "warnings": [],
    }


class FakeSmarttt:
    def __init__(self) -> None:
        self.snapshot = snapshot_data()
        self.publications: dict[int, dict[str, Any]] = {}
        self.payloads: list[dict[str, Any]] = []
        self.refuse_publish: dict[str, Any] | None = None
        self.down = False  # True: SMARTTT can't be reached

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)

    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectError("SMARTTT is down", request=request)
        if request.headers.get("X-API-Key") != API_KEY:
            return httpx.Response(403, json={"detail": "A valid X-API-Key header is required."})
        route = request.url.path[len(PREFIX) :]
        body = json.loads(request.content) if request.content else {}
        if route == "/terms/":
            return httpx.Response(200, json={"terms": [TERM]})
        if route == "/snapshot/":
            return httpx.Response(200, json=copy.deepcopy(self.snapshot))
        if route == "/publish/":
            self.payloads.append(body)
            if self.refuse_publish:
                return httpx.Response(409, json=self.refuse_publish)
            missing = publish_payload_problems(body)
            if missing:
                return httpx.Response(400, json={"code": "invalid_payload", "detail": "Not valid.", "errors": missing})
            latest = max(self.publications, default=None)
            if body["based_on_version"] != latest:
                return httpx.Response(409, json={"code": "stale_base", "detail": "Stale.", "latest_version": latest})
            if not body["term_id"] and not (body.get("term_start") and body.get("term_end")):
                return httpx.Response(422, json={"code": "term_dates_required", "detail": "Give the term its dates."})
            # Like SMARTTT: a null term_id is found (or created) by year and semester.
            term_id = body["term_id"] or (TERM["id"] if body["academic_year"] == TERM["academic_year"] else NEW_TERM)
            publication = {
                "term_id": term_id,
                "version": body["version"],
                "based_on_version": body["based_on_version"],
                "session_count": len(body["sessions"]),
                "changes": {"added": [s["key"] for s in body["sessions"]], "moved": [], "removed": [], "unchanged": 0},
                # SMARTTT's id for each unit: the one sent, else a new one.
                "units": {s["unit_code"]: s["unit_id"] or 900 + i for i, s in enumerate(body["sessions"])},
            }
            self.publications[body["version"]] = publication
            return httpx.Response(201, json=publication)
        return httpx.Response(404, json={"detail": f"No route {route}"})


NEW_TERM = "7d1f5c2e-0000-4000-8000-00000000a001"

# What SMARTTT's publish endpoint requires of each session
# (apps/integrations/generator_publish.py there).
SESSION_FIELDS = ("key", "unit_code", "unit_name", "department", "room", "day_of_week", "start_time", "end_time")
ROOM_FIELDS = ("code", "capacity", "room_type")
ROW_FIELDS = ("label", "program_code", "year_of_study")


def publish_payload_problems(body: dict[str, Any]) -> list[str]:
    problems = [f for f in ("academic_year", "semester", "version", "published_by", "sessions") if f not in body]
    for s in body.get("sessions") or []:
        problems += [f"{s.get('key')}.{f}" for f in SESSION_FIELDS if s.get(f) in (None, "")]
        problems += [f"{s.get('key')}.room.{f}" for f in ROOM_FIELDS if not (s.get("room") or {}).get(f)]
        if not s.get("class_rows"):
            problems.append(f"{s.get('key')}.class_rows")
        for row in s.get("class_rows") or []:
            problems += [f"{s.get('key')}.class_rows.{f}" for f in ROW_FIELDS if row.get(f) in (None, "")]
    return problems
