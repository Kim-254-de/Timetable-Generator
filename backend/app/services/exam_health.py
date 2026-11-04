"""
Health and nursing papers the Director uploads: the moderation letter as Word,
read and reviewed like a department's list in Smart Attendance, kept here.

Each paper's classes are those taking its units on SMARTTT's master timetable,
and those of the students who synced them; numbers are who synced, and the
Director corrects any, adds a class or removes one (kept when SMARTTT is read
again). No department names their invigilators, so the Director does. A unit a
department already listed isn't entered twice: its paper is marked as health.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import Identity
from app.clients.smarttt import SmartttClient, SmartttError
from app.errors import ApiError
from app.exam_solver.model import HEALTH
from app.models import DIRECTOR_REF, ClassRow, Department, ExamPaper, ExamPaperRow, ExamPlacement, Term
from app.services.allocator_import import _department, row_label, upsert_class_rows
from app.services.exam_list_read import read_exam_list
from app.services.setup import audit, compact

DEPARTMENT_CODE = "HLTH"
DEPARTMENT_NAME = "Health Sciences and Nursing"


def _paper_key(codes: list[str], sitting: str) -> str:
    return "/".join(sorted(compact(c) for c in codes)) + "|" + sitting


def _course_id(programme: str, year: int, semester: int, stream: str) -> str:
    # As Smart Attendance names them: one class sitting several papers is one class row, whoever listed the paper.
    return f"listed:{compact(programme)}|{year}|{semester}|{compact(stream)}"


def _enrolment(smarttt: SmartttClient, codes: list[str]) -> dict[str, Any]:
    if not codes:
        return {"available": True, "units": {}, "unknown": set(), "reason": None}
    try:
        data = smarttt.unit_enrolment(list(dict.fromkeys(codes)))
    except SmartttError as down:
        return {"available": False, "units": {}, "unknown": set(), "reason": getattr(down, "message", None) or "SMARTTT can't be reached."}
    return {
        "available": True,
        "units": {compact(k): v for k, v in (data.get("units") or {}).items()},
        "unknown": {compact(c) for c in data.get("unknown") or []},
        "reason": None,
    }


def _classes(enrolment: dict[str, Any], codes: list[str], sitting: str, odel_twin: bool) -> dict[str, dict[str, Any]]:
    """Who sits a paper of these codes, by class. A class taking two of its codes counts once, at the larger number."""
    out: dict[str, dict[str, Any]] = {}
    for code in codes:
        for r in (enrolment["units"].get(compact(code)) or {}).get("rows") or []:
            odel = r.get("sitting") == "odel"
            if (sitting == "odel" and not odel) or (sitting != "odel" and odel and odel_twin):
                continue
            year = max(1, min(10, int(r.get("year_of_study") or 1)))
            semester = max(1, min(3, int(r.get("study_semester") or 1)))
            stream = r.get("stream") or ("ODEL" if odel else "")
            key = _course_id(r["program"], year, semester, stream)
            students = int(r.get("students") or 0)
            if key not in out or out[key]["students"] < students:
                out[key] = {"programme": r["program"], "year": year, "semester": semester, "stream": stream, "students": students, "odel": odel}
    return out


def _decode(file: str) -> bytes:
    try:
        return base64.b64decode(file, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ApiError(422, "VALIDATION_ERROR", "That file could not be read.") from exc


def _papers(db: Session, term: Term) -> list[ExamPaper]:
    return list(db.scalars(select(ExamPaper).where(ExamPaper.term_id == term.id)))


def review(db: Session, smarttt: SmartttClient, term: Term, file: str) -> dict[str, Any]:
    """The uploaded document read and checked against SMARTTT and the papers already here. Nothing is stored."""
    entries = read_exam_list(_decode(file))
    enrolment = _enrolment(smarttt, [c for e in entries for c in e.codes])
    papers = _papers(db, term)
    departments = {d.id: d.code for d in db.scalars(select(Department))}
    seen: dict[str, int] = {}
    pending = {_paper_key(e.codes, e.sitting) for e in entries}
    out = []
    for e in entries:
        key = _paper_key(e.codes, e.sitting)
        duplicate_of = seen.get(key)
        seen.setdefault(key, e.line)
        mine = {compact(c) for c in e.codes}
        overlapping = [p for p in papers if p.sitting == e.sitting and mine & {compact(c) for c in p.codes}]
        twin = any(any(k.split("|")[0] and compact(c) in k.split("|")[0].split("/") for c in e.codes) and k.endswith("|odel") for k in pending)
        classes = _classes(enrolment, e.codes, e.sitting, twin)
        out.append(
            {
                "line": e.line,
                "codes": e.codes,
                "title": e.title,
                "section": e.section,
                "sitting": e.sitting,
                "students": sum(c["students"] for c in classes.values()) if enrolment["available"] else None,
                "classes": sorted(
                    row_label(c["programme"], c["year"], c["semester"], c["stream"]) for c in classes.values()
                ),
                "unknown_codes": [c for c in e.codes if compact(c) in enrolment["unknown"]],
                "duplicate_of": duplicate_of,
                "department_lists": sorted({departments.get(p.department_id, "?") for p in overlapping if not p.is_director_paper}),
                "already_here": any(p.is_director_paper for p in overlapping),
            }
        )
    return {
        "entries": out,
        "smarttt": {"available": enrolment["available"], "reason": enrolment["reason"]},
        "summary": {
            "papers": sum(1 for x in out if x["duplicate_of"] is None),
            "duplicates": sum(1 for x in out if x["duplicate_of"] is not None),
            "unknown": sum(1 for x in out if x["unknown_codes"]),
            "no_classes": sum(1 for x in out if x["students"] == 0 and not x["classes"]),
        },
    }


def _class_rows(
    db: Session, identity: Identity, term: Term, classes: dict[str, dict[str, Any]], department: Department
) -> dict[str, ClassRow]:
    courses = [
        {
            "id": key,
            "department_code": department.code,
            "programme": c["programme"],
            "year": c["year"],
            "semester": c["semester"],
            "sub_class": c["stream"],
            "students": c["students"],
        }
        for key, c in classes.items()
    ]
    return upsert_class_rows(db, identity, term, courses, {department.code: department}, {"added": [], "changed": [], "removed": []})


def _set_rows(
    db: Session,
    identity: Identity,
    term: Term,
    paper: ExamPaper,
    fresh: dict[str, dict[str, Any]],
    department: Department,
) -> None:
    """SMARTTT's classes over the rows the paper has: a row the Director set keeps its number."""
    refs = {r.id: r.allocator_ref for r in db.scalars(select(ClassRow).where(ClassRow.term_id == term.id))}
    kept = {refs.get(r.class_row_id): r for r in paper.rows if r.edited}
    rows = _class_rows(db, identity, term, {k: v for k, v in fresh.items() if k not in kept}, department)
    paper.rows = [
        ExamPaperRow(class_row_id=r.class_row_id, students=r.students, odel=r.odel, guessed=False, edited=True) for r in kept.values()
    ] + [
        ExamPaperRow(class_row_id=rows[k].id, students=c["students"], odel=c["odel"], guessed=False, edited=False)
        for k, c in fresh.items()
        if k not in kept
    ]


def save(db: Session, smarttt: SmartttClient, identity: Identity, term: Term, wanted: list[dict[str, Any]]) -> dict[str, Any]:
    """The reviewed list. A paper here already gets its new title; a unit a department listed is marked as health."""
    department = _department(db, identity, DEPARTMENT_CODE, DEPARTMENT_NAME)
    papers = _papers(db, term)
    cleaned: dict[str, dict[str, Any]] = {}
    for p in wanted:
        codes = list(dict.fromkeys(" ".join(c.upper().split()) for c in p["codes"] if c.strip()))
        if not codes:
            raise ApiError(422, "VALIDATION_ERROR", "Every paper needs a unit code.")
        if not p["title"].strip():
            raise ApiError(422, "VALIDATION_ERROR", f"Give {'/'.join(codes)} a title.")
        sitting = "odel" if p.get("sitting") == "odel" else "regular"
        cleaned[_paper_key(codes, sitting)] = {"codes": codes, "title": p["title"].strip()[:255], "sitting": sitting}
    enrolment = _enrolment(smarttt, [c for p in cleaned.values() for c in p["codes"]])
    keys = list(cleaned)
    created, updated, marked = 0, 0, []
    for key, p in cleaned.items():
        mine = {compact(c) for c in p["codes"]}
        overlapping = [x for x in papers if x.sitting == p["sitting"] and mine & {compact(c) for c in x.codes}]
        own = next((x for x in overlapping if x.is_director_paper and _paper_key(x.codes, x.sitting) == key), None)
        listed = [x for x in overlapping if not x.is_director_paper]
        if listed and own is None:
            for x in listed:
                x.category_override = HEALTH
                marked.append(x.label)
            continue
        twin = any(k.endswith("|odel") and mine & set(k.split("|")[0].split("/")) for k in keys) or any(
            x.sitting == "odel" and mine & {compact(c) for c in x.codes} for x in papers
        )
        fresh = _classes(enrolment, p["codes"], p["sitting"], twin)
        if own is None:
            own = ExamPaper(
                term_id=term.id,
                allocator_ref=f"{DIRECTOR_REF}{uuid.uuid4().hex}",
                department_id=department.id,
                codes=p["codes"],
                title=p["title"],
                sitting=p["sitting"],
                category_override=HEALTH,
                examiner_name="",
                notes="",
                director_invigilators={},
            )
            db.add(own)
            papers.append(own)
            db.flush()
            created += 1
        else:
            own.title = p["title"]
            updated += 1
        if enrolment["available"]:
            _set_rows(db, identity, term, own, fresh, department)
    result = {"created": created, "updated": updated, "marked_health": sorted(marked), "smarttt": {"available": enrolment["available"], "reason": enrolment["reason"]}}
    audit(db, identity, "exam_health.save", "term", str(term.id), None, {k: result[k] for k in ("created", "updated", "marked_health")})
    db.commit()
    return result


def recount(db: Session, smarttt: SmartttClient, identity: Identity, term: Term) -> dict[str, Any]:
    """SMARTTT read again for the Director's papers; what the Director set stays."""
    mine = [p for p in _papers(db, term) if p.is_director_paper]
    if not mine:
        return {"papers": 0, "available": True, "reason": None}
    enrolment = _enrolment(smarttt, [c for p in mine for c in p.codes])
    if not enrolment["available"]:
        return {"papers": 0, "available": False, "reason": enrolment["reason"]}
    department = _department(db, identity, DEPARTMENT_CODE, DEPARTMENT_NAME)
    all_papers = _papers(db, term)
    for p in mine:
        codes = {compact(c) for c in p.codes}
        twin = any(x.sitting == "odel" and codes & {compact(c) for c in x.codes} for x in all_papers)
        _set_rows(db, identity, term, p, _classes(enrolment, p.codes, p.sitting, twin), department)
    db.commit()
    return {"papers": len(mine), "available": True, "reason": None}


def _director_paper(db: Session, term: Term, paper_id: str) -> ExamPaper:
    paper = next((p for p in _papers(db, term) if str(p.id) == paper_id and p.is_director_paper), None)
    if paper is None:
        raise ApiError(404, "NOT_FOUND", "No such uploaded paper in this term.")
    return paper


def set_rows(db: Session, identity: Identity, term: Term, paper_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The paper's classes and numbers as the Director wants them. A class left out doesn't sit it, and stays out."""
    paper = _director_paper(db, term, paper_id)
    department = _department(db, identity, DEPARTMENT_CODE, DEPARTMENT_NAME)
    classes: dict[str, dict[str, Any]] = {}
    for r in rows:
        programme = r["programme"].strip().upper()
        if not programme:
            raise ApiError(422, "VALIDATION_ERROR", "Every class needs its programme code.")
        key = _course_id(programme, r["year"], r["semester"], r["stream"])
        if key in classes:
            raise ApiError(422, "VALIDATION_ERROR", f"{row_label(programme, r['year'], r['semester'], r['stream'])} is listed twice.")
        classes[key] = {**r, "programme": programme, "odel": paper.sitting == "odel"}
    by_key = _class_rows(db, identity, term, classes, department)
    refs = {x.id: x.allocator_ref for x in db.scalars(select(ClassRow).where(ClassRow.term_id == term.id))}
    before = {refs.get(r.class_row_id): r for r in paper.rows}
    out = [
        ExamPaperRow(
            class_row_id=by_key[k].id,
            students=c["students"],
            odel=c["odel"],
            guessed=False,
            # A class SMARTTT named, left at its number, still follows SMARTTT.
            edited=k not in before or before[k].edited or before[k].students != c["students"],
        )
        for k, c in classes.items()
    ]
    out += [
        ExamPaperRow(class_row_id=r.class_row_id, students=0, odel=r.odel, guessed=False, edited=True)
        for k, r in before.items()
        if k not in classes
    ]
    paper.rows = out
    audit(db, identity, "exam_health.rows", "exam_paper", paper_id, None, {"rows": len(rows)})
    db.commit()
    return {"id": paper_id, "students": paper.students}


def remove(db: Session, identity: Identity, term: Term, paper_id: str) -> None:
    paper = _director_paper(db, term, paper_id)
    db.execute(delete(ExamPlacement).where(ExamPlacement.paper_id == paper.id))
    audit(db, identity, "exam_health.delete", "exam_paper", paper_id, {"codes": paper.codes}, None)
    db.delete(paper)
    db.commit()


def set_invigilators(db: Session, identity: Identity, term: Term, paper_id: str, named: dict[str, dict[str, str]]) -> dict[str, Any]:
    """Who invigilates: "" is the main invigilator, a room code that extra room's. SMARTTT checks the staff numbers on publishing."""
    paper = _director_paper(db, term, paper_id)
    paper.director_invigilators = {
        room: {"staff_number": v["staff_number"].strip().upper(), "name": v.get("name", "").strip()}
        for room, v in named.items()
        if v.get("staff_number", "").strip()
    }
    paper.invigilator_staff_number = paper.director_invigilators.get("", {}).get("staff_number")
    audit(db, identity, "exam_health.invigilators", "exam_paper", paper_id, None, paper.director_invigilators)
    db.commit()
    return {"id": paper_id, "invigilators": paper.director_invigilators}
