"""
The university's letterhead for every PDF the Generator prints, from the
"Template for system documents": the standard header on the first page only,
and on every page the logo as a faint watermark and the footer
"TUN is ISO 9001:2015 Certified" with the certification mark and the motto.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple

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
NAME_FONT, NAME_SIZE = "Times-Bold", 20
TEXT_FONT, TEXT_SIZE = "Times-Roman", 10
# Between the logo and the text on either side of it.
HEADER_GAP = 6 * mm


class _Measures(NamedTuple):
    label_width: float
    value_width: float
    left_width: float
    side: float


def _measure() -> _Measures:
    """Widths of the header's blocks, so both sides are equal and the logo is on the centre line."""
    label_width = max(stringWidth(label, TEXT_FONT, TEXT_SIZE) for label, _, _ in CONTACTS) + 2 * mm
    value_width = max(stringWidth(value, TEXT_FONT, TEXT_SIZE) for _, value, _ in CONTACTS) + 1 * mm
    left_width = (
        max(
            stringWidth("THARAKA", NAME_FONT, NAME_SIZE), *(stringWidth(line, TEXT_FONT, TEXT_SIZE) for line in ADDRESS)
        )
        + 1 * mm
    )
    right_width = max(label_width + value_width, stringWidth("UNIVERSITY", NAME_FONT, NAME_SIZE) + 1 * mm)
    return _Measures(label_width, value_width, left_width, max(left_width, right_width) + HEADER_GAP)


def first_page_header() -> Table:
    """The standard header, put first in the story so it appears on page 1 only.

    Laid out like the university's letterhead at its A4 size: THARAKA over the postal address,
    the logo, UNIVERSITY over the contacts, in a serif face. The logo is on the page's centre
    line and both blocks sit the same distance from it, so the header stays balanced.
    """
    m = _measure()
    name = ParagraphStyle("lh-name", fontName=NAME_FONT, fontSize=NAME_SIZE, leading=NAME_SIZE * 1.2)
    small = ParagraphStyle("lh-small", fontName=TEXT_FONT, fontSize=TEXT_SIZE, leading=TEXT_SIZE * 1.2)
    contacts = Table(
        [[Paragraph(label, small), Paragraph(_link(value, href), small)] for label, value, href in CONTACTS],
        colWidths=[m.label_width, m.value_width],
    )
    contacts.setStyle(_no_padding())
    address = Paragraph("<br/>".join(ADDRESS), small)
    side, gap, left_width = m.side, HEADER_GAP, m.left_width
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


# -- Word ---------------------------------------------------------------------------------------
# The same letterhead in the Word downloads: the header as a borderless table at the top of the
# first page, and in the page header and footer of every page the faint logo behind the text and
# the ISO line, mark and motto.

WORD_WATERMARK_OPACITY = 12_000  # of 100_000


def apply_to_docx(document: Any) -> None:
    """Puts the letterhead on a python-docx document; call it before or after adding the content."""
    section = document.sections[0]
    section.different_first_page_header_footer = False
    section.header.is_linked_to_previous = False
    section.footer.is_linked_to_previous = False
    text_width = section.page_width - section.left_margin - section.right_margin
    _docx_watermark(section, min(section.page_width, section.page_height) * 0.6)
    _docx_footer(section, text_width)
    table = _docx_header_table(document)
    spacer = document.add_paragraph()  # space between the header and what follows
    body = document.element.body
    body.insert(0, table._tbl)
    table._tbl.addnext(spacer._p)


def _docx_header_table(document: Any) -> Any:
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    m = _measure()
    emu = 12700  # per point
    side, logo = int(m.side * emu), int(LOGO_WIDTH * emu)
    table = document.add_table(rows=1, cols=3)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    left, middle, right = table.rows[0].cells
    for cell, column, width in zip((left, middle, right), table.columns, (side, logo, side), strict=True):
        cell.width = column.width = width
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER

    picture = middle.paragraphs[0]
    picture.alignment = WD_ALIGN_PARAGRAPH.CENTER
    picture.add_run().add_picture(str(LOGO), width=logo, height=int(LOGO_HEIGHT * emu))

    def block(cell: Any, name: str, rows: list[tuple[str, str, str | None]], indent: float, tab: float = 0) -> None:
        """A name over its lines; `indent` places the block so it keeps HEADER_GAP from the logo."""
        title = cell.paragraphs[0]
        _docx_run(title, name, NAME_SIZE, bold=True)
        title.paragraph_format.space_after = Pt(8)
        title.paragraph_format.left_indent = int(indent * emu)
        for label, value, href in rows:
            p = cell.add_paragraph()
            p.paragraph_format.space_after = Pt(0)
            p.paragraph_format.left_indent = int(indent * emu)
            if tab:
                p.paragraph_format.tab_stops.add_tab_stop(int((indent + tab) * emu))
            if label:
                _docx_run(p, f"{label}\t", TEXT_SIZE)
            if href:
                _docx_hyperlink(p, value, href)
            else:
                _docx_run(p, value, TEXT_SIZE)

    block(left, "THARAKA", [("", line, None) for line in ADDRESS], m.side - HEADER_GAP - m.left_width)
    block(right, "UNIVERSITY", list(CONTACTS), HEADER_GAP, m.label_width)
    return table


def _docx_run(paragraph: Any, text: str, size: float, bold: bool = False, color: str | None = None) -> Any:
    from docx.shared import Pt, RGBColor

    run = paragraph.add_run(text)
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)
    run.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    return run


def _docx_hyperlink(paragraph: Any, text: str, href: str) -> None:
    from docx.opc.constants import RELATIONSHIP_TYPE
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    rel = paragraph.part.relate_to(href, RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), rel)
    run = _docx_run(paragraph, text, TEXT_SIZE, color=LINK_BLUE.lstrip("#"))
    run.font.underline = True
    link.append(run._r)
    paragraph._p.append(link)


def _docx_watermark(section: Any, size: int) -> None:
    """The logo behind the text, centred on the page and faint, from the page header so it is on every page."""
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls, qn

    paragraph = section.header.paragraphs[0]
    inline = paragraph.add_run().add_picture(str(LOGO), width=size, height=size)._inline
    blip = inline.find(".//" + qn("a:blip"))
    blip.append(parse_xml(f'<a:alphaModFix {nsdecls("a")} amt="{WORD_WATERMARK_OPACITY}"/>'))
    anchor = parse_xml(
        f'<wp:anchor {nsdecls("wp")} distT="0" distB="0" distL="0" distR="0" simplePos="0" '
        'relativeHeight="0" behindDoc="1" locked="1" layoutInCell="1" allowOverlap="1">'
        '<wp:simplePos x="0" y="0"/>'
        '<wp:positionH relativeFrom="page"><wp:align>center</wp:align></wp:positionH>'
        '<wp:positionV relativeFrom="page"><wp:align>center</wp:align></wp:positionV>'
        "</wp:anchor>"
    )
    extent, doc_pr, frame_pr, graphic = (
        inline.find(qn(tag)) for tag in ("wp:extent", "wp:docPr", "wp:cNvGraphicFramePr", "a:graphic")
    )
    anchor.append(extent)
    anchor.append(parse_xml(f'<wp:effectExtent {nsdecls("wp")} l="0" t="0" r="0" b="0"/>'))
    anchor.append(parse_xml(f"<wp:wrapNone {nsdecls('wp')}/>"))
    for part in (doc_pr, frame_pr, graphic):
        anchor.append(part)
    inline.getparent().replace(inline, anchor)


def _docx_footer(section: Any, text_width: int) -> None:
    from docx.enum.text import WD_TAB_ALIGNMENT

    emu = 12700
    paragraph = section.footer.paragraphs[0]
    paragraph.paragraph_format.tab_stops.add_tab_stop(text_width, WD_TAB_ALIGNMENT.RIGHT)
    blue = "0070C0"
    _docx_run(paragraph, f"{ISO_LINE}  ", 9, color=blue).font.name = "Calibri"
    paragraph.add_run().add_picture(str(ISO_MARK), width=int(ISO_MARK_WIDTH * emu), height=int(ISO_MARK_HEIGHT * emu))
    _docx_run(paragraph, f"\t{MOTTO}", 9, color=blue).font.name = "Calibri"
