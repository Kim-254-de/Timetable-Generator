"""
The Directorate enters everything in the Generator, with no SMARTTT data:
a term, lecture halls, departments, class rows and units; then it generates,
publishes and downloads the timetable as PDF, Word and Excel.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import sign_in


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()["data"]


def enter_term(client: TestClient) -> dict[str, Any]:
    """The client's example: COSC 100 for one class row, COSC 103 split into GR A/B/C."""
    term = ok(
        client.post(
            "/api/terms",
            json={
                "academic_year": "2026/2027",
                "semester": 1,
                "name": "September-December 2026",
                "version_label": "VERSION_1 DATED 19/09/2026",
                "use_from": "2026-09-21",
                "prepared_by": "Dr. Alex Mutegi Rwanda",
            },
        )
    )
    assert term["smarttt_term_id"] is None and term["default_session_length"] == 3

    result = ok(
        client.post(
            "/api/rooms/bulk",
            json={
                "rows": [
                    {"code": "UTC 1", "building": "UTC", "capacity": "200", "room_type": "Lecture hall"},
                    {"code": "STB 1", "building": "STB", "capacity": "120", "room_type": "Lecture hall"},
                    {"code": "STB 2", "building": "STB", "capacity": "120", "room_type": "lecture hall"},
                    {"code": "STB 3", "building": "STB", "capacity": "120", "room_type": "Hall"},
                    {"code": "LAB 1", "building": "STB", "capacity": "40", "room_type": "Computer lab"},
                    {"code": "BAD", "building": "X", "capacity": "lots"},
                ]
            },
        )
    )
    assert result["created"] == 5 and result["error_count"] == 1 and result["errors"][0]["line"] == 6

    cs = ok(client.post("/api/departments", json={"code": "DCOMP", "name": "Computer Science", "lecturer_count": 6}))
    edu = ok(client.post("/api/departments", json={"code": "DEDU", "name": "Education"}))
    assert cs["id"] >= 100_000 and edu["id"] == cs["id"] + 1

    rows = ok(
        client.post(
            f"/api/terms/{term['id']}/class-rows/bulk",
            json={
                "rows": [
                    {
                        "programme": "BSC.COMP SCI",
                        "year": "1",
                        "semester": "1",
                        "department": "DCOMP",
                        "students": "90",
                    },
                    {
                        "programme": "BED.ENG/LIT",
                        "year": "1",
                        "semester": "1",
                        "sub_class": "1",
                        "department": "DEDU",
                        "students": "110",
                    },
                    {
                        "programme": "BED.KISW/RELI",
                        "year": "1",
                        "semester": "1",
                        "department": "DEDU",
                        "students": "100",
                    },
                    {
                        "programme": "BED.MATH/BIO",
                        "year": "1",
                        "semester": "1",
                        "department": "DEDU",
                        "students": "105",
                    },
                ]
            },
        )
    )
    assert rows["created"] == 4, rows
    labels = {r["label"]: r["id"] for r in ok(client.get(f"/api/terms/{term['id']}/class-rows"))}
    assert "BED.ENG/LIT Y1S1 (1)" in labels

    cosc100 = ok(
        client.post(
            f"/api/terms/{term['id']}/offerings",
            json={
                "unit_code": "COSC 100",
                "unit_name": "Introduction to Computing",
                "department_id": cs["id"],
                "class_row_ids": [labels["BSC.COMP SCI Y1S1"]],
            },
        )
    )
    # Hours default to the term's 3-hour block; a unit with sized class rows starts as one whole class.
    assert cosc100["weekly_hours"] == 3 and cosc100["session_length"] == 3
    assert [g["label"] for g in cosc100["groups"]] == [""]

    education = [labels["BED.ENG/LIT Y1S1 (1)"], labels["BED.KISW/RELI Y1S1"], labels["BED.MATH/BIO Y1S1"]]
    cosc103 = ok(
        client.post(
            f"/api/terms/{term['id']}/offerings",
            json={
                "unit_code": "COSC 103",
                "unit_name": "Introduction to ICT Skills",
                "department_id": cs["id"],
                "class_row_ids": education,
            },
        )
    )
    whole = cosc103["groups"][0]
    ok(client.delete(f"/api/groups/{whole['id']}"))
    for label, row_id, students in zip(("GR A", "GR B", "GR C"), education, (110, 100, 105), strict=True):
        ok(
            client.post(
                f"/api/offerings/{cosc103['id']}/groups",
                json={"label": label, "members": [{"class_row_id": row_id, "students": students}]},
            )
        )
    return term


def test_director_enters_everything_and_downloads(client, smarttt):
    sign_in(client)
    term = enter_term(client)
    overview = ok(client.get(f"/api/terms/{term['id']}"))
    assert overview["readiness"]["ready"] is True, overview["readiness"]["problems"]

    run = ok(client.post("/api/runs", json={"term_id": term["id"], "time_limit_s": 20}))
    assert run["status"] == "succeeded", run["failure"]
    draft_id = run["draft_id"]
    grid = ok(client.get(f"/api/drafts/{draft_id}?view=row"))
    assert grid["draft"]["violation_count"] == 0
    groups = {c["group"] for e in grid["entities"] for c in e["cells"] if c["unit_code"] == "COSC 103"}
    assert groups == {"GR A", "GR B", "GR C"}

    # Published without SMARTTT: the approval stands, flagged as not sent.
    published = ok(client.post(f"/api/drafts/{draft_id}/publish", json={}))
    assert published["version"] == 1 and published["smarttt"]["sent"] is False
    assert smarttt.payloads == []
    assert ok(client.get(f"/api/terms/{term['id']}"))["publications"][0]["sent_to_smarttt"] is False

    pdf = client.get(f"/api/drafts/{draft_id}/export.pdf?view=row")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    word = client.get(f"/api/drafts/{draft_id}/export.docx?view=row")
    assert word.status_code == 200 and word.content.startswith(b"PK")
    assert "wordprocessingml" in word.headers["content-type"]
    excel = client.get(f"/api/drafts/{draft_id}/export.xlsx?view=room")
    assert excel.status_code == 200 and excel.content.startswith(b"PK")
    assert client.get(f"/api/drafts/{draft_id}/export.txt").status_code == 404

    from docx import Document

    document = Document(BytesIO(word.content))
    text = "\n".join(p.text for p in document.paragraphs)
    assert "SEPTEMBER-DECEMBER 2026 TEACHING TIMETABLE" in text
    assert "Prepared by Dr. Alex Mutegi Rwanda, Director Examination & Timetabling" in text
    assert "To be used from Monday 21/09/2026" in text
    table = document.tables[0]
    assert len(table.columns) == 61
    assert any("COSC 103" in c.text and "GR A" in c.text for row in table.rows for c in row.cells)


def test_allocator_reads_units_groups_and_meetings(client, smarttt):
    sign_in(client)
    term = enter_term(client)
    no_key = client.get("/api/integrations/allocator/terms")
    assert no_key.status_code == 401
    headers = {"X-API-Key": "test-allocator-key"}
    terms = ok(client.get("/api/integrations/allocator/terms", headers=headers))
    assert terms[0]["id"] == term["id"] and terms[0]["published_version"] is None

    before = ok(client.get(f"/api/integrations/allocator/terms/{term['id']}/sections", headers=headers))
    keys = {s["key"]: s for s in before["sections"]}
    assert set(keys) == {"COSC100-MAIN", "COSC103-GRA", "COSC103-GRB", "COSC103-GRC"}
    assert keys["COSC103-GRA"]["department"]["code"] == "DCOMP"
    assert keys["COSC103-GRA"]["class_rows"][0]["department"]["code"] == "DEDU"  # servicing
    assert keys["COSC103-GRA"]["meetings"] == []  # nothing published yet

    draft_id = ok(client.post("/api/runs", json={"term_id": term["id"], "time_limit_s": 20}))["draft_id"]
    ok(client.post(f"/api/drafts/{draft_id}/publish", json={}))
    after = ok(client.get(f"/api/integrations/allocator/terms/{term['id']}/sections", headers=headers))
    assert after["published_version"] == 1
    meeting = next(s for s in after["sections"] if s["key"] == "COSC103-GRB")["meetings"][0]
    assert meeting["room"] in {"UTC 1", "STB 1", "STB 2", "STB 3"}
    assert int(meeting["end_time"][:2]) - int(meeting["start_time"][:2]) == 3


def test_deleting_what_is_in_use_is_refused(client, smarttt):
    sign_in(client)
    term = enter_term(client)
    rows = ok(client.get(f"/api/terms/{term['id']}/class-rows"))
    in_use = next(r for r in rows if r["label"] == "BSC.COMP SCI Y1S1")
    refused = client.delete(f"/api/class-rows/{in_use['id']}")
    assert refused.status_code == 409 and refused.json()["error"]["code"] == "IN_USE"

    departments = {d["code"]: d for d in ok(client.get("/api/departments"))}
    assert client.delete(f"/api/departments/{departments['DCOMP']['id']}").status_code == 409

    draft_id = ok(client.post("/api/runs", json={"term_id": term["id"], "time_limit_s": 20}))["draft_id"]
    grid = ok(client.get(f"/api/drafts/{draft_id}?view=room"))
    used_room = grid["entities"][0]["id"]
    assert client.delete(f"/api/rooms/{used_room}").status_code == 409
    closed = ok(client.patch(f"/api/rooms/{used_room}", json={"active": False}))
    assert closed["active"] is False


def test_duplicates_are_refused_and_bulk_updates(client, smarttt):
    sign_in(client)
    term = enter_term(client)
    dup = client.post("/api/rooms", json={"code": "utc 1", "capacity": 50})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "CODE_TAKEN"
    again = ok(client.post("/api/rooms/bulk", json={"rows": [{"code": "UTC 1", "capacity": "250"}]}))
    assert again == {"created": 0, "updated": 1, "errors": [], "error_count": 0}
    assert next(r for r in ok(client.get("/api/rooms")) if r["code"] == "UTC 1")["capacity"] == 250

    departments = {d["code"]: d for d in ok(client.get("/api/departments"))}
    dup_unit = client.post(
        f"/api/terms/{term['id']}/offerings",
        json={"unit_code": "cosc100", "unit_name": "Again", "department_id": departments["DCOMP"]["id"]},
    )
    assert dup_unit.status_code == 409

    bulk_units = ok(
        client.post(
            f"/api/terms/{term['id']}/offerings/bulk",
            json={
                "rows": [
                    {
                        "unit_code": "COSC 104",
                        "unit_title": "Web Programming",
                        "department": "DCOMP",
                        "class_rows": "BSC.COMP SCI Y1S1",
                        "room_type": "Lab",
                    },
                    {
                        "unit_code": "COSC 105",
                        "unit_title": "Support",
                        "department": "NOPE",
                        "class_rows": "BSC.COMP SCI Y1S1",
                    },
                    {
                        "unit_code": "COSC 106",
                        "unit_title": "Install",
                        "department": "DCOMP",
                        "class_rows": "NO SUCH ROW Y1S1",
                    },
                ]
            },
        )
    )
    assert bulk_units["created"] == 1 and bulk_units["error_count"] == 2
    assert "department" in bulk_units["errors"][0]["message"]
    assert "class rows not found" in bulk_units["errors"][1]["message"]


def test_copy_a_term_into_the_next(client, smarttt):
    sign_in(client)
    first = enter_term(client)
    second = ok(
        client.post("/api/terms", json={"academic_year": "2026/2027", "semester": 2, "copy_from_term_id": first["id"]})
    )
    offerings = {o["unit_code"]: o for o in ok(client.get(f"/api/terms/{second['id']}/offerings"))}
    assert set(offerings) == {"COSC 100", "COSC 103"}
    assert sorted(g["label"] for g in offerings["COSC 103"]["groups"]) == ["GR A", "GR B", "GR C"]
    assert len(ok(client.get(f"/api/terms/{second['id']}/class-rows"))) == 4
    twice = ok(client.post(f"/api/terms/{second['id']}/copy", json={"source_term_id": first["id"]}))
    assert twice == {"class_rows_copied": 0, "units_copied": 0}
    clash = client.post("/api/terms", json={"academic_year": "2026/2027", "semester": 2})
    assert clash.status_code == 409
