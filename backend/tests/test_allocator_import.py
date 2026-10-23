"""
Departments publish their teaching in the Allocator; the Director imports it,
adds rooms, generates and publishes, with each group's lecturer.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DraftSession, Group, Publication
from app.solver.model import covered
from tests.conftest import sign_in
from tests.fake_allocator import FakeAllocator, course, group, unit


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()["data"]


def new_term(client: TestClient) -> str:
    term = ok(client.post("/api/terms", json={"academic_year": "2026/2027", "semester": 1, "name": "Sep-Dec 2026"}))
    rows = [{"code": f"LH {i}", "building": "LH", "capacity": "200", "room_type": "Lecture hall"} for i in range(1, 5)]
    ok(client.post("/api/rooms/bulk", json={"rows": rows}))
    return str(term["id"])


def cs_and_ed(allocator: FakeAllocator) -> None:
    """CS teaches COSC 103 in two groups and COSC 110 to Education's students; one lecturer has three of them."""
    allocator.courses = [course("c-cs1", "CS", "BSC.CS", 120), course("c-ed1", "ED", "BED.SCI", 80)]
    allocator.publish(
        "CS",
        "Computer Science",
        [
            unit(
                "u-103",
                "COSC 103",
                ["c-cs1"],
                [
                    group("g-103a", "GR A", [("c-cs1", 60)], "STF/9", "Dr. Jane Otieno (FT)", lecture_hours=30),
                    group("g-103b", "GR B", [("c-cs1", 60)], "STF/9", "Dr. Jane Otieno (FT)"),
                ],
            ),
            unit("u-110", "COSC 110", ["c-ed1"], [group("g-110", "", [("c-ed1", 80)], "STF/9")]),
        ],
    )


def offerings(client: TestClient, term_id: str) -> dict[str, Any]:
    return {o["unit_code"]: o for o in ok(client.get(f"/api/terms/{term_id}/offerings"))}


def test_import_creates_class_rows_units_and_groups_with_lecturers(client, allocator):
    sign_in(client)
    term_id = new_term(client)
    cs_and_ed(allocator)
    allocator.waiting("ED", "Education")

    status = ok(client.get(f"/api/terms/{term_id}/departments"))
    assert [(d["code"], d["published"], d["needs_import"]) for d in status["departments"]] == [
        ("CS", True, True),
        ("ED", False, False),
    ]
    result = ok(client.post(f"/api/terms/{term_id}/departments/import"))
    assert result["departments"] == ["CS"] and result["not_published"] == [{"code": "ED", "name": "Education"}]
    assert sorted(result["units"]["CS"]["added"]) == ["COSC 103", "COSC 110"]
    assert sorted(result["class_rows"]["added"]) == ["BED.SCI Y1S1", "BSC.CS Y1S1"]

    units = offerings(client, term_id)
    cosc103 = units["COSC 103"]
    assert cosc103["from_allocator"] is True and cosc103["source"] == "allocator"
    assert [(g["label"], g["student_count"], g["lecturer_staff_number"]) for g in cosc103["groups"]] == [
        ("GR A", 60, "STF/9"),
        ("GR B", 60, "STF/9"),
    ]
    rows = {r["label"]: r for r in ok(client.get(f"/api/terms/{term_id}/class-rows"))}
    assert rows["BED.SCI Y1S1"]["student_count"] == 80 and rows["BED.SCI Y1S1"]["from_allocator"] is True
    departments = {d["code"] for d in ok(client.get("/api/departments"))}
    assert {"CS", "ED"} <= departments
    assert ok(client.get(f"/api/terms/{term_id}/departments"))["needs_import"] == 0

    # Importing again changes nothing; then CS's changes come in place.
    again = ok(client.post(f"/api/terms/{term_id}/departments/import"))
    assert again["units"] == {} and again["class_rows"] == {"added": [], "changed": [], "removed": []}
    allocator.publish(
        "CS",
        "Computer Science",
        [unit("u-103", "COSC 103", ["c-cs1"], [group("g-103a", "", [("c-cs1", 120)], "STF/9")], hours=4, length=2)],
        at="2026-10-21T08:00:00+00:00",
    )
    assert ok(client.get(f"/api/terms/{term_id}/departments"))["needs_import"] == 1
    changed = ok(client.post(f"/api/terms/{term_id}/departments/import"))
    assert changed["units"]["CS"] == {"added": [], "changed": ["COSC 103"], "removed": ["COSC 110"]}
    units = offerings(client, term_id)
    assert set(units) == {"COSC 103"}
    assert units["COSC 103"]["weekly_hours"] == 4 and units["COSC 103"]["session_length"] == 2
    assert [(g["label"], g["student_count"]) for g in units["COSC 103"]["groups"]] == [("", 120)]


def test_imported_rows_are_edited_in_the_allocator(client, allocator):
    sign_in(client)
    term_id = new_term(client)
    cs_and_ed(allocator)
    ok(client.post(f"/api/terms/{term_id}/departments/import"))
    cosc103 = offerings(client, term_id)["COSC 103"]
    refused = client.patch(f"/api/offerings/{cosc103['id']}", json={"weekly_hours": 5})
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "FROM_ALLOCATOR"
    assert client.delete(f"/api/offerings/{cosc103['id']}").status_code == 409
    assert client.delete(f"/api/groups/{cosc103['groups'][0]['id']}").status_code == 409
    row = next(r for r in ok(client.get(f"/api/terms/{term_id}/class-rows")) if r["label"] == "BSC.CS Y1S1")
    assert client.patch(f"/api/class-rows/{row['id']}", json={"student_count": 5}).status_code == 409
    # The hours a class row can't be taught stay the Director's.
    assert ok(client.patch(f"/api/class-rows/{row['id']}", json={"unavailable": [0, 1]}))["unavailable"] == [0, 1]
    proposed = ok(client.post(f"/api/terms/{term_id}/groups/propose", json={"replace": True}))
    assert proposed["proposed"] == 0


def _lecturer_slots(db: Session, draft_id: str, staff: str) -> list[set[int]]:
    groups = {g.id for g in db.scalars(select(Group).where(Group.lecturer_staff_number == staff))}
    sessions = db.scalars(select(DraftSession).where(DraftSession.draft_id == uuid.UUID(draft_id)))
    return [set(covered(s.start_slot, s.length)) for s in sessions if s.group_id in groups]


def test_the_solver_never_puts_a_lecturer_in_two_classes_at_once(client, allocator, db):
    sign_in(client)
    term_id = new_term(client)
    cs_and_ed(allocator)
    # Education gives the same person (same staff number) a class of its own.
    allocator.publish(
        "ED", "Education", [unit("u-edfo", "EDFO 111", ["c-ed1"], [group("g-edfo", "", [("c-ed1", 80)], "stf/9")])]
    )
    ok(client.post(f"/api/terms/{term_id}/departments/import"))
    run = ok(client.post("/api/runs", json={"term_id": term_id, "time_limit_s": 20}))
    assert run["status"] == "succeeded", run
    slots = _lecturer_slots(db, run["draft_id"], "STF/9")
    assert len(slots) == 4  # COSC 103 GR A and GR B, COSC 110 and EDFO 111
    for i, a in enumerate(slots):
        for b in slots[i + 1 :]:
            assert not a & b
    grid = ok(client.get(f"/api/drafts/{run['draft_id']}?view=row"))
    assert grid["draft"]["violations"] == []
    assert any(c.get("lecturer") == "Dr. Jane Otieno (FT)" for e in grid["entities"] for c in e["cells"])


def test_a_lecturer_given_more_than_the_week_is_named_before_solving(client, allocator):
    sign_in(client)
    term_id = new_term(client)
    allocator.courses = [course(f"c{i}", "CS", f"BSC.P{i}", 50) for i in range(4)]
    units = [
        unit(
            f"u{i}",
            f"COSC {200 + i}",
            [f"c{i}"],
            [group(f"g{i}", "", [(f"c{i}", 50)], "STF/1", "Dr. Busy")],
            hours=16,
            length=4,
        )
        for i in range(4)
    ]
    allocator.publish("CS", "Computer Science", units)
    ok(client.post(f"/api/terms/{term_id}/departments/import"))
    run = ok(client.post("/api/runs", json={"term_id": term_id, "time_limit_s": 20}))
    assert run["status"] == "failed"
    reasons = run["failure"]["reasons"]
    assert any(r["rule"] == "H13" and "Dr. Busy is given 64 teaching hours" in r["message"] for r in reasons)


def test_a_late_department_is_added_without_moving_published_classes(client, allocator, db):
    sign_in(client)
    term_id = new_term(client)
    cs_and_ed(allocator)
    allocator.waiting("ED", "Education")
    ok(client.post(f"/api/terms/{term_id}/departments/import"))
    first = ok(client.post("/api/runs", json={"term_id": term_id, "time_limit_s": 20}))
    ok(client.post(f"/api/drafts/{first['draft_id']}/publish", json={}))
    published = {
        s.key: (s.start_slot, s.smarttt_room_id)
        for s in db.scalars(select(DraftSession).where(DraftSession.draft_id == uuid.UUID(first["draft_id"])))
    }

    # Education publishes late, with the same lecturer, and is imported.
    allocator.publish(
        "ED",
        "Education",
        [unit("u-edfo", "EDFO 111", ["c-ed1"], [group("g-edfo", "", [("c-ed1", 80)], "STF/9")])],
        at="2026-10-22T08:00:00+00:00",
    )
    ok(client.post(f"/api/terms/{term_id}/departments/import"))
    resolved = ok(
        client.post(f"/api/drafts/{first['draft_id']}/resolve", json={"keep_published": True, "time_limit_s": 20})
    )
    assert resolved["status"] == "succeeded", resolved
    db.expire_all()
    after = {
        s.key: (s.start_slot, s.smarttt_room_id)
        for s in db.scalars(select(DraftSession).where(DraftSession.draft_id == uuid.UUID(resolved["draft_id"])))
    }
    assert {k: after[k] for k in published} == published
    assert "EDFO111-MAIN-1" in after
    slots = _lecturer_slots(db, resolved["draft_id"], "STF/9")
    assert len(slots) == 4 and all(not (a & b) for i, a in enumerate(slots) for b in slots[i + 1 :])


def test_keeping_published_classes_needs_a_published_timetable(client, allocator):
    sign_in(client)
    term_id = new_term(client)
    cs_and_ed(allocator)
    ok(client.post(f"/api/terms/{term_id}/departments/import"))
    first = ok(client.post("/api/runs", json={"term_id": term_id, "time_limit_s": 20}))
    refused = client.post(f"/api/drafts/{first['draft_id']}/resolve", json={"keep_published": True})
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "NOTHING_PUBLISHED"


def test_the_published_timetable_carries_each_lecturer(client, allocator, db):
    sign_in(client)
    term_id = new_term(client)
    cs_and_ed(allocator)
    ok(client.post(f"/api/terms/{term_id}/departments/import"))
    run = ok(client.post("/api/runs", json={"term_id": term_id, "time_limit_s": 20}))
    ok(client.post(f"/api/drafts/{run['draft_id']}/publish", json={}))
    publication = db.scalar(select(Publication))
    assert publication is not None and publication.payload is not None
    sessions = publication.payload["sessions"]
    assert sessions and all(s["lecturer_staff_number"] == "STF/9" for s in sessions)
    assert {s["lecturer_name"] for s in sessions} == {"Dr. Jane Otieno (FT)", "Dr. STF/9"}
    xlsx = client.get(f"/api/drafts/{run['draft_id']}/export.xlsx?view=row")
    assert xlsx.status_code == 200


def test_import_needs_a_published_department(client, allocator):
    sign_in(client)
    term_id = new_term(client)
    allocator.waiting("CS", "Computer Science")
    refused = client.post(f"/api/terms/{term_id}/departments/import")
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "NOTHING_PUBLISHED"
