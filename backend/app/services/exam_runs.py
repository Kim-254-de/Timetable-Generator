"""
Exam solver runs: the term's papers, exam period and rooms as the exam
solver's problem, solved in the background like teaching runs (the same
`runs` table, mode `exam`), each success saved as a new exam draft.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import Identity
from app.config import get_settings
from app.errors import ApiError
from app.exam_solver.model import ExamProblem, ExamWeights, Paper, Sitting
from app.exam_solver.solve import solve
from app.models import ClassRow, ExamDraft, ExamPaper, ExamPlacement, ExamSeat, Run, RunMode, RunStatus, Term, utcnow
from app.services.exam_setup import exam_days, exam_rooms
from app.services.setup import audit, latest_snapshot


def build(db: Session, term: Term, base: ExamDraft | None = None, weights: ExamWeights | None = None) -> ExamProblem:
    """The problem; with a base draft, its pinned papers stay and the others start where they were."""
    days = exam_days(term)
    sessions = len(term.exam_sessions or [])
    placed = {pl.paper_id: pl for pl in base.placements} if base is not None else {}

    def slot_of(pl: ExamPlacement) -> int | None:
        if pl.day not in days or not 0 <= pl.session < sessions:
            return None
        return days.index(pl.day) * sessions + pl.session

    papers = []
    for p in db.scalars(select(ExamPaper).where(ExamPaper.term_id == term.id).order_by(ExamPaper.id)):
        pl = placed.get(p.id)
        slot = slot_of(pl) if pl is not None else None
        papers.append(
            Paper(
                id=str(p.id),
                label=p.label,
                rows=tuple(Sitting(str(r.class_row_id), r.students, r.odel) for r in p.rows),
                pinned=slot if pl is not None and pl.pinned else None,
                previous=slot,
            )
        )
    labels = {str(r.id): r.label for r in db.scalars(select(ClassRow).where(ClassRow.term_id == term.id))}
    return ExamProblem(
        papers=papers,
        days=days,
        sessions=sessions,
        rooms=exam_rooms(db, term),
        weights=weights or ExamWeights(),
        row_labels=labels,
    )


def readiness(db: Session, term: Term) -> list[dict[str, str]]:
    problems = []
    if not exam_days(term):
        problems.append({"code": "no_period", "message": "Set the exam period (dates and weekdays)."})
    if not exam_rooms(db, term):
        problems.append({"code": "no_rooms", "message": "Add the rooms, and keep some open for exams."})
    if not db.scalar(select(func.count()).select_from(ExamPaper).where(ExamPaper.term_id == term.id)):
        problems.append({"code": "no_papers", "message": "Import the exam papers departments published."})
    return problems


def create_exam_run(
    db: Session,
    identity: Identity,
    term: Term,
    weights: dict[str, int] | None,
    time_limit_s: int | None,
    base: ExamDraft | None,
) -> Run:
    from app.services import runs

    settings = get_settings()
    problems = readiness(db, term)
    if problems:
        raise ApiError(409, "NOT_READY", problems[0]["message"], {"problems": problems})
    snapshot = latest_snapshot(db, term)
    if snapshot is None:
        raise ApiError(409, "NO_SNAPSHOT", "Add the rooms first.")
    try:
        merged = ExamWeights.from_dict(weights)
    except ValueError as exc:
        raise ApiError(422, "VALIDATION_ERROR", str(exc)) from exc
    limit = time_limit_s or min(settings.default_time_limit_seconds, 300)
    if not 10 <= limit <= settings.max_time_limit_seconds:
        raise ApiError(
            422, "VALIDATION_ERROR", f"The time limit must be between 10 and {settings.max_time_limit_seconds} seconds."
        )
    run = Run(
        term_id=term.id,
        snapshot_id=snapshot.id,
        mode=RunMode.EXAM,
        weights=merged.as_dict(),
        time_limit_s=limit,
        exam_base_id=base.id if base else None,
        created_by=identity.actor,
        progress={"phase": "queued"},
    )
    db.add(run)
    db.flush()
    audit(db, identity, "run.create", "run", str(run.id), None, {"mode": "exam", "time_limit_s": limit})
    db.commit()
    runs.dispatch(db, run)
    return run


def solve_run(db: Session, run: Run) -> None:
    """The worker's part for an exam run: solve, then store the exam draft or the failure."""
    term = db.get(Term, run.term_id)
    if term is None:
        raise RuntimeError(f"Run {run.id} lost its term")
    base = db.get(ExamDraft, run.exam_base_id) if run.exam_base_id else None
    problem = build(db, term, base, ExamWeights.from_dict(run.weights))
    run.progress = {"phase": "solving", "papers": len(problem.papers)}
    db.commit()
    result = solve(problem, time_limit_s=run.time_limit_s, workers=get_settings().solver_workers)
    run.solve_seconds = result.solve_seconds
    run.finished_at = utcnow()
    if result.failure is not None or not result.slots:
        run.status = RunStatus.FAILED
        run.failure = result.failure
        run.progress = {"phase": "done", "status": result.status}
        db.commit()
        return
    count = db.scalar(select(func.count()).select_from(ExamDraft).where(ExamDraft.term_id == term.id)) or 0
    draft = ExamDraft(term_id=term.id, run_id=run.id, name=f"Exam draft {count + 1}", soft_scores=result.soft_scores)
    seats_by_paper: dict[str, list[Any]] = {}
    for s in result.seats:
        seats_by_paper.setdefault(s.paper_id, []).append(s)
    pinned = {p.id for p in problem.papers if p.pinned is not None}
    for paper_id, slot in result.slots.items():
        draft.placements.append(
            ExamPlacement(
                paper_id=uuid.UUID(paper_id),
                day=problem.days[problem.day_of(slot)],
                session=problem.session_of(slot),
                pinned=paper_id in pinned,
                seats=[
                    ExamSeat(
                        room_id=s.room_id,
                        class_row_id=uuid.UUID(s.row_id),
                        part=s.part,
                        parts=s.parts,
                        students=s.students,
                    )
                    for s in seats_by_paper.get(paper_id, [])
                ],
            )
        )
    db.add(draft)
    db.flush()
    run.status = RunStatus.SUCCEEDED
    run.soft_scores = result.soft_scores
    run.result_draft_id = draft.id
    run.failure = None
    run.progress = {"phase": "done", "status": result.status, "papers": len(problem.papers)}
    db.commit()
