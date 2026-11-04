"""
Exam downloads, Word and PDF:

- the exam timetable in the Directorate's layout, on the university's
  letterhead: DIRECTORATE OF EXAMINATION & TIMETABLING, the title line, a DATE/DAY x
  session grid of `paper -> rooms`, practicals on their dates, "Prepared by";
- room sheets: per date and session, each room's papers, class rows,
  students and invigilator;
- the invigilation roster per department.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from app.models import Term
from app.services.exam_drafts import MAIN, room_sheets

DIRECTORATE = "DIRECTORATE OF EXAMINATION & TIMETABLING"


def _title(term: Term, version: int | None) -> list[str]:
    name = (term.name or f"{term.academic_year} semester {term.semester}").upper()
    line = f"END OF {name} EXAMINATION TIMETABLE"
    # The university is named by the letterhead above this (letterhead.py).
    return [DIRECTORATE, line + (f" - VERSION {version}" if version else " - DRAFT")]


def _prepared(term: Term, printed_by: str) -> str:
    return f"Prepared by: {term.prepared_by or printed_by}, {term.prepared_by_title}"


def _session_label(s: dict[str, str]) -> str:
    return f"{s['start']}-{s['end']}"


def timetable_table(rec: dict[str, Any]) -> tuple[list[str], list[list[str]]]:
    """The header and rows of the date x session grid; each cell lists `paper -> rooms`."""
    cells: dict[tuple[str, int], list[str]] = defaultdict(list)
    for p in rec["papers"]:
        if p["day"] is None:
            continue
        rooms = sorted({s["room"] for s in p["seating"]})
        cells[(p["day"], p["session"])].append(f"{p['codes']} → {', '.join(rooms)}")
    header = ["DATE/DAY", *[_session_label(s) for s in rec["sessions"]]]
    rows = []
    for d in rec["days"]:
        rows.append([d["label"], *["\n".join(sorted(cells[(d["date"], i)])) for i in range(len(rec["sessions"]))]])
    return header, rows


def practical_lines(rec: dict[str, Any]) -> list[str]:
    return [
        f"{date.fromisoformat(p['date']):%a %d/%m/%Y}  {p['start_time']}-{p['end_time']}  "
        f"{p['codes']} {p['title']} PRACTICALS"
        for p in rec["practicals"]
    ]


ROSTER_HEADERS = ["Paper", "Date", "Session", "Room", "Duty", "Invigilator"]
ROOM_HEADERS = ["Room", "Paper", "Class row", "Students", "Invigilator"]


def roster(rec: dict[str, Any]) -> dict[str, list[list[str]]]:
    """Per department: each paper's main invigilator (collects every room's scripts), then one per extra room."""
    out: dict[str, list[list[str]]] = defaultdict(list)
    days = {d["date"]: d["label"] for d in rec["days"]}
    for p in rec["papers"]:
        if p["day"] is None:
            continue
        when = [days.get(p["day"], p["day"]), _session_label(rec["sessions"][p["session"]])]
        main = p["invigilators"].get(MAIN) or {}
        out[p["department"]].append([p["codes"], *when, p["main_room"] or "", "Main", main.get("name") or "Not named"])
        for room in p["extra_rooms"]:
            extra = p["invigilators"].get(room) or {}
            out[p["department"]].append([p["codes"], *when, room, "Extra", extra.get("name") or "Not named"])
    return dict(sorted(out.items()))


def _room_rows(slot: dict[str, Any]) -> list[list[str]]:
    rows = []
    for room in slot["rooms"]:
        for paper in room["papers"]:
            who = paper["invigilator"] or "Not named"
            who += " (main)" if paper["main"] else f" (extra; main: {paper['main_invigilator'] or 'not named'})"
            for row in paper["rows"]:
                odel = " (ODEL)" if row["odel"] else ""
                rows.append([room["room"], paper["codes"], row["row"] + odel, str(row["students"]), who])
    return rows


# -- Word ---------------------------------------------------------------------------------------


def _docx_heading(doc: Any, lines: list[str]) -> None:
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    for line in lines:
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(line)
        run.bold = True
        run.font.size = Pt(12)


def _docx_table(doc: Any, header: list[str], rows: list[list[str]]) -> None:
    table = doc.add_table(rows=len(rows) + 1, cols=len(header))
    table.style = "Table Grid"
    for r, values in enumerate([header, *rows]):
        for c, value in enumerate(values):
            cell = table.rows[r].cells[c]
            cell.text = value
            if r == 0:
                for run in cell.paragraphs[0].runs:
                    run.bold = True


def _new_docx(landscape: bool) -> Any:
    from docx import Document
    from docx.enum.section import WD_ORIENT
    from docx.shared import Cm, Pt

    doc = Document()
    section = doc.sections[0]
    if landscape:
        section.orientation = WD_ORIENT.LANDSCAPE
        section.page_width, section.page_height = section.page_height, section.page_width
    section.left_margin = section.right_margin = Cm(1.2)
    section.top_margin = section.bottom_margin = Cm(1.2)
    doc.styles["Normal"].font.size = Pt(8)
    return doc


def _save(doc: Any) -> bytes:
    from app.services import letterhead

    letterhead.apply_to_docx(doc)
    out = BytesIO()
    doc.save(out)
    return out.getvalue()


def timetable_docx(term: Term, rec: dict[str, Any], version: int | None, printed_by: str) -> bytes:
    doc = _new_docx(landscape=True)
    _docx_heading(doc, _title(term, version))
    header, rows = timetable_table(rec)
    _docx_table(doc, header, rows)
    lines = practical_lines(rec)
    if lines:
        doc.add_paragraph().add_run("PRACTICALS").bold = True
        for line in lines:
            doc.add_paragraph(line)
    doc.add_paragraph()
    doc.add_paragraph(_prepared(term, printed_by))
    return _save(doc)


def rooms_docx(term: Term, rec: dict[str, Any], version: int | None, printed_by: str) -> bytes:
    doc = _new_docx(landscape=False)
    _docx_heading(doc, [*_title(term, version), "ROOM SHEETS"])
    days = {d["date"]: d["label"] for d in rec["days"]}
    for slot in room_sheets(rec):
        session = rec["sessions"][slot["session"]]
        doc.add_paragraph().add_run(f"{days.get(slot['day'], slot['day'])}  {_session_label(session)}").bold = True
        rows = _room_rows(slot)
        _docx_table(doc, ROOM_HEADERS, rows)
    doc.add_paragraph(_prepared(term, printed_by))
    return _save(doc)


def roster_docx(term: Term, rec: dict[str, Any], version: int | None, printed_by: str) -> bytes:
    doc = _new_docx(landscape=False)
    _docx_heading(doc, [*_title(term, version), "INVIGILATION ROSTER"])
    for department, rows in roster(rec).items():
        doc.add_paragraph().add_run(department).bold = True
        _docx_table(doc, ROSTER_HEADERS, rows)
    doc.add_paragraph(_prepared(term, printed_by))
    return _save(doc)


# -- PDF ----------------------------------------------------------------------------------------


PDF_MARGIN_MM = 10  # left, right and top; the bottom leaves room for the letterhead footer
FRAME_PADDING = 6  # what ReportLab's page frame keeps inside the margins on every side, in points


def _pdf_body_height(landscape_page: bool) -> float:
    """The height a page's story can fill: the page less its margins and the frame's padding."""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm

    from app.services import letterhead

    height = (landscape(A4) if landscape_page else A4)[1]
    return height - PDF_MARGIN_MM * mm - (letterhead.FOOTER_HEIGHT + 3 * mm) - 2 * FRAME_PADDING


def _pdf(story_for: Any, landscape_page: bool, title: str) -> bytes:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate

    from app.services import letterhead

    out = BytesIO()
    page = letterhead.on_page()
    pagesize = landscape(A4) if landscape_page else A4
    SimpleDocTemplate(
        out,
        pagesize=pagesize,
        leftMargin=PDF_MARGIN_MM * mm,
        rightMargin=PDF_MARGIN_MM * mm,
        topMargin=PDF_MARGIN_MM * mm,
        bottomMargin=letterhead.FOOTER_HEIGHT + 3 * mm,
        title=title,
    ).build([letterhead.first_page_header(), *story_for()], onFirstPage=page, onLaterPages=page)
    return out.getvalue()


def _styles() -> dict[str, Any]:
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Title"], fontSize=11, leading=14, spaceAfter=0),
        "cell": ParagraphStyle("cell", parent=base["BodyText"], fontSize=7, leading=8.5),
        "heading": ParagraphStyle("heading", parent=base["Heading4"], spaceBefore=6, spaceAfter=3),
        "body": base["BodyText"],
    }


def _cell(text: str, bold: bool = False) -> Any:
    from reportlab.platypus import Paragraph

    markup = escape(text).replace("\n", "<br/>")
    return Paragraph(f"<b>{markup}</b>" if bold else markup, _styles()["cell"])


def _pdf_table(header: list[str], rows: list[list[str]], widths: list[float] | None = None) -> Any:
    from reportlab.lib import colors
    from reportlab.platypus import Table, TableStyle

    data = [[_cell(h, bold=True) for h in header]] + [[_cell(v) for v in row] for row in rows]
    table = Table(data, colWidths=widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table


# A table cell's default padding: 6 pt left and right, 3 pt top and bottom.
CELL_PAD_X, CELL_PAD_Y = 12, 6
# Fewer lines than this left at the foot of a page: the day starts on the next page instead.
MIN_ROW_LINES = 3
# Points kept free at the foot of each page, so rounding never pushes a row over.
PAGE_SLACK = 2


def _row_height(row: list[str], widths: list[float], bold: bool = False) -> float:
    tallest = max(_cell(text, bold).wrap(w - CELL_PAD_X, 1e6)[1] for text, w in zip(row, widths, strict=True))
    return float(tallest) + CELL_PAD_Y


def _stack_height(flowables: list[Any], width: float) -> float:
    return float(sum(f.wrap(width, 1e6)[1] + f.getSpaceBefore() + f.getSpaceAfter() for f in flowables))


def _fit_pages(rows: list[list[str]], widths: list[float], first_space: float, page_space: float) -> list[list[str]]:
    """Each day as one grid row, cut into several (the date repeated, "(cont.)") where it doesn't fit the page.

    ReportLab never splits a row: one taller than the space left moves whole to the next page, which left
    page 1 blank under the letterhead. So rows are measured as they will print (long room lists wrap),
    and a day fills what is left of its page: `first_space` under the letterhead and title on page 1,
    `page_space` on every later page (both net of the repeated header row).
    """
    out: list[list[str]] = []
    space = first_space
    for label, *cells in rows:
        lines = [cell.split("\n") if cell else [] for cell in cells]
        tallest = max((len(c) for c in lines), default=0)
        start = 0
        while True:
            name = label if start == 0 else f"{label} (cont.)"
            left = tallest - start
            need = min(left, MIN_ROW_LINES)
            if _row_height(_chunk(name, lines, start, need), widths) > space and space < page_space:
                space = page_space  # too little room at the foot: the day goes on the next page
                continue
            lo, hi = need, left  # the most lines that still fit
            while lo < hi:
                mid = (lo + hi + 1) // 2
                fits = _row_height(_chunk(name, lines, start, mid), widths) <= space
                lo, hi = (mid, hi) if fits else (lo, mid - 1)
            row = _chunk(name, lines, start, lo)
            out.append(row)
            space -= _row_height(row, widths)
            start += lo
            if start >= tallest:
                break
    return out


def _chunk(name: str, lines: list[list[str]], start: int, count: int) -> list[str]:
    """A grid row: the date, then `count` lines of each session from line `start`."""
    return [name, *["\n".join(c[start : start + count]) for c in lines]]


def timetable_pdf(term: Term, rec: dict[str, Any], version: int | None, printed_by: str) -> bytes:
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer

    st = _styles()
    title = _title(term, version)

    def story() -> list[Any]:
        from app.services import letterhead

        header, rows = timetable_table(rec)
        first = 28 * mm
        rest = (277 * mm - first) / max(1, len(header) - 1)
        widths = [first] + [rest] * (len(header) - 1)
        out: list[Any] = [Paragraph(escape(line), st["title"]) for line in title]
        out.append(Spacer(1, 4 * mm))
        page_space = _pdf_body_height(True) - _row_height(header, widths, bold=True) - PAGE_SLACK
        above = _stack_height([letterhead.first_page_header(), *out], 277 * mm - 2 * FRAME_PADDING)
        rows = _fit_pages(rows, widths, page_space - above, page_space)
        out.append(_pdf_table(header, rows, widths))
        lines = practical_lines(rec)
        if lines:
            out += [Paragraph("PRACTICALS", st["heading"]), *[Paragraph(escape(line), st["cell"]) for line in lines]]
        out += [Spacer(1, 6 * mm), Paragraph(escape(_prepared(term, printed_by)), st["body"])]
        return out

    return _pdf(story, True, title[-1])


def rooms_pdf(term: Term, rec: dict[str, Any], version: int | None, printed_by: str) -> bytes:
    from reportlab.platypus import Paragraph

    st = _styles()
    title = [*_title(term, version), "ROOM SHEETS"]
    days = {d["date"]: d["label"] for d in rec["days"]}

    def story() -> list[Any]:
        out: list[Any] = [Paragraph(escape(line), st["title"]) for line in title]
        for slot in room_sheets(rec):
            session = rec["sessions"][slot["session"]]
            out.append(
                Paragraph(escape(f"{days.get(slot['day'], slot['day'])}  {_session_label(session)}"), st["heading"])
            )
            rows = _room_rows(slot)
            out.append(_pdf_table(ROOM_HEADERS, rows))
        out.append(Paragraph(escape(_prepared(term, printed_by)), st["body"]))
        return out

    return _pdf(story, False, title[-1])


def roster_pdf(term: Term, rec: dict[str, Any], version: int | None, printed_by: str) -> bytes:
    from reportlab.platypus import Paragraph

    st = _styles()
    title = [*_title(term, version), "INVIGILATION ROSTER"]

    def story() -> list[Any]:
        out: list[Any] = [Paragraph(escape(line), st["title"]) for line in title]
        for department, rows in roster(rec).items():
            out.append(Paragraph(escape(department), st["heading"]))
            out.append(_pdf_table(ROSTER_HEADERS, rows))
        out.append(Paragraph(escape(_prepared(term, printed_by)), st["body"]))
        return out

    return _pdf(story, False, title[-1])


BUILDERS = {
    ("timetable", "docx"): timetable_docx,
    ("timetable", "pdf"): timetable_pdf,
    ("rooms", "docx"): rooms_docx,
    ("rooms", "pdf"): rooms_pdf,
    ("roster", "docx"): roster_docx,
    ("roster", "pdf"): roster_pdf,
}
MEDIA = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
