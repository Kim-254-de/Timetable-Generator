"""
The exam period, rooms' exam seats, and importing the papers departments published.

The exam period sits on the term beside its teaching timetable: its dates,
the weekdays used, days off, and the sessions of each day. Rooms are the
teaching rooms: exam seats are capacity x the term's spacing (0.9 unless
changed), unless a room has its own number; a room can be kept out of exams.
"""

from __future__ import annotations

import math
import re
from datetime import date, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import Identity
from app.clients.teaching import TeachingClient
from app.errors import ApiError
from app.exam_solver.model import CATEGORIES, REGULAR, ExamRoom
from app.models import (
    ClassRow,
    Department,
    ExamPaper,
    ExamPaperRow,
    ExamPlacement,
    ExamPractical,
    Room,
    Term,
)
from app.services.allocator_import import _department, upsert_class_rows
from app.services.setup import audit

HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def exam_days(term: Term) -> list[date]:
    """The exam period's days: its dates, on the weekdays used, less days off."""
    if term.exam_start is None or term.exam_end is None:
        return []
    off = set(term.exam_days_off or [])
    weekdays = set(term.exam_weekdays or [])
    out, day = [], term.exam_start
    while day <= term.exam_end:
        if day.weekday() in weekdays and day.isoformat() not in off:
            out.append(day)
        day += timedelta(days=1)
    return out


def exam_seats(room: Room, spacing: float) -> int:
    return room.exam_seats if room.exam_seats is not None else math.floor(room.capacity * spacing)


def exam_rooms(db: Session, term: Term) -> list[ExamRoom]:
    rooms = db.scalars(select(Room).where(Room.active.is_(True)).order_by(Room.code))
    return [
        ExamRoom(id=r.id, code=r.code, block=r.block, seats=exam_seats(r, term.exam_spacing), health=r.health_unit)
        for r in rooms
        if r.used_for_exams and exam_seats(r, term.exam_spacing) > 0
    ]


def period_dict(db: Session, term: Term) -> dict[str, Any]:
    days = exam_days(term)
    rooms = exam_rooms(db, term)
    return {
        "exam_start": term.exam_start.isoformat() if term.exam_start else None,
        "exam_end": term.exam_end.isoformat() if term.exam_end else None,
        "exam_weekdays": term.exam_weekdays,
        "exam_days_off": term.exam_days_off,
        "exam_sessions": term.exam_sessions,
        "exam_spacing": term.exam_spacing,
        "exam_health_prefixes": term.exam_health_prefixes or [],
        "health_seats": sum(r.seats for r in rooms if r.health),
        "days": [d.isoformat() for d in days],
        "slots": len(days) * len(term.exam_sessions or []),
        "rooms": len(rooms),
        "exam_seats": sum(r.seats for r in rooms),
    }


def update_period(db: Session, identity: Identity, term: Term, fields: dict[str, Any]) -> dict[str, Any]:
    start = fields.get("exam_start", term.exam_start)
    end = fields.get("exam_end", term.exam_end)
    if start and end and end < start:
        raise ApiError(422, "VALIDATION_ERROR", "The exam period must end after it starts.")
    if start and end and (end - start).days > 120:
        raise ApiError(422, "VALIDATION_ERROR", "An exam period is at most four months.")
    sessions = fields.get("exam_sessions")
    if sessions is not None:
        if not sessions:
            raise ApiError(422, "VALIDATION_ERROR", "An exam day needs at least one session.")
        previous = "00:00"
        for s in sessions:
            if not HHMM.match(s["start"]) or not HHMM.match(s["end"]) or not s["start"] < s["end"]:
                raise ApiError(422, "VALIDATION_ERROR", "Each session needs a start and a later end (HH:MM).")
            if s["start"] < previous:
                raise ApiError(422, "VALIDATION_ERROR", "Sessions must be in order and not overlap.")
            previous = s["end"]
    before = period_dict(db, term)
    for key in ("exam_start", "exam_end", "exam_weekdays", "exam_sessions", "exam_spacing"):
        if key in fields:
            setattr(term, key, fields[key])
    if "exam_health_prefixes" in fields:
        term.exam_health_prefixes = sorted(
            {p.strip().upper() for p in fields["exam_health_prefixes"] or [] if p.strip()}
        )
    if "exam_days_off" in fields:
        term.exam_days_off = sorted({d.isoformat() if isinstance(d, date) else str(d) for d in fields["exam_days_off"]})
    after = period_dict(db, term)
    audit(db, identity, "term.exam_period", "term", str(term.id), before, after)
    db.commit()
    return after


# -- importing published papers ----------------------------------------------------------------


def import_exams(db: Session, teaching: TeachingClient, identity: Identity, term: Term) -> dict[str, Any]:
    """
    Brings in every department's published exam papers (creating or updating
    by Attendance's ids) and practicals. A published department's paper it
    no longer has is removed, with its places in the drafts.
    """
    data = teaching.exams(str(term.id))
    published = list(data.get("published") or [])
    if not published:
        raise ApiError(409, "NOTHING_PUBLISHED", "No department has published its exam papers for this term yet.")
    departments: dict[str, Department] = {d["code"]: _department(db, identity, d["code"], d["name"]) for d in published}
    row_changes: dict[str, list[str]] = {"added": [], "changed": [], "removed": []}
    rows = upsert_class_rows(db, identity, term, data.get("courses") or [], departments, row_changes)

    existing = {p.allocator_ref: p for p in db.scalars(select(ExamPaper).where(ExamPaper.term_id == term.id))}
    practicals = {p.allocator_ref: p for p in db.scalars(select(ExamPractical).where(ExamPractical.term_id == term.id))}
    added: list[str] = []
    changed: list[str] = []
    removed: list[str] = []
    for d in published:
        dept = departments[d["code"]]
        kept: set[str] = set()
        for p in d.get("papers") or []:
            kept.add(p["id"])
            sitting = sorted(
                (rows[r["course_id"]].id, int(r["students"]), r.get("mode") == "odel", bool(r.get("guessed")))
                for r in p.get("rows") or []
                if r["course_id"] in rows
            )
            examiner = p.get("examiner") or {}
            invigilator = p.get("invigilator") or {}
            values = {
                "department_id": dept.id,
                "codes": list(p["codes"]),
                "title": p["title"],
                "examiner_staff_number": (examiner.get("staff_number") or "").strip().upper() or None,
                "examiner_name": examiner.get("name") or "",
                "notes": p.get("notes") or "",
                "sitting": "odel" if p.get("sitting") == "odel" else "regular",
                "invigilator_staff_number": (invigilator.get("staff_number") or "").strip().upper() or None,
            }
            paper = existing.get(p["id"])
            label = "/".join(p["codes"]) + (" (ODEL)" if values["sitting"] == "odel" else "")
            if paper is None:
                paper = ExamPaper(term_id=term.id, allocator_ref=p["id"], **values)
                db.add(paper)
                existing[p["id"]] = paper
                added.append(label)
            else:
                differs = any(getattr(paper, k) != v for k, v in values.items())
                had = sorted((r.class_row_id, r.students, r.odel, r.guessed) for r in paper.rows)
                differs = differs or had != sitting
                if differs:
                    changed.append(label)
                for k, v in values.items():
                    setattr(paper, k, v)
            paper.rows = [ExamPaperRow(class_row_id=i, students=n, odel=o, guessed=g) for i, n, o, g in sitting]
        for ref, paper in list(existing.items()):
            if paper.department_id == dept.id and ref not in kept and not paper.is_director_paper:
                db.execute(delete(ExamPlacement).where(ExamPlacement.paper_id == paper.id))
                db.delete(paper)
                removed.append(paper.label)
                del existing[ref]
        kept_practicals: set[str] = set()
        for pr in d.get("practicals") or []:
            kept_practicals.add(pr["id"])
            values = {
                "department_id": dept.id,
                "codes": list(pr["codes"]),
                "title": pr["title"],
                "date": date.fromisoformat(pr["date"]),
                "start_time": pr["start_time"],
                "end_time": pr["end_time"],
            }
            found = practicals.get(pr["id"])
            if found is None:
                db.add(ExamPractical(term_id=term.id, allocator_ref=pr["id"], **values))
            else:
                for k, v in values.items():
                    setattr(found, k, v)
        for ref, found in list(practicals.items()):
            if found.department_id == dept.id and ref not in kept_practicals:
                db.delete(found)
    summary = {
        "departments": [d["code"] for d in published],
        "papers": {"added": sorted(added), "changed": sorted(changed), "removed": sorted(removed)},
        "class_rows": row_changes,
    }
    audit(db, identity, "allocator.import_exams", "term", str(term.id), None, summary)
    db.commit()
    return {
        **summary,
        "not_published": [{"code": d["code"], "name": d["name"]} for d in data.get("not_published") or []],
    }


def papers_of(db: Session, term: Term) -> list[dict[str, Any]]:
    row_of = {r.id: r for r in db.scalars(select(ClassRow).where(ClassRow.term_id == term.id))}
    labels = {i: r.label for i, r in row_of.items()}
    departments = {d.id: d.code for d in db.scalars(select(Department))}
    papers = list(db.scalars(select(ExamPaper).where(ExamPaper.term_id == term.id)))
    from app.services.exam_runs import build

    problem = build(db, term)
    category = {p.id: problem.category(p) for p in problem.papers}
    out = [
        {
            "id": str(p.id),
            "category": category.get(str(p.id), REGULAR),
            "category_override": p.category_override,
            "director_paper": p.is_director_paper,
            "codes": p.label,
            "title": p.title,
            "department": departments.get(p.department_id, "?"),
            "examiner": p.examiner_name,
            "students": p.students,
            "rows": sorted(
                (
                    {
                        "label": labels.get(r.class_row_id, "?"),
                        "students": r.students,
                        "odel": r.odel,
                        "programme": row_of[r.class_row_id].program_code if r.class_row_id in row_of else "",
                        "year": row_of[r.class_row_id].study_year if r.class_row_id in row_of else 1,
                        "semester": row_of[r.class_row_id].study_semester if r.class_row_id in row_of else 1,
                        "stream": row_of[r.class_row_id].sub_class if r.class_row_id in row_of else "",
                    }
                    for r in p.rows
                    if r.students or not r.edited
                ),
                key=lambda r: str(r["label"]),
            ),
        }
        for p in papers
    ]
    return sorted(out, key=lambda p: p["codes"])


def set_category(db: Session, identity: Identity, term: Term, paper_id: str, category: str | None) -> dict[str, Any]:
    """The Director's choice of a paper's category; None goes back to working it out."""
    if category is not None and category not in CATEGORIES:
        raise ApiError(422, "VALIDATION_ERROR", f"A paper is {', '.join(CATEGORIES)}.")
    paper = next(
        (p for p in db.scalars(select(ExamPaper).where(ExamPaper.term_id == term.id)) if str(p.id) == paper_id), None
    )
    if paper is None:
        raise ApiError(404, "NOT_FOUND", "No such paper in this term.")
    before = paper.category_override
    paper.category_override = category
    audit(db, identity, "exam_paper.category", "exam_paper", paper_id, {"category": before}, {"category": category})
    db.commit()
    return {"id": paper_id, "category_override": category}


def practicals_of(db: Session, term: Term) -> list[dict[str, Any]]:
    departments = {d.id: d.code for d in db.scalars(select(Department))}
    found = db.scalars(
        select(ExamPractical)
        .where(ExamPractical.term_id == term.id)
        .order_by(ExamPractical.date, ExamPractical.start_time)
    )
    return [
        {
            "codes": "/".join(p.codes),
            "title": p.title,
            "department": departments.get(p.department_id, "?"),
            "date": p.date.isoformat(),
            "start_time": p.start_time,
            "end_time": p.end_time,
        }
        for p in found
    ]
