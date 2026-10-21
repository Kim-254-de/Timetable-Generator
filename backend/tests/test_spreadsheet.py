from __future__ import annotations

import io
from datetime import date, time

from openpyxl import Workbook

from tests.conftest import sign_in

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def workbook_bytes() -> bytes:
    book = Workbook()
    sheet = book.active
    sheet.title = "Allocation"
    sheet.append(["TEACHING TIMETABLE MAY-AUGUST 2026: UNITS"])
    sheet.append([])
    sheet.append(["Unit code", "Lecturer", "Hours", "Starts", "At", None])
    sheet.append(["COSC 103", "Dr. Jane\tMwangi", 3.0, date(2026, 9, 7), time(8, 0)])
    sheet.append(["COSC 211", None, 2.5])
    book.create_sheet("Empty")
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_a_prepared_workbook_comes_back_as_text_cells(client, smarttt):
    sign_in(client)
    response = client.post("/api/spreadsheets/read", content=workbook_bytes(), headers={"Content-Type": XLSX})
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {
        "sheets": [
            {
                "name": "Allocation",
                "rows": [
                    ["TEACHING TIMETABLE MAY-AUGUST 2026: UNITS"],
                    ["Unit code", "Lecturer", "Hours", "Starts", "At"],
                    ["COSC 103", "Dr. Jane Mwangi", "3", "2026-09-07", "08:00"],
                    ["COSC 211", "", "2.5"],
                ],
            }
        ]
    }


def test_other_files_are_refused_with_a_way_out(client, smarttt):
    sign_in(client)
    for content in (b"Unit code,Lecturer\nCOSC 103,Jane\n", b"PK\x03\x04 not really a zip", b""):
        response = client.post("/api/spreadsheets/read", content=content, headers={"Content-Type": XLSX})
        assert response.status_code == 422, response.text
        assert response.json()["error"]["code"] in ("NOT_XLSX", "EMPTY_FILE")


def test_reading_needs_a_sign_in(client, smarttt):
    response = client.post("/api/spreadsheets/read", content=workbook_bytes(), headers={"Content-Type": XLSX})
    assert response.status_code in (401, 403)
