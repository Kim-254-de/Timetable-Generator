"""
"Import published departments": what departments entered and published in
the Timetable Allocator becomes the term's class rows, units and groups.

Each department's course becomes a class row, each unit an offering, and
each group a group with its courses' students and its lecturer (by staff
number). Rows imported carry `allocator_ref`, the Allocator's id, so
importing again updates them in place and says what changed; a department's
unit or group it no longer has is removed (with its classes in the drafts).
A row entered here with the same label or unit code is taken over.

Departments that haven't published are listed and left as they are: the
Director can generate without them, import them later, and re-solve
keeping the published classes where they are.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import Identity
from app.clients.allocator import AllocatorClient
from app.errors import ApiError
from app.models import (
    ClassRow,
    Department,
    DepartmentImport,
    Group,
    GroupClassRow,
    OfferingClassRow,
    Term,
    UnitOffering,
)
from app.services.grouping import remove_group
from app.services.master import FIRST_LOCAL_DEPARTMENT_ID, department_dict
from app.services.setup import audit, compact, row_label

ROOM_TYPES = {"lecture_hall", "lab", "seminar"}


def _when(value: str | None) -> datetime | None:
    if not value:
        return None
    moment = datetime.fromisoformat(value)
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _imports(db: Session, term: Term) -> dict[str, DepartmentImport]:
    return {
        i.department_code: i for i in db.scalars(select(DepartmentImport).where(DepartmentImport.term_id == term.id))
    }


def status(db: Session, allocator: AllocatorClient, term: Term) -> dict[str, Any]:
    """Each department: published or not yet, when, and whether its latest publish is imported."""
    data = allocator.submissions(str(term.id))
    imported = _imports(db, term)
    rows: list[dict[str, Any]] = []
    for d in data.get("published") or []:
        last = imported.get(d["code"])
        published_at = _when(d["published_at"])
        rows.append(
            {
                "code": d["code"],
                "name": d["name"],
                "published": True,
                "published_at": d["published_at"],
                "published_by": d.get("published_by"),
                "units": len(d.get("units") or []),
                "imported_at": last.imported_at.isoformat() if last else None,
                "needs_import": last is None or (published_at is not None and _aware(last.published_at) < published_at),
            }
        )
    for d in data.get("not_published") or []:
        last = imported.get(d["code"])
        rows.append(
            {
                "code": d["code"],
                "name": d["name"],
                "published": False,
                "reopened_at": d.get("reopened_at"),
                "last_published_at": d.get("last_published_at"),
                "changed_units": d.get("changed_units") or [],
                "imported_at": last.imported_at.isoformat() if last else None,
                "needs_import": False,
            }
        )
    rows.sort(key=lambda r: (not r["published"], r["name"]))
    return {
        "departments": rows,
        "published": sum(1 for r in rows if r["published"]),
        "not_published": sum(1 for r in rows if not r["published"]),
        "needs_import": sum(1 for r in rows if r["needs_import"]),
    }


def _department(db: Session, identity: Identity, code: str, name: str) -> Department:
    """The department with this code (spacing and case ignored), added to the Departments list if new."""
    found = next((d for d in db.scalars(select(Department)) if compact(d.code) == compact(code)), None)
    if found is not None:
        return found
    next_id = max(int(db.scalar(select(func.max(Department.id))) or 0) + 1, FIRST_LOCAL_DEPARTMENT_ID)
    d = Department(id=next_id, code=code, name=name or code, school="")
    db.add(d)
    db.flush()
    audit(db, identity, "department.create", "department", str(d.id), None, department_dict(d))
    return d


class _Changes:
    def __init__(self) -> None:
        self.by_department: dict[str, dict[str, list[str]]] = {}
        self.class_rows: dict[str, list[str]] = {"added": [], "changed": [], "removed": []}

    def note(self, department: str, kind: str, what: str) -> None:
        self.by_department.setdefault(department, {"added": [], "changed": [], "removed": []})[kind].append(what)


def _set(obj: Any, values: dict[str, Any]) -> bool:
    """Sets the attributes that differ; True when anything did."""
    changed = False
    for key, value in values.items():
        if getattr(obj, key) != value:
            setattr(obj, key, value)
            changed = True
    return changed


def import_departments(db: Session, allocator: AllocatorClient, identity: Identity, term: Term) -> dict[str, Any]:
    data = allocator.submissions(str(term.id))
    published = list(data.get("published") or [])
    if not published:
        raise ApiError(409, "NOTHING_PUBLISHED", "No department has published its teaching for this term yet.")
    changes = _Changes()
    departments: dict[str, Department] = {}
    for d in published:
        departments[d["code"]] = _department(db, identity, d["code"], d["name"])

    # Class rows, from every course the published units take (any department's).
    term_rows = list(db.scalars(select(ClassRow).where(ClassRow.term_id == term.id)))
    by_ref = {r.allocator_ref: r for r in term_rows if r.allocator_ref}
    by_label = {compact(r.label): r for r in term_rows}
    rows: dict[str, ClassRow] = {}
    for c in data.get("courses") or []:
        owner = departments.get(c["department_code"]) or _department(
            db, identity, c["department_code"], c["department_code"]
        )
        label = row_label(c["programme"], int(c["year"]), int(c["semester"]), c.get("sub_class") or "")
        row = by_ref.get(c["id"]) or by_label.get(compact(label))
        values = {
            "program_code": c["programme"],
            "study_year": int(c["year"]),
            "study_semester": int(c["semester"]),
            "sub_class": c.get("sub_class") or "",
            "label": label,
            "student_count": int(c["students"]),
            "department_id": owner.id,
            "allocator_ref": c["id"],
        }
        if row is None:
            row = ClassRow(term_id=term.id, unavailable=[], **values)
            db.add(row)
            changes.class_rows["added"].append(label)
        elif _set(row, values):
            changes.class_rows["changed"].append(label)
        by_label[compact(label)] = row
        rows[c["id"]] = row
    db.flush()

    offerings = list(db.scalars(select(UnitOffering).where(UnitOffering.term_id == term.id)))
    offering_by_ref = {o.allocator_ref: o for o in offerings if o.allocator_ref}
    offering_by_code = {compact(o.unit_code): o for o in offerings}
    for d in published:
        dept = departments[d["code"]]
        kept: set[uuid.UUID] = set()
        for u in d.get("units") or []:
            offering, what = _import_unit(db, term, dept, u, rows, offering_by_ref, offering_by_code)
            kept.add(offering.id)
            if what:
                changes.note(d["code"], what, u["code"])
        for o in offerings:
            if o.allocator_ref and o.owning_department_id == dept.id and o.id not in kept:
                for group in list(o.groups):
                    remove_group(db, o, group)
                db.delete(o)
                changes.note(d["code"], "removed", o.unit_code)
        db.flush()
        record = db.scalar(
            select(DepartmentImport).where(
                DepartmentImport.term_id == term.id, DepartmentImport.department_code == d["code"]
            )
        )
        if record is None:
            record = DepartmentImport(term_id=term.id, department_code=d["code"])
            db.add(record)
        record.published_at = _when(d["published_at"]) or datetime.now(UTC)
        record.imported_at = datetime.now(UTC)
        record.imported_by = identity.actor
        record.changes = changes.by_department.get(d["code"], {"added": [], "changed": [], "removed": []})

    # A published department's course it no longer has, and no unit takes, goes.
    published_ids = {dept.id for dept in departments.values()}
    used = set(db.scalars(select(OfferingClassRow.class_row_id)))
    for row in db.scalars(select(ClassRow).where(ClassRow.term_id == term.id, ClassRow.allocator_ref.is_not(None))):
        if row.department_id in published_ids and row.allocator_ref not in rows and row.id not in used:
            changes.class_rows["removed"].append(row.label)
            db.delete(row)
    summary = {
        "departments": [d["code"] for d in published],
        "class_rows": changes.class_rows,
        "units": changes.by_department,
    }
    audit(db, identity, "allocator.import", "term", str(term.id), None, summary)
    db.commit()
    return {
        **summary,
        "not_published": [{"code": d["code"], "name": d["name"]} for d in data.get("not_published") or []],
    }


def _import_unit(
    db: Session,
    term: Term,
    dept: Department,
    u: dict[str, Any],
    rows: dict[str, ClassRow],
    by_ref: dict[str, UnitOffering],
    by_code: dict[str, UnitOffering],
) -> tuple[UnitOffering, str | None]:
    """Creates or updates one offering and its groups; says whether it was 'added', 'changed' or neither."""
    offering = by_ref.get(u["id"]) or by_code.get(compact(u["code"]))
    room_type = u["room_type"] if u["room_type"] in ROOM_TYPES else "lecture_hall"
    values = {
        "unit_code": u["code"],
        "unit_name": u["title"],
        "owning_department_id": dept.id,
        "weekly_hours": int(u["weekly_hours"]),
        "session_length": int(u["class_length"]),
        "room_type": room_type,
        "source": "allocator",
        "allocator_ref": u["id"],
    }
    what: str | None = None
    if offering is None:
        offering = UnitOffering(term_id=term.id, **values)
        db.add(offering)
        what = "added"
    elif _set(offering, values):
        what = "changed"
    by_ref[u["id"]] = offering
    by_code[compact(u["code"])] = offering

    row_ids = [rows[c].id for c in u.get("course_ids") or [] if c in rows]
    if sorted(link.class_row_id for link in offering.class_rows) != sorted(row_ids):
        offering.class_rows = [OfferingClassRow(class_row_id=i) for i in row_ids]
        what = what or "changed"
    db.flush()

    existing_by_ref = {g.allocator_ref: g for g in offering.groups if g.allocator_ref}
    existing_by_label = {g.label: g for g in offering.groups}
    kept: set[uuid.UUID] = set()
    for g in u.get("groups") or []:
        group = existing_by_ref.get(g["id"]) or existing_by_label.get(g["label"])
        lecturer = g.get("lecturer") or {}
        staff = (lecturer.get("staff_number") or "").strip().upper() or None
        values = {
            "label": g["label"],
            "allocator_ref": g["id"],
            "lecturer_staff_number": staff,
            "lecturer_name": lecturer.get("name") or "",
            "lecture_hours": g.get("lecture_hours"),
            "practical_hours": g.get("practical_hours"),
            "cf_hours": g.get("cf_hours"),
        }
        members = sorted((rows[m["course_id"]].id, int(m["students"])) for m in g["members"] if m["course_id"] in rows)
        if group is None:
            group = Group(**values)
            offering.groups.append(group)
            what = what or "changed"
        elif _set(group, values):
            what = what or "changed"
        if sorted((m.class_row_id, m.students) for m in group.members) != members:
            group.members = [GroupClassRow(class_row_id=row_id, students=n) for row_id, n in members]
            what = what or "changed"
        db.flush()
        kept.add(group.id)
    for group in list(offering.groups):
        if group.id not in kept:
            remove_group(db, offering, group)
            what = what or "changed"
    return offering, what
