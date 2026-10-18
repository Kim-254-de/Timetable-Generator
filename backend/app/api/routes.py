"""HTTP API, mounted under /api. Every response uses the {success, data} wrapper (app.errors)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.schemas import (
    ClassRowPatch,
    GroupBody,
    LoginBody,
    MoveBody,
    OfferingPatch,
    OpenTermBody,
    ProposeBody,
    PublishBody,
    ResolveBody,
    RunBody,
)
from app.auth import Identity, current_identity, sign_in, sign_out
from app.clients.smarttt import SmartttClient, get_smarttt
from app.config import Settings, get_settings
from app.db import get_db
from app.errors import ApiError, ok
from app.models import ClassRow, Group, Run, RunMode, Term, UnitOffering
from app.services import drafts, export, grouping, runs, setup

router = APIRouter()

Db = Annotated[Session, Depends(get_db)]
Smarttt = Annotated[SmartttClient, Depends(get_smarttt)]
Me = Annotated[Identity, Depends(current_identity)]
Cfg = Annotated[Settings, Depends(get_settings)]


def _get(db: Session, model: type[Any], object_id: str, what: str) -> Any:
    try:
        found = db.get(model, uuid.UUID(object_id))
    except ValueError:
        found = None
    if found is None:
        raise ApiError(404, "NOT_FOUND", f"No such {what}.")
    return found


@router.get("/health")
def health(db: Db) -> dict[str, Any]:
    db.execute(text("SELECT 1"))
    return ok({"status": "ok"})


# -- sign-in ----------------------------------------------------------------------


@router.post("/auth/login")
def login(
    body: LoginBody, request: Request, response: Response, db: Db, smarttt: Smarttt, settings: Cfg
) -> dict[str, Any]:
    return ok(sign_in(db, response, request, body.identifier, body.password, smarttt, settings).public())


@router.post("/auth/logout")
def logout(request: Request, response: Response, db: Db, settings: Cfg) -> dict[str, Any]:
    sign_out(db, request, response, settings)
    return ok(None)


@router.get("/auth/me")
def me(identity: Me) -> dict[str, Any]:
    return ok(identity.public())


# -- terms and setup ------------------------------------------------------------------


@router.get("/smarttt/terms")
def smarttt_terms(_me: Me, smarttt: Smarttt) -> dict[str, Any]:
    return ok(smarttt.terms())


@router.get("/terms")
def list_terms(_me: Me, db: Db) -> dict[str, Any]:
    terms = db.scalars(select(Term).order_by(Term.academic_year.desc(), Term.semester.desc()))
    return ok(
        [
            {
                "id": str(t.id),
                "smarttt_term_id": t.smarttt_term_id,
                "academic_year": t.academic_year,
                "semester": t.semester,
            }
            for t in terms
        ]
    )


@router.post("/terms")
def open_term(body: OpenTermBody, identity: Me, db: Db, smarttt: Smarttt) -> dict[str, Any]:
    term = setup.open_term(db, smarttt, identity, body.smarttt_term_id)
    return ok(
        {
            "id": str(term.id),
            "smarttt_term_id": term.smarttt_term_id,
            "academic_year": term.academic_year,
            "semester": term.semester,
        }
    )


@router.get("/terms/{term_id}")
def term_overview(term_id: str, _me: Me, db: Db) -> dict[str, Any]:
    term = setup.get_term(db, term_id)
    return ok(
        {
            "id": str(term.id),
            "smarttt_term_id": term.smarttt_term_id,
            "academic_year": term.academic_year,
            "semester": term.semester,
            "readiness": setup.readiness(db, term),
            "drafts": drafts.drafts_of(db, term),
            "publications": drafts.publications(db, term),
        }
    )


@router.post("/terms/{term_id}/snapshots")
def take_snapshot(term_id: str, identity: Me, db: Db, smarttt: Smarttt) -> dict[str, Any]:
    term = setup.get_term(db, term_id)
    return ok(setup.snapshot_summary(setup.take_snapshot(db, smarttt, identity, term)))


@router.post("/terms/{term_id}/setup/import")
def import_setup(term_id: str, identity: Me, db: Db) -> dict[str, Any]:
    return ok(setup.import_setup(db, identity, setup.get_term(db, term_id)))


@router.get("/terms/{term_id}/rooms")
def term_rooms(term_id: str, _me: Me, db: Db) -> dict[str, Any]:
    """Active rooms from the latest snapshot, for moving sessions by hand."""
    snapshot = setup.latest_snapshot(db, setup.get_term(db, term_id))
    if snapshot is None:
        raise ApiError(409, "NO_SNAPSHOT", "Take a snapshot of SMARTTT first.")
    rooms = [r for r in snapshot.data["rooms"] if r["status"] == "active"]
    return ok(sorted(rooms, key=lambda r: (r["building"] or "", r["code"])))


@router.get("/terms/{term_id}/class-rows")
def class_rows(term_id: str, _me: Me, db: Db) -> dict[str, Any]:
    term = setup.get_term(db, term_id)
    rows = db.scalars(select(ClassRow).where(ClassRow.term_id == term.id).order_by(ClassRow.label))
    return ok([setup.class_row_dict(r) for r in rows])


@router.patch("/class-rows/{row_id}")
def patch_class_row(row_id: str, body: ClassRowPatch, identity: Me, db: Db) -> dict[str, Any]:
    row: ClassRow = _get(db, ClassRow, row_id, "class row")
    before = setup.class_row_dict(row)
    if body.student_count is not None:
        row.student_count = body.student_count
    if body.unavailable is not None:
        row.unavailable = sorted(set(body.unavailable))
    setup.audit(db, identity, "class_row.update", "class_row", row_id, before, setup.class_row_dict(row))
    db.commit()
    return ok(setup.class_row_dict(row))


@router.get("/terms/{term_id}/offerings")
def offerings(term_id: str, _me: Me, db: Db) -> dict[str, Any]:
    term = setup.get_term(db, term_id)
    rows = {r.id: r for r in db.scalars(select(ClassRow).where(ClassRow.term_id == term.id))}
    found = db.scalars(select(UnitOffering).where(UnitOffering.term_id == term.id).order_by(UnitOffering.unit_code))
    return ok([setup.offering_dict(o, rows) for o in found])


@router.patch("/offerings/{offering_id}")
def patch_offering(offering_id: str, body: OfferingPatch, identity: Me, db: Db) -> dict[str, Any]:
    offering: UnitOffering = _get(db, UnitOffering, offering_id, "offering")
    rows = {r.id: r for r in db.scalars(select(ClassRow).where(ClassRow.term_id == offering.term_id))}
    before = setup.offering_dict(offering, rows)
    for field in ("weekly_hours", "session_length", "room_type"):
        value = getattr(body, field)
        if value is not None:
            setattr(offering, field, value)
    if offering.weekly_hours and offering.session_length and offering.session_length > offering.weekly_hours:
        raise ApiError(422, "VALIDATION_ERROR", "A session can't be longer than the unit's weekly hours.")
    after = setup.offering_dict(offering, rows)
    setup.audit(
        db,
        identity,
        "offering.update",
        "offering",
        offering_id,
        {k: before[k] for k in ("weekly_hours", "session_length", "room_type")},
        {k: after[k] for k in ("weekly_hours", "session_length", "room_type")},
    )
    db.commit()
    return ok(after)


@router.post("/terms/{term_id}/groups/propose")
def propose_groups(term_id: str, body: ProposeBody, identity: Me, db: Db) -> dict[str, Any]:
    return ok(grouping.propose_groups(db, identity, setup.get_term(db, term_id), body.replace))


@router.post("/offerings/{offering_id}/groups")
def add_group(offering_id: str, body: GroupBody, identity: Me, db: Db) -> dict[str, Any]:
    offering: UnitOffering = _get(db, UnitOffering, offering_id, "offering")
    group = grouping.replace_group(
        db, identity, offering, None, body.label, [(m.class_row_id, m.students) for m in body.members]
    )
    rows = {r.id: r for r in db.scalars(select(ClassRow).where(ClassRow.term_id == offering.term_id))}
    return ok(setup.group_dict(group, rows))


@router.patch("/groups/{group_id}")
def patch_group(group_id: str, body: GroupBody, identity: Me, db: Db) -> dict[str, Any]:
    group: Group = _get(db, Group, group_id, "group")
    offering = db.get(UnitOffering, group.offering_id)
    if offering is None:
        raise ApiError(404, "NOT_FOUND", "No such offering.")
    group = grouping.replace_group(
        db, identity, offering, group, body.label, [(m.class_row_id, m.students) for m in body.members]
    )
    rows = {r.id: r for r in db.scalars(select(ClassRow).where(ClassRow.term_id == offering.term_id))}
    return ok(setup.group_dict(group, rows))


@router.delete("/groups/{group_id}")
def delete_group(group_id: str, identity: Me, db: Db) -> dict[str, Any]:
    group: Group = _get(db, Group, group_id, "group")
    setup.audit(db, identity, "group.delete", "group", group_id, {"label": group.label}, None)
    db.delete(group)
    db.commit()
    return ok(None)


# -- runs ---------------------------------------------------------------------------------


@router.post("/runs")
def start_run(body: RunBody, identity: Me, db: Db) -> dict[str, Any]:
    term = setup.get_term(db, str(body.term_id))
    base = drafts.get_draft(db, str(body.base_draft_id)) if body.base_draft_id else None
    run = runs.create_run(db, identity, term, RunMode(body.mode), body.weights, body.time_limit_s, base)
    return ok(runs.run_dict(run))


@router.get("/runs/{run_id}")
def get_run(run_id: str, _me: Me, db: Db) -> dict[str, Any]:
    return ok(runs.run_dict(_get(db, Run, run_id, "run")))


@router.get("/terms/{term_id}/runs")
def term_runs(term_id: str, _me: Me, db: Db) -> dict[str, Any]:
    term = setup.get_term(db, term_id)
    found = db.scalars(select(Run).where(Run.term_id == term.id).order_by(Run.created_at.desc()).limit(50))
    return ok([runs.run_dict(r) for r in found])


# -- drafts ---------------------------------------------------------------------------------


@router.get("/drafts/{draft_id}")
def get_draft(draft_id: str, _me: Me, db: Db, view: str = Query("row")) -> dict[str, Any]:
    return ok(drafts.grid(db, drafts.get_draft(db, draft_id), view))


@router.patch("/drafts/{draft_id}/sessions/{key}")
def move_session(draft_id: str, key: str, body: MoveBody, identity: Me, db: Db) -> dict[str, Any]:
    draft = drafts.get_draft(db, draft_id)
    return ok(drafts.move_session(db, identity, draft, key, body.day, body.start_time, body.room_id, body.pinned))


@router.post("/drafts/{draft_id}/resolve")
def resolve(draft_id: str, body: ResolveBody, identity: Me, db: Db) -> dict[str, Any]:
    draft = drafts.get_draft(db, draft_id)
    term = setup.get_term(db, str(draft.term_id))
    run = runs.create_run(db, identity, term, RunMode.RESOLVE, body.weights, body.time_limit_s, draft)
    return ok(runs.run_dict(run))


@router.post("/drafts/{draft_id}/copy")
def copy(draft_id: str, identity: Me, db: Db) -> dict[str, Any]:
    new = drafts.copy_draft(db, identity, drafts.get_draft(db, draft_id))
    return ok(drafts.draft_summary(db, new))


@router.post("/drafts/{draft_id}/publish")
def publish(draft_id: str, body: PublishBody, identity: Me, db: Db, smarttt: Smarttt) -> dict[str, Any]:
    return ok(drafts.publish(db, smarttt, identity, drafts.get_draft(db, draft_id), body.replace_unpublished))


@router.get("/drafts/{draft_id}/export.pdf")
def export_pdf(draft_id: str, identity: Me, db: Db, view: str = Query("row")) -> Response:
    draft = drafts.get_draft(db, draft_id)
    data = drafts.grid(db, draft, view)
    term = setup.get_term(db, str(draft.term_id))
    pdf = export.build_pdf(term, data, identity.full_name)
    filename = f"teaching-timetable-{term.academic_year.replace('/', '-')}-S{term.semester}-{view}.pdf"
    return Response(
        pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
