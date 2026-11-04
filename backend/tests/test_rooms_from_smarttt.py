"""The rooms the admin uploads to SMARTTT come into the Generator, by code."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ExamDraft, ExamPaper, ExamPlacement, ExamSeat, Room, Term
from tests.conftest import sign_in
from tests.fake_smarttt import FakeSmarttt
from tests.fake_teaching import FakeTeaching
from tests.test_exams import ok, setup_exams


def _placement(db: Session) -> uuid.UUID:
    """A placement to hang an exam seat on."""
    term = Term(academic_year="2030/2031", semester=1)
    db.add(term)
    db.flush()
    paper = ExamPaper(term_id=term.id, allocator_ref=f"p-{uuid.uuid4().hex[:8]}", department_id=1, codes=["X 1"], title="X")
    draft = ExamDraft(term_id=term.id, name="d")
    db.add_all([paper, draft])
    db.flush()
    placement = ExamPlacement(draft_id=draft.id, paper_id=paper.id, day=date(2030, 1, 7), session=0)
    db.add(placement)
    db.flush()
    return placement.id


def room(code: str, capacity: int, building: str = "UTC", room_type: str = "lecture_hall", status: str = "active"):
    return {
        "code": code,
        "name": code,
        "building": building,
        "capacity": capacity,
        "room_type": room_type,
        "status": status,
    }


def test_sync_adds_and_updates_by_code_and_keeps_the_generators_own_settings(client, smarttt: FakeSmarttt):
    sign_in(client)
    ok(client.post("/api/rooms", json={"code": "UTC 1", "building": "UTC", "capacity": 100}))
    ok(client.post("/api/rooms", json={"code": "OLD 9", "building": "OLD", "capacity": 30}))
    rooms = {r["code"]: r for r in ok(client.get("/api/rooms"))}
    ok(client.patch(f"/api/rooms/{rooms['UTC 1']['id']}", json={"exam_seats": 80, "for_exams": False}))
    smarttt.rooms = [
        room("utc 1", 300),
        room("LAB 2", 40, building="SCI", room_type="lab"),
        room("STB 3", 120, building="STB", status="maintenance"),
        room("ODD 1", 50, room_type="studio"),
    ]
    result = ok(client.post("/api/rooms/sync"))
    assert result == {"added": ["LAB 2", "STB 3", "ODD 1"], "updated": ["utc 1"], "only_here": ["OLD 9"], "merged": []}
    rooms = {r["code"]: r for r in ok(client.get("/api/rooms"))}
    assert (rooms["UTC 1"]["capacity"], rooms["UTC 1"]["exam_seats"], rooms["UTC 1"]["for_exams"]) == (300, 80, False)
    assert (rooms["LAB 2"]["room_type"], rooms["STB 3"]["active"], rooms["ODD 1"]["room_type"]) == (
        "lab",
        False,
        "lecture_hall",
    )
    assert ok(client.post("/api/rooms/sync"))["updated"] == []


def test_exam_import_brings_the_rooms_in_first(client, teaching: FakeTeaching, smarttt: FakeSmarttt):
    sign_in(client)
    term_id = setup_exams(client, teaching)
    smarttt.rooms = [room("NEW 1", 500)]
    result = ok(client.post(f"/api/terms/{term_id}/exams/import"))
    assert result["rooms"]["added"] == ["NEW 1"]
    smarttt.down = True
    result = ok(client.post(f"/api/terms/{term_id}/exams/import"))
    assert "error" in result["rooms"] and result["papers"] is not None


def test_the_administrators_exam_use_and_health_unit_are_read_and_the_director_overrules(client, smarttt: FakeSmarttt):
    sign_in(client)
    smarttt.rooms = [room("TC 1", 100), {**room("NURS 1", 60), "health_unit": True}, {**room("TC 2", 80), "for_exams": False}]
    ok(client.post("/api/rooms/sync"))
    rooms = {r["code"]: r for r in ok(client.get("/api/rooms"))}
    assert rooms["TC 2"]["for_exams"] is False and rooms["TC 2"]["admin_for_exams"] is False
    assert rooms["NURS 1"]["health_unit"] is True and rooms["TC 1"]["health_unit"] is False

    # The Director uses a room the administrator kept out, and keeps out one they allowed.
    ok(client.patch(f"/api/rooms/{rooms['TC 2']['id']}", json={"for_exams": True}))
    ok(client.patch(f"/api/rooms/{rooms['TC 1']['id']}", json={"for_exams": False}))
    smarttt.rooms = [{**room("TC 1", 100), "for_exams": True}, {**room("TC 2", 80), "for_exams": False}]
    ok(client.post("/api/rooms/sync"))
    rooms = {r["code"]: r for r in ok(client.get("/api/rooms"))}
    assert (rooms["TC 2"]["for_exams"], rooms["TC 2"]["exam_override"]) == (True, True)
    assert (rooms["TC 1"]["for_exams"], rooms["TC 1"]["exam_override"]) == (False, False)

    # Back to following the administrator.
    ok(client.patch(f"/api/rooms/{rooms['TC 2']['id']}", json={"for_exams": None}))
    assert next(r for r in ok(client.get("/api/rooms")) if r["code"] == "TC 2")["for_exams"] is False


def test_one_room_under_two_codes_is_one_room_and_a_mark_on_either_keeps_it_out(client, smarttt: FakeSmarttt):
    sign_in(client)
    smarttt.rooms = [
        {**room("TC 1", 50, building="TC"), "capacity_confirmed": False},
        {**room("TC1", 100, building="TC"), "capacity_confirmed": True, "for_exams": False},
        {**room("UTC 1", 900), "capacity_confirmed": True, "health_unit": True},
        {**room("UTC1", 50), "capacity_confirmed": False},
        room("TC 10", 80),
    ]
    ok(client.post("/api/rooms/sync"))
    rooms = {r["code"]: r for r in ok(client.get("/api/rooms"))}
    assert sorted(rooms) == ["TC 10", "TC1", "UTC 1"]
    assert (rooms["TC1"]["capacity"], rooms["TC1"]["for_exams"]) == (100, False)
    assert (rooms["UTC 1"]["capacity"], rooms["UTC 1"]["health_unit"], rooms["UTC 1"]["for_exams"]) == (900, True, True)
    assert rooms["TC 10"]["for_exams"] is True


def test_twins_already_here_are_merged_and_their_exam_seats_follow(client, teaching, smarttt: FakeSmarttt, db):
    sign_in(client)
    # As they got here before one room's codes were recognised; the API now refuses the second.
    twin = {"id": "old-twin"}
    db.add(Room(id="old-twin", code="STB1", building="STB", capacity=800, exam_seats=700, unavailable=[]))
    db.add(Room(id="old-other", code="STB 1", building="STB", capacity=50, unavailable=[]))
    db.commit()
    refused = client.post("/api/rooms", json={"code": "stb-01", "building": "STB", "capacity": 10})
    assert refused.status_code == 409
    db.add(ExamSeat(placement_id=_placement(db), room_id=twin["id"], class_row_id=uuid.uuid4(), students=5))
    db.commit()
    smarttt.rooms = [{**room("STB 1", 800, building="STB"), "capacity_confirmed": True}]
    assert ok(client.post("/api/rooms/sync"))["merged"] == ["STB1 into STB 1"]
    rooms = {r["code"]: r for r in ok(client.get("/api/rooms"))}
    assert list(rooms) == ["STB 1"] and rooms["STB 1"]["exam_seats"] == 700
    db.expire_all()
    assert db.scalar(select(ExamSeat.room_id)) == rooms["STB 1"]["id"]


def test_a_venue_marked_after_the_import_counts_for_the_next_run_and_only_here_rooms_stay_out(client, teaching, smarttt: FakeSmarttt):
    sign_in(client)
    term_id = setup_exams(client, teaching)
    codes = [r["code"] for r in ok(client.get("/api/rooms"))]
    smarttt.rooms = [{**room(c, 1000), "for_exams": True} for c in codes]
    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    out = codes[0]
    smarttt.rooms = [{**room(c, 1000), "for_exams": c != out} for c in codes[:-1]]
    ok(client.post("/api/exam-runs", json={"term_id": term_id, "time_limit_s": 20}))
    rooms = {r["code"]: r for r in ok(client.get("/api/rooms"))}
    assert rooms[out]["for_exams"] is False
    assert rooms[codes[-1]]["for_exams"] is False  # not in SMARTTT: the administrator can't see it
    ok(client.patch(f"/api/rooms/{rooms[codes[-1]]['id']}", json={"for_exams": True}))  # the Director can choose it
    ok(client.post("/api/rooms/sync"))
    assert next(r for r in ok(client.get("/api/rooms")) if r["code"] == codes[-1])["for_exams"] is True
    data = ok(client.get(f"/api/terms/{term_id}/exams"))
    assert data["period"]["rooms"] == len(codes) - 1
