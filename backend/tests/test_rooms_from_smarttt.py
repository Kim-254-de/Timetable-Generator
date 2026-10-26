"""The rooms the admin uploads to SMARTTT come into the Generator, by code."""

from __future__ import annotations

from tests.conftest import sign_in
from tests.fake_smarttt import FakeSmarttt
from tests.fake_teaching import FakeTeaching
from tests.test_exams import ok, setup_exams


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
    assert result == {"added": ["LAB 2", "STB 3", "ODD 1"], "updated": ["utc 1"], "only_here": ["OLD 9"]}
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
