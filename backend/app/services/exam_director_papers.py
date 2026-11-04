"""
Papers the Director uploaded while health and nursing had their own letter.

Health and nursing departments now upload and publish in Smart Attendance like
any other, so nothing new comes here. A paper already saved stays an ordinary
paper until the Director removes it or a department lists its unit (exam_setup).
No department names its invigilators, so the Director does.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import Identity
from app.errors import ApiError
from app.models import ExamPaper, ExamPlacement, Term
from app.services.setup import audit


def _director_paper(db: Session, term: Term, paper_id: str) -> ExamPaper:
    papers = db.scalars(select(ExamPaper).where(ExamPaper.term_id == term.id))
    paper = next((p for p in papers if str(p.id) == paper_id and p.is_director_paper), None)
    if paper is None:
        raise ApiError(404, "NOT_FOUND", "No such paper of yours in this term.")
    return paper


def remove(db: Session, identity: Identity, term: Term, paper_id: str) -> None:
    paper = _director_paper(db, term, paper_id)
    db.execute(delete(ExamPlacement).where(ExamPlacement.paper_id == paper.id))
    audit(db, identity, "exam_director_paper.delete", "exam_paper", paper_id, {"codes": paper.codes}, None)
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
    audit(db, identity, "exam_director_paper.invigilators", "exam_paper", paper_id, None, paper.director_invigilators)
    db.commit()
    return {"id": paper_id, "invigilators": paper.director_invigilators}
