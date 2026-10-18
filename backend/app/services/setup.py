"""
Opening a term: take a snapshot of SMARTTT's master data, then import the
term's class rows and unit offerings from it. Importing only ever adds what
is missing, so the Director's edits (sizes, hours, room types, groups) are
never overwritten by a later snapshot.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import Counter, defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Identity
from app.clients.smarttt import SmartttClient
from app.errors import ApiError
from app.models import AuditLog, ClassRow, Group, OfferingClassRow, Snapshot, Term, UnitOffering

ROOM_TYPES = ("lecture_hall", "lab", "seminar")


def audit(
    db: Session,
    identity: Identity,
    action: str,
    entity: str,
    entity_id: str,
    before: dict[str, Any] | None,
    after: dict[str, Any] | None,
) -> None:
    db.add(
        AuditLog(
            actor_account_id=identity.account_id,
            actor_name=identity.actor,
            action=action,
            entity=entity,
            entity_id=entity_id,
            before=before,
            after=after,
        )
    )


def get_term(db: Session, term_id: str) -> Term:
    try:
        term = db.get(Term, uuid.UUID(str(term_id)))
    except ValueError:
        term = None
    if term is None:
        raise ApiError(404, "NOT_FOUND", "No such term.")
    return term


def open_term(db: Session, smarttt: SmartttClient, identity: Identity, smarttt_term_id: str) -> Term:
    existing = db.scalar(select(Term).where(Term.smarttt_term_id == smarttt_term_id))
    if existing is not None:
        return existing
    term_data = next((t for t in smarttt.terms() if t["id"] == smarttt_term_id), None)
    if term_data is None:
        raise ApiError(404, "NOT_FOUND", "SMARTTT has no such term.")
    term = Term(
        smarttt_term_id=smarttt_term_id, academic_year=term_data["academic_year"], semester=int(term_data["semester"])
    )
    db.add(term)
    db.flush()
    audit(db, identity, "term.open", "term", str(term.id), None, {"smarttt_term_id": smarttt_term_id})
    db.commit()
    return term


def latest_snapshot(db: Session, term: Term) -> Snapshot | None:
    return db.scalar(select(Snapshot).where(Snapshot.term_id == term.id).order_by(Snapshot.created_at.desc()).limit(1))


def take_snapshot(db: Session, smarttt: SmartttClient, identity: Identity, term: Term) -> Snapshot:
    data = smarttt.snapshot(term.smarttt_term_id)
    canonical = json.dumps({k: v for k, v in data.items() if k != "taken_at"}, sort_keys=True, separators=(",", ":"))
    snapshot = Snapshot(
        term_id=term.id, data=data, sha256=hashlib.sha256(canonical.encode()).hexdigest(), created_by=identity.actor
    )
    db.add(snapshot)
    db.flush()
    audit(
        db,
        identity,
        "snapshot.take",
        "term",
        str(term.id),
        None,
        {"snapshot_id": str(snapshot.id), "sha256": snapshot.sha256},
    )
    db.commit()
    return snapshot


def snapshot_summary(snapshot: Snapshot) -> dict[str, Any]:
    d = snapshot.data
    return {
        "id": str(snapshot.id),
        "sha256": snapshot.sha256,
        "taken_at": snapshot.created_at.isoformat(),
        "taken_by": snapshot.created_by,
        "counts": {
            k: len(d.get(k) or [])
            for k in ("rooms", "departments", "lecturers", "programs", "units", "curricula", "class_sizes")
        },
        "published_version": (d.get("published") or {}).get("version"),
        "published_sessions": len((d.get("published") or {}).get("sessions") or []),
        "warnings": d.get("warnings") or [],
    }


def row_label(program_code: str, year: int, semester: int, sub_class: str) -> str:
    return f"{program_code} Y{year}S{semester}" + (f" ({sub_class})" if sub_class else "")


def compact(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def import_setup(db: Session, identity: Identity, term: Term) -> dict[str, Any]:
    """
    Adds the class rows and unit offerings the latest snapshot implies:
    - class rows from class sizes (programme/year/semester); where the
      published timetable splits a cohort into sub-classes, one row per
      sub-class instead, with its size left for the Director to enter;
    - offerings from the curricula of those class rows, then any unit taught
      in the published timetable that no curriculum covers;
    - weekly hours, session length and room type prefilled from the
      published timetable when the unit is in it, otherwise left to set.
    """
    snapshot = latest_snapshot(db, term)
    if snapshot is None:
        raise ApiError(409, "NO_SNAPSHOT", "Take a snapshot of SMARTTT first.")
    data = snapshot.data
    programs = {p["id"]: p for p in data["programs"]}
    units = {u["id"]: u for u in data["units"]}
    rooms = {r["id"]: r for r in data["rooms"]}
    published = (data.get("published") or {}).get("sessions") or []

    rows: dict[tuple[int, int, int, str], ClassRow] = {
        (r.smarttt_program_id, r.study_year, r.study_semester, r.sub_class): r
        for r in db.scalars(select(ClassRow).where(ClassRow.term_id == term.id))
    }
    unresolved: list[str] = []
    created_rows = 0

    sizes: dict[tuple[int, int], dict[int, int]] = defaultdict(dict)
    for size in data["class_sizes"]:
        sizes[(size["program_id"], size["study_year"])][size["study_semester"]] = size["students"]

    streams: dict[tuple[int, int], set[str]] = defaultdict(set)
    for session in published:
        for row in session["class_rows"]:
            if row.get("program_id") and row.get("stream"):
                streams[(row["program_id"], row["year_of_study"])].add(row["stream"])

    def add_row(program_id: int, year: int, semester: int, sub: str, students: int | None) -> None:
        nonlocal created_rows
        key = (program_id, year, semester, sub)
        if key in rows or program_id not in programs:
            return
        code = programs[program_id]["code"]
        row = ClassRow(
            term_id=term.id,
            smarttt_program_id=program_id,
            program_code=code,
            study_year=year,
            study_semester=semester,
            sub_class=sub,
            label=row_label(code, year, semester, sub),
            student_count=students,
            unavailable=[],
        )
        db.add(row)
        rows[key] = row
        created_rows += 1

    for (program_id, year), by_semester in sizes.items():
        for semester, students in by_semester.items():
            subs = streams.get((program_id, year))
            if subs:
                for sub in sorted(subs):
                    add_row(program_id, year, semester, sub, None)
            else:
                add_row(program_id, year, semester, "", students)
    db.flush()

    def semester_for(program_id: int, year: int, given: int | None) -> int | None:
        if given:
            return given
        known = sizes.get((program_id, year), {})
        if len(known) == 1:
            return next(iter(known))
        return None

    offerings = {o.smarttt_unit_id: o for o in db.scalars(select(UnitOffering).where(UnitOffering.term_id == term.id))}
    created_offerings = 0

    def offering_for(unit_id: int, source: str) -> UnitOffering | None:
        nonlocal created_offerings
        if unit_id in offerings:
            return offerings[unit_id]
        unit = units.get(unit_id)
        if unit is None:
            return None
        offering = UnitOffering(
            term_id=term.id,
            smarttt_unit_id=unit_id,
            unit_code=unit["code"],
            unit_name=unit["name"],
            owning_department_id=unit["department_id"],
            room_type="lecture_hall",
            source=source,
        )
        db.add(offering)
        offerings[unit_id] = offering
        created_offerings += 1
        return offering

    def link(offering: UnitOffering, row: ClassRow) -> None:
        if all(link.class_row_id != row.id for link in offering.class_rows):
            offering.class_rows.append(OfferingClassRow(class_row_id=row.id))

    for curriculum in data["curricula"]:
        matching = [
            r
            for (p, y, s, _sub), r in rows.items()
            if p == curriculum["program_id"] and y == curriculum["study_year"] and s == curriculum["study_semester"]
        ]
        for entry in curriculum["units"]:
            if not matching:
                continue
            offering = offering_for(entry["unit_id"], "curriculum")
            if offering is not None:
                for row in matching:
                    link(offering, row)

    # Units taught in the published timetable: prefill their weekly pattern and
    # offer those no curriculum covers.
    by_unit: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for session in published:
        by_unit[session["unit_id"]].append(session)
    for unit_id, sessions in by_unit.items():
        offering = offering_for(unit_id, "published")
        if offering is None:
            continue
        for session in sessions:
            for r in session["class_rows"]:
                if not r.get("program_id"):
                    continue
                row_semester = semester_for(r["program_id"], r["year_of_study"], r.get("study_semester"))
                if row_semester is None:
                    unresolved.append(
                        f"{units[unit_id]['code']}: can't tell the study semester of programme "
                        f"{programs.get(r['program_id'], {}).get('code', r['program_id'])} "
                        f"year {r['year_of_study']}"
                    )
                    continue
                row = rows.get((r["program_id"], r["year_of_study"], row_semester, r.get("stream") or ""))
                if row is None:
                    add_row(r["program_id"], r["year_of_study"], row_semester, r.get("stream") or "", None)
                    db.flush()
                    row = rows.get((r["program_id"], r["year_of_study"], row_semester, r.get("stream") or ""))
                if row is not None:
                    link(offering, row)
        if offering.weekly_hours is None:
            per_section: dict[str, int] = defaultdict(int)
            lengths: Counter[int] = Counter()
            types: Counter[str] = Counter()
            for session in sessions:
                length = _hours(session["start_time"], session["end_time"])
                per_section[session["section_key"]] += length
                lengths[length] += 1
                types[(rooms.get(session["room_id"]) or {}).get("room_type", "lecture_hall")] += 1
            offering.weekly_hours = max(per_section.values())
            offering.session_length = lengths.most_common(1)[0][0]
            offering.room_type = types.most_common(1)[0][0]

    audit(
        db,
        identity,
        "setup.import",
        "term",
        str(term.id),
        None,
        {"class_rows": created_rows, "offerings": created_offerings, "snapshot_id": str(snapshot.id)},
    )
    db.commit()
    return {
        "class_rows_created": created_rows,
        "offerings_created": created_offerings,
        "unresolved": sorted(set(unresolved))[:200],
    }


def _hours(start: str, end: str) -> int:
    sh, sm = map(int, start.split(":"))
    eh, em = map(int, end.split(":"))
    return max(1, round(((eh * 60 + em) - (sh * 60 + sm)) / 60))


def readiness(db: Session, term: Term) -> dict[str, Any]:
    """What still has to be set before a run, in the Director's terms."""
    snapshot = latest_snapshot(db, term)
    problems: list[dict[str, str]] = []
    if snapshot is None:
        return {"ready": False, "problems": [{"code": "no_snapshot", "message": "Take a snapshot of SMARTTT."}]}
    rows = {r.id: r for r in db.scalars(select(ClassRow).where(ClassRow.term_id == term.id))}
    offerings = list(db.scalars(select(UnitOffering).where(UnitOffering.term_id == term.id)))
    biggest: dict[str, int] = defaultdict(int)
    for room in snapshot.data["rooms"]:
        if room["status"] == "active":
            biggest[room["room_type"]] = max(biggest[room["room_type"]], room["capacity"])

    for o in offerings:
        if not o.weekly_hours or not o.session_length:
            problems.append(
                {
                    "code": "offering_hours",
                    "entity": o.unit_code,
                    "message": f"{o.unit_code}: set weekly hours and session length.",
                }
            )
        if not o.groups:
            problems.append(
                {
                    "code": "offering_groups",
                    "entity": o.unit_code,
                    "message": f"{o.unit_code}: no groups yet; propose or add them.",
                }
            )
        for g in o.groups:
            if not g.members:
                problems.append(
                    {
                        "code": "group_empty",
                        "entity": o.unit_code,
                        "message": f"{o.unit_code} {g.label or '(whole class)'} has no class rows.",
                    }
                )
            if g.student_count > biggest.get(o.room_type, 0):
                problems.append(
                    {
                        "code": "group_too_big",
                        "entity": o.unit_code,
                        "message": f"{o.unit_code} {g.label or ''} has {g.student_count} students; the "
                        f"largest {o.room_type.replace('_', ' ')} seats "
                        f"{biggest.get(o.room_type, 0)}.",
                    }
                )
    used_rows = {link.class_row_id for o in offerings for link in o.class_rows}
    for row_id in used_rows:
        row = rows.get(row_id)
        if row is not None and row.student_count is None:
            problems.append(
                {"code": "row_size", "entity": row.label, "message": f"{row.label}: enter the number of students."}
            )
    return {
        "ready": not problems,
        "problems": problems[:500],
        "problem_count": len(problems),
        "snapshot": snapshot_summary(snapshot),
    }


def class_row_dict(row: ClassRow) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "label": row.label,
        "program_id": row.smarttt_program_id,
        "program_code": row.program_code,
        "study_year": row.study_year,
        "study_semester": row.study_semester,
        "sub_class": row.sub_class,
        "student_count": row.student_count,
        "unavailable": row.unavailable,
    }


def offering_dict(o: UnitOffering, rows: dict[Any, ClassRow]) -> dict[str, Any]:
    return {
        "id": str(o.id),
        "unit_id": o.smarttt_unit_id,
        "unit_code": o.unit_code,
        "unit_name": o.unit_name,
        "department_id": o.owning_department_id,
        "weekly_hours": o.weekly_hours,
        "session_length": o.session_length,
        "room_type": o.room_type,
        "source": o.source,
        "class_row_ids": [str(link.class_row_id) for link in o.class_rows],
        "class_rows": sorted(rows[link.class_row_id].label for link in o.class_rows if link.class_row_id in rows),
        "groups": [group_dict(g, rows) for g in o.groups],
    }


def group_dict(g: Group, rows: dict[Any, ClassRow]) -> dict[str, Any]:
    return {
        "id": str(g.id),
        "label": g.label,
        "student_count": g.student_count,
        "members": [
            {
                "class_row_id": str(m.class_row_id),
                "label": rows[m.class_row_id].label if m.class_row_id in rows else None,
                "students": m.students,
            }
            for m in g.members
        ],
    }
