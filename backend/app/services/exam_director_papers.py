"""
What the Director enters on papers: student numbers and classes on any paper
that lacks them, and for the papers the Director uploaded while health and
nursing had their own letter, the invigilators and their removal.

Those departments now upload and publish in Smart Attendance like any other, so
no new papers come here. A paper already saved stays an ordinary paper until the
Director removes it or a department lists its unit (exam_setup). No department
names its invigilators, so the Director does.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import Identity
from app.errors import ApiError
from app.models import Department, ExamPaper, ExamPaperRow, ExamPlacement, Term
from app.services.allocator_import import upsert_class_rows
from app.services.setup import audit, compact, row_label


def _director_paper(db: Session, term: Term, paper_id: str) -> ExamPaper:
    papers = db.scalars(select(ExamPaper).where(ExamPaper.term_id == term.id))
    paper = next((p for p in papers if str(p.id) == paper_id and p.is_director_paper), None)
    if paper is None:
        raise ApiError(404, "NOT_FOUND", "No such paper of yours in this term.")
    return paper


def _course_id(programme: str, year: int, semester: int, stream: str) -> str:
    # As Smart Attendance names them: one class sitting several papers is one class row, whoever listed the paper.
    return f"listed:{compact(programme)}|{year}|{semester}|{compact(stream)}"


def set_rows(db: Session, identity: Identity, term: Term, paper_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """
    The paper's classes and numbers as the Director wants them. They stay when the
    papers are imported again, until the department sends a number for that class.
    A class left out doesn't sit the paper. Seats change on the next draft.
    """
    papers = db.scalars(select(ExamPaper).where(ExamPaper.term_id == term.id))
    paper = next((p for p in papers if str(p.id) == paper_id), None)
    if paper is None:
        raise ApiError(404, "NOT_FOUND", "No such paper in this term.")
    classes: dict[str, dict[str, Any]] = {}
    for r in rows:
        programme = r["programme"].strip().upper()
        if not programme:
            raise ApiError(422, "VALIDATION_ERROR", "Every class needs its programme code.")
        key = _course_id(programme, r["year"], r["semester"], r["stream"])
        if key in classes:
            raise ApiError(
                422,
                "VALIDATION_ERROR",
                f"{row_label(programme, r['year'], r['semester'], r['stream'])} is listed twice.",
            )
        classes[key] = {**r, "programme": programme}
    department = db.get(Department, paper.department_id)
    assert department is not None
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
    found = upsert_class_rows(
        db, identity, term, courses, {department.code: department}, {"added": [], "changed": [], "removed": []}
    )
    before = {r.class_row_id: r for r in paper.rows}
    wanted = {found[key].id: c for key, c in classes.items()}
    out = []
    for row_id, c in wanted.items():
        was = before.get(row_id)
        same = was is not None and was.students == c["students"]
        out.append(
            ExamPaperRow(
                class_row_id=row_id,
                students=c["students"],
                odel=was.odel if was else paper.sitting == "odel",
                guessed=was.guessed if was else False,  # a guess stays a guess: no hard rule holds it
                edited=was.edited if was and same else c["students"] > 0,
            )
        )
    paper.rows = out
    db.flush()
    audit(db, identity, "exam_paper.rows", "exam_paper", paper_id, None, {"rows": len(rows)})
    db.commit()
    return {"id": paper_id, "students": sum(c["students"] for c in classes.values())}


def remove(db: Session, identity: Identity, term: Term, paper_id: str) -> None:
    paper = _director_paper(db, term, paper_id)
    db.execute(delete(ExamPlacement).where(ExamPlacement.paper_id == paper.id))
    audit(db, identity, "exam_director_paper.delete", "exam_paper", paper_id, {"codes": paper.codes}, None)
    db.delete(paper)
    db.commit()


def set_invigilators(
    db: Session, identity: Identity, term: Term, paper_id: str, named: dict[str, dict[str, str]]
) -> dict[str, Any]:
    """Who invigilates: "" is the main invigilator, a room code that extra room's.

    SMARTTT checks the staff numbers on publishing.
    """
    paper = _director_paper(db, term, paper_id)
    paper.director_invigilators = {
        room: {"staff_number": v["staff_number"].strip().upper(), "name": v.get("name", "").strip()}
        for room, v in named.items()
        if v.get("staff_number", "").strip()
    }
    paper.invigilator_staff_number = paper.director_invigilators.get("", {}).get("staff_number")
    audit(db, identity, "exam_director_paper.invigilators", "exam_paper", paper_id, None, paper.director_invigilators)
    db.commit()
    return {"id": paper_id, "invigilators": paper.director_invigilators}
