"""
Proposes how each unit offering is split into groups. Only a proposal: the
Director decides the final split (and edits labels, members and sizes).

Rule: a group must fit the largest room of the offering's room type. Class
rows are packed into groups first-fit decreasing by size, so rows stay whole
where they can; a single row bigger than the largest room is itself split
into equal groups (GR A, GR B ...), which may meet together or in turn.
"""

from __future__ import annotations

import math
import string
from dataclasses import dataclass


@dataclass(frozen=True)
class RowDemand:
    class_row_id: str
    label: str
    students: int


@dataclass
class ProposedGroup:
    label: str
    members: list[tuple[str, int]]  # (class_row_id, students from that row)

    @property
    def students(self) -> int:
        return sum(n for _row, n in self.members)


def group_labels(count: int) -> list[str]:
    """GR A .. GR Z, then GR AA, GR AB ..."""
    letters = string.ascii_uppercase
    labels = []
    for i in range(count):
        name = ""
        n = i
        while True:
            name = letters[n % 26] + name
            n = n // 26 - 1
            if n < 0:
                break
        labels.append(f"GR {name}")
    return labels


def propose(rows: list[RowDemand], largest_room: int) -> list[ProposedGroup]:
    """
    Groups for one offering. One group (label "") when everyone fits the
    largest room. Raises ValueError when there is no room of the type at all.
    """
    if largest_room <= 0:
        raise ValueError("No room of the required type.")
    total = sum(r.students for r in rows)
    if total <= largest_room:
        return [ProposedGroup(label="", members=[(r.class_row_id, r.students) for r in rows])]

    bins: list[list[tuple[str, int]]] = []
    loads: list[int] = []
    for row in sorted(rows, key=lambda r: r.students, reverse=True):
        if row.students > largest_room:
            parts = math.ceil(row.students / largest_room)
            base, extra = divmod(row.students, parts)
            for i in range(parts):
                bins.append([(row.class_row_id, base + (1 if i < extra else 0))])
                loads.append(base + (1 if i < extra else 0))
            continue
        for i, load in enumerate(loads):
            if load + row.students <= largest_room and all(m[0] != row.class_row_id for m in bins[i]):
                bins[i].append((row.class_row_id, row.students))
                loads[i] += row.students
                break
        else:
            bins.append([(row.class_row_id, row.students)])
            loads.append(row.students)

    labels = group_labels(len(bins))
    return [ProposedGroup(label=label, members=members) for label, members in zip(labels, bins, strict=True)]
