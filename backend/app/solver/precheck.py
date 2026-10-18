"""
Quick counting checks run before the solver, so an impossible problem is
explained in the Director's terms ("BED.BIO/AGR Y1S1 (3) needs 64 hours; the
week has 60") instead of a bare INFEASIBLE.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from app.solver.model import SLOTS, Problem, Session, covered, valid_start


@dataclass(frozen=True)
class Finding:
    rule: str
    entity: str
    message: str


def feasible_starts(s: Session, problem: Problem) -> list[int]:
    """Starts that keep the session inside one teaching day and off its class rows' unavailable hours."""
    if s.pinned is not None:
        return [s.pinned.start] if valid_start(s.pinned.start, s.length) else []
    blocked: set[int] = set()
    rows = problem.rows_by_id()
    for row_id in s.class_row_ids:
        row = rows.get(row_id)
        if row is not None:
            blocked |= row.unavailable
    return [p for p in range(SLOTS) if valid_start(p, s.length) and not blocked.intersection(covered(p, s.length))]


def suitable_rooms(s: Session, problem: Problem) -> list[str]:
    if s.pinned is not None:
        return [s.pinned.room_id]
    return [r.id for r in problem.rooms if r.room_type == s.room_type and r.capacity >= s.students]


def run(problem: Problem) -> list[Finding]:
    findings: list[Finding] = []
    rows = problem.rows_by_id()

    for s in problem.sessions:
        if not feasible_starts(s, problem):
            findings.append(Finding("H8", s.label, f"{s.label} ({s.length} h) has no free time left in the week."))
        if not suitable_rooms(s, problem):
            findings.append(
                Finding(
                    "H3",
                    s.label,
                    f"No {s.room_type.replace('_', ' ')} seats {s.students} students for {s.label}; "
                    "split the group or add a room.",
                )
            )
        if problem.require_department_capacity and s.department_id not in problem.department_capacity:
            findings.append(
                Finding(
                    "H9",
                    f"department {s.department_id}",
                    f"Department {s.department_id} has no lecturer count in the snapshot.",
                )
            )

    # H2: a class row's hours must fit in its free hours of the week. A row
    # split across groups of one unit needs at least its busiest group's hours.
    group_hours: dict[tuple[str, str, str], int] = defaultdict(int)
    for s in problem.sessions:
        for row_id in s.class_row_ids:
            group_hours[(row_id, s.offering_id, s.group_id)] += s.length
    per_offering: dict[tuple[str, str], int] = defaultdict(int)
    for (row_id, offering_id, _group), hours in group_hours.items():
        per_offering[(row_id, offering_id)] = max(per_offering[(row_id, offering_id)], hours)
    row_hours: dict[str, int] = defaultdict(int)
    for (row_id, _offering), hours in per_offering.items():
        row_hours[row_id] += hours
    for row_id, hours in row_hours.items():
        row = rows.get(row_id)
        free = SLOTS - len(row.unavailable) if row else SLOTS
        if hours > free:
            label = row.label if row else row_id
            findings.append(Finding("H2", label, f"{label} needs {hours} teaching hours; it has {free} free hours."))

    # H1/H3/H4: per room type and size, the session-hours must fit in the room-hours.
    by_type: dict[str, list[Session]] = defaultdict(list)
    for s in problem.sessions:
        by_type[s.room_type].append(s)
    for room_type, sessions in by_type.items():
        for threshold in sorted({s.students for s in sessions}):
            need = sum(s.length for s in sessions if s.students >= threshold)
            have = sum(
                SLOTS - len(r.unavailable)
                for r in problem.rooms
                if r.room_type == room_type and r.capacity >= threshold
            )
            if need > have:
                findings.append(
                    Finding(
                        "H1",
                        f"{room_type} >= {threshold}",
                        f"Classes of {threshold}+ students need {need} {room_type.replace('_', ' ')}-hours; "
                        f"rooms that size offer {have}.",
                    )
                )
                break

    # H9: a department's teaching hours must fit its lecturers x 60.
    dept_hours: dict[int, int] = defaultdict(int)
    for s in problem.sessions:
        dept_hours[s.department_id] += s.length
    for dept, hours in dept_hours.items():
        cap = problem.department_capacity.get(dept)
        if cap is not None and hours > cap * SLOTS:
            findings.append(
                Finding(
                    "H9",
                    f"department {dept}",
                    f"Department {dept} teaches {hours} hours a week with {cap} lecturers (at most {cap * SLOTS}).",
                )
            )
    return findings
