"""Proposing and editing how offerings are split into groups. The Director decides the final split."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Identity
from app.errors import ApiError
from app.models import ClassRow, Group, GroupClassRow, Term, UnitOffering
from app.services.setup import audit, latest_snapshot
from app.solver.groups import RowDemand, propose


def largest_rooms(snapshot_data: dict[str, Any]) -> dict[str, int]:
    biggest: dict[str, int] = {}
    for room in snapshot_data["rooms"]:
        if room["status"] == "active":
            biggest[room["room_type"]] = max(biggest.get(room["room_type"], 0), room["capacity"])
    return biggest


def propose_groups(db: Session, identity: Identity, term: Term, replace: bool) -> dict[str, Any]:
    """
    Proposes groups for every offering that has none (or for all, with
    `replace`). Offerings whose class rows have no student count yet, or
    whose room type has no room, are listed and left alone.
    """
    snapshot = latest_snapshot(db, term)
    if snapshot is None:
        raise ApiError(409, "NO_SNAPSHOT", "Take a snapshot of SMARTTT first.")
    biggest = largest_rooms(snapshot.data)
    rows = {r.id: r for r in db.scalars(select(ClassRow).where(ClassRow.term_id == term.id))}
    proposed, skipped = 0, []

    for offering in db.scalars(select(UnitOffering).where(UnitOffering.term_id == term.id)):
        if offering.groups and not replace:
            continue
        members = [rows[link.class_row_id] for link in offering.class_rows if link.class_row_id in rows]
        missing = [r.label for r in members if r.student_count is None]
        if not members or missing:
            skipped.append(
                {
                    "unit_code": offering.unit_code,
                    "reason": "no class rows" if not members else f"no size for {', '.join(missing[:5])}",
                }
            )
            continue
        room = biggest.get(offering.room_type, 0)
        if room <= 0:
            skipped.append({"unit_code": offering.unit_code, "reason": f"no active {offering.room_type}"})
            continue
        demands = [RowDemand(str(r.id), r.label, int(r.student_count or 0)) for r in members]
        offering.groups.clear()
        db.flush()
        for g in propose(demands, room):
            offering.groups.append(
                Group(
                    label=g.label,
                    members=[GroupClassRow(class_row_id=uuid.UUID(row_id), students=n) for row_id, n in g.members],
                )
            )
        proposed += 1
    audit(db, identity, "groups.propose", "term", str(term.id), None, {"proposed": proposed, "replace": replace})
    db.commit()
    return {"proposed": proposed, "skipped": skipped}


def replace_group(
    db: Session,
    identity: Identity,
    offering: UnitOffering,
    group: Group | None,
    label: str,
    members: list[tuple[uuid.UUID, int]],
) -> Group:
    """Creates or edits one group. Members must be class rows that take the offering."""
    allowed = {link.class_row_id for link in offering.class_rows}
    unknown = [str(row_id) for row_id, _n in members if row_id not in allowed]
    if unknown:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "Every member must be a class row that takes this unit.",
            {"class_row_ids": unknown},
        )
    if len({row_id for row_id, _n in members}) != len(members):
        raise ApiError(422, "VALIDATION_ERROR", "A class row is listed twice.")
    clash = next((g for g in offering.groups if g.label == label and g is not group), None)
    if clash is not None:
        raise ApiError(409, "LABEL_TAKEN", f"{offering.unit_code} already has a group {label or '(whole class)'}.")
    before = None
    if group is None:
        group = Group(label=label)
        offering.groups.append(group)
    else:
        before = {"label": group.label, "members": [[str(m.class_row_id), m.students] for m in group.members]}
        group.label = label
        group.members.clear()
        db.flush()
    group.members.extend(GroupClassRow(class_row_id=row_id, students=n) for row_id, n in members)
    db.flush()
    audit(
        db,
        identity,
        "group.save",
        "group",
        str(group.id),
        before,
        {"label": label, "members": [[str(r), n] for r, n in members]},
    )
    db.commit()
    return group
