"""
The data the Directorate enters in the Generator: lecture halls, departments,
class rows and units (with the class rows that take each unit), entered one
at a time or pasted in bulk from Excel, and copying a previous term's class
rows, units and groups into a new term.

Deleting refuses anything still in use and says where, so a timetable is
never left pointing at a room, class row or unit that no longer exists.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.schemas import ClassRowBody, DepartmentBody, DepartmentPatch, OfferingBody, RoomBody, RoomPatch
from app.auth import Identity
from app.errors import ApiError
from app.models import (
    ClassRow,
    Department,
    DraftSession,
    Group,
    GroupClassRow,
    OfferingClassRow,
    Room,
    Term,
    UnitOffering,
)
from app.services.setup import audit, compact, row_label

FIRST_LOCAL_DEPARTMENT_ID = 100_000


# -- lecture halls ---------------------------------------------------------------------


def room_dict(room: Room, in_use: int = 0) -> dict[str, Any]:
    return {
        "id": room.id,
        "code": room.code,
        "building": room.building,
        "capacity": room.capacity,
        "room_type": room.room_type,
        "active": room.active,
        "unavailable": sorted(room.unavailable or []),
        "in_use": in_use,
    }


def list_rooms(db: Session) -> list[dict[str, Any]]:
    usage = dict(
        db.execute(select(DraftSession.smarttt_room_id, func.count()).group_by(DraftSession.smarttt_room_id)).all()
    )
    rooms = db.scalars(select(Room).order_by(Room.building, Room.code))
    return [room_dict(r, int(usage.get(r.id, 0))) for r in rooms]


def _room_by_code(db: Session, code: str) -> Room | None:
    return db.scalar(select(Room).where(func.upper(Room.code) == code.strip().upper()))


def _apply_room(db: Session, room: Room, fields: dict[str, Any]) -> None:
    if "code" in fields and fields["code"] is not None:
        clash = _room_by_code(db, fields["code"])
        if clash is not None and clash.id != room.id:
            raise ApiError(409, "CODE_TAKEN", f"There is already a lecture hall {clash.code}.")
    for key in ("code", "building", "capacity", "room_type", "active"):
        if key in fields and fields[key] is not None:
            setattr(room, key, fields[key])
    if fields.get("unavailable") is not None:
        room.unavailable = sorted(set(fields["unavailable"]))


def create_room(db: Session, identity: Identity, fields: dict[str, Any], commit: bool = True) -> Room:
    room = Room(id=uuid.uuid4().hex, code="", building="", capacity=1, room_type="lecture_hall", unavailable=[])
    _apply_room(db, room, fields)
    db.add(room)
    db.flush()
    audit(db, identity, "room.create", "room", room.id, None, room_dict(room))
    if commit:
        db.commit()
    return room


def update_room(db: Session, identity: Identity, room: Room, fields: dict[str, Any], commit: bool = True) -> Room:
    before = room_dict(room)
    _apply_room(db, room, fields)
    db.flush()
    audit(db, identity, "room.update", "room", room.id, before, room_dict(room))
    if commit:
        db.commit()
    return room


def delete_room(db: Session, identity: Identity, room: Room) -> None:
    used = db.scalar(select(func.count()).select_from(DraftSession).where(DraftSession.smarttt_room_id == room.id))
    if used:
        raise ApiError(
            409,
            "IN_USE",
            f"{room.code} is used by {used} classes in saved timetables. Mark it not available instead.",
        )
    audit(db, identity, "room.delete", "room", room.id, room_dict(room), None)
    db.delete(room)
    db.commit()


# -- departments ---------------------------------------------------------------------------


def department_dict(d: Department) -> dict[str, Any]:
    return {
        "id": d.id,
        "code": d.code,
        "name": d.name,
        "school": d.school,
        "lecturer_count": d.lecturer_count,
        "smarttt_department_id": d.smarttt_department_id,
    }


def list_departments(db: Session) -> list[dict[str, Any]]:
    return [department_dict(d) for d in db.scalars(select(Department).order_by(Department.name))]


def get_department(db: Session, department_id: int) -> Department:
    found = db.get(Department, department_id)
    if found is None:
        raise ApiError(404, "NOT_FOUND", "No such department.")
    return found


def _department_by_code(db: Session, code: str) -> Department | None:
    return db.scalar(select(Department).where(func.upper(Department.code) == code.strip().upper()))


def _apply_department(db: Session, d: Department, fields: dict[str, Any]) -> None:
    if fields.get("code") is not None:
        clash = _department_by_code(db, fields["code"])
        if clash is not None and clash.id != d.id:
            raise ApiError(409, "CODE_TAKEN", f"There is already a department {clash.code}.")
    for key in ("code", "name", "school"):
        if fields.get(key) is not None:
            setattr(d, key, fields[key])
    if "lecturer_count" in fields and fields["lecturer_count"] is not None:
        d.lecturer_count = fields["lecturer_count"] or None


def create_department(db: Session, identity: Identity, fields: dict[str, Any], commit: bool = True) -> Department:
    next_id = max(int(db.scalar(select(func.max(Department.id))) or 0) + 1, FIRST_LOCAL_DEPARTMENT_ID)
    d = Department(id=next_id, code="", name="", school="")
    _apply_department(db, d, fields)
    db.add(d)
    db.flush()
    audit(db, identity, "department.create", "department", str(d.id), None, department_dict(d))
    if commit:
        db.commit()
    return d


def update_department(
    db: Session, identity: Identity, d: Department, fields: dict[str, Any], commit: bool = True
) -> Department:
    before = department_dict(d)
    _apply_department(db, d, fields)
    db.flush()
    audit(db, identity, "department.update", "department", str(d.id), before, department_dict(d))
    if commit:
        db.commit()
    return d


def delete_department(db: Session, identity: Identity, d: Department) -> None:
    units = db.scalar(select(func.count()).select_from(UnitOffering).where(UnitOffering.owning_department_id == d.id))
    rows = db.scalar(select(func.count()).select_from(ClassRow).where(ClassRow.department_id == d.id))
    if units or rows:
        raise ApiError(409, "IN_USE", f"{d.code} still owns {units} units and {rows} class rows.")
    audit(db, identity, "department.delete", "department", str(d.id), department_dict(d), None)
    db.delete(d)
    db.commit()


# -- class rows -------------------------------------------------------------------------------


def _check_department(db: Session, department_id: int | None) -> None:
    if department_id is not None and db.get(Department, department_id) is None:
        raise ApiError(422, "VALIDATION_ERROR", "Choose a department from the Departments list.")


def _label_taken(db: Session, term: Term, label: str, exclude: uuid.UUID | None) -> bool:
    query = select(ClassRow).where(ClassRow.term_id == term.id)
    return any(r.id != exclude and compact(r.label) == compact(label) for r in db.scalars(query))


def create_class_row(
    db: Session, identity: Identity, term: Term, fields: dict[str, Any], commit: bool = True
) -> ClassRow:
    _check_department(db, fields.get("department_id"))
    label = row_label(fields["program_code"], fields["study_year"], fields["study_semester"], fields["sub_class"])
    if _label_taken(db, term, label, None):
        raise ApiError(409, "LABEL_TAKEN", f"{label} already exists in this term.")
    row = ClassRow(
        term_id=term.id,
        smarttt_program_id=None,
        department_id=fields.get("department_id"),
        program_code=fields["program_code"],
        study_year=fields["study_year"],
        study_semester=fields["study_semester"],
        sub_class=fields["sub_class"],
        label=label,
        student_count=fields.get("student_count"),
        unavailable=sorted(set(fields.get("unavailable") or [])),
    )
    db.add(row)
    db.flush()
    audit(db, identity, "class_row.create", "class_row", str(row.id), None, {"label": label})
    if commit:
        db.commit()
    return row


def update_class_row(db: Session, row: ClassRow, fields: dict[str, Any]) -> None:
    """Applies a patch (the caller audits and commits). Everything is checked before anything changes."""
    if fields.get("department_id") is not None:
        _check_department(db, fields["department_id"])
    new = {
        key: fields[key] if fields.get(key) is not None else getattr(row, key)
        for key in ("program_code", "study_year", "study_semester", "sub_class")
    }
    label = row_label(new["program_code"], new["study_year"], new["study_semester"], new["sub_class"])
    if compact(label) != compact(row.label):
        term = db.get(Term, row.term_id)
        if term is not None and _label_taken(db, term, label, row.id):
            raise ApiError(409, "LABEL_TAKEN", f"{label} already exists in this term.")
    for key, value in new.items():
        setattr(row, key, value)
    row.label = label
    if fields.get("department_id") is not None:
        row.department_id = fields["department_id"]
    if fields.get("student_count") is not None:
        row.student_count = fields["student_count"]
    if fields.get("unavailable") is not None:
        row.unavailable = sorted(set(fields["unavailable"]))


def delete_class_row(db: Session, identity: Identity, row: ClassRow) -> None:
    units = db.scalar(select(func.count()).select_from(OfferingClassRow).where(OfferingClassRow.class_row_id == row.id))
    if units:
        raise ApiError(409, "IN_USE", f"{row.label} takes {units} units. Remove it from those units first.")
    audit(db, identity, "class_row.delete", "class_row", str(row.id), {"label": row.label}, None)
    db.delete(row)
    db.commit()


# -- units ------------------------------------------------------------------------------------


def _offering_code_taken(db: Session, term: Term, code: str, exclude: uuid.UUID | None) -> bool:
    query = select(UnitOffering).where(UnitOffering.term_id == term.id)
    return any(o.id != exclude and compact(o.unit_code) == compact(code) for o in db.scalars(query))


def _term_rows(db: Session, term_id: uuid.UUID, ids: list[uuid.UUID]) -> list[ClassRow]:
    rows = {r.id: r for r in db.scalars(select(ClassRow).where(ClassRow.term_id == term_id))}
    unknown = [str(i) for i in ids if i not in rows]
    if unknown:
        raise ApiError(422, "VALIDATION_ERROR", "Every class row must belong to this term.", {"class_row_ids": unknown})
    return [rows[i] for i in dict.fromkeys(ids)]


def _whole_class_group(offering: UnitOffering, rows: list[ClassRow]) -> None:
    """A new unit taken by class rows with known sizes starts as one whole class; the Director can split it."""
    if rows and all(r.student_count for r in rows) and not offering.groups:
        offering.groups.append(
            Group(
                label="",
                members=[GroupClassRow(class_row_id=r.id, students=int(r.student_count or 0)) for r in rows],
            )
        )


def create_offering(
    db: Session, identity: Identity, term: Term, fields: dict[str, Any], commit: bool = True
) -> UnitOffering:
    if _offering_code_taken(db, term, fields["unit_code"], None):
        raise ApiError(409, "CODE_TAKEN", f"{fields['unit_code']} is already a unit in this term.")
    get_department(db, fields["department_id"])
    rows = _term_rows(db, term.id, list(fields.get("class_row_ids") or []))
    session_length = fields.get("session_length") or term.default_session_length
    weekly_hours = fields.get("weekly_hours") or session_length
    if session_length > weekly_hours:
        raise ApiError(422, "VALIDATION_ERROR", "A session can't be longer than the unit's weekly hours.")
    offering = UnitOffering(
        term_id=term.id,
        smarttt_unit_id=None,
        unit_code=fields["unit_code"],
        unit_name=fields["unit_name"],
        owning_department_id=fields["department_id"],
        weekly_hours=weekly_hours,
        session_length=session_length,
        room_type=fields.get("room_type") or "lecture_hall",
        source="manual",
    )
    offering.class_rows = [OfferingClassRow(class_row_id=r.id) for r in rows]
    db.add(offering)
    db.flush()
    _whole_class_group(offering, rows)
    db.flush()
    audit(
        db,
        identity,
        "offering.create",
        "offering",
        str(offering.id),
        None,
        {"unit_code": offering.unit_code, "class_rows": [r.label for r in rows]},
    )
    if commit:
        db.commit()
    return offering


def update_offering(db: Session, term: Term, offering: UnitOffering, fields: dict[str, Any]) -> None:
    """Applies a patch (the caller audits and commits). Everything is checked before anything changes."""
    if fields.get("unit_code") is not None and _offering_code_taken(db, term, fields["unit_code"], offering.id):
        raise ApiError(409, "CODE_TAKEN", f"{fields['unit_code']} is already a unit in this term.")
    if fields.get("department_id") is not None:
        get_department(db, fields["department_id"])
    rows = _term_rows(db, term.id, list(fields["class_row_ids"])) if fields.get("class_row_ids") is not None else None
    weekly = fields.get("weekly_hours") or offering.weekly_hours
    length = fields.get("session_length") or offering.session_length
    if weekly and length and length > weekly:
        raise ApiError(422, "VALIDATION_ERROR", "A session can't be longer than the unit's weekly hours.")

    if fields.get("unit_code") is not None:
        offering.unit_code = fields["unit_code"]
    if fields.get("unit_name") is not None:
        offering.unit_name = fields["unit_name"]
    if fields.get("department_id") is not None:
        offering.owning_department_id = fields["department_id"]
    for key in ("weekly_hours", "session_length", "room_type"):
        if fields.get(key) is not None:
            setattr(offering, key, fields[key])
    if rows is not None:
        keep = {r.id for r in rows}
        offering.class_rows = [OfferingClassRow(class_row_id=r.id) for r in rows]
        # A class row taken off the unit leaves its groups too.
        for group in offering.groups:
            group.members = [m for m in group.members if m.class_row_id in keep]
        db.flush()
        _whole_class_group(offering, rows)
    db.flush()


def delete_offering(db: Session, identity: Identity, offering: UnitOffering) -> None:
    group_ids = [g.id for g in offering.groups]
    used = (
        db.scalar(select(func.count()).select_from(DraftSession).where(DraftSession.group_id.in_(group_ids)))
        if group_ids
        else 0
    )
    if used:
        raise ApiError(
            409,
            "IN_USE",
            f"{offering.unit_code} is in {used} classes of saved timetables. Delete those drafts first.",
        )
    audit(db, identity, "offering.delete", "offering", str(offering.id), {"unit_code": offering.unit_code}, None)
    db.delete(offering)
    db.commit()


# -- bulk entry ---------------------------------------------------------------------------------


def _clean(row: dict[str, Any]) -> dict[str, Any]:
    """Pasted cells arrive as text; blank cells mean 'not given'."""
    out: dict[str, Any] = {}
    for key, value in row.items():
        k = re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                continue
        if value is None:
            continue
        out[k] = value
    return out


def _yes(value: Any) -> bool:
    return str(value).strip().lower() not in {"no", "n", "false", "0", "closed", "inactive"}


ROOM_TYPE_WORDS = {
    "lecture_hall": "lecture_hall",
    "lecture hall": "lecture_hall",
    "hall": "lecture_hall",
    "lecture": "lecture_hall",
    "lab": "lab",
    "laboratory": "lab",
    "computer lab": "lab",
    "science lab": "lab",
    "seminar": "seminar",
    "seminar room": "seminar",
}


def _room_type(value: Any) -> str:
    word = str(value or "lecture hall").strip().lower().replace("_", " ")
    if word not in ROOM_TYPE_WORDS:
        raise ValueError(f"room type '{value}' must be Lecture hall, Lab or Seminar")
    return ROOM_TYPE_WORDS[word]


def _validated(model: type[BaseModel], data: dict[str, Any], exclude_unset: bool = False) -> dict[str, Any]:
    try:
        return model.model_validate(data).model_dump(exclude_unset=exclude_unset)
    except ValidationError as exc:
        first = exc.errors()[0]
        field = ".".join(str(p) for p in first["loc"])
        raise ValueError(f"{field}: {first['msg']}") from exc


def _bulk(db: Session, rows: list[dict[str, Any]], one: Any) -> dict[str, Any]:
    """Applies `one(cleaned_row) -> 'created' | 'updated'` per row; a bad row is reported and skipped."""
    created = updated = 0
    errors: list[dict[str, Any]] = []
    for line, raw in enumerate(rows, start=1):
        # Each row is fully checked before it changes anything, so a refused
        # row leaves nothing half-written behind.
        try:
            outcome = one(_clean(raw))
            db.flush()
        except (ValueError, ApiError) as exc:
            errors.append({"line": line, "message": getattr(exc, "message", None) or str(exc)})
            continue
        if outcome == "created":
            created += 1
        else:
            updated += 1
    db.commit()
    return {"created": created, "updated": updated, "errors": errors[:200], "error_count": len(errors)}


def _given(values: dict[str, Any]) -> dict[str, Any]:
    """The fields a pasted row actually filled in, so an update never blanks what was left out."""
    return {k: v for k, v in values.items() if v is not None}


def bulk_rooms(db: Session, identity: Identity, rows: list[dict[str, Any]]) -> dict[str, Any]:
    def one(r: dict[str, Any]) -> str:
        kind = r.get("room_type") or r.get("type")
        available = r.get("available", r.get("active"))
        given = _given(
            {
                "code": r.get("code") or r.get("room") or r.get("room_code"),
                "building": r.get("building"),
                "capacity": r.get("capacity"),
                "room_type": _room_type(kind) if kind is not None else None,
                "active": _yes(available) if available is not None else None,
            }
        )
        existing = _room_by_code(db, str(given.get("code") or ""))
        if existing is not None:
            update_room(db, identity, existing, _validated(RoomPatch, given, exclude_unset=True), commit=False)
            return "updated"
        create_room(db, identity, _validated(RoomBody, given), commit=False)
        return "created"

    return _bulk(db, rows, one)


def bulk_departments(db: Session, identity: Identity, rows: list[dict[str, Any]]) -> dict[str, Any]:
    def one(r: dict[str, Any]) -> str:
        given = _given(
            {
                "code": r.get("code"),
                "name": r.get("name") or r.get("department"),
                "school": r.get("school", r.get("faculty")),
                "lecturer_count": r.get("lecturer_count") or r.get("lecturers"),
            }
        )
        existing = _department_by_code(db, str(given.get("code") or ""))
        if existing is not None:
            fields = _validated(DepartmentPatch, given, exclude_unset=True)
            update_department(db, identity, existing, fields, commit=False)
            return "updated"
        create_department(db, identity, _validated(DepartmentBody, given), commit=False)
        return "created"

    return _bulk(db, rows, one)


def _department_id(db: Session, value: Any) -> int | None:
    if value in (None, ""):
        return None
    found = _department_by_code(db, str(value))
    if found is None:
        raise ValueError(f"department '{value}' is not in the Departments list (use its code)")
    return found.id


def bulk_class_rows(db: Session, identity: Identity, term: Term, rows: list[dict[str, Any]]) -> dict[str, Any]:
    def one(r: dict[str, Any]) -> str:
        fields = _validated(
            ClassRowBody,
            {
                "program_code": r.get("programme") or r.get("program") or r.get("program_code"),
                "study_year": r.get("year") or r.get("study_year"),
                "study_semester": r.get("semester") or r.get("study_semester"),
                "sub_class": str(r.get("sub_class") or r.get("sub") or ""),
                "department_id": _department_id(db, r.get("department")),
                "student_count": r.get("students") or r.get("student_count"),
            },
        )
        label = row_label(fields["program_code"], fields["study_year"], fields["study_semester"], fields["sub_class"])
        existing = next(
            (
                x
                for x in db.scalars(select(ClassRow).where(ClassRow.term_id == term.id))
                if compact(x.label) == compact(label)
            ),
            None,
        )
        if existing is not None:
            update_class_row(
                db,
                existing,
                {"department_id": fields["department_id"], "student_count": fields["student_count"]},
            )
            return "updated"
        create_class_row(db, identity, term, fields, commit=False)
        return "created"

    return _bulk(db, rows, one)


def bulk_offerings(db: Session, identity: Identity, term: Term, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    One unit per line. `class_rows` lists the class rows that take it,
    separated by ';' (e.g. "BED.MATH/CHEM Y1S1; BSC.COMP SCI Y1S1").
    """
    labels = {compact(r.label): r.id for r in db.scalars(select(ClassRow).where(ClassRow.term_id == term.id))}

    def one(r: dict[str, Any]) -> str:
        names = [x.strip() for x in str(r.get("class_rows") or "").split(";") if x.strip()]
        missing = [n for n in names if compact(n) not in labels]
        if missing:
            raise ValueError(f"class rows not found: {', '.join(missing[:5])}")
        department_id = _department_id(db, r.get("department"))
        if department_id is None:
            raise ValueError("department is required (use its code)")
        kind = r.get("room_type") or r.get("type")
        given = _given(
            {
                "unit_code": r.get("unit_code") or r.get("code"),
                "unit_name": r.get("unit_title") or r.get("title") or r.get("unit_name"),
                "department_id": department_id,
                "weekly_hours": r.get("hours_per_week") or r.get("weekly_hours"),
                "session_length": r.get("class_length") or r.get("session_length"),
                "room_type": _room_type(kind) if kind is not None else None,
                "class_row_ids": [str(labels[compact(n)]) for n in names] if names else None,
            }
        )
        fields = _validated(OfferingBody, given)
        existing = next(
            (
                o
                for o in db.scalars(select(UnitOffering).where(UnitOffering.term_id == term.id))
                if compact(o.unit_code) == compact(fields["unit_code"])
            ),
            None,
        )
        if existing is not None:
            update_offering(db, term, existing, {k: v for k, v in fields.items() if k in given})
            return "updated"
        create_offering(db, identity, term, fields, commit=False)
        return "created"

    return _bulk(db, rows, one)


# -- copying a term -----------------------------------------------------------------------------


def copy_term(db: Session, identity: Identity, target: Term, source: Term) -> dict[str, int]:
    """
    Copies the source term's class rows, units and groups into the target,
    skipping any class row or unit the target already has (same label/code).
    Lecture halls and departments are shared by all terms, so they need no copy.
    """
    if source.id == target.id:
        raise ApiError(422, "VALIDATION_ERROR", "Choose a different term to copy from.")
    existing_rows = {compact(r.label): r for r in db.scalars(select(ClassRow).where(ClassRow.term_id == target.id))}
    row_map: dict[uuid.UUID, uuid.UUID] = {}
    rows_copied = 0
    for r in db.scalars(select(ClassRow).where(ClassRow.term_id == source.id)):
        if compact(r.label) in existing_rows:
            row_map[r.id] = existing_rows[compact(r.label)].id
            continue
        copy = ClassRow(
            term_id=target.id,
            smarttt_program_id=r.smarttt_program_id,
            department_id=r.department_id,
            program_code=r.program_code,
            study_year=r.study_year,
            study_semester=r.study_semester,
            sub_class=r.sub_class,
            label=r.label,
            student_count=r.student_count,
            unavailable=list(r.unavailable or []),
        )
        db.add(copy)
        db.flush()
        row_map[r.id] = copy.id
        rows_copied += 1

    existing_units = {
        compact(o.unit_code) for o in db.scalars(select(UnitOffering).where(UnitOffering.term_id == target.id))
    }
    units_copied = 0
    for o in db.scalars(select(UnitOffering).where(UnitOffering.term_id == source.id)):
        if compact(o.unit_code) in existing_units:
            continue
        copy_o = UnitOffering(
            term_id=target.id,
            smarttt_unit_id=o.smarttt_unit_id,
            unit_code=o.unit_code,
            unit_name=o.unit_name,
            owning_department_id=o.owning_department_id,
            weekly_hours=o.weekly_hours,
            session_length=o.session_length,
            room_type=o.room_type,
            source="copied",
        )
        copy_o.class_rows = [
            OfferingClassRow(class_row_id=row_map[link.class_row_id])
            for link in o.class_rows
            if link.class_row_id in row_map
        ]
        copy_o.groups = [
            Group(
                label=g.label,
                members=[
                    GroupClassRow(class_row_id=row_map[m.class_row_id], students=m.students)
                    for m in g.members
                    if m.class_row_id in row_map
                ],
            )
            for g in o.groups
        ]
        db.add(copy_o)
        units_copied += 1
    db.flush()
    audit(
        db,
        identity,
        "term.copy",
        "term",
        str(target.id),
        None,
        {"from": str(source.id), "class_rows": rows_copied, "units": units_copied},
    )
    db.commit()
    return {"class_rows_copied": rows_copied, "units_copied": units_copied}
