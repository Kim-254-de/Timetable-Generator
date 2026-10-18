"""
A draft as a PDF in the layout of today's teaching timetable: the
Directorate's header, one row per class row (or room, or department), a
Monday-Friday x 07:00-19:00 grid, cells "UNIT / GR X / ROOM" spanning the
class's hours, and the "Prepared by ... Director Examination & Timetabling"
footer.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models import Term

DAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
TERM_MONTHS = {1: "SEPTEMBER-DECEMBER", 2: "JANUARY-APRIL", 3: "MAY-AUGUST"}


def term_title(term: Term) -> str:
    first, _, second = term.academic_year.partition("/")
    year = first if term.semester == 1 else (second or first)
    return f"{TERM_MONTHS.get(term.semester, f'SEMESTER {term.semester}')} {year} TEACHING TIMETABLE"


def build_pdf(term: Term, grid: dict[str, Any], printed_by: str) -> bytes:
    styles = getSampleStyleSheet()
    cell_style = ParagraphStyle("cell", parent=styles["BodyText"], fontSize=5.5, leading=6.5, alignment=1)
    label_style = ParagraphStyle("label", parent=styles["BodyText"], fontSize=6.5, leading=7.5)
    hours = grid["hours"]
    first_hour = grid["first_hour"]

    header_days: list[Any] = [""]
    header_hours: list[Any] = [""]
    for day in DAY_NAMES:
        header_days += [day] + [""] * (hours - 1)
        header_hours += [f"{h}-{h + 1}" for h in range(first_hour, first_hour + hours)]
    data: list[list[Any]] = [header_days, header_hours]
    style: list[Any] = [
        ("FONT", (0, 0), (-1, 1), "Helvetica-Bold", 6),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (-1, 1), "CENTER"),
        ("BACKGROUND", (0, 0), (-1, 1), colors.HexColor("#e5e7eb")),
    ]
    for d in range(len(DAY_NAMES)):
        style.append(("SPAN", (1 + d * hours, 0), (d * hours + hours, 0)))

    for entity in grid["entities"]:
        # A row can hold parallel classes at the same hour (rooms, departments):
        # stack them in extra lines of the same entity.
        lines: list[list[dict[str, Any]]] = []
        for cell in entity["cells"]:
            for line in lines:
                if all(
                    cell["start_slot"] >= c["start_slot"] + c["length"]
                    or c["start_slot"] >= cell["start_slot"] + cell["length"]
                    for c in line
                ):
                    line.append(cell)
                    break
            else:
                lines.append([cell])
        for n, line in enumerate(lines or [[]]):
            row: list[Any] = [Paragraph(entity["label"], label_style) if n == 0 else ""] + [""] * (5 * hours)
            r = len(data)
            for cell in line:
                text = "<br/>".join(x for x in (cell["unit_code"], cell["group"], cell["room"]) if x)
                if grid["view"] == "room":
                    text = "<br/>".join(x for x in (cell["unit_code"], cell["group"]) if x)
                row[1 + cell["start_slot"]] = Paragraph(text, cell_style)
                style.append(("SPAN", (1 + cell["start_slot"], r), (cell["start_slot"] + cell["length"], r)))
                if cell["pinned"]:
                    style.append(
                        (
                            "BACKGROUND",
                            (1 + cell["start_slot"], r),
                            (cell["start_slot"] + cell["length"], r),
                            colors.HexColor("#fef3c7"),
                        )
                    )
            data.append(row)

    width = landscape(A3)[0] - 20 * mm
    label_width = 32 * mm
    col = (width - label_width) / (5 * hours)
    table = Table(data, colWidths=[label_width] + [col] * (5 * hours), repeatRows=2)
    table.setStyle(TableStyle(style))

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A3),
        leftMargin=10 * mm,
        rightMargin=10 * mm,
        topMargin=10 * mm,
        bottomMargin=14 * mm,
        title=term_title(term),
        author=printed_by,
    )
    draft = grid["draft"]
    version_line = f"{draft['name']} ({draft['status']})"

    def footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.drawString(10 * mm, 7 * mm, f"Prepared by {printed_by}, Director Examination & Timetabling")
        canvas.drawRightString(landscape(A3)[0] - 10 * mm, 7 * mm, f"{version_line} - Page {document.page}")
        canvas.restoreState()

    story = [
        Paragraph("DIRECTORATE OF EXAMINATIONS AND TIMETABLING", styles["Title"]),
        Paragraph(term_title(term), styles["Heading2"]),
        Spacer(1, 3 * mm),
        table,
    ]
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
