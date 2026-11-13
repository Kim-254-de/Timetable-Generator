"""
Phase 2: where each session's papers sit (bin packing).

Papers are placed biggest first. A paper's students go in one room when any
room has the seats for them all (its ODEL students and its others each count
as one lot, as they sit apart), preferring a room the paper already uses, then
a room already in use, so small papers share rooms, then the tightest fit.
A paper no room can hold is cut into seating blocks of whole class rows; a class
row bigger than every room is cut into equal parts, each given one room ("part
1 of 2"). Each block goes in a room the paper already uses, else the emptiest,
so the paper takes as few rooms as possible.
A paper stays in one building. It starts in the building that holds all of it
in the fewest rooms, and students who don't fit a room take other rooms there
("UTC 1", then "UTC 2"), even if that splits a class row. It moves on to
another building only when its building has no seats left; if no building
holds it all, it starts in the one with the most seats.
A session's postgraduate papers share one room when they fit, and so do its
certificate papers and its diploma papers, each level in its own room. Other
papers keep out of those rooms while they can sit anywhere else.
With a postgraduate room set for the term ("TC 1"), a session's postgraduate
papers sit there first; students who don't fit take other rooms in its building
(TC), and undergraduates fill the seats left in those rooms. Only the
postgraduate room itself is kept from undergraduates, and only in sessions with
postgraduate papers. When the building is full they go on to the next one.
A paper's ODEL class rows sit apart from its other class rows.
A paper the
Director gave its venues on the draft keeps them; the rest are seated around it.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from app.exam_solver.model import CERTIFICATE, DIPLOMA, POSTGRADUATE, ExamRoom, Paper, Seat, venue_group


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
        if r.students == 0:  # a class known to sit it, number not known yet: held apart, nothing to seat
            continue
        parts = math.ceil(r.students / biggest)
        base, extra = divmod(r.students, parts)
        for i in range(parts):
            out.append(_Block(paper, r.row_id, base + (1 if i < extra else 0), r.odel, i + 1, parts))
    return sorted(out, key=lambda b: -b.students)


def _keeps_seats(paper: Paper, rooms: dict[str, ExamRoom]) -> bool:
    """Its chosen venues still hold: every room open, and the same students as its class rows."""
    if not paper.fixed_seats or any(s.room_id not in rooms for s in paper.fixed_seats):
        return False
    wanted: dict[str, int] = defaultdict(int)
    for s in paper.fixed_seats:
        wanted[s.row_id] += s.students
    return dict(wanted) == {r.row_id: r.students for r in paper.rows if r.students}


def _next_building(rooms: list[ExamRoom], left: dict[str, int], taken: set[str], students: int) -> str | None:
    """The building to seat these students in next, of those the paper isn't in yet."""
    free: dict[str, list[ExamRoom]] = defaultdict(list)
    for r in rooms:
        if r.block not in taken and left[r.id] > 0:
            free[r.block].append(r)

    def rank(block: str) -> tuple[Any, ...]:
        sizes = sorted((left[r.id] for r in free[block]), reverse=True)
        total = sum(sizes)
        if total < students:
            return (1, -total, block)  # none holds them all: the most seats, so the fewest buildings
        needed, still = 0, students
        for size in sizes:
            if still <= 0:
                break
            still -= size
            needed += 1
        one_room = [r for r in free[block] if left[r.id] >= students]
        shares = any(left[r.id] < r.seats for r in one_room)  # small papers share rooms
        spare = min(left[r.id] for r in one_room) - students if one_room else total - students
        return (0, needed, not shares, spare, block)

    return min(free, key=rank, default=None)


def seat_session(papers: list[Paper], rooms: list[ExamRoom], postgraduate_room: str | None = None) -> list[Seat]:
    if not papers:
        return []
    if not rooms:
        raise SeatingError("No room is available for exams.")
    need = sum(p.students for p in papers)
    have = sum(r.seats for r in rooms)
    if need > have:
        raise SeatingError(f"{need} students but only {have} exam seats.")
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

    # The room(s) of this session's postgraduate, certificate and diploma papers (S-E8).
    shared: dict[str, list[str]] = defaultdict(list)
    groups = {p.id: venue_group(p.kind, p.codes) for p in papers}
    # The venues the Director chose stay, while the room is open and the numbers are the same.
    placed: set[str] = set()
    for paper in papers:
        if not _keeps_seats(paper, by_id):
            continue
        placed.add(paper.id)
        for s in paper.fixed_seats:
            left[s.room_id] -= s.students
            odel = next((r.odel for r in paper.rows if r.row_id == s.row_id), False)
            holds[(paper.id, s.room_id)].add(odel)
            if s.room_id not in paper_rooms[paper.id]:
                paper_rooms[paper.id].append(s.room_id)
            level = groups[paper.id]
            if level and s.room_id not in shared[level]:
                shared[level].append(s.room_id)
            seats.append(s)
    # Each level takes its own rooms first, then the rest.
    order = {POSTGRADUATE: 0, CERTIFICATE: 1, DIPLOMA: 2}
    waiting: dict[str, int] = defaultdict(int)  # students of each level still to seat
    for p in papers:
        level = groups[p.id]
        if p.id not in placed and level:
            waiting[level] += p.students
    settled = {g for g, kept in shared.items() if kept}
    # The term's postgraduate room is their home, whatever else the Director chose for some of them.
    graduate_room = postgraduate_room if postgraduate_room in by_id else None
    if graduate_room and any(groups[p.id] == POSTGRADUATE for p in papers):
        if graduate_room not in shared[POSTGRADUATE]:
            shared[POSTGRADUATE].insert(0, graduate_room)
        settled.add(POSTGRADUATE)
    else:
        graduate_room = None

    def kept_for(level: str) -> list[str]:
        """The rooms kept from other papers: with a postgraduate room, only that room is."""
        return [graduate_room] if level == POSTGRADUATE and graduate_room else shared[level]

    unseated = (p for p in papers if p.id not in placed)
    for paper in sorted(unseated, key=lambda p: (order.get(groups[p.id] or "", 3), -p.students, p.label)):
        group = groups[paper.id]
        if group and group not in settled:
            settled.add(group)
            total = waiting[group]
            home = sorted(
                (r for r in rooms if left[r.id] >= total and left[r.id] == r.seats),
                key=lambda r: (r.seats, r.code),
            )
            if total and home:
                shared[group].append(home[0].id)
        own = shared[group] if group else []
        others = {room for g in list(shared) if g != group for room in kept_for(g)}
        biggest = max(r.seats for r in rooms)
        if group == POSTGRADUATE and graduate_room:
            buildings = {by_id[graduate_room].block}  # its building, not where a chosen venue put one of them
        else:
            buildings = {by_id[r].block for r in own}
        # The first paper of a level picks the building for them all.
        to_seat = waiting[group] if group and not own else paper.students
        # The first paper of a level picks the building for them all, even if it fits a room anywhere.
        if group and not buildings:
            first = _next_building([r for r in rooms if r.id not in others], left, buildings, waiting[group])
            if first is not None:
                buildings.add(first)
        blocks = _blocks(paper, biggest)
        cut: list[_Block] = []
        for odel in (False, True):
            lot = [b for b in blocks if b.odel == odel]
            if not lot:
                continue
            students = sum(b.students for b in lot)
            buildings |= {by_id[r].block for r in paper_rooms[paper.id]}
            room = None
            for pool in ([r for r in rooms if r.id not in others], rooms):
                can = [
                    r
                    for r in pool
                    if left[r.id] >= students and (not buildings or r.block in buildings) and allowed(lot[0], r.id)
                ]
                if can:
                    room = min(
                        can,
                        # min() ranks the rooms now, inside this loop pass, so `students` is current.
                        key=lambda r: (
                            bool(group) and r.id not in own,
                            r.id in others,
                            r.id not in paper_rooms[paper.id],
                            left[r.id] == r.seats,  # unused rooms last: small papers share
                            left[r.id] - students,
                            r.code,
                        ),
                    )
                    break
            if room is None:
                cut.extend(lot)
                continue
            for b in lot:
                place(b, room.id, b.students, b.part, b.parts)
            to_seat -= students
            if group:
                waiting[group] -= students
                if room.id not in own:
                    own.append(room.id)
        for block in sorted(cut, key=lambda b: -b.students):
            mine = paper_rooms[paper.id]
            buildings |= {by_id[r].block for r in mine}
            # Stay in the paper's building(s) until they can't take this block. Rooms kept
            # for another level count only when nothing else is left.
            kept_out = [r for r in rooms if r.id not in others]
            for pool in (kept_out, rooms):
                while True:
                    here = [r for r in pool if r.block in buildings and allowed(block, r.id)]
                    fits = [r for r in here if left[r.id] >= block.students]
                    enough = bool(fits) or sum(max(left[r.id], 0) for r in here) >= block.students
                    if enough:
                        break
                    # A building is judged on all that is still to seat, this block included.
                    next_building = _next_building(pool, left, buildings, max(to_seat, block.students))
                    if next_building is None:
                        break
                    buildings.add(next_building)
                if enough:
                    break
            to_seat -= block.students
            if group:
                waiting[group] -= block.students
            if fits:
                best = min(
                    fits,
                    key=lambda r: (
                        bool(group) and r.id not in own,
                        r.id in others,
                        r.id not in mine,
                        -left[r.id],  # the emptiest: this paper needs as few rooms as it can get
                        r.code,
                    ),
                )
                place(block, best.id, block.students, block.part, block.parts)
                if group and best.id not in own:
                    own.append(best.id)
                continue
            # No single room has the space: spread this block over the building's emptiest allowed rooms.
            spread = sorted((r for r in here if left[r.id] > 0), key=lambda r: (r.id in others, -left[r.id]))
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
                if group and room_id not in own:
                    own.append(room_id)
    return seats
