"""Every PDF and Word download is on the university's letterhead.

The header is on page 1; the watermark and footer are on every page.
"""

from __future__ import annotations

from io import BytesIO
from types import SimpleNamespace
from typing import Any

import pypdfium2 as pdfium
import pytest
from docx import Document
from docx.oxml.ns import qn

from app.services import exam_export, export, letterhead
from tests.conftest import sign_in
from tests.fake_smarttt import TERM as TERM_REF
from tests.test_exams import _generate, ok, setup_exams

TERM = SimpleNamespace(
    academic_year="2026/2027",
    semester=1,
    name="",
    prepared_by="",
    prepared_by_title="",
    version_label="",
    use_from=None,
)


def _grid() -> dict[str, Any]:
    """Enough class rows for the teaching timetable to run over several pages."""
    cells = [
        {"unit_code": "COSC 101", "group": "GR A", "room": "LH 1", "lecturer": "", "start_slot": 0, "length": 2},
        {"unit_code": "COSC 102", "group": "", "room": "LH 2", "lecturer": "", "start_slot": 20, "length": 3},
    ]
    entities = [{"label": f"BSC.CS Y1S1 GR{i}", "cells": [{**c, "pinned": False} for c in cells]} for i in range(60)]
    return {
        "view": "row",
        "hours": 12,
        "first_hour": 7,
        "draft": {"name": "Draft 1", "status": "shared"},
        "entities": entities,
    }


def _busy_exam_timetable() -> dict[str, Any]:
    """An exam timetable long enough to run over several pages."""
    days = [{"date": f"2026-12-0{d}", "label": f"DAY 0{d}/12/2026"} for d in range(1, 6)]
    papers = [
        {
            "codes": f"COSC {100 + i}",
            "day": days[i % 5]["date"],
            "session": i % 2,
            "seating": [{"room": f"UTC {i % 9}"}],
        }
        for i in range(260)
    ]
    sessions = [{"start": "08:30", "end": "10:30"}, {"start": "11:30", "end": "13:30"}]
    return {"days": days, "sessions": sessions, "papers": papers, "practicals": []}


@pytest.fixture
def downloads(client, teaching) -> dict[str, bytes]:
    """Every PDF and Word download: the teaching timetable, and the exam timetable, room sheets and roster of a
    generated exam draft as the API serves them."""
    sign_in(client)
    term_id = setup_exams(client, teaching, smarttt_term_id=TERM_REF["id"])
    ok(client.post(f"/api/terms/{term_id}/exams/import"))
    draft_id = _generate(client, term_id)
    files = {
        f"exam {kind}.{fmt}": client.get(f"/api/exam-drafts/{draft_id}/export/{kind}.{fmt}").content
        for kind in ("timetable", "rooms", "roster")
        for fmt in ("pdf", "docx")
    }
    files["teaching.pdf"] = export.build_pdf(TERM, _grid(), "Director")  # type: ignore[arg-type]
    files["teaching.docx"] = export.build_docx(TERM, _grid(), "Director")  # type: ignore[arg-type]
    files["busy exam timetable.pdf"] = exam_export.timetable_pdf(TERM, _busy_exam_timetable(), 1, "Director")  # type: ignore[arg-type]
    return files


def _check_pdf(content: bytes) -> int:
    pdf = pdfium.PdfDocument(content)
    for n, page in enumerate(pdf):
        text = page.get_textpage().get_text_range()
        assert letterhead.ISO_LINE in text and letterhead.MOTTO in text
        # The logo watermark and the certification mark, plus the header's logo on page 1.
        images = [o for o in page.get_objects() if o.type == pdfium.raw.FPDF_PAGEOBJ_IMAGE]
        assert len(images) == (3 if n == 0 else 2)
        assert ("THARAKA" in text and "+254 745 838 353" in text) is (n == 0)
        assert text.count("UNIVERSITY") == (1 if n == 0 else 0), "only the letterhead names the university"
    return len(pdf)


def _check_docx(content: bytes) -> None:
    doc = Document(BytesIO(content))
    first = doc.element.body[0]
    assert first.tag == qn("w:tbl")
    header_text = "".join(t.text or "" for t in first.iter(qn("w:t")))
    assert "THARAKA" in header_text and "UNIVERSITY" in header_text and "+254 745 838 353" in header_text
    assert "THARAKA UNIVERSITY" not in "\n".join(p.text for p in doc.paragraphs), "the title doesn't repeat it"

    section = doc.sections[0]
    assert not section.different_first_page_header_footer, "page 1 gets the watermark and footer too"
    watermark = section.header._element.find(".//" + qn("wp:anchor"))
    assert watermark is not None and watermark.get("behindDoc") == "1"
    assert watermark.find(".//" + qn("a:alphaModFix")) is not None
    footer = section.footer.paragraphs[0]
    assert letterhead.ISO_LINE in footer.text and letterhead.MOTTO in footer.text
    assert footer._p.find(".//" + qn("a:blip")) is not None, "the certification mark"


def test_every_download_is_on_the_letterhead(downloads):
    """The header on page 1 only; the watermark and the ISO footer on every page, page 1 included."""
    pages = {name: _check_pdf(content) for name, content in downloads.items() if name.endswith(".pdf")}
    assert pages["teaching.pdf"] > 1 and pages["busy exam timetable.pdf"] > 1, "checked over several pages"
    for name, content in downloads.items():
        if name.endswith(".docx"):
            _check_docx(content)
    assert len(downloads) == 9
