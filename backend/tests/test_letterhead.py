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
from PIL import Image

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
    # Pale in the image itself, so every viewer shows it faint, and in the logo's proportions.
    blip = watermark.find(".//" + qn("a:blip")).get(qn("r:embed"))
    picture = Image.open(BytesIO(section.header.part.related_parts[blip].blob)).convert("L")
    assert picture.getextrema()[0] > 200
    extent = watermark.find(qn("wp:extent"))
    assert int(extent.get("cx")) / int(extent.get("cy")) == pytest.approx(365 / 359, abs=0.01)
    assert int(extent.get("cy")) <= section.page_height * 0.6 and int(extent.get("cx")) <= section.page_width * 0.6
    footer = section.footer.paragraphs[0]
    assert letterhead.ISO_LINE in footer.text and letterhead.MOTTO in footer.text
    assert footer._p.find(".//" + qn("a:blip")) is not None, "the certification mark"
    tabs = {t.get(qn("w:val")): t.get(qn("w:pos")) for t in footer._p.iter(qn("w:tab")) if t.get(qn("w:val"))}
    assert tabs["clear"] and int(tabs["right"]) * 635 == section.page_width - section.left_margin - section.right_margin
    margins = first.find(qn("w:tblPr")).find(qn("w:tblCellMar"))
    assert margins is not None and {m.get(qn("w:w")) for m in margins} == {"0"}, "the header text mustn't wrap"


def test_every_download_is_on_the_letterhead(downloads):
    """The header on page 1 only; the watermark and the ISO footer on every page, page 1 included."""
    pages = {name: _check_pdf(content) for name, content in downloads.items() if name.endswith(".pdf")}
    assert pages["teaching.pdf"] > 1 and pages["busy exam timetable.pdf"] > 1, "checked over several pages"
    for name, content in downloads.items():
        if name.endswith(".docx"):
            _check_docx(content)
    assert len(downloads) == 9


def test_the_exam_timetable_pdf_runs_on_from_the_letterhead_like_the_word_download():
    """A PDF table can't split a row: uncut, a busy day left page 1 empty and gaps on later pages."""
    rec = _busy_exam_timetable()
    pdf = pdfium.PdfDocument(exam_export.timetable_pdf(TERM, rec, 1, "Director"))  # type: ignore[arg-type]
    pages = [page.get_textpage().get_text_range() for page in pdf]
    assert "DATE/DAY" in pages[0] and "DAY 01/12/2026" in pages[0] and "COSC 100" in pages[0]
    text = "\n".join(pages)
    assert all(f"COSC {100 + i} " in text for i in range(260)), "every paper is there"
    assert all(text.count(f"COSC {100 + i} ") == 1 for i in range(260)), "and only once"
    # Every page but the last is full: its last line of a paper sits near the footer.
    for page in list(pdf)[:-1]:
        lowest = min(
            o.get_bounds()[1]
            for o in page.get_objects()
            if o.type == pdfium.raw.FPDF_PAGEOBJ_TEXT and o.get_bounds()[1] > letterhead.FOOTER_HEIGHT
        )
        assert lowest < letterhead.FOOTER_HEIGHT + 30


def test_a_day_with_nothing_on_it_keeps_its_row_and_a_long_day_keeps_its_date():
    rows = [["MON 01/12/2026", "", ""], ["TUE 02/12/2026", "\n".join(f"P{i}" for i in range(100)), "Q"]]
    flowed = exam_export._flow_rows(rows, [80.0, 300.0, 300.0], 200.0, 400.0)
    assert flowed[0] == ["MON 01/12/2026", "", ""]
    assert [r[0] for r in flowed[1:]] == ["TUE 02/12/2026"] + ["TUE 02/12/2026 (cont.)"] * (len(flowed) - 2)
    assert "\n".join(r[1] for r in flowed[1:]).split("\n") == [f"P{i}" for i in range(100)]
    assert flowed[1][2] == "Q"


def test_the_exam_word_downloads_are_a4_and_the_timetable_keeps_its_headings_on_every_page():
    rec = _busy_exam_timetable()
    doc = Document(BytesIO(exam_export.timetable_docx(TERM, rec, 1, "Director")))  # type: ignore[arg-type]
    section = doc.sections[0]
    assert (round(section.page_width.mm), round(section.page_height.mm)) == (297, 210)
    grid = doc.tables[1]
    assert grid.rows[0]._tr.trPr.find(qn("w:tblHeader")) is not None
    assert round(grid.columns[0].width.mm) == 28
    room = section.page_width - section.left_margin - section.right_margin
    assert abs(sum(c.width for c in grid.columns) - room) < 12700  # within a point
