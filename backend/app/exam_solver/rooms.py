"""
Phase 2: where each session's papers sit (bin packing).

A paper is cut into seating blocks of whole class rows; a class row bigger
than every room is cut into equal parts, each given one room ("part 1 of 2").
Blocks are placed biggest paper first, each block in one room within its exam
seats, preferring in order:
  1. a room the paper already uses, then one in the same building block, so a
     paper takes as few rooms as it can, close together;
  2. a room already in use, so small papers share rooms;
  3. the tightest fit, so as few rooms as possible are used.
A paper's ODEL class rows sit apart from its other class rows. A block that
fits no single room (seats fragmented) is spread over the emptiest rooms.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from app.exam_solver.model import ExamRoom, Paper, Seat


class SeatingError(Exception):
    """The session's students don't fit its rooms."""


@dataclass
class _Block:
    paper: Paper
    row_id: str
    students: int
    odel: bool
    part: int = 1
    parts: int = 1


def _blocks(paper: Paper, biggest: int) -> list[_Block]:
    out: list[_Block] = []
    for r in paper.rows:
        parts = max(1, math.ceil(r.students / biggest))
        base, extra = divmod(r.students, parts)
        for i in range(parts):
            out.append(_Block(paper, r.row_id, base + (1 if i < extra else 0), r.odel, i + 1, parts))
    return sorted(out, key=lambda b: -b.students)


def seat_session(papers: list[Paper], rooms: list[ExamRoom]) -> list[Seat]:
    if not papers:
        return []
    if not rooms:
        raise SeatingError("No room is available for exams.")
    need = sum(p.students for p in papers)
    have = sum(r.seats for r in rooms)
    if need > have:
        raise SeatingError(f"{need} students but only {have} exam seats.")
    biggest = max(r.seats for r in rooms)
    left = {r.id: r.seats for r in rooms}
    by_id = {r.id: r for r in rooms}
    # Which of a paper's kinds (ODEL or not) each room holds, so the two never share a room.
    holds: dict[tuple[str, str], set[bool]] = defaultdict(set)
    paper_rooms: dict[str, list[str]] = defaultdict(list)
    seats: list[Seat] = []

    def allowed(block: _Block, room_id: str) -> bool:
        kinds = holds[(block.paper.id, room_id)]
        return not kinds or kinds == {block.odel}

    def place(block: _Block, room_id: str, students: int, part: int, parts: int) -> None:
        left[room_id] -= students
        holds[(block.paper.id, room_id)].add(block.odel)
        if room_id not in paper_rooms[block.paper.id]:
            paper_rooms[block.paper.id].append(room_id)
        seats.append(Seat(block.paper.id, block.row_id, room_id, students, part, parts))

    for paper in sorted(papers, key=lambda p: (-p.students, p.label)):
        for block in _blocks(paper, biggest):
            mine = paper_rooms[paper.id]
            blocks_used = {by_id[r].block for r in mine}
            fits = [r for r in rooms if left[r.id] >= block.students and allowed(block, r.id)]
            if fits:
                best = min(
                    fits,
                    key=lambda r: (
                        r.id not in mine,
                        bool(blocks_used) and r.block not in blocks_used,
                        left[r.id] == r.seats,  # unused rooms last: small papers share
                        left[r.id] - block.students,
                        r.code,
                    ),
                )
                place(block, best.id, block.students, block.part, block.parts)
                continue
            # No single room has the space: spread this block over the emptiest allowed rooms.
            spread = sorted((r for r in rooms if left[r.id] > 0 and allowed(block, r.id)), key=lambda r: -left[r.id])
            remaining, pieces = block.students, []
            for r in spread:
                if remaining <= 0:
                    break
                take = min(left[r.id], remaining)
                pieces.append((r.id, take))
                remaining -= take
            if remaining > 0:
                raise SeatingError(f"{paper.label}: no room left for {remaining} of its students.")
            total = len(pieces) * block.parts
            for i, (room_id, take) in enumerate(pieces):
                place(block, room_id, take, (block.part - 1) * len(pieces) + i + 1, total)
    return seats
