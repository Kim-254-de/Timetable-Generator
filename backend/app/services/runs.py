"""
Solver runs. A run is queued to the RQ worker (a separate process with the
solver), reports its progress to the runs table, and on success becomes a
new draft the Director can review. Runs never change an existing draft.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.auth import Identity
from app.config import get_settings
from app.db import get_sessionmaker
from app.errors import ApiError
from app.models import Draft, DraftSession, Run, RunMode, RunStatus, Snapshot, Term, utcnow
from app.services.problem import build_problem
from app.services.setup import audit, latest_snapshot, readiness
from app.solver import cpsat
from app.solver.model import Weights

logger = logging.getLogger(__name__)

# Repairs keep the published timetable unless a rule forces a move (S8);
# re-solves around pins may move anything else freely.
MODE_DEFAULTS: dict[RunMode, dict[str, int]] = {
    RunMode.FULL: {"keep_previous": 0},
    RunMode.RESOLVE: {"keep_previous": 0},
    RunMode.REPAIR: {},
}


# A job may run this long past the solver's own limit (room phase, writing the draft).
JOB_GRACE_SECONDS = 900
# A queued run no worker has picked up within this long was lost (e.g. Redis restarted).
QUEUE_WAIT = timedelta(hours=1)


def _aware(moment: datetime) -> datetime:
    # SQLite hands back naive datetimes; everything here is UTC.
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def reap_stale(db: Session, found: Iterable[Run]) -> None:
    """
    Marks failed the runs whose worker died (killed, out of memory, redeployed)
    or whose job was lost, which would otherwise show as queued or running
    forever: running past the job's own timeout, or queued over QUEUE_WAIT.
    """
    now = utcnow()
    changed = False
    for run in found:
        if run.status == RunStatus.RUNNING and run.started_at is not None:
            stale = _aware(run.started_at) + timedelta(seconds=run.time_limit_s + JOB_GRACE_SECONDS) < now
            message = "The solver stopped without finishing (its worker was restarted). Start the run again."
        elif run.status == RunStatus.QUEUED:
            stale = _aware(run.created_at) + QUEUE_WAIT < now
            message = "No solver worker picked this run up. Check the worker is running, then start it again."
        else:
            continue
        if stale:
            run.status = RunStatus.FAILED
            run.failure = {
                "stage": "worker",
                "count": 1,
                "reasons": [{"rule": "?", "entity": "run", "message": message}],
            }
            run.finished_at = now
            changed = True
            logger.warning("Run %s marked failed: %s", run.id, message)
    if changed:
        db.commit()


def run_dict(run: Run) -> dict[str, Any]:
    return {
        "id": str(run.id),
        "term_id": str(run.term_id),
        "mode": run.mode.value,
        "status": run.status.value,
        "base_draft_id": str(run.base_draft_id) if run.base_draft_id else None,
        "weights": run.weights,
        "time_limit_s": run.time_limit_s,
        "progress": run.progress,
        "score": run.score,
        "soft_scores": run.soft_scores,
        "solve_seconds": run.solve_seconds,
        "failure": run.failure,
        "draft_id": str(run.result_draft_id) if run.result_draft_id else None,
        "created_by": run.created_by,
        "created_at": run.created_at.isoformat(),
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


def create_run(
    db: Session,
    identity: Identity,
    term: Term,
    mode: RunMode,
    weights: dict[str, int] | None,
    time_limit_s: int | None,
    base_draft: Draft | None,
    keep_published: bool = False,
) -> Run:
    settings = get_settings()
    snapshot = latest_snapshot(db, term)
    if snapshot is None:
        raise ApiError(409, "NO_SNAPSHOT", "Take a snapshot of SMARTTT first.")
    if mode == RunMode.RESOLVE and base_draft is None:
        raise ApiError(422, "VALIDATION_ERROR", "A re-solve needs the draft to re-solve.")
    if keep_published and not (snapshot.data.get("published") or {}).get("version"):
        raise ApiError(409, "NOTHING_PUBLISHED", "Nothing is published yet, so there are no classes to keep.")
    if mode == RunMode.REPAIR and not (snapshot.data.get("published") or {}).get("version"):
        raise ApiError(409, "NOTHING_PUBLISHED", "A repair re-solve needs a published timetable; run a full solve.")
    ready = readiness(db, term)
    if not ready["ready"]:
        raise ApiError(
            409,
            "NOT_READY",
            "Some inputs are missing; fix them before solving.",
            {"problems": ready["problems"][:50], "problem_count": ready["problem_count"]},
        )
    try:
        merged = Weights.from_dict({**MODE_DEFAULTS[mode], **(weights or {})})
    except ValueError as exc:
        raise ApiError(422, "VALIDATION_ERROR", str(exc)) from exc
    limit = time_limit_s or settings.default_time_limit_seconds
    if not 10 <= limit <= settings.max_time_limit_seconds:
        raise ApiError(
            422, "VALIDATION_ERROR", f"The time limit must be between 10 and {settings.max_time_limit_seconds} seconds."
        )

    run = Run(
        term_id=term.id,
        snapshot_id=snapshot.id,
        mode=mode,
        weights=merged.as_dict(),
        time_limit_s=limit,
        base_draft_id=base_draft.id if base_draft else None,
        keep_published=keep_published,
        created_by=identity.actor,
        progress={"phase": "queued"},
    )
    db.add(run)
    db.flush()
    audit(
        db,
        identity,
        "run.create",
        "run",
        str(run.id),
        None,
        {"mode": mode.value, "time_limit_s": limit, "keep_published": keep_published},
    )
    db.commit()

    if settings.run_inline:
        execute_run(str(run.id))
        db.refresh(run)
    else:
        _enqueue(str(run.id), limit)
    return run


def _enqueue(run_id: str, time_limit_s: int) -> None:
    from redis import Redis
    from rq import Queue

    settings = get_settings()
    queue = Queue(settings.run_queue, connection=Redis.from_url(settings.redis_url))
    queue.enqueue(
        "app.worker.jobs.execute_run",
        run_id,
        job_timeout=time_limit_s + JOB_GRACE_SECONDS,
        result_ttl=3600,
        failure_ttl=86400,
    )


def execute_run(run_id: str) -> None:
    """The worker's job: solve, then store the draft or the failure. Never raises."""
    db = get_sessionmaker()()
    try:
        run = db.get(Run, uuid.UUID(run_id))
        if run is None or run.status != RunStatus.QUEUED:
            return
        run.status = RunStatus.RUNNING
        run.started_at = utcnow()
        run.progress = {"phase": "building"}
        db.commit()
        try:
            _solve(db, run)
        except Exception:
            logger.exception("Run %s crashed", run_id)
            db.rollback()
            run = db.get(Run, uuid.UUID(run_id))
            if run is not None:
                run.status = RunStatus.FAILED
                run.failure = {
                    "stage": "internal",
                    "count": 1,
                    "reasons": [
                        {"rule": "?", "entity": "run", "message": "The run stopped unexpectedly; it has been logged."}
                    ],
                }
                run.finished_at = utcnow()
                db.commit()
    finally:
        db.close()


def _solve(db: Session, run: Run) -> None:
    term = db.get(Term, run.term_id)
    snapshot = db.get(Snapshot, run.snapshot_id)
    base = db.get(Draft, run.base_draft_id) if run.base_draft_id else None
    if term is None or snapshot is None:
        raise RuntimeError(f"Run {run.id} lost its term or snapshot")
    built = build_problem(
        db, term, snapshot, Weights.from_dict(run.weights), run.mode, base, keep_published=run.keep_published
    )

    last_write = 0.0

    def progress(info: dict[str, object]) -> None:
        nonlocal last_write
        now = time.monotonic()
        if now - last_write < 5:
            return
        last_write = now
        run.progress = {**info, "sessions": len(built.problem.sessions)}
        db.commit()

    result = cpsat.solve(
        built.problem, time_limit_s=run.time_limit_s, workers=get_settings().solver_workers, on_progress=progress
    )
    run.solve_seconds = result.solve_seconds
    run.finished_at = utcnow()
    if not result.placements:
        run.status = RunStatus.FAILED
        run.failure = result.failure
        run.progress = {"phase": "done", "status": result.status}
        db.commit()
        return

    count = db.query(Draft).filter(Draft.term_id == term.id).count()
    draft = Draft(
        term_id=term.id,
        run_id=run.id,
        parent_draft_id=run.base_draft_id,
        name=f"Draft {count + 1} ({run.mode.value})",
        soft_scores=result.soft_scores,
    )
    for s in built.problem.sessions:
        p = result.placements[s.key]
        draft.sessions.append(
            DraftSession(
                key=s.key,
                group_id=uuid.UUID(s.group_id),
                index=s.index,
                smarttt_room_id=p.room_id,
                start_slot=p.start,
                length=s.length,
                pinned=s.pinned is not None,
            )
        )
    db.add(draft)
    db.flush()
    run.status = RunStatus.SUCCEEDED
    run.score = result.objective
    run.soft_scores = result.soft_scores
    run.result_draft_id = draft.id
    run.failure = None
    run.progress = {"phase": "done", "status": result.status, "sessions": len(built.problem.sessions)}
    db.commit()
