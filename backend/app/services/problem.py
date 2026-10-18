"""
Turns the term's data (snapshot, class rows, offerings, groups, and a base
draft or the published timetable) into the solver's Problem, and back.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ClassRow, Draft, Group, RunMode, Snapshot, Term, UnitOffering
from app.solver.model import (
    DAYS,
    Placement,
    Problem,
    Room,
    Weights,
    slot,
    slot_day,
    slot_hour,
)
from app.solver.model import (
    ClassRow as SolverRow,
)
from app.solver.model import (
    Session as SolverSession,
)


def session_key(unit_code: str, group_label: str, index: int) -> str:
    """Stable across drafts and versions: 'COSC 103', 'GR A', 0 -> 'COSC103-GRA-1'."""
    unit = re.sub(r"[^A-Za-z0-9]", "", unit_code).upper()
    group = re.sub(r"[^A-Za-z0-9]", "", group_label).upper() or "MAIN"
    return f"{unit}-{group}-{index + 1}"


def start_slot(day: str, start_time: str) -> int:
    return slot(DAYS.index(day), int(start_time.split(":")[0]))


def times(start: int, length: int) -> tuple[str, str, str]:
    """(day, start HH:MM, end HH:MM) of a slot range."""
    return DAYS[slot_day(start)], f"{slot_hour(start):02d}:00", f"{slot_hour(start) + length:02d}:00"


@dataclass
class Built:
    problem: Problem
    groups: dict[str, Group]  # session key -> group
    offerings: dict[str, UnitOffering]  # session key -> offering
    rows: dict[uuid.UUID, ClassRow]
    rooms: dict[str, dict[str, Any]]  # SMARTTT room id -> snapshot room


def build_problem(
    db: Session, term: Term, snapshot: Snapshot, weights: Weights, mode: RunMode, base: Draft | None
) -> Built:
    data = snapshot.data
    rooms = {r["id"]: r for r in data["rooms"]}
    solver_rooms = [
        Room(
            id=r["id"],
            code=r["code"],
            building=r["building"] or r["code"],
            capacity=r["capacity"],
            room_type=r["room_type"],
        )
        for r in data["rooms"]
        if r["status"] == "active"
    ]
    capacity = {
        d["id"]: int(d["lecturers"].get("full_time", 0)) + int(d["lecturers"].get("part_time", 0))
        for d in data["departments"]
    }

    rows = {r.id: r for r in db.scalars(select(ClassRow).where(ClassRow.term_id == term.id))}
    solver_rows = [
        SolverRow(id=str(r.id), label=r.label, unavailable=frozenset(r.unavailable or ())) for r in rows.values()
    ]

    base_sessions = {s.key: s for s in base.sessions} if base is not None else {}
    published = {s["key"]: s for s in (data.get("published") or {}).get("sessions") or [] if s.get("key")}

    sessions: list[SolverSession] = []
    groups: dict[str, Group] = {}
    offerings: dict[str, UnitOffering] = {}
    for offering in db.scalars(
        select(UnitOffering).where(UnitOffering.term_id == term.id).order_by(UnitOffering.unit_code)
    ):
        lengths = offering.session_lengths()
        for group in offering.groups:
            if not group.members:
                continue
            for index, length in enumerate(lengths):
                key = session_key(offering.unit_code, group.label, index)
                pinned = previous = None
                lecturer = None
                if mode == RunMode.RESOLVE and key in base_sessions:
                    b = base_sessions[key]
                    placement = Placement(start=b.start_slot, room_id=b.smarttt_room_id)
                    if b.pinned:
                        pinned = placement
                    previous = placement
                elif mode == RunMode.REPAIR and key in published:
                    p = published[key]
                    previous = Placement(start=start_slot(p["day_of_week"], p["start_time"]), room_id=p["room_id"])
                    lecturer = p.get("lecturer_id")
                    if key in base_sessions and base_sessions[key].pinned:
                        b = base_sessions[key]
                        pinned = Placement(start=b.start_slot, room_id=b.smarttt_room_id)
                label = f"{offering.unit_code}{' ' + group.label if group.label else ''} #{index + 1}"
                sessions.append(
                    SolverSession(
                        key=key,
                        offering_id=str(offering.id),
                        group_id=str(group.id),
                        index=index,
                        label=label,
                        department_id=offering.owning_department_id,
                        class_row_ids=tuple(str(m.class_row_id) for m in group.members),
                        students=group.student_count,
                        length=length,
                        room_type=offering.room_type,
                        pinned=pinned,
                        previous=previous,
                        lecturer_id=lecturer,
                    )
                )
                groups[key] = group
                offerings[key] = offering

    problem = Problem(
        rooms=solver_rooms, class_rows=solver_rows, sessions=sessions, department_capacity=capacity, weights=weights
    )
    return Built(problem=problem, groups=groups, offerings=offerings, rows=rows, rooms=rooms)


def placements_of(draft: Draft) -> dict[str, Placement]:
    return {s.key: Placement(start=s.start_slot, room_id=s.smarttt_room_id) for s in draft.sessions}
