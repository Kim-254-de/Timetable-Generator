"""
Independent check of a timetable against the hard rules, without the solver.

Used to verify every solver result, to accept or refuse the Director's manual
moves (a move that breaks a hard rule is refused), and to report on the
hand-made timetable in the benchmark.
"""

from __future__ import annotations

from collections import defaultdict

from app.solver.model import (
    DAYS,
    Placement,
    Problem,
    Violation,
    covered,
    slot_day,
    slot_hour,
    valid_start,
)


def _when(t: int) -> str:
    return f"{DAYS[slot_day(t)]} {slot_hour(t):02d}:00"


def check(problem: Problem, placements: dict[str, Placement]) -> list[Violation]:
    """Every hard-rule violation (H1-H10, H13) in the placements."""
    rooms = problem.rooms_by_id()
    rows = problem.rows_by_id()
    out: list[Violation] = []

    room_use: dict[tuple[str, int], list[str]] = defaultdict(list)
    # (row, slot) -> offering -> group -> session keys. Different groups of one
    # unit may share a row's hour (a split row); anything else may not.
    row_use: dict[tuple[str, int], dict[str, dict[str, list[str]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    dept_use: dict[tuple[int, int], int] = defaultdict(int)
    dept_keys: dict[tuple[int, int], list[str]] = defaultdict(list)
    lecturer_use: dict[tuple[str, int], list[str]] = defaultdict(list)

    for s in problem.sessions:
        p = placements.get(s.key)
        if p is None:
            out.append(Violation("H5", f"{s.label} is not scheduled.", (s.key,)))
            continue
        if not valid_start(p.start, s.length):
            out.append(Violation("H6", f"{s.label} must fit in one day between 07:00 and 19:00.", (s.key,)))
            continue
        room = rooms.get(p.room_id)
        if room is None:
            out.append(Violation("H4", f"{s.label} is in an unknown room.", (s.key,)))
            continue
        if room.capacity < s.students:
            out.append(
                Violation("H3", f"{s.label} has {s.students} students; {room.code} seats {room.capacity}.", (s.key,))
            )
        if room.room_type != s.room_type:
            out.append(
                Violation(
                    "H4",
                    f"{s.label} needs a {s.room_type.replace('_', ' ')}; {room.code} is a "
                    f"{room.room_type.replace('_', ' ')}.",
                    (s.key,),
                )
            )
        if s.pinned is not None and s.pinned != p:
            out.append(Violation("H10", f"{s.label} is pinned and was moved.", (s.key,)))
        for t in covered(p.start, s.length):
            room_use[(room.id, t)].append(s.key)
            if t in room.unavailable:
                out.append(Violation("H8", f"{room.code} is unavailable on {_when(t)} ({s.label}).", (s.key,)))
            for row_id in s.class_row_ids:
                row = rows.get(row_id)
                if row is not None and t in row.unavailable:
                    out.append(Violation("H8", f"{row.label} is unavailable on {_when(t)} ({s.label}).", (s.key,)))
                row_use[(row_id, t)][s.offering_id][s.group_id].append(s.key)
            dept_use[(s.department_id, t)] += 1
            dept_keys[(s.department_id, t)].append(s.key)
            if s.lecturer_id:
                lecturer_use[(s.lecturer_id, t)].append(s.key)

    for (room_id, t), keys in room_use.items():
        if len(keys) > 1:
            out.append(Violation("H1", f"{rooms[room_id].code} hosts {len(keys)} classes on {_when(t)}.", tuple(keys)))
    for (row_id, t), offerings in row_use.items():
        label = rows[row_id].label if row_id in rows else row_id
        row_keys = tuple(k for groups in offerings.values() for ks in groups.values() for k in ks)
        if len(offerings) > 1 or any(len(ks) > 1 for groups in offerings.values() for ks in groups.values()):
            out.append(Violation("H2", f"{label} has {len(row_keys)} classes on {_when(t)}.", row_keys))
    for (dept, t), count in dept_use.items():
        cap = problem.department_capacity.get(dept)
        if cap is not None and count > cap:
            out.append(
                Violation(
                    "H9",
                    f"Department {dept} runs {count} classes on {_when(t)} with {cap} lecturers.",
                    tuple(dept_keys[(dept, t)]),
                )
            )
    for (_lecturer, t), keys in lecturer_use.items():
        if len(keys) > 1:
            out.append(
                Violation("H13", f"An allocated lecturer would teach {len(keys)} classes on {_when(t)}.", tuple(keys))
            )
    return _dedupe(out)


def _dedupe(violations: list[Violation]) -> list[Violation]:
    seen: set[tuple[str, str]] = set()
    result = []
    for v in violations:
        key = (v.rule, v.message)
        if key not in seen:
            seen.add(key)
            result.append(v)
    return result
