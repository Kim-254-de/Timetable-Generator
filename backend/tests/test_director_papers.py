"""Venues changed on the draft, and the papers the Director uploaded before departments did it for health and nursing."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DIRECTOR_REF, Department, ExamPaper
from tests.conftest import sign_in
from tests.fake_smarttt import TERM
from tests.test_exams import _generate, ok, setup_exams


def _earlier_upload(db: Session, term_id: str, codes: list[str]) -> str:
    department = db.scalars(select(Department)).first()
    assert department is not None
    paper = ExamPaper(
        term_id=uuid.UUID(term_id), allocator_ref=f"{DIRECTOR_REF}{uuid.uuid4().hex}", department_id=department.id,
        codes=codes, title="Uploaded earlier", sitting="regular", examiner_name="", notes="", director_invigilators={},
    )
    db.add(paper)
    db.commit()
    return str(paper.id)


def _papers(client: Any, term_id: str) -> dict[str, Any]:
    return {p["codes"]: p for p in ok(client.get(f"/api/terms/{term_id}/exams"))["papers"]}


def test_a_health_room_is_like_any_other_and_the_old_upload_is_gone(client, teaching, smarttt):
    from tests.test_rooms_from_smarttt import room

    sign_in(client)
    term_id = setup_exams(client, teaching)
    ok(client.post("/api/rooms", json={"code": "NUR 1", "building": "Health", "capacity": 500}))
    codes = [r["code"] for r in ok(client.get("/api/rooms"))]
    smarttt.rooms = [{**room(c, 500), "health_unit": c == "NUR 1", "capacity_confirmed": True} for c in codes]
    ok(client.post("/api/rooms/sync"))
    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    draft = _generate(client, term_id)
    grid = ok(client.get(f"/api/exam-drafts/{draft}"))
    assert grid["draft"]["violations"] == []
    assert "NUR 1" in {r["code"] for r in grid["exam_rooms"]}
    paper = next(p for p in grid["papers"] if p["codes"] == "COSC 301")
    if {s["room"] for s in paper["seating"]} != {"NUR 1"}:
        ok(client.patch(f"/api/exam-drafts/{draft}/papers/{paper['id']}/venue", json={"from_room": paper["seating"][0]["room"], "to_room": "NUR 1"}))
    assert client.post(f"/api/terms/{term_id}/health-papers", json={"papers": []}).status_code in (404, 405)
    assert client.post(f"/api/terms/{term_id}/health-papers/read", json={"file": "x"}).status_code in (404, 405)


def test_the_director_changes_a_venue_on_the_draft_checked_and_kept(client, teaching, smarttt):
    sign_in(client)
    term_id = setup_exams(client, teaching)
    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    draft = _generate(client, term_id)
    grid = ok(client.get(f"/api/exam-drafts/{draft}"))
    paper = next(p for p in grid["papers"] if p["seating"] and p["codes"] == "COSC 301")
    was = paper["seating"][0]["room"]
    other = next(r["code"] for r in grid["exam_rooms"] if r["code"] != was)
    url = f"/api/exam-drafts/{draft}/papers/{paper['id']}/venue"
    assert client.patch(url, json={"from_room": was, "to_room": "NOPE"}).status_code == 409
    assert client.patch(url, json={"from_room": "NOPE", "to_room": other}).status_code == 404
    ok(client.patch(url, json={"from_room": was, "to_room": other}))
    grid = ok(client.get(f"/api/exam-drafts/{draft}"))
    moved = next(p for p in grid["papers"] if p["id"] == paper["id"])
    assert {s["room"] for s in moved["seating"]} == {other} and moved["pinned"] is True
    assert grid["draft"]["violations"] == []
    # Moving another paper into that session re-seats it around the chosen venue.
    mover = next(p for p in grid["papers"] if p["seating"] and p["codes"] == "EPSC 121")
    ok(client.patch(f"/api/exam-drafts/{draft}/papers/{mover['id']}", json={"day": moved["day"], "session": moved["session"], "pinned": True}))
    grid = ok(client.get(f"/api/exam-drafts/{draft}"))
    assert {s["room"] for s in next(p for p in grid["papers"] if p["id"] == paper["id"])["seating"]} == {other}
    assert grid["draft"]["violations"] == []


def test_a_venue_with_no_seats_left_is_refused(client, teaching, smarttt):
    sign_in(client)
    term_id = setup_exams(client, teaching)
    ok(client.post("/api/rooms", json={"code": "TINY", "building": "T", "capacity": 2}))
    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    draft = _generate(client, term_id)
    grid = ok(client.get(f"/api/exam-drafts/{draft}"))
    paper = next(p for p in grid["papers"] if p["seating"])
    refused = client.patch(f"/api/exam-drafts/{draft}/papers/{paper['id']}/venue", json={"from_room": paper["seating"][0]["room"], "to_room": "TINY"})
    assert refused.status_code == 409 and "TINY" in refused.text


def test_a_paper_uploaded_earlier_stays_until_a_department_lists_its_unit_or_the_director_removes_it(client, teaching, smarttt, db: Session):
    sign_in(client)
    term_id = setup_exams(client, teaching)
    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    kept = _earlier_upload(db, term_id, ["NURS 101"])
    other = _earlier_upload(db, term_id, ["NURS 102"])
    replaced = _earlier_upload(db, term_id, ["COSC 200"])  # a unit on a department's list
    result = ok(client.post(f"/api/terms/{term_id}/exams/import"))
    assert "COSC 200" in result["papers"]["removed"]
    papers = _papers(client, term_id)
    assert papers["NURS 101"]["director_paper"] is True and papers["NURS 101"]["category"] == "regular"
    assert papers["COSC 200"]["director_paper"] is False and papers["COSC 200"]["id"] != replaced
    ok(client.delete(f"/api/terms/{term_id}/director-papers/{other}"))
    assert "NURS 102" not in _papers(client, term_id)
    # A department's paper isn't the Director's to remove.
    assert client.delete(f"/api/terms/{term_id}/director-papers/{papers['COSC 200']['id']}").status_code == 404
    assert kept == papers["NURS 101"]["id"]


def test_the_director_names_invigilators_of_a_paper_uploaded_earlier(client, teaching, smarttt, db: Session):
    sign_in(client)
    term_id = setup_exams(client, teaching, smarttt_term_id=TERM["id"])
    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    mine = _earlier_upload(db, term_id, ["NURS 101"])
    department_paper = _papers(client, term_id)["COSC 200"]["id"]
    named = {"": {"staff_number": "stf/1", "name": "Dr. X"}}
    ok(client.put(f"/api/terms/{term_id}/director-papers/{mine}/invigilators", json={"invigilators": named}))
    draft = _generate(client, term_id)
    grid = ok(client.get(f"/api/exam-drafts/{draft}"))
    nurs = next(p for p in grid["papers"] if p["codes"] == "NURS 101")
    assert nurs["invigilators"][""]["name"] == "Dr. X" and nurs["director_paper"] is True
    assert client.put(f"/api/terms/{term_id}/director-papers/{department_paper}/invigilators", json={"invigilators": {}}).status_code == 404


def test_the_director_enters_numbers_on_any_paper_and_import_keeps_them_until_the_department_sends_one(client, teaching, smarttt):
    sign_in(client)
    term_id = setup_exams(client, teaching)
    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    paper = _papers(client, term_id)["COSC 301"]
    published = next(p for d in teaching.exam_published for p in d["papers"] if p["codes"] == ["COSC 301"])
    for r in published["rows"]:
        r["students"] = 0  # nobody synced, the letter gave none
    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    assert _papers(client, term_id)["COSC 301"]["students"] == 0

    url = f"/api/terms/{term_id}/exam-papers/{paper['id']}/rows"
    first = paper["rows"][0]
    typed = {k: first[k] for k in ("programme", "year", "semester", "stream")}
    assert client.put(url, json={"rows": [{**typed, "students": 40}, {**typed, "students": 41}]}).status_code == 422
    ok(client.put(url, json={"rows": [{**typed, "students": 40}, {"programme": "bsc.added", "year": 2, "semester": 1, "stream": "", "students": 6}]}))
    assert _papers(client, term_id)["COSC 301"]["students"] == 46

    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    assert _papers(client, term_id)["COSC 301"]["students"] == 46

    # The department's letter now gives the class a number: it replaces the Director's.
    published["rows"][0]["students"] = 107
    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    numbers = {r["programme"]: r["students"] for r in _papers(client, term_id)["COSC 301"]["rows"]}
    assert numbers[first["programme"]] == 107 and numbers["BSC.ADDED"] == 6

    other = _papers(client, term_id)["COSC 200"]["id"]
    assert client.put(f"/api/terms/{term_id}/exam-papers/{uuid.uuid4()}/rows", json={"rows": []}).status_code == 404
    ok(client.put(f"/api/terms/{term_id}/exam-papers/{other}/rows", json={"rows": []}))
    assert _papers(client, term_id)["COSC 200"]["students"] == 0
