"""
The exam timetable: departments publish papers in Smart Attendance, the Director
sets the exam period, imports, generates, shares the draft for invigilators,
and publishes.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from io import BytesIO
from typing import Any

import pypdfium2 as pdfium
from docx import Document
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ClassRow, ExamDraft, ExamPaper, ExamPublication, Run
from tests.conftest import sign_in
from tests.fake_smarttt import TERM
from tests.fake_teaching import FakeTeaching, course, paper


def _pdf_text(content: bytes) -> str:
    return "\n".join(page.get_textpage().get_text_range() for page in pdfium.PdfDocument(content))


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()["data"]


def setup_exams(client: TestClient, teaching: FakeTeaching, smarttt_term_id: str | None = None) -> str:
    body = (
        {"smarttt_term_id": smarttt_term_id}
        if smarttt_term_id
        else {
            "academic_year": "2026/2027",
            "semester": 1,
            "name": "Semester I 2026/2027",
            "start_date": "2026-09-07",
            "end_date": "2026-12-18",
        }
    )
    term = ok(client.post("/api/terms", json=body))
    rows = [
        {"code": "ADM 1", "building": "ADM", "capacity": "100", "room_type": "Lecture hall"},
        {"code": "STB 1", "building": "STB", "capacity": "200", "room_type": "Lecture hall"},
        {"code": "STB 2", "building": "STB", "capacity": "200", "room_type": "Lecture hall"},
        {"code": "UTC 1", "building": "UTC", "capacity": "300", "room_type": "Lecture hall"},
    ]
    ok(client.post("/api/rooms/bulk", json={"rows": rows}))
    ok(
        client.patch(
            f"/api/terms/{term['id']}/exam-period",
            json={"exam_start": "2026-11-23", "exam_end": "2026-11-27", "exam_days_off": ["2026-11-26"]},
        )
    )
    teaching.exam_courses = [
        course("c-cs1", "CS", "BSC.CS", 120),
        course("c-cs3", "CS", "BSC.CS", 20, year=3),
        {**course("c-odel", "CS", "BSC.CS", 30), "sub_class": "ODEL", "label": "BSC.CS Y1S1 (ODEL)"},
        course("c-ed1", "ED", "BED.SCI", 80),
        course("c-ed2", "ED", "BED.ARTS", 300, year=2),
    ]
    teaching.exam_published = [
        {
            "code": "CS",
            "name": "Computer Science",
            "published_at": "2026-10-23T08:00:00+00:00",
            "published_by": "A Cod",
            "papers": [
                paper(
                    "p-shared",
                    ["BITE 131", "COSC 130"],
                    [("c-cs1", 120, "regular"), ("c-odel", 30, "odel"), ("c-ed1", 80, "regular")],
                ),
                paper("p-200", ["COSC 200"], [("c-cs1", 120, "regular")]),
                paper("p-301", ["COSC 301"], [("c-cs3", 20, "regular")]),
                paper("p-epsc", ["EPSC 121"], [("c-ed2", 300, "regular")]),
            ],
            "practicals": [
                {
                    "id": "pr-1",
                    "codes": ["COSC 200"],
                    "title": "Data",
                    "date": "2026-11-20",
                    "start_time": "09:00",
                    "end_time": "11:00",
                }
            ],
        }
    ]
    teaching.exam_not_published = [{"code": "ED", "name": "Education", "reopened_at": None}]
    return str(term["id"])


def test_the_exam_period_and_exam_seats(client, teaching):
    sign_in(client)
    term_id = setup_exams(client, teaching)
    period = ok(client.get(f"/api/terms/{term_id}/exams"))["period"]
    assert period["days"] == ["2026-11-23", "2026-11-24", "2026-11-25", "2026-11-27"]  # Thursday off
    assert period["slots"] == 12 and period["exam_seats"] == 90 + 180 + 180 + 270  # 0.9 x capacity
    rooms = {r["code"]: r for r in ok(client.get("/api/rooms"))}
    ok(client.patch(f"/api/rooms/{rooms['UTC 1']['id']}", json={"exam_seats": 300}))
    ok(client.patch(f"/api/rooms/{rooms['ADM 1']['id']}", json={"for_exams": False}))
    assert ok(client.get(f"/api/terms/{term_id}/exams"))["period"]["exam_seats"] == 180 + 180 + 300
    assert rooms["UTC 1"]["block"] == "UTC"


def test_exam_seats_are_090_of_capacity_in_every_room(client, teaching):
    sign_in(client)
    term_id = setup_exams(client, teaching)
    ok(client.post("/api/rooms", json={"code": "TC 7", "building": "TC", "capacity": 110}))
    assert ok(client.get(f"/api/terms/{term_id}/exams"))["period"]["exam_seats"] == 90 + 180 + 180 + 270 + 99
    # The Director's factor applies to every room, big halls included.
    period = ok(client.patch(f"/api/terms/{term_id}/exam-period", json={"exam_spacing": 0.8}))
    assert period["exam_seats"] == 80 + 160 + 160 + 240 + 88
    # A room that can't be used at that share (fixed benches) gets its own number, never above its capacity.
    rooms = {r["code"]: r for r in ok(client.get("/api/rooms"))}
    ok(client.patch(f"/api/rooms/{rooms['TC 7']['id']}", json={"exam_seats": 60}))
    assert ok(client.get(f"/api/terms/{term_id}/exams"))["period"]["exam_seats"] == 80 + 160 + 160 + 240 + 60
    too_many = client.patch(f"/api/rooms/{rooms['TC 7']['id']}", json={"exam_seats": 111})
    assert too_many.status_code == 422


def test_import_generate_share_and_publish(client, teaching, smarttt, db: Session):
    sign_in(client)
    term_id = setup_exams(client, teaching, smarttt_term_id=TERM["id"])
    status = ok(client.get(f"/api/terms/{term_id}/exam-departments"))
    assert [d["code"] for d in status["published"]] == ["CS"] and status["not_published"][0]["code"] == "ED"
    result = ok(client.post(f"/api/terms/{term_id}/exams/import"))
    assert sorted(result["papers"]["added"]) == ["BITE 131/COSC 130", "COSC 200", "COSC 301", "EPSC 121"]
    exams = ok(client.get(f"/api/terms/{term_id}/exams"))
    assert exams["readiness"] == [] and exams["practicals"][0]["date"] == "2026-11-20"

    run = ok(client.post("/api/exam-runs", json={"term_id": term_id, "time_limit_s": 20}))
    assert run["status"] == "succeeded", run
    grid = ok(client.get(f"/api/exam-drafts/{run['draft_id']}"))
    assert grid["draft"]["violations"] == [] and grid["draft"]["placed"] == 4
    papers = {p["codes"]: p for p in grid["papers"]}

    # A class row sits at most 2 papers a day, never two at once (BSC.CS Y1S1 sits two papers).
    by_day: dict[str, list[int]] = defaultdict(list)
    for codes in ("BITE 131/COSC 130", "COSC 200"):
        by_day[papers[codes]["day"]].append(papers[codes]["session"])
    assert all(len(set(s)) == len(s) <= 2 for s in by_day.values())
    # The ODEL class row sits in its own room; the big class row (300 > every room) is split over two.
    shared = papers["BITE 131/COSC 130"]["seating"]
    odel_rooms = {s["room"] for s in shared if s["odel"]}
    assert odel_rooms and odel_rooms.isdisjoint({s["room"] for s in shared if not s["odel"]})
    epsc = papers["EPSC 121"]["seating"]
    assert len(epsc) == 2 and {(s["part"], s["parts"]) for s in epsc} == {(1, 2), (2, 2)}
    # Practicals are shown on their own date, not moved into the period.
    assert grid["practicals"][0]["date"] == "2026-11-20"

    # Move COSC 301 beside COSC 200: the small paper shares a room within its seats.
    draft_id = run["draft_id"]
    target = papers["COSC 200"]
    ok(
        client.patch(
            f"/api/exam-drafts/{draft_id}/papers/{papers['COSC 301']['id']}",
            json={"day": target["day"], "session": target["session"]},
        )
    )
    grid = ok(client.get(f"/api/exam-drafts/{draft_id}"))
    papers = {p["codes"]: p for p in grid["papers"]}
    assert {s["room"] for s in papers["COSC 301"]["seating"]} == {s["room"] for s in papers["COSC 200"]["seating"]}
    # A move that breaks a rule is refused: the shared paper into COSC 200's session (BSC.CS Y1S1 sits both).
    clash = client.patch(
        f"/api/exam-drafts/{draft_id}/papers/{papers['BITE 131/COSC 130']['id']}",
        json={"day": target["day"], "session": target["session"]},
    )
    assert clash.status_code == 409 and clash.json()["error"]["code"] == "BREAKS_RULE"

    # Publishing needs the draft shared, then an invigilator for every paper.
    assert client.post(f"/api/exam-drafts/{draft_id}/publish").json()["error"]["code"] == "NOT_SHARED"
    ok(client.post(f"/api/exam-drafts/{draft_id}/share"))
    shared_view = ok(
        client.get(
            f"/api/integrations/attendance/terms/{term_id}/exam-draft", headers={"X-API-Key": "test-attendance-key"}
        )
    )
    assert {p["paper_ref"] for p in shared_view["papers"]} == {"p-shared", "p-200", "p-301", "p-epsc"}
    assert all(p["rooms"] and p["start_time"] for p in shared_view["papers"])
    # Codes as a list, the way Smart Attendance's invigilator page reads them.
    shared_paper = next(p for p in shared_view["papers"] if p["paper_ref"] == "p-shared")
    assert shared_paper["codes"] == ["BITE 131", "COSC 130"] and shared_paper["sitting"] == "regular"
    refused = client.post(f"/api/exam-drafts/{draft_id}/publish")
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "NO_INVIGILATOR"
    # Each paper's main invigilator is not enough: every extra room needs one of its own.
    teaching.invigilators = {
        ref: {"": {"staff_number": f"STF/{n}", "name": f"Dr. Invigilator {n}"}}
        for n, ref in enumerate(["p-shared", "p-200", "p-301", "p-epsc"])
    }
    extras = {p["paper_ref"]: p["extra_rooms"] for p in shared_view["papers"]}
    assert len(extras["p-epsc"]) == 1  # the big paper sits in two rooms
    still = client.post(f"/api/exam-drafts/{draft_id}/publish")
    assert still.status_code == 409 and f"EPSC 121 in {extras['p-epsc'][0]}" in still.json()["error"]["message"]
    for ref, rooms in extras.items():
        for i, room in enumerate(rooms):
            teaching.invigilators[ref][room] = {"staff_number": f"STF/X{i}{ref}", "name": f"Dr. Extra {ref} {room}"}
    published = ok(client.post(f"/api/exam-drafts/{draft_id}/publish"))
    assert published["version"] == 1 and published["smarttt"]["sent"] is True

    publication = db.scalar(select(ExamPublication).where(ExamPublication.draft_id == uuid.UUID(draft_id)))
    assert publication is not None
    by_key = {p["key"]: p for p in publication.payload["papers"]}
    seat = by_key["p-200"]["seating"][0]
    assert seat["room_code"] and seat["students"] == 120 and seat["invigilator_staff_number"] == "STF/1"
    # SMARTTT's exam-publish shape: the main invigilator in the main room, an extra one in each other room.
    epsc = by_key["p-epsc"]
    roles = {s["room_code"]: (s["role"], s["invigilator_staff_number"]) for s in epsc["seating"]}
    assert sorted(r for r, _staff in roles.values()) == ["extra", "main"]
    assert roles[extras["p-epsc"][0]][0] == "extra" and roles[extras["p-epsc"][0]][1].startswith("STF/X")
    assert next(staff for role, staff in roles.values() if role == "main") == "STF/3"
    assert {(s["part"], s["parts"]) for s in epsc["seating"]} == {(1, 2), (2, 2)}
    assert epsc["seating"][0]["class_rows"] == [
        {"program": "BED.ARTS", "year_of_study": 2, "study_semester": 1, "stream": ""}
    ]
    assert by_key["p-shared"]["unit_codes"] == ["BITE 131", "COSC 130"] and by_key["p-shared"]["start_time"]
    assert {r["code"] for r in publication.payload["rooms"]} >= {s["room_code"] for s in epsc["seating"]}
    # ODEL and part-time classes sit their own paper; SMARTTT is told which.
    assert by_key["p-shared"]["sitting"] == "regular"
    odel = next(s for s in by_key["p-shared"]["seating"] if s["class_rows"][0]["stream"] == "ODEL")
    assert odel["class_rows"][0]["program"] == "BSC.CS"

    # Downloads: the timetable, room sheets and roster.
    timetable = client.get(f"/api/exam-drafts/{draft_id}/export/timetable.docx")
    assert timetable.status_code == 200
    doc = Document(BytesIO(timetable.content))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "DIRECTORATE OF EXAMINATION & TIMETABLING" in text and "VERSION 1" in text
    cells = " ".join(c.text for row in doc.tables[1].rows for c in row.cells)  # tables[0] is the letterhead
    assert "DATE/DAY" in cells and "COSC 200 →" in cells
    for kind in ("timetable", "rooms", "roster"):
        assert client.get(f"/api/exam-drafts/{draft_id}/export/{kind}.pdf").content[:4] == b"%PDF"
    roster = Document(BytesIO(client.get(f"/api/exam-drafts/{draft_id}/export/roster.docx").content))
    roster_text = " ".join(c.text for t in roster.tables for row in t.rows for c in row.cells)
    assert "Dr. Invigilator 1" in roster_text and "Main" in roster_text
    assert f"Dr. Extra p-epsc {extras['p-epsc'][0]}" in roster_text and "Extra" in roster_text


def test_generating_needs_the_period_rooms_and_papers(client, teaching):
    sign_in(client)
    term = ok(client.post("/api/terms", json={"academic_year": "2026/2027", "semester": 1}))
    ok(client.post("/api/rooms/bulk", json={"rows": [{"code": "A", "building": "A", "capacity": "50"}]}))
    refused = client.post("/api/exam-runs", json={"term_id": term["id"]})
    assert refused.status_code == 409
    codes = {p["code"] for p in refused.json()["error"]["details"]["problems"]}
    assert codes == {"no_period", "no_papers"}


def _generate(client: TestClient, term_id: str) -> str:
    run = ok(client.post("/api/exam-runs", json={"term_id": term_id, "time_limit_s": 20}))
    assert run["status"] == "succeeded", run
    return str(run["draft_id"])


def _name_invigilators(client: TestClient, teaching: FakeTeaching, term_id: str) -> None:
    """Departments name every paper's main invigilator and one for each extra room."""
    shared = ok(
        client.get(
            f"/api/integrations/attendance/terms/{term_id}/exam-draft", headers={"X-API-Key": "test-attendance-key"}
        )
    )
    teaching.invigilators = {
        p["paper_ref"]: {
            room: {"staff_number": f"STF/{n}{room}", "name": f"Dr. {n} {room}"} for room in ["", *p["extra_rooms"]]
        }
        for n, p in enumerate(shared["papers"])
    }


def test_an_exam_version_smarttt_missed_is_sent_later(client, teaching, smarttt):
    sign_in(client)
    term_id = setup_exams(client, teaching, smarttt_term_id=TERM["id"])
    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    draft_id = _generate(client, term_id)
    ok(client.post(f"/api/exam-drafts/{draft_id}/share"))
    _name_invigilators(client, teaching, term_id)
    smarttt.down = True
    published = ok(client.post(f"/api/exam-drafts/{draft_id}/publish"))
    assert published["version"] == 1 and published["smarttt"]["sent"] is False
    (version,) = ok(client.get(f"/api/terms/{term_id}/exams"))["publications"]
    assert version["sent_to_smarttt"] is False and version["can_send"] is True

    assert ok(client.post(f"/api/terms/{term_id}/exam-publications/1/send"))["smarttt"]["sent"] is False
    smarttt.down = False
    sent = ok(client.post(f"/api/terms/{term_id}/exam-publications/1/send"))
    assert sent["smarttt"]["sent"] is True and len(smarttt.exam_payloads[-1]["papers"]) == 4
    (version,) = ok(client.get(f"/api/terms/{term_id}/exams"))["publications"]
    assert version["sent_to_smarttt"] is True and version["can_send"] is False
    again = client.post(f"/api/terms/{term_id}/exam-publications/1/send")
    assert again.json()["error"]["code"] == "ALREADY_SENT"


def test_an_odel_paper_of_the_same_unit_is_its_own_paper(client, teaching, smarttt):
    sign_in(client)
    term_id = setup_exams(client, teaching, smarttt_term_id=TERM["id"])
    # COSC 200's ODEL class sits a separate paper, as Smart Attendance sends it.
    teaching.exam_published[0]["papers"].append(
        {**paper("p-200-odel", ["COSC 200"], [("c-odel", 30, "odel")]), "sitting": "odel"}
    )
    result = ok(client.post(f"/api/terms/{term_id}/exams/import"))
    assert "COSC 200 (ODEL)" in result["papers"]["added"] and "COSC 200" in result["papers"]["added"]
    draft_id = _generate(client, term_id)
    papers = {p["codes"]: p for p in ok(client.get(f"/api/exam-drafts/{draft_id}"))["papers"]}
    assert papers["COSC 200 (ODEL)"]["sitting"] == "odel" and papers["COSC 200"]["sitting"] == "regular"
    assert {s["row"] for s in papers["COSC 200 (ODEL)"]["seating"]} == {"BSC.CS Y1S1 (ODEL)"}

    ok(client.post(f"/api/exam-drafts/{draft_id}/share"))
    _name_invigilators(client, teaching, term_id)
    assert ok(client.post(f"/api/exam-drafts/{draft_id}/publish"))["smarttt"]["sent"] is True
    sent = {p["key"]: p for p in smarttt.exam_payloads[-1]["papers"]}
    # SMARTTT gets the codes as they are, and the sitting beside them.
    assert (sent["p-200-odel"]["unit_codes"], sent["p-200-odel"]["sitting"]) == (["COSC 200"], "odel")
    assert sent["p-200"]["sitting"] == "regular"


def test_the_timetable_pdf_holds_a_session_busier_than_a_page():
    """At full size (899 papers) one session had 86 papers: its day must not overflow the page."""
    from types import SimpleNamespace

    from app.services import exam_export

    day = {"date": "2026-12-01", "label": "TUE 01/12/2026"}
    papers = [
        {"codes": f"COSC {100 + i}", "day": day["date"], "session": 0, "seating": [{"room": f"UTC {i % 14}"}]}
        for i in range(150)
    ]
    rec = {"days": [day], "sessions": [{"start": "08:30", "end": "10:30"}], "papers": papers, "practicals": []}
    term = SimpleNamespace(
        academic_year="2026/2027", semester=1, name="Semester I", prepared_by="", prepared_by_title=""
    )
    pdf = exam_export.timetable_pdf(term, rec, 1, "Director")
    assert pdf[:4] == b"%PDF"
    assert "TUE 01/12/2026 (cont.)" in _pdf_text(pdf).replace("\r\n", " ").replace("\n", " ")


def test_a_paper_nobody_synced_is_timetabled_and_published_without_a_room(client, teaching, smarttt, db: Session):
    sign_in(client)
    term_id = setup_exams(client, teaching, smarttt_term_id=TERM["id"])
    # Part-time students may never sync the unit: no class rows, yet it is offered and needs a date.
    nobody = paper("p-nobody", ["MATH 100"], [])
    nobody["invigilator"] = {"staff_number": "STF/7", "name": "Dr. Seven"}
    teaching.exam_published[0]["papers"].append(nobody)
    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    stored = db.scalar(select(ExamPaper).where(ExamPaper.allocator_ref == "p-nobody"))
    assert stored is not None and stored.invigilator_staff_number == "STF/7" and stored.rows == []
    draft_id = _generate(client, term_id)
    grid = ok(client.get(f"/api/exam-drafts/{draft_id}"))
    placed = next(p for p in grid["papers"] if p["codes"] == "MATH 100")
    assert placed["day"] is not None and placed["seating"] == []
    ok(client.post(f"/api/exam-drafts/{draft_id}/share"))
    _name_invigilators(client, teaching, term_id)
    del teaching.invigilators["p-nobody"]  # no room, so nobody to name
    assert ok(client.post(f"/api/exam-drafts/{draft_id}/publish"))["smarttt"]["sent"] is True
    sent = next(p for p in smarttt.exam_payloads[-1]["papers"] if p["key"] == "p-nobody")
    assert sent["seating"] == [] and sent["date"]


def test_a_class_guessed_from_the_code_is_seated_but_cant_stop_a_run(client, teaching, smarttt, db: Session):
    sign_in(client)
    term_id = setup_exams(client, teaching, smarttt_term_id=TERM["id"])
    # Nine papers of one guessed class over four days: more than two a day allows for a known class.
    teaching.exam_courses.append(course("c-guess", "CS", "COSC", 10))
    for i in range(9):
        guessed = paper(f"p-g{i}", [f"COSC 10{i}"], [("c-guess", 10, "regular")])
        guessed["rows"][0]["guessed"] = True
        teaching.exam_published[0]["papers"].append(guessed)
    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    stored = db.scalar(select(ExamPaper).where(ExamPaper.allocator_ref == "p-g0"))
    assert stored is not None and [r.guessed for r in stored.rows] == [True]
    grid = ok(client.get(f"/api/exam-drafts/{_generate(client, term_id)}"))
    assert grid["draft"]["violations"] == []
    placed = next(p for p in grid["papers"] if p["codes"] == "COSC 100")
    assert placed["day"] is not None and sum(s["students"] for s in placed["seating"]) == 10

    # The department corrects the class: re-importing clears the mark.
    guessed = next(p for p in teaching.exam_published[0]["papers"] if p["id"] == "p-g0")
    guessed["rows"][0]["guessed"] = False
    changed = ok(client.post(f"/api/terms/{term_id}/exams/import"))["papers"]["changed"]
    db.expire_all()
    assert changed == ["COSC 100"] and [r.guessed for r in stored.rows] == [False]


def test_a_class_with_no_number_yet_keeps_its_papers_apart_and_waits_for_a_room(client, teaching, smarttt, db: Session):
    """The master timetable names the class before anyone syncs: no clash, no seat, no invigilator needed yet."""
    sign_in(client)
    term_id = setup_exams(client, teaching, smarttt_term_id=TERM["id"])
    teaching.exam_courses.append(course("listed:BCOM|2|2|", "CS", "BCOM", 0, year=2))
    for code in ("BCOM 201", "BCOM 202", "BCOM 203"):
        teaching.exam_published[0]["papers"].append(paper(f"p-{code}", [code], [("listed:BCOM|2|2|", 0, "regular")]))
    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    grid = ok(client.get(f"/api/exam-drafts/{_generate(client, term_id)}"))
    assert grid["draft"]["violations"] == []
    placed = [p for p in grid["papers"] if p["codes"].startswith("BCOM")]
    assert all(p["seating"] == [] for p in placed)
    assert len({(p["day"], p["session"]) for p in placed}) == 3

    # A department's number for a class row doesn't get wiped by a later read with none.
    row = db.scalar(select(ClassRow).where(ClassRow.allocator_ref == "c-cs1"))
    assert row is not None and row.student_count == 120
    teaching.exam_courses = [
        {**c, "students": 0} if c["id"] == "c-cs1" else c for c in teaching.exam_courses
    ]
    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    db.expire_all()
    assert row.student_count == 120


def test_set_as_current_links_the_term_so_exams_can_be_sent(client, teaching, smarttt):
    sign_in(client)
    term_id = setup_exams(client, teaching)
    assert ok(client.get(f"/api/terms/{term_id}"))["smarttt_term_id"] is None
    result = ok(client.post(f"/api/terms/{term_id}/set-current"))
    assert result["is_current"] is True and result["smarttt_term_id"] == "smarttt-term-new"
    assert smarttt.set_current_calls[0]["academic_year"]
    assert ok(client.get(f"/api/terms/{term_id}"))["smarttt_term_id"] == "smarttt-term-new"


def test_the_director_sets_a_papers_category(client, teaching, smarttt):
    sign_in(client)
    term_id = setup_exams(client, teaching)
    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    papers = {p["codes"]: p for p in ok(client.get(f"/api/terms/{term_id}/exams"))["papers"]}
    assert papers["BITE 131/COSC 130"]["category"] == "common" and papers["COSC 200"]["category"] == "regular"
    url = f"/api/terms/{term_id}/exam-papers/{papers['COSC 200']['id']}/category"
    ok(client.patch(url, json={"category": "postgraduate"}))
    papers = {p["codes"]: p for p in ok(client.get(f"/api/terms/{term_id}/exams"))["papers"]}
    assert papers["COSC 200"]["category"] == "postgraduate"
    assert client.patch(url, json={"category": "x"}).status_code == 422
    assert client.patch(url, json={"category": "health"}).status_code == 422  # revoked
    ok(client.patch(url, json={"category": None}))
    assert client.patch(f"/api/terms/{term_id}/exam-period", json={"exam_health_prefixes": ["NURS"]}).status_code == 422
    run = client.post("/api/exam-runs", json={"term_id": term_id, "time_limit_s": 30})
    assert run.status_code < 300


def test_a_postgraduate_paper_stays_in_the_first_week_and_older_drafts_are_left_alone(client, teaching, db):
    sign_in(client)
    term_id = setup_exams(client, teaching)
    ok(client.patch(f"/api/terms/{term_id}/exam-period", json={"exam_end": "2026-12-04"}))
    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    listed = {p["codes"]: p for p in ok(client.get(f"/api/terms/{term_id}/exams"))["papers"]}
    paper_id = listed["COSC 200"]["id"]
    ok(client.patch(f"/api/terms/{term_id}/exam-papers/{paper_id}/category", json={"category": "postgraduate"}))
    draft_id = _generate(client, term_id)
    placed = {p["codes"]: p for p in ok(client.get(f"/api/exam-drafts/{draft_id}"))["papers"]}["COSC 200"]
    assert "2026-11-23" <= placed["day"] <= "2026-11-27" and placed["session"] in (0, 2)

    moved = client.patch(f"/api/exam-drafts/{draft_id}/papers/{paper_id}", json={"day": "2026-11-30", "session": 0})
    assert moved.status_code == 409 and "first week" in moved.json()["error"]["message"]

    # A draft from a run made before the rule: the same move goes through.
    run = db.get(Run, db.get(ExamDraft, uuid.UUID(draft_id)).run_id)
    run.weights = {k: v for k, v in run.weights.items() if k != "postgraduate_first_week"}
    db.commit()
    ok(client.patch(f"/api/exam-drafts/{draft_id}/papers/{paper_id}", json={"day": "2026-11-30", "session": 0}))


def test_the_placeholder_room_is_never_an_exam_room(client, teaching):
    sign_in(client)
    term_id = setup_exams(client, teaching)
    before = ok(client.get(f"/api/terms/{term_id}/exams"))["period"]["exam_seats"]
    placeholder = {"code": "TBA", "building": "", "capacity": "50", "room_type": "Lecture hall"}
    ok(client.post("/api/rooms/bulk", json={"rows": [placeholder]}))
    rooms = {r["code"]: r for r in ok(client.get("/api/rooms"))}
    assert rooms["TBA"]["for_exams"] is False
    # The Director's own choice can't open it either.
    ok(client.patch(f"/api/rooms/{rooms['TBA']['id']}", json={"for_exams": True}))
    assert ok(client.get(f"/api/terms/{term_id}/exams"))["period"]["exam_seats"] == before


def test_the_director_makes_room_in_a_full_venue(client, teaching, smarttt):
    sign_in(client)
    term_id = setup_exams(client, teaching, smarttt_term_id=TERM["id"])
    # Seats: ADM 1 84, STB 1 and STB 2 151, UTC 1 226: EPSC 121's 300 fill the STB rooms.
    period = ok(client.patch(f"/api/terms/{term_id}/exam-period", json={"exam_spacing": 0.84}))
    assert period["exam_postgraduate_room"] == "TC 1" and period["postgraduate_room"] is None  # no TC 1 here
    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    draft_id = _generate(client, term_id)
    papers = {p["codes"]: p for p in ok(client.get(f"/api/exam-drafts/{draft_id}"))["papers"]}
    epsc = papers["EPSC 121"]
    ok(
        client.patch(
            f"/api/exam-drafts/{draft_id}/papers/{papers['COSC 301']['id']}",
            json={"day": epsc["day"], "session": epsc["session"]},
        )
    )
    papers = {p["codes"]: p for p in ok(client.get(f"/api/exam-drafts/{draft_id}"))["papers"]}
    assert {s["room"] for s in papers["EPSC 121"]["seating"]} == {"STB 1", "STB 2"}
    cosc = papers["COSC 301"]
    start = cosc["seating"][0]["room"]
    assert start not in ("STB 1", "STB 2")
    url = f"/api/exam-drafts/{draft_id}/papers/{cosc['id']}/venue"
    full = client.patch(url, json={"from_room": start, "to_room": "STB 1"})
    assert full.json()["error"]["code"] == "ROOM_FULL"
    assert [r["paper"] for r in full.json()["error"]["details"]["in_room"]] == ["EPSC 121"]
    made = ok(client.patch(url, json={"from_room": start, "to_room": "STB 1", "make_room": True}))
    assert made["violations"] == []
    assert [m["paper"] for m in made["made_room"]] == ["EPSC 121"] and made["made_room"][0]["from"] == "STB 1"
    papers = {p["codes"]: p for p in ok(client.get(f"/api/exam-drafts/{draft_id}"))["papers"]}
    assert {s["room"] for s in papers["COSC 301"]["seating"]} == {"STB 1"}
    assert sum(s["students"] for s in papers["EPSC 121"]["seating"]) == 300
    # COSC 301's venue is now the Director's: it can't be cleared for another paper.
    epsc_room = next(s["room"] for s in papers["EPSC 121"]["seating"] if s["room"] != "STB 1")
    locked = client.patch(
        f"/api/exam-drafts/{draft_id}/papers/{papers['EPSC 121']['id']}/venue",
        json={"from_room": epsc_room, "to_room": "STB 1", "make_room": True},
    )
    assert locked.json()["error"]["code"] in ("ROOM_FULL", "ROOM_TOO_SMALL")
