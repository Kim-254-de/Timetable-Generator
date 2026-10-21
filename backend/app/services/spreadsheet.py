"""
Reading a prepared Excel workbook (.xlsx) for the "Paste from Excel" dialogs.
The browser can't read .xlsx itself, so it sends the file here and gets each
sheet back as plain text cells; it then finds the header row and saves the
rows the same way as pasted cells. Nothing is stored.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date, datetime, time
from typing import Any

from app.errors import ApiError

MAX_FILE_BYTES = 5 * 1024 * 1024
# A workbook is a zip; this caps what it unpacks to, so a tiny file can't expand without limit.
MAX_UNPACKED_BYTES = 60 * 1024 * 1024
MAX_ROWS = 5000
MAX_COLUMNS = 60

NOT_XLSX = "This isn't an Excel workbook (.xlsx). In Excel, use File > Save As > Excel Workbook (.xlsx) and try again."
TOO_BIG = "The workbook is larger than 5 MB. Keep only the sheet you need."


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else str(value)
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == time(0) else value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.strftime("%H:%M")
    # Tabs and line breaks inside a cell would split it when the browser reads the rows.
    return " ".join(str(value).split())


def read_workbook(content: bytes) -> dict[str, Any]:
    """Every sheet with something in it, as rows of text cells (empty rows dropped)."""
    if not content:
        raise ApiError(422, "EMPTY_FILE", "The file is empty.")
    if len(content) > MAX_FILE_BYTES:
        raise ApiError(413, "FILE_TOO_LARGE", TOO_BIG)
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if sum(info.file_size for info in archive.infolist()) > MAX_UNPACKED_BYTES:
                raise ApiError(413, "FILE_TOO_LARGE", TOO_BIG)
    except zipfile.BadZipFile:
        raise ApiError(422, "NOT_XLSX", NOT_XLSX) from None

    from openpyxl import load_workbook

    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:  # openpyxl raises many kinds for a damaged or non-Excel zip
        raise ApiError(422, "NOT_XLSX", NOT_XLSX) from None
    sheets: list[dict[str, Any]] = []
    try:
        for sheet in workbook.worksheets:
            rows: list[list[str]] = []
            for values in sheet.iter_rows(values_only=True):
                cells = [_text(v) for v in values[:MAX_COLUMNS]]
                while cells and cells[-1] == "":
                    cells.pop()
                if not cells:
                    continue
                if len(rows) == MAX_ROWS:
                    raise ApiError(
                        413,
                        "TOO_MANY_ROWS",
                        f"Sheet “{sheet.title}” has more than {MAX_ROWS} rows. Split it into smaller files.",
                    )
                rows.append(cells)
            if rows:
                sheets.append({"name": sheet.title, "rows": rows})
    finally:
        workbook.close()
    if not sheets:
        raise ApiError(422, "EMPTY_FILE", "The workbook has no filled-in cells.")
    return {"sheets": sheets}
