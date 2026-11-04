"""
Reads an exam list written for moderation (the Word letter with its table of
drafts) into papers. The same reading as a department's upload in Smart
Attendance (teaching/exam-list.read.ts): each table row with a unit code is one
paper, its title the next cell with words in it; a row or short capitals line
with no code is a heading; papers under an ODEL or part-time heading are ODEL.
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from typing import Any

from docx import Document
from docx.oxml.ns import qn

from app.errors import ApiError

MAX_BYTES = 5 * 1024 * 1024

_CODE_CELL = re.compile(
    r"^([A-Za-z]{2,6})\s*-?\s*(\d{2,5}[A-Za-z]?)((?:\s*[/&,]\s*(?:[A-Za-z]{2,6}\s*-?\s*)?\d{2,5}[A-Za-z]?)*)"
    r"(?:\s*[-(]?\s*(odel|part[\s-]?time)\s*\)?)?\s*$",
    re.I,
)
_PART = re.compile(r"^([A-Za-z]{2,6})?\s*-?\s*(\d{2,5}[A-Za-z]?)$")
_ODEL_HEADING = re.compile(r"\b(odel|part[\s-]?time|distance|open\s+and\s+distance)\b", re.I)
_HEADER_WORDS = re.compile(
    r"^(s/?\s*no\.?|no\.?|#|unit\s*code|code|unit\s*(name|title)|title|course\s*(code|title)|comments?|remarks?)$", re.I
)


@dataclass(frozen=True)
class ListedEntry:
    line: int
    codes: list[str]
    title: str
    section: str
    sitting: str


def codes_of(cell: str) -> tuple[list[str], bool] | None:
    """'Math 241' -> ['MATH 241']; 'COSC 0172/0170' -> ['COSC 0172', 'COSC 0170']. None when the cell isn't codes."""
    m = _CODE_CELL.match(" ".join(cell.split()))
    if not m:
        return None
    prefix = m.group(1).upper()
    codes = [f"{prefix} {m.group(2).upper()}"]
    for part in (p.strip() for p in re.split(r"[/&,]", m.group(3) or "") if p.strip()):
        pm = _PART.match(part)
        if not pm:
            return None
        prefix = (pm.group(1) or prefix).upper()
        codes.append(f"{prefix} {pm.group(2).upper()}")
    return list(dict.fromkeys(codes)), bool(m.group(4))


def _text(element: Any) -> str:
    parts = []
    for node in element.iter():
        if node.tag == qn("w:t"):
            parts.append(node.text or "")
        elif node.tag in (qn("w:tab"), qn("w:br")):
            parts.append(" ")
    return " ".join("".join(parts).split())


def _blocks(parent: Any) -> Any:
    for el in parent.iterchildren():
        if el.tag == qn("w:p"):
            yield "p", _text(el)
        elif el.tag == qn("w:tbl"):
            for row in el.iterchildren(qn("w:tr")):
                yield "row", [_text(c) for c in row.iterchildren(qn("w:tc"))]
        elif el.tag == qn("w:sdt"):
            content = el.find(qn("w:sdtContent"))
            if content is not None:
                yield from _blocks(content)


def _is_words(text: str) -> bool:
    return bool(re.search(r"[A-Za-z]{2}", text)) and not _HEADER_WORDS.match(text)


def read_exam_list(file: bytes) -> list[ListedEntry]:
    if len(file) > MAX_BYTES:
        raise ApiError(413, "VALIDATION_ERROR", "The document is over 5 MB.")
    try:
        body = Document(io.BytesIO(file)).element.body
    except (ValueError, KeyError, zipfile.BadZipFile, OSError) as exc:
        raise ApiError(422, "VALIDATION_ERROR", "That is not a Word document (.docx). Save it as .docx and upload it again.") from exc
    entries: list[ListedEntry] = []
    section = ""
    odel = False
    for kind, value in _blocks(body):
        if kind == "p":
            t = value
            looks_heading = _ODEL_HEADING.search(t) or (re.search(r"[A-Z]{3}", t) and t == t.upper())
            if t and len(t) <= 80 and not re.search(r"[.,;]$", t) and looks_heading:
                section, odel = t[:120], bool(_ODEL_HEADING.search(t))
            continue
        at = next((i for i, c in enumerate(value) if codes_of(c) is not None), None)
        if at is None:
            words = [c for c in value if _is_words(c)]
            if len(words) == 1 and len([c for c in value if c]) <= 2:
                section, odel = words[0][:120], bool(_ODEL_HEADING.search(words[0]))
            continue
        found = codes_of(value[at])
        assert found is not None
        title = next((c for c in value[at + 1 :] if _is_words(c)), "")
        entries.append(
            ListedEntry(len(entries) + 1, found[0], title[:255], section, "odel" if found[1] or odel else "regular")
        )
    if not entries:
        raise ApiError(422, "VALIDATION_ERROR", "No unit codes were found in the tables of this document.")
    return entries
