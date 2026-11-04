"""
The university's letterhead for every PDF the Generator prints, from the
"Template for system documents": the standard header on the first page only,
and on every page the logo as a faint watermark and the footer
"TUN is ISO 9001:2015 Certified" with the certification mark and the motto.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any, NamedTuple

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
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
# Logo pixels this light (all of red, green and blue at least WHITE) are paper: fully clear in the
# watermark. Darker ones fade in over FEATHER levels, so the logo's edge stays smooth.
WHITE, FEATHER = 248, 40
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


@lru_cache(maxsize=1)
def faded_logo() -> bytes:
    """The logo as the watermark: a PNG that is faint in itself, its white background clear.

    The faintness is in the image's alpha channel, not in a setting that asks the viewer to fade it
    (a PDF fill opacity, Word's alphaModFix or "Washout"). Phone viewers and Word-to-PDF converters
    ignore those settings, and printed the logo at full strength over the timetable.
    """
    from PIL import Image as PILImage
    from PIL import ImageChops

    with PILImage.open(LOGO) as image:
        rgb = image.convert("RGB")
    red, green, blue = rgb.split()
    darkest = ImageChops.darker(ImageChops.darker(red, green), blue)
    top = WATERMARK_OPACITY * 255
    rgb.putalpha(darkest.point(lambda v: round(top * min(1.0, max(0.0, (WHITE - v) / FEATHER)))))
    out = BytesIO()
    rgb.save(out, "PNG", optimize=True)
    return out.getvalue()


def _watermark(canvas: Any, page_width: float, page_height: float) -> None:
    size = min(page_width, page_height) * 0.6
    canvas.drawImage(
        ImageReader(BytesIO(faded_logo())),
        (page_width - size) / 2,
        (page_height - size) / 2,
        size,
        size,
        preserveAspectRatio=True,
        anchor="c",
        mask="auto",
    )


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

EMU_PER_POINT = 12700


def apply_to_docx(document: Any) -> None:
    """Puts the letterhead on a python-docx document, once its page size and margins are set;
    call it before or after adding the content."""
    section = document.sections[0]
    section.different_first_page_header_footer = False
    section.header.is_linked_to_previous = False
    section.footer.is_linked_to_previous = False
    text_width = section.page_width - section.left_margin - section.right_margin
    _docx_watermark(section, min(section.page_width, section.page_height) * 0.6)
    _docx_footer(section, text_width)
    table = _docx_header_table(document, text_width)
    spacer = document.add_paragraph()  # space between the header and what follows
    body = document.element.body
    body.insert(0, table._tbl)
    table._tbl.addnext(spacer._p)


def _docx_header_table(document: Any, text_width: int) -> Any:
    """The header as two rows, like the PDF's: THARAKA and UNIVERSITY on the first, the address and
    the contacts on the second, the logo down both.

    The names share a row, so they stay level whatever a viewer does to the lines below them (a
    phone without Times New Roman sets them in a wider font, and the contacts may wrap). The sides
    take all the width the logo leaves, so the contacts have room to stay on one line; each block
    is still placed HEADER_GAP from the logo, as in the PDF.
    """
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    m = _measure()
    emu = EMU_PER_POINT
    logo = int(LOGO_WIDTH * emu)
    side = (text_width - logo) // 2
    table = document.add_table(rows=2, cols=3)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    _docx_no_cell_margins(table)
    for column, width in zip(table.columns, (side, logo, side), strict=True):
        column.width = width
        for cell in column.cells:
            cell.width = width
    names, details = table.rows
    names.height, names.height_rule = int(LOGO_HEIGHT * 0.45 * emu), WD_ROW_HEIGHT_RULE.AT_LEAST

    middle = table.cell(0, 1).merge(table.cell(1, 1))
    middle.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    picture = middle.paragraphs[0]
    picture.alignment = WD_ALIGN_PARAGRAPH.CENTER
    picture.add_run().add_picture(str(LOGO), width=logo, height=int(LOGO_HEIGHT * emu))

    # The left block ends HEADER_GAP before the logo; the right one starts HEADER_GAP after it.
    left_indent = side - int((HEADER_GAP + m.left_width) * emu)
    right_indent = int(HEADER_GAP * emu)
    for cell, name, indent in ((names.cells[0], "THARAKA", left_indent), (names.cells[2], "UNIVERSITY", right_indent)):
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.BOTTOM
        title = cell.paragraphs[0]
        title.paragraph_format.left_indent = indent
        title.paragraph_format.space_after = Pt(0)
        _docx_run(title, name, NAME_SIZE, bold=True)

    def lines(cell: Any, rows: list[tuple[str, str, str | None]], indent: int, tab: float = 0) -> None:
        cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
        for i, (label, value, href) in enumerate(rows):
            p = cell.paragraphs[0] if i == 0 else cell.add_paragraph()
            p.paragraph_format.left_indent = indent
            p.paragraph_format.space_before = Pt(3 * mm if i == 0 else 0)
            p.paragraph_format.space_after = Pt(5 * mm if i == len(rows) - 1 else 0)
            if tab:
                p.paragraph_format.tab_stops.add_tab_stop(indent + int(tab * emu))
            if label:
                _docx_run(p, f"{label}\t", TEXT_SIZE)
            if href:
                _docx_hyperlink(p, value, href)
            else:
                _docx_run(p, value, TEXT_SIZE)

    lines(details.cells[0], [("", line, None) for line in ADDRESS], left_indent)
    lines(details.cells[2], list(CONTACTS), right_indent, m.label_width)
    return table


def _docx_no_cell_margins(table: Any) -> None:
    """No padding inside the cells, so the blocks sit exactly where the indents put them."""
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls

    margins = parse_xml(
        f"<w:tblCellMar {nsdecls('w')}>"
        + "".join(f'<w:{side} w:w="0" w:type="dxa"/>' for side in ("top", "left", "bottom", "right"))
        + "</w:tblCellMar>"
    )
    properties = table._tbl.tblPr
    look = properties.find(margins.tag.replace("tblCellMar", "tblLook"))
    if look is not None:
        look.addprevious(margins)
    else:
        properties.append(margins)


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
    inline = paragraph.add_run().add_picture(BytesIO(faded_logo()), width=size, height=size)._inline
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

    emu = EMU_PER_POINT
    paragraph = section.footer.paragraphs[0]
    paragraph.paragraph_format.tab_stops.add_tab_stop(text_width, WD_TAB_ALIGNMENT.RIGHT)
    blue = "0070C0"
    _docx_run(paragraph, f"{ISO_LINE}  ", 9, color=blue).font.name = "Calibri"
    paragraph.add_run().add_picture(str(ISO_MARK), width=int(ISO_MARK_WIDTH * emu), height=int(ISO_MARK_HEIGHT * emu))
    _docx_run(paragraph, f"\t{MOTTO}", 9, color=blue).font.name = "Calibri"
