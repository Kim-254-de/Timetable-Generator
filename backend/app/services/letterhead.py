"""
The university's letterhead for every PDF the Generator prints, from the
"Template for system documents": the standard header on the first page only,
and on every page the logo as a faint watermark and the footer
"TUN is ISO 9001:2015 Certified" with the certification mark and the motto.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Image, Paragraph, Table, TableStyle

ASSETS = Path(__file__).resolve().parent.parent / "assets" / "letterhead"
LOGO = ASSETS / "tu-logo.jpg"
ISO_MARK = ASSETS / "iso-9001-certified.png"

# Label, value and link, in the order of the university's letterhead.
CONTACTS = (
    ("Telephone:", "+254 745 838 353", None),
    ("Website:", "https://tharaka.ac.ke", "https://tharaka.ac.ke"),
    ("Social Media:", "tharakauni", None),
    ("Email:", "info@tharaka.ac.ke", "mailto:info@tharaka.ac.ke"),
)
ADDRESS = ("P.O BOX 193-60215,", "MARIMANTI, KENYA")
LINK_BLUE = "#0563C1"
ISO_LINE = "TUN is ISO 9001:2015 Certified"
MOTTO = "Education for Freedom/ Elimu ni Uhuru"
FOOTER_BLUE = colors.HexColor("#0070C0")

# The letterhead as it sits on an A4 page (the header is 15.9 cm wide there), whatever the page size;
# the certification mark is the template's 2.25 x 1.26 cm.
LOGO_HEIGHT = 34 * mm
LOGO_WIDTH = LOGO_HEIGHT * 365 / 359
ISO_MARK_HEIGHT = 12.6 * mm
ISO_MARK_WIDTH = ISO_MARK_HEIGHT * 1024 / 576
FOOTER_BOTTOM = 6 * mm
# Room a page keeps at the bottom for the footer; a builder adds its own lines above it.
FOOTER_HEIGHT = FOOTER_BOTTOM + ISO_MARK_HEIGHT + 2 * mm
WATERMARK_OPACITY = 0.1


def first_page_header() -> Table:
    """The standard header, put first in the story so it appears on page 1 only.

    Laid out like the university's letterhead at its A4 size: THARAKA over the postal address,
    the logo, UNIVERSITY over the contacts, in a serif face. The logo is on the page's centre
    line and both blocks sit the same distance from it, so the header stays balanced.
    """
    name_font, name_size = "Times-Bold", 20
    text_font, text_size = "Times-Roman", 10
    name = ParagraphStyle("lh-name", fontName=name_font, fontSize=name_size, leading=name_size * 1.2)
    small = ParagraphStyle("lh-small", fontName=text_font, fontSize=text_size, leading=text_size * 1.2)

    label_width = max(stringWidth(label, text_font, text_size) for label, _, _ in CONTACTS) + 2 * mm
    value_width = max(stringWidth(value, text_font, text_size) for _, value, _ in CONTACTS) + 1 * mm
    contacts = Table(
        [[Paragraph(label, small), Paragraph(_link(value, href), small)] for label, value, href in CONTACTS],
        colWidths=[label_width, value_width],
    )
    contacts.setStyle(_no_padding())
    address = Paragraph("<br/>".join(ADDRESS), small)

    left_width = max(stringWidth(line, text_font, text_size) for line in ("THARAKA", *ADDRESS))
    left_width = max(left_width, stringWidth("THARAKA", name_font, name_size)) + 1 * mm
    right_width = max(label_width + value_width, stringWidth("UNIVERSITY", name_font, name_size) + 1 * mm)
    gap = 6 * mm
    side = max(left_width, right_width) + gap
    table = Table(
        [
            [Paragraph("THARAKA", name), Image(str(LOGO), LOGO_WIDTH, LOGO_HEIGHT), Paragraph("UNIVERSITY", name)],
            [address, "", contacts],
        ],
        colWidths=[side, LOGO_WIDTH, side],
        rowHeights=[LOGO_HEIGHT * 0.45, None],
        hAlign="CENTER",
    )
    table.setStyle(
        TableStyle(
            [
                *_no_padding().getCommands(),
                ("SPAN", (1, 0), (1, 1)),
                ("VALIGN", (1, 0), (1, 0), "MIDDLE"),
                ("VALIGN", (0, 0), (-1, 0), "BOTTOM"),
                ("VALIGN", (0, 1), (-1, 1), "TOP"),
                ("TOPPADDING", (0, 1), (-1, 1), 3 * mm),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 5 * mm),
                # The left block ends `gap` before the logo; the right one starts `gap` after it.
                ("LEFTPADDING", (0, 0), (0, -1), side - gap - left_width),
                ("LEFTPADDING", (2, 0), (2, -1), gap),
            ]
        )
    )
    return table


def _link(text: str, href: str | None) -> str:
    return f'<link href="{href}" color="{LINK_BLUE}"><u>{text}</u></link>' if href else text


def _no_padding() -> TableStyle:
    return TableStyle(
        [(side, (0, 0), (-1, -1), 0) for side in ("LEFTPADDING", "RIGHTPADDING", "TOPPADDING", "BOTTOMPADDING")]
    )


def _watermark(canvas: Any, page_width: float, page_height: float) -> None:
    size = min(page_width, page_height) * 0.6
    canvas.saveState()
    canvas.setFillAlpha(WATERMARK_OPACITY)
    canvas.drawImage(
        str(LOGO),
        (page_width - size) / 2,
        (page_height - size) / 2,
        size,
        size,
        preserveAspectRatio=True,
        anchor="c",
    )
    canvas.restoreState()


def _footer(canvas: Any, page_width: float, margin: float) -> None:
    mark_y = FOOTER_BOTTOM
    text_y = mark_y + ISO_MARK_HEIGHT / 2 - 3
    canvas.saveState()
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(FOOTER_BLUE)
    canvas.drawString(margin, text_y, ISO_LINE)
    mark_x = margin + canvas.stringWidth(ISO_LINE, "Helvetica", 9) + 4 * mm
    canvas.drawImage(
        str(ISO_MARK), mark_x, mark_y, ISO_MARK_WIDTH, ISO_MARK_HEIGHT, preserveAspectRatio=True, mask="auto"
    )
    canvas.drawRightString(page_width - margin, text_y, MOTTO)
    canvas.restoreState()


def on_page(extra: Callable[[Any, Any], None] | None = None) -> Callable[[Any, Any], None]:
    """The page callback for every page: watermark under the content, then the footer, then `extra`."""

    def draw(canvas: Any, doc: Any) -> None:
        page_width, page_height = doc.pagesize
        _watermark(canvas, page_width, page_height)
        _footer(canvas, page_width, doc.leftMargin)
        if extra:
            extra(canvas, doc)

    return draw
