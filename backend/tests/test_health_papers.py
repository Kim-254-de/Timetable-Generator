"""The Director uploads the health and nursing moderation letter; venues are changed on the draft."""

from __future__ import annotations

import base64
import io
from typing import Any

import docx
from sqlalchemy.orm import Session

from app.models import ExamPaper
from sqlalchemy import select
from app.services.exam_list_read import class_of
from tests.conftest import sign_in
from tests.test_exams import _generate, ok, setup_exams
from tests.test_rooms_from_smarttt import room


def letter(rows: list[list[str]], paragraphs: tuple[str, ...] = ()) -> str:
    doc = docx.Document()
    doc.add_paragraph("SCHOOL OF HEALTH SCIENCES")
    doc.add_paragraph("Dear Madam, this is to forward the following examination drafts.")
    for p in paragraphs:
        doc.add_paragraph(p)
    table = doc.add_table(rows=0, cols=3)
    for r in rows:
        cells = table.add_row().cells
        for i, text in enumerate(r):
            cells[i].text = text
    out = io.BytesIO()
    doc.save(out)
    return base64.b64encode(out.getvalue()).decode()


def cls(program: str, year: int, students: int, semester: int = 1, stream: str = "", sitting: str = "regular") -> dict[str, Any]:
    return {"program": program, "year_of_study": year, "study_semester": semester, "stream": stream, "sitting": sitting, "students": students}


def unit(*rows: dict[str, Any]) -> dict[str, Any]:
    return {"rows": list(rows), "students": sum(r["students"] for r in rows), "lecturers": [], "name": ""}


LETTER = [
    ["S/NO", "UNIT CODE", "UNIT TITLE"],
    ["1", "nurs 101", "Fundamentals of Nursing"],
    ["2", "HPA 3111/NURS 112", "Physics for Health Sciences"],
    ["3", "NURS 101", "Fundamentals again"],
    ["4", "NURS 999", "Not a unit"],
    ["", "ODEL/PART-TIME DRAFTS", ""],
    ["5", "NURS 101", "Fundamentals of Nursing"],
    ["6", "COSC 200", "Data"],
]


def test_the_letter_is_read_and_checked_and_nothing_is_stored(client, teaching, smarttt, db: Session):
    sign_in(client)
    term_id = setup_exams(client, teaching)
    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    before = len(list(db.scalars(select(ExamPaper))))
    smarttt.enrolment = {
        "NURS 101": unit(cls("BSCN", 1, 40), cls("BSCN", 1, 5, sitting="odel")),
        "HPA 3111": unit(cls("BSCN", 2, 0, semester=2)),
        "NURS 112": unit(),
    }
    r = ok(client.post(f"/api/terms/{term_id}/health-papers/read", json={"file": letter(LETTER)}))
    assert [(e["codes"], e["sitting"], e["students"]) for e in r["entries"]] == [
        (["NURS 101"], "regular", 40),
        (["HPA 3111", "NURS 112"], "regular", 0),
        (["NURS 101"], "regular", 40),
        (["NURS 999"], "regular", 0),
        (["NURS 101"], "odel", 5),
        (["COSC 200"], "odel", 0),
    ]
    assert r["entries"][1]["classes"] == ["BSCN Y2S2"]
    assert r["entries"][2]["duplicate_of"] == 1
    assert r["entries"][3]["unknown_codes"] == ["NURS 999"]
    assert r["entries"][4]["section"] == "ODEL/PART-TIME DRAFTS"
    assert r["summary"]["papers"] == 5 and r["summary"]["duplicates"] == 1
    assert len(list(db.scalars(select(ExamPaper)))) == before
    bad = client.post(f"/api/terms/{term_id}/health-papers/read", json={"file": base64.b64encode(b"not a docx").decode()})
    assert bad.status_code == 422 and "Word document" in bad.text
    scan = client.post(f"/api/terms/{term_id}/health-papers/read", json={"file": base64.b64encode(b"%PDF-1.5 a scan").decode()})
    assert scan.status_code == 422 and "This is a PDF" in scan.text


def _saved(client: Any, term_id: str, smarttt: Any) -> dict[str, Any]:
    smarttt.enrolment = {"NURS 101": unit(cls("BSCN", 1, 40)), "NURS 112": unit(cls("BSCN", 1, 0), cls("BSCM", 1, 0))}
    body = {
        "papers": [
            {"codes": ["NURS 101"], "title": "Fundamentals", "sitting": "regular"},
            {"codes": ["NURS 112"], "title": "Anatomy", "sitting": "regular"},
        ]
    }
    ok(client.post(f"/api/terms/{term_id}/health-papers", json=body))
    papers = ok(client.get(f"/api/terms/{term_id}/exams"))["papers"]
    return {p["codes"]: p for p in papers}


def test_saved_papers_are_health_with_their_classes_and_keep_the_directors_numbers(client, teaching, smarttt):
    sign_in(client)
    term_id = setup_exams(client, teaching)
    papers = _saved(client, term_id, smarttt)
    nurs = papers["NURS 101"]
    assert (nurs["category"], nurs["director_paper"], nurs["department"], nurs["students"]) == ("health", True, "HLTH", 40)
    assert [r["label"] for r in papers["NURS 112"]["rows"]] == ["BSCM Y1S1", "BSCN Y1S1"]

    # Numbers typed, a class removed; reading SMARTTT again keeps both.
    rows = [{"programme": "BSCN", "year": 1, "semester": 1, "stream": "", "students": 55}]
    ok(client.put(f"/api/terms/{term_id}/health-papers/{papers['NURS 112']['id']}/rows", json={"rows": rows}))
    smarttt.enrolment["NURS 112"] = unit(cls("BSCN", 1, 3), cls("BSCM", 1, 9))
    smarttt.enrolment["NURS 101"] = unit(cls("BSCN", 1, 44))
    assert ok(client.post(f"/api/terms/{term_id}/health-papers/recount"))["papers"] == 2
    papers = {p["codes"]: p for p in ok(client.get(f"/api/terms/{term_id}/exams"))["papers"]}
    assert [(r["label"], r["students"]) for r in papers["NURS 112"]["rows"]] == [("BSCN Y1S1", 55)]
    assert papers["NURS 101"]["students"] == 44

    # The same list again updates, never doubles; a paper can be removed.
    again = {"papers": [{"codes": ["nurs 101"], "title": "Fundamentals I", "sitting": "regular"}]}
    assert ok(client.post(f"/api/terms/{term_id}/health-papers", json=again))["updated"] == 1
    ok(client.delete(f"/api/terms/{term_id}/health-papers/{papers['NURS 112']['id']}"))
    papers = {p["codes"]: p for p in ok(client.get(f"/api/terms/{term_id}/exams"))["papers"]}
    assert "NURS 112" not in papers and papers["NURS 101"]["title"] == "Fundamentals I"


def test_importing_departments_keeps_the_directors_papers_and_a_listed_unit_isnt_doubled(client, teaching, smarttt):
    sign_in(client)
    term_id = setup_exams(client, teaching)
    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    papers = _saved(client, term_id, smarttt)
    teaching.exam_published[0]["papers"] = teaching.exam_published[0]["papers"][:2]  # a department drops papers
    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    codes = {p["codes"] for p in ok(client.get(f"/api/terms/{term_id}/exams"))["papers"]}
    assert {"NURS 101", "NURS 112"} <= codes
    # COSC 200 is on a department's list: not entered again.
    result = ok(client.post(f"/api/terms/{term_id}/health-papers", json={"papers": [{"codes": ["COSC 200"], "title": "Data", "sitting": "regular"}]}))
    assert (result["created"], result["listed_by_departments"]) == (0, ["COSC 200"])
    papers = {p["codes"]: p for p in ok(client.get(f"/api/terms/{term_id}/exams"))["papers"]}
    # It stays the department's, and an ordinary paper: its students aren't sent to the health unit.
    assert papers["COSC 200"]["category"] == "regular" and papers["COSC 200"]["director_paper"] is False


def _health_setup(client: Any, teaching: Any, smarttt: Any, term_smarttt: str | None = None) -> tuple[str, dict[str, Any]]:
    term_id = setup_exams(client, teaching, smarttt_term_id=term_smarttt) if term_smarttt else setup_exams(client, teaching)
    ok(client.post("/api/rooms", json={"code": "NUR 1", "building": "Health", "capacity": 100}))
    codes = [r["code"] for r in ok(client.get("/api/rooms"))]
    smarttt.rooms = [{**room(c, 500), "health_unit": c == "NUR 1", "capacity_confirmed": True} for c in codes]
    ok(client.post("/api/rooms/sync"))
    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    return term_id, _saved(client, term_id, smarttt)


def test_the_draft_keeps_health_papers_in_the_unit_and_others_out_first_and_last_only(client, teaching, smarttt):
    sign_in(client)
    term_id, _ = _health_setup(client, teaching, smarttt)
    grid = ok(client.get(f"/api/exam-drafts/{_generate(client, term_id)}"))
    assert grid["draft"]["violations"] == []
    last = len(grid["sessions"]) - 1
    for p in grid["papers"]:
        rooms = {s["room"] for s in p["seating"]}
        if p["category"] == "health":
            assert rooms <= {"NUR 1"} and p["session"] in (0, last)
        else:
            assert "NUR 1" not in rooms
    assert any(r["health"] and r["code"] == "NUR 1" for r in grid["exam_rooms"])


def test_the_director_changes_a_venue_on_the_draft_checked_and_kept(client, teaching, smarttt):
    sign_in(client)
    term_id, _ = _health_setup(client, teaching, smarttt)
    draft = _generate(client, term_id)
    grid = ok(client.get(f"/api/exam-drafts/{draft}"))
    paper = next(p for p in grid["papers"] if p["category"] == "regular" and p["seating"] and p["codes"] == "COSC 301")
    was = paper["seating"][0]["room"]
    other = next(r["code"] for r in grid["exam_rooms"] if not r["health"] and r["code"] != was)
    url = f"/api/exam-drafts/{draft}/papers/{paper['id']}/venue"

    refused = client.patch(url, json={"from_room": was, "to_room": "NUR 1"})  # the health unit is for health papers
    assert refused.status_code == 409 and "health paper" in refused.text
    assert client.patch(url, json={"from_room": was, "to_room": "NOPE"}).status_code == 409
    assert client.patch(url, json={"from_room": "NOPE", "to_room": other}).status_code == 404

    ok(client.patch(url, json={"from_room": was, "to_room": other}))
    grid = ok(client.get(f"/api/exam-drafts/{draft}"))
    moved = next(p for p in grid["papers"] if p["id"] == paper["id"])
    assert {s["room"] for s in moved["seating"]} == {other} and moved["pinned"] is True
    assert grid["draft"]["violations"] == []

    # Moving another paper into that session re-seats it around the chosen venue.
    mover = next(p for p in grid["papers"] if p["id"] != paper["id"] and p["category"] == "regular" and p["seating"] and p["codes"] == "EPSC 121")
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


def test_the_director_names_invigilators_of_their_papers_and_they_publish(client, teaching, smarttt):
    sign_in(client)
    from tests.fake_smarttt import TERM

    term_id, papers = _health_setup(client, teaching, smarttt, TERM["id"])
    draft = _generate(client, term_id)
    ok(client.post(f"/api/exam-drafts/{draft}/share"))
    grid = ok(client.get(f"/api/exam-drafts/{draft}"))
    teaching.invigilator_map = {}
    for p in grid["papers"]:
        if not p["seating"]:
            continue
        named = {"": {"staff_number": f"STF/{p['id'][:6]}", "name": "Dr. X"}, **{r: {"staff_number": f"STF/{p['id'][:5]}{i}", "name": "Y"} for i, r in enumerate(p["extra_rooms"])}}
        if p["director_paper"]:
            ok(client.put(f"/api/terms/{term_id}/health-papers/{p['id']}/invigilators", json={"invigilators": named}))
    grid = ok(client.get(f"/api/exam-drafts/{draft}"))
    nurs = next(p for p in grid["papers"] if p["codes"] == "NURS 101")
    assert nurs["invigilators"][""]["name"] == "Dr. X" and nurs["director_paper"] is True
    # Department papers aren't the Director's to name here.
    other = next(p for p in grid["papers"] if not p["director_paper"])
    assert client.put(f"/api/terms/{term_id}/health-papers/{other['id']}/invigilators", json={"invigilators": {}}).status_code == 404


def test_a_heading_names_a_class_and_its_students():
    assert class_of("BACHELOR OF SCIENCE NURSING (SEPTEMBER 2026 INTAKE) Y1S1 (107 STUDENTS) MISHECK 0793315005") == {
        "name": "BACHELOR OF SCIENCE NURSING", "year": 1, "semester": 1, "students": 107,
    }
    assert class_of("BACHELOR OF SCIENCE IN MEDICAL BIOCHEMISTRY YEAR 3 SEMESTER 1 GSS (2 STUDENTS)") == {
        "name": "BACHELOR OF SCIENCE IN MEDICAL BIOCHEMISTRY", "year": 3, "semester": 1, "students": 2,
    }
    assert class_of("BACHELOR OF SCIENCE IN ENVIRONMENTAL SCIENCE Y1S1 2026 INTAKE 3 STUDENTS SSP")["students"] == 3
    health = class_of("BACHELOR OF SCIENCE IN HEALTH RECORDS (SEPTEMBER 2026 INTAKE) (14 STUDENTS) PATRICK")
    assert health == {"name": "BACHELOR OF SCIENCE IN HEALTH RECORDS", "year": None, "semester": None, "students": 14}
    for heading in ("SERVICING UNITS", "CERTIFICATE IN ANIMAL HEALTH", "ODEL/PART-TIME DRAFTS", "REGULAR EXAM DRAFTS"):
        assert class_of(heading) is None


NAMED = [
    ["", "BACHELOR OF SCIENCE NURSING (SEPTEMBER 2026 INTAKE) Y1S1 (107 STUDENTS)", ""],
    ["1", "NURS 111", "Human Anatomy I"],
    ["2", "MATH 101", "Mathematics for Sciences"],
    ["", "BSc Health Records (14 students)", ""],
    ["3", "NURS 111", "Human Anatomy I"],
    ["", "SERVICING UNITS", ""],
    ["4", "BOTA 473", "Plant Biochemistry"],
]


def test_the_review_lists_the_letters_classes_matched_to_programmes_and_what_counts_as_health(client, teaching, smarttt):
    sign_in(client)
    term_id = setup_exams(client, teaching)
    smarttt.programs = [{"code": "BSCN", "name": "Bachelor of Science in Nursing"}, {"code": "COSC", "name": "BSc Computer Science"}]
    r = ok(client.post(f"/api/terms/{term_id}/health-papers/read", json={"file": letter(NAMED)}))
    assert [(c["name"], c["year"], c["students"], c["programme"], c["matched"]) for c in r["classes"]] == [
        ("BACHELOR OF SCIENCE NURSING", 1, 107, "BSCN", True),
        ("BSc Health Records", None, 14, "", False),
    ]
    by_code = {e["codes"][0]: e for e in r["entries"] if e["duplicate_of"] is None}
    assert len(by_code["NURS 111"]["letter_classes"]) == 2  # both classes sit the one paper
    assert (by_code["NURS 111"]["category"], by_code["MATH 101"]["category"], by_code["BOTA 473"]["category"]) == ("health", "regular", "regular")
    assert by_code["BOTA 473"]["letter_classes"] == []


def test_saved_classes_and_numbers_come_from_the_letter_and_stay(client, teaching, smarttt):
    sign_in(client)
    term_id = setup_exams(client, teaching)
    nursing = {"programme": "BSCN", "year": 1, "semester": 1, "stream": "", "students": 107}
    records = {"programme": "BSC HEALTH RECORDS", "year": 1, "semester": 1, "stream": "", "students": 14}
    smarttt.enrolment = {"NURS 111": unit(cls("BSCN", 1, 3), cls("BSCM", 1, 9)), "ZOOL 143": unit()}
    body = {
        "papers": [
            {"codes": ["NURS 111"], "title": "Human Anatomy I", "classes": [nursing, records]},
            {"codes": ["ZOOL 143"], "title": "HIV/AIDS and Society", "classes": [{**nursing, "students": 50, "programme": "BSC AGRIBUSINESS"}]},
        ]
    }
    ok(client.post(f"/api/terms/{term_id}/health-papers", json=body))
    data = ok(client.get(f"/api/terms/{term_id}/exams"))
    papers = {p["codes"]: p for p in data["papers"]}
    assert sorted((r["programme"], r["students"]) for r in papers["NURS 111"]["rows"]) == [("BSC HEALTH RECORDS", 14), ("BSCM", 9), ("BSCN", 107)]
    assert papers["NURS 111"]["category"] == "health" and papers["ZOOL 143"]["category"] == "regular"
    assert "NURS" in data["period"]["exam_health_prefixes"] and "ZOOL" not in data["period"]["exam_health_prefixes"]
    # SMARTTT read again: the letter's numbers stay.
    smarttt.enrolment["NURS 111"] = unit(cls("BSCN", 1, 30))
    ok(client.post(f"/api/terms/{term_id}/health-papers/recount"))
    papers = {p["codes"]: p for p in ok(client.get(f"/api/terms/{term_id}/exams"))["papers"]}
    assert ("BSCN", 107) in [(r["programme"], r["students"]) for r in papers["NURS 111"]["rows"]]

