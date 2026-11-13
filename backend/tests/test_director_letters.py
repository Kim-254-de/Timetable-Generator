"""The Director uploads a department's moderation letter: read and saved by Smart Attendance, then imported here."""

from __future__ import annotations

from typing import Any

from tests.conftest import sign_in
from tests.fake_smarttt import TERM
from tests.fake_teaching import FakeTeaching

DOCX = b"PK\x03\x04 a pretend Word document"


def ok(response: Any) -> Any:
    assert response.status_code == 200, response.text
    return response.json()["data"]


def test_the_director_uploads_a_letter_and_its_papers_come_in(client, teaching: FakeTeaching, smarttt):
    sign_in(client)
    term = ok(client.post("/api/terms", json={"smarttt_term_id": TERM["id"]}))
    me = ok(client.get("/api/auth/me"))

    review = ok(client.post(f"/api/terms/{term['id']}/exam-list/read?department=DHRM", content=DOCX))
    assert review["entries"][0]["codes"] == ["HRIM 111"]
    assert teaching.letters_read[0]["account_id"] == me["account_id"]
    assert teaching.letters_read[0]["department_code"] == "DHRM"

    letter = {"codes": ["HRIM 111"], "title": "Records", "sitting": "regular", "replacesPaperId": None}
    result = ok(client.post(f"/api/terms/{term['id']}/exam-list", json={"department_code": "DHRM", "papers": [letter]}))
    assert result["saved"]["published"] == 1
    assert teaching.letters_saved[0]["papers"] == [{"codes": ["HRIM 111"], "title": "Records", "sitting": "regular"}]
    assert [p["codes"] for p in ok(client.get(f"/api/terms/{term['id']}/exams"))["papers"]] == ["HRIM 111"]


def test_attendance_refusals_are_shown_as_it_said_them(client, teaching: FakeTeaching, smarttt):
    sign_in(client)
    term = ok(client.post("/api/terms", json={"smarttt_term_id": TERM["id"]}))
    bad = client.post(f"/api/terms/{term['id']}/exam-list/read?department=DHRM", content=b"not a docx")
    assert bad.status_code == 422
    assert "not a Word document" in bad.json()["error"]["message"]
    unknown = client.post(
        f"/api/terms/{term['id']}/exam-list",
        json={"department_code": "NOPE", "papers": [{"codes": ["X 1"], "title": "X", "sitting": "regular"}]},
    )
    assert unknown.status_code == 404
    assert "NOPE" in unknown.json()["error"]["message"]


def test_a_letter_is_capped_at_5_mb(client, teaching: FakeTeaching, smarttt):
    sign_in(client)
    term = ok(client.post("/api/terms", json={"smarttt_term_id": TERM["id"]}))
    big = client.post(
        f"/api/terms/{term['id']}/exam-list/read?department=DHRM", content=DOCX + b"x" * (5 * 1024 * 1024)
    )
    assert big.status_code == 413
