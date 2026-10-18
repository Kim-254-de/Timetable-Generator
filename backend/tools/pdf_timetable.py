"""
Reads the Directorate's teaching-timetable PDF (class rows x Mon-Fri 07-19
grid, cells "UNIT / [GR X] / ROOM") into JSON: one entry per meeting, with
every class row it serves.

    python -m tools.pdf_timetable "TUN SEP-DEC 2026 TEACHING TT V2.pdf" tests/fixtures/sep_dec_2026.json

Cells are mapped to hours by their x position against the page's hour
header, not by column index, because rows with merged empty cells come out
of the PDF with fewer columns. A cell spanning several hour columns is one
meeting of that many hours. The output holds no personal data: unit codes,
group labels, room codes and class-row labels only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import pdfplumber

DAYS = ("MON", "TUE", "WED", "THU", "FRI")
ROOM_RE = re.compile(r"([A-Z]{1,3}(?:-[A-Z]{2})?)\s*(\d{1,3})\s*$")
GROUP_RE = re.compile(r"\bGR\.?\s*([A-Z]{1,2}\d?|\d{1,2})\b")
UNIT_RE = re.compile(r"([A-Z]{2,5})(\d{3,4}[A-Z]?)")


def _hour_columns(table: Any) -> list[tuple[float, float]] | None:
    """x ranges of the 60 hour columns, from the header row of hour labels ("7-8" ...)."""
    for row in table.rows[:3]:
        cells = [c for c in row.cells[1:] if c is not None]
        if len(cells) == 60:
            return [(c[0], c[2]) for c in cells]
    return None


def _nearest(columns: list[tuple[float, float]], x: float, edge: int) -> int:
    return min(range(len(columns)), key=lambda i: abs(columns[i][edge] - x))


def parse_cell(text: str) -> dict[str, str | None] | None:
    """
    'LAWP 103 / TC 7' -> unit, group, room. The PDF wraps cell text
    unpredictably ('G R I1 UTC / 8', 'CHEM 11 0', 'GEOG / 144 GR A'), so the
    lines are joined and read from the end: room, then group, then unit code.
    None when the cell has no room or no unit code.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    joined = re.sub(r"\bG\s+R\b", "GR", " ".join(lines))
    room = ROOM_RE.search(joined)
    if room is None:
        return None
    building, number = room.group(1), room.group(2)
    if building == "GR":
        return None  # the last thing in the cell is a group label: no room printed
    rest = joined[: room.start()]
    group = GROUP_RE.search(rest)
    if group:
        rest = rest[: group.start()] + rest[group.end() :]
    unit = UNIT_RE.search(rest.replace(" ", ""))
    if unit is None:
        return None
    return {
        "unit": f"{unit.group(1)} {unit.group(2)}",
        "group": f"GR {group.group(1)}" if group else None,
        "room": f"{building}{number}" if "-" in building else f"{building} {number}",
    }


def extract(pdf_path: Path) -> dict[str, Any]:
    meetings: dict[tuple, set[str]] = defaultdict(set)
    rows: list[str] = []
    skipped: list[dict[str, Any]] = []
    columns: list[tuple[float, float]] | None = None

    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            for table in page.find_tables():
                columns = _hour_columns(table) or columns
                if columns is None:
                    continue
                for row in table.rows:
                    first = row.cells[0]
                    if first is None:
                        continue
                    label = (page.crop(first).extract_text() or "").replace("\n", " ").strip()
                    if (
                        not label
                        or label.lower().startswith(("monday", "tuesday"))
                        or re.fullmatch(r"[\d\-\s]+", label)
                    ):
                        continue
                    if label not in rows:
                        rows.append(label)
                    for cell in row.cells[1:]:
                        if cell is None:
                            continue
                        text = page.crop(cell).extract_text() or ""
                        if not text.strip():
                            continue
                        parsed = parse_cell(text)
                        start = _nearest(columns, cell[0], 0)
                        end = _nearest(columns, cell[2], 1)
                        if parsed is None or end < start:
                            skipped.append({"page": page_no, "row": label, "text": text})
                            continue
                        day, hour = divmod(start, 12)
                        length = end - start + 1
                        if (start // 12) != (end // 12):
                            skipped.append({"page": page_no, "row": label, "text": text, "why": "crosses a day"})
                            continue
                        key = (parsed["unit"], parsed["group"], parsed["room"], DAYS[day], 7 + hour, length)
                        meetings[key].add(label)

    return {
        "source": pdf_path.name,
        "class_rows": rows,
        "meetings": [
            {"unit": u, "group": g, "room": r, "day": d, "start_hour": h, "length": n, "class_rows": sorted(cr)}
            for (u, g, r, d, h, n), cr in sorted(
                meetings.items(), key=lambda kv: (kv[0][0], kv[0][1] or "", kv[0][3], kv[0][4])
            )
        ],
        "skipped": skipped,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("pdf", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args(argv)
    data = extract(args.pdf)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, indent=1), encoding="utf-8")
    units = {m["unit"] for m in data["meetings"]}
    rooms = {m["room"] for m in data["meetings"]}
    print(
        f"{len(data['class_rows'])} class rows, {len(data['meetings'])} meetings, {len(units)} units, "
        f"{len(rooms)} rooms; {len(data['skipped'])} cells skipped",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
