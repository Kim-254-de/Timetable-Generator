"""HTTP API, mounted under /api. Every response uses the {success, data} wrapper (app.errors)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.api.schemas import (
    BulkBody,
    ClassRowBody,
    ClassRowPatch,
    CopyTermBody,
    DepartmentPatch,
    ExamMoveBody,
    ExamPeriodBody,
    ExamResolveBody,
    ExamRunBody,
    GroupBody,
    LoginBody,
    MoveBody,
    OfferingBody,
    OfferingPatch,
    OpenTermBody,
    ProposeBody,
    PublishBody,
    ResolveBody,
    RoomBody,
    RoomPatch,
    RunBody,
    TermPatch,
)
from app.auth import Identity, current_identity, sign_in, sign_out
from app.clients.attendance import AttendanceClient, AttendanceError, get_attendance
from app.clients.smarttt import SmartttClient, get_smarttt
from app.clients.teaching import TeachingClient, get_teaching
from app.config import Settings, get_settings
from app.db import get_db
from app.errors import ApiError, ok
from app.models import ClassRow, Group, Room, Run, RunMode, Term, UnitOffering
from app.services import (
    allocator_import,
    departments,
    drafts,
    exam_drafts,
    exam_export,
    exam_runs,
    exam_setup,
    export,
    grouping,
    integration,
    master,
    runs,
    setup,
    spreadsheet,
)

router = APIRouter()

Db = Annotated[Session, Depends(get_db)]
Smarttt = Annotated[SmartttClient, Depends(get_smarttt)]
Attendance = Annotated[AttendanceClient, Depends(get_attendance)]
Teaching = Annotated[TeachingClient, Depends(get_teaching)]
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


# -- Excel files -------------------------------------------------------------------------


@router.post("/spreadsheets/read")
async def read_spreadsheet(request: Request, identity: Me) -> dict[str, Any]:
    """The cells of a prepared .xlsx, sent as the raw request body, for the "Paste from Excel" dialogs."""
    content = bytearray()
    async for chunk in request.stream():
        content += chunk
        if len(content) > spreadsheet.MAX_FILE_BYTES:
            raise ApiError(413, "FILE_TOO_LARGE", spreadsheet.TOO_BIG)
    return ok(await run_in_threadpool(spreadsheet.read_workbook, bytes(content)))


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
    return ok([setup.term_dict(t) for t in terms])


@router.post("/terms")
def open_term(body: OpenTermBody, identity: Me, db: Db, smarttt: Smarttt) -> dict[str, Any]:
    """Opens a SMARTTT term, or creates a term here when academic year and semester are given."""
    if body.smarttt_term_id:
        term = setup.open_term(db, smarttt, identity, body.smarttt_term_id)
    elif body.academic_year and body.semester:
        term = setup.create_term(db, identity, body.model_dump(exclude={"smarttt_term_id", "copy_from_term_id"}))
    else:
        raise ApiError(422, "VALIDATION_ERROR", "Give the academic year and semester of the new term.")
    if body.copy_from_term_id:
        master.copy_term(db, identity, term, setup.get_term(db, str(body.copy_from_term_id)))
    return ok(setup.term_dict(term))


@router.get("/terms/{term_id}")
def term_overview(term_id: str, _me: Me, db: Db) -> dict[str, Any]:
    term = setup.get_term(db, term_id)
    return ok(
        {
            **setup.term_dict(term),
            "readiness": setup.readiness(db, term),
            "drafts": drafts.drafts_of(db, term),
            "publications": drafts.publications(db, term),
        }
    )


@router.patch("/terms/{term_id}")
def patch_term(term_id: str, body: TermPatch, identity: Me, db: Db) -> dict[str, Any]:
    term = setup.get_term(db, term_id)
    return ok(setup.term_dict(setup.update_term(db, identity, term, body.model_dump(exclude_unset=True))))


@router.post("/terms/{term_id}/copy")
def copy_term(term_id: str, body: CopyTermBody, identity: Me, db: Db) -> dict[str, Any]:
    target = setup.get_term(db, term_id)
    return ok(master.copy_term(db, identity, target, setup.get_term(db, str(body.source_term_id))))


# -- lecture halls and departments (shared by every term) ---------------------------------


def _room(db: Session, room_id: str) -> Room:
    room = db.get(Room, room_id)
    if room is None:
        raise ApiError(404, "NOT_FOUND", "No such lecture hall.")
    return room


@router.get("/rooms")
def list_rooms(_me: Me, db: Db) -> dict[str, Any]:
    return ok(master.list_rooms(db))


@router.post("/rooms")
def create_room(body: RoomBody, identity: Me, db: Db) -> dict[str, Any]:
    return ok(master.room_dict(master.create_room(db, identity, body.model_dump())))


@router.post("/rooms/bulk")
def bulk_rooms(body: BulkBody, identity: Me, db: Db) -> dict[str, Any]:
    return ok(master.bulk_rooms(db, identity, body.rows))


@router.patch("/rooms/{room_id}")
def patch_room(room_id: str, body: RoomPatch, identity: Me, db: Db) -> dict[str, Any]:
    room = master.update_room(db, identity, _room(db, room_id), body.model_dump(exclude_unset=True))
    return ok(master.room_dict(room))


@router.delete("/rooms/{room_id}")
def delete_room(room_id: str, identity: Me, db: Db) -> dict[str, Any]:
    master.delete_room(db, identity, _room(db, room_id))
    return ok(None)


@router.get("/departments")
def list_departments(identity: Me, db: Db, attendance: Attendance) -> dict[str, Any]:
    """Departments come from Smart Attendance: read from there first (at most every DEPARTMENT_SYNC_SECONDS)."""
    return ok(departments.list_departments(db, attendance, identity))


@router.post("/departments/sync")
def sync_departments(identity: Me, db: Db, attendance: Attendance) -> dict[str, Any]:
    """Reads the departments from Smart Attendance now. 503 when it can't be reached."""
    if not attendance.enabled:
        raise ApiError(
            409, "ATTENDANCE_NOT_CONNECTED", "Smart Attendance is not connected (ATTENDANCE_BASE_URL is unset)."
        )
    try:
        report = departments.sync_departments(db, attendance, identity, force=True)
    except AttendanceError as exc:
        raise ApiError(503, "ATTENDANCE_UNAVAILABLE", exc.message) from exc
    return ok({"report": report, **departments.list_departments(db, attendance, identity)})


@router.post("/departments/bulk")
def bulk_departments(body: BulkBody, identity: Me, db: Db) -> dict[str, Any]:
    return ok(master.bulk_departments(db, identity, body.rows))


@router.patch("/departments/{department_id}")
def patch_department(department_id: int, body: DepartmentPatch, identity: Me, db: Db) -> dict[str, Any]:
    department = master.get_department(db, department_id)
    updated = master.update_department(db, identity, department, body.model_dump(exclude_unset=True))
    return ok(master.department_dict(updated))


@router.delete("/departments/{department_id}")
def delete_department(department_id: int, identity: Me, db: Db) -> dict[str, Any]:
    master.delete_department(db, identity, master.get_department(db, department_id))
    return ok(None)


@router.post("/terms/{term_id}/snapshots")
def take_snapshot(term_id: str, identity: Me, db: Db, smarttt: Smarttt) -> dict[str, Any]:
    term = setup.get_term(db, term_id)
    return ok(setup.snapshot_summary(setup.take_snapshot(db, smarttt, identity, term)))


@router.get("/terms/{term_id}/departments")
def department_submissions(term_id: str, _me: Me, db: Db, teaching: Teaching) -> dict[str, Any]:
    """Which departments have published their teaching in Smart Attendance, and whether it's imported."""
    return ok(allocator_import.status(db, teaching, setup.get_term(db, term_id)))


@router.post("/terms/{term_id}/departments/import")
def import_departments(term_id: str, identity: Me, db: Db, teaching: Teaching) -> dict[str, Any]:
    """Brings in what departments have published: class rows, units and groups with lecturers."""
    return ok(allocator_import.import_departments(db, teaching, identity, setup.get_term(db, term_id)))


@router.post("/terms/{term_id}/setup/import")
def import_setup(term_id: str, identity: Me, db: Db, attendance: Attendance) -> dict[str, Any]:
    # The units SMARTTT names belong to departments, which come from Attendance: read them in first.
    departments.sync_departments(db, attendance, identity)
    return ok(setup.import_setup(db, identity, setup.get_term(db, term_id)))


@router.get("/terms/{term_id}/rooms")
def term_rooms(term_id: str, _me: Me, db: Db) -> dict[str, Any]:
    """Active rooms from the latest snapshot, for moving sessions by hand."""
    snapshot = setup.latest_snapshot(db, setup.get_term(db, term_id))
    if snapshot is None:
        raise ApiError(409, "NO_SNAPSHOT", "Add the lecture halls first (or import them from SMARTTT).")
    rooms = [r for r in snapshot.data["rooms"] if r["status"] == "active"]
    return ok(sorted(rooms, key=lambda r: (r["building"] or "", r["code"])))


@router.get("/terms/{term_id}/class-rows")
def class_rows(term_id: str, _me: Me, db: Db) -> dict[str, Any]:
    term = setup.get_term(db, term_id)
    rows = db.scalars(select(ClassRow).where(ClassRow.term_id == term.id).order_by(ClassRow.label))
    return ok([setup.class_row_dict(r) for r in rows])


@router.post("/terms/{term_id}/class-rows")
def create_class_row(term_id: str, body: ClassRowBody, identity: Me, db: Db) -> dict[str, Any]:
    term = setup.get_term(db, term_id)
    return ok(setup.class_row_dict(master.create_class_row(db, identity, term, body.model_dump())))


@router.post("/terms/{term_id}/class-rows/bulk")
def bulk_class_rows(term_id: str, body: BulkBody, identity: Me, db: Db) -> dict[str, Any]:
    return ok(master.bulk_class_rows(db, identity, setup.get_term(db, term_id), body.rows))


@router.patch("/class-rows/{row_id}")
def patch_class_row(row_id: str, body: ClassRowPatch, identity: Me, db: Db) -> dict[str, Any]:
    row: ClassRow = _get(db, ClassRow, row_id, "class row")
    before = setup.class_row_dict(row)
    master.update_class_row(db, identity, row, body.model_dump(exclude_unset=True))
    setup.audit(db, identity, "class_row.update", "class_row", row_id, before, setup.class_row_dict(row))
    db.commit()
    return ok(setup.class_row_dict(row))


@router.delete("/class-rows/{row_id}")
def delete_class_row(row_id: str, identity: Me, db: Db) -> dict[str, Any]:
    return ok(master.delete_class_row(db, identity, _get(db, ClassRow, row_id, "class row")))


@router.get("/terms/{term_id}/offerings")
def offerings(term_id: str, _me: Me, db: Db) -> dict[str, Any]:
    term = setup.get_term(db, term_id)
    rows = {r.id: r for r in db.scalars(select(ClassRow).where(ClassRow.term_id == term.id))}
    found = db.scalars(select(UnitOffering).where(UnitOffering.term_id == term.id).order_by(UnitOffering.unit_code))
    return ok([setup.offering_dict(o, rows) for o in found])


@router.post("/terms/{term_id}/offerings")
def create_offering(term_id: str, body: OfferingBody, identity: Me, db: Db) -> dict[str, Any]:
    term = setup.get_term(db, term_id)
    offering = master.create_offering(db, identity, term, body.model_dump())
    rows = {r.id: r for r in db.scalars(select(ClassRow).where(ClassRow.term_id == term.id))}
    return ok(setup.offering_dict(offering, rows))


@router.post("/terms/{term_id}/offerings/bulk")
def bulk_offerings(term_id: str, body: BulkBody, identity: Me, db: Db) -> dict[str, Any]:
    return ok(master.bulk_offerings(db, identity, setup.get_term(db, term_id), body.rows))


@router.patch("/offerings/{offering_id}")
def patch_offering(offering_id: str, body: OfferingPatch, identity: Me, db: Db) -> dict[str, Any]:
    offering: UnitOffering = _get(db, UnitOffering, offering_id, "offering")
    term = setup.get_term(db, str(offering.term_id))
    rows = {r.id: r for r in db.scalars(select(ClassRow).where(ClassRow.term_id == offering.term_id))}
    before = setup.offering_dict(offering, rows)
    master.update_offering(db, identity, term, offering, body.model_dump(exclude_unset=True))
    after = setup.offering_dict(offering, rows)
    fields = ("unit_code", "unit_name", "department_id", "weekly_hours", "session_length", "room_type", "class_rows")
    setup.audit(
        db,
        identity,
        "offering.update",
        "offering",
        offering_id,
        {k: before[k] for k in fields},
        {k: after[k] for k in fields},
    )
    db.commit()
    return ok(after)


@router.delete("/offerings/{offering_id}")
def delete_offering(offering_id: str, identity: Me, db: Db) -> dict[str, Any]:
    master.delete_offering(db, identity, _get(db, UnitOffering, offering_id, "offering"))
    return ok(None)


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
    offering = db.get(UnitOffering, group.offering_id)
    if offering is None:
        raise ApiError(404, "NOT_FOUND", "No such offering.")
    setup.require_local(offering)
    setup.audit(db, identity, "group.delete", "group", group_id, {"label": group.label}, None)
    grouping.remove_group(db, offering, group)
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
    run: Run = _get(db, Run, run_id, "run")
    runs.reap_stale(db, [run])
    return ok(runs.run_dict(run))


@router.get("/terms/{term_id}/runs")
def term_runs(term_id: str, _me: Me, db: Db) -> dict[str, Any]:
    term = setup.get_term(db, term_id)
    found = list(db.scalars(select(Run).where(Run.term_id == term.id).order_by(Run.created_at.desc()).limit(50)))
    runs.reap_stale(db, found)
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
    run = runs.create_run(
        db, identity, term, RunMode.RESOLVE, body.weights, body.time_limit_s, draft, keep_published=body.keep_published
    )
    return ok(runs.run_dict(run))


@router.post("/drafts/{draft_id}/copy")
def copy(draft_id: str, identity: Me, db: Db) -> dict[str, Any]:
    new = drafts.copy_draft(db, identity, drafts.get_draft(db, draft_id))
    return ok(drafts.draft_summary(db, new))


@router.post("/drafts/{draft_id}/publish")
def publish(draft_id: str, body: PublishBody, identity: Me, db: Db, smarttt: Smarttt) -> dict[str, Any]:
    return ok(drafts.publish(db, smarttt, identity, drafts.get_draft(db, draft_id), body.replace_unpublished))


@router.post("/terms/{term_id}/publications/{version}/send")
def send_publication(term_id: str, version: int, identity: Me, db: Db, smarttt: Smarttt) -> dict[str, Any]:
    return ok(drafts.send_publication(db, smarttt, identity, setup.get_term(db, term_id), version))


EXPORTS = {
    "pdf": ("application/pdf", export.build_pdf),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", export.build_docx),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", export.build_xlsx),
}


@router.get("/drafts/{draft_id}/export.{fmt}")
def export_draft(draft_id: str, fmt: str, identity: Me, db: Db, view: str = Query("row")) -> Response:
    """The timetable as PDF, Word (.docx) or Excel (.xlsx), by class row, lecture hall or department."""
    if fmt not in EXPORTS:
        raise ApiError(404, "NOT_FOUND", "Downloads are .pdf, .docx or .xlsx.")
    media_type, build = EXPORTS[fmt]
    draft = drafts.get_draft(db, draft_id)
    data = drafts.grid(db, draft, view)
    term = setup.get_term(db, str(draft.term_id))
    content = build(term, data, identity.full_name)
    filename = f"teaching-timetable-{term.academic_year.replace('/', '-')}-S{term.semester}-{view}.{fmt}"
    return Response(
        content, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# -- exams ------------------------------------------------------------------------------------


@router.get("/terms/{term_id}/exams")
def term_exams(term_id: str, _me: Me, db: Db) -> dict[str, Any]:
    """The term's exam period, papers, practicals, drafts and versions, and what is missing to generate."""
    term = setup.get_term(db, term_id)
    return ok(
        {
            "period": exam_setup.period_dict(db, term),
            "papers": exam_setup.papers_of(db, term),
            "practicals": exam_setup.practicals_of(db, term),
            "drafts": exam_drafts.drafts_of(db, term),
            "publications": exam_drafts.publications(db, term),
            "readiness": exam_runs.readiness(db, term),
        }
    )


@router.patch("/terms/{term_id}/exam-period")
def exam_period(term_id: str, body: ExamPeriodBody, identity: Me, db: Db) -> dict[str, Any]:
    term = setup.get_term(db, term_id)
    return ok(exam_setup.update_period(db, identity, term, body.model_dump(exclude_unset=True)))


@router.get("/terms/{term_id}/exam-departments")
def exam_departments(term_id: str, _me: Me, db: Db, teaching: Teaching) -> dict[str, Any]:
    """Which departments have published their exam papers in Smart Attendance."""
    data = teaching.exams(str(setup.get_term(db, term_id).id))
    return ok(
        {
            "published": [
                {"code": d["code"], "name": d["name"], "published_at": d["published_at"], "papers": len(d["papers"])}
                for d in data.get("published") or []
            ],
            "not_published": data.get("not_published") or [],
        }
    )


@router.post("/terms/{term_id}/exams/import")
def import_exams(term_id: str, identity: Me, db: Db, teaching: Teaching) -> dict[str, Any]:
    return ok(exam_setup.import_exams(db, teaching, identity, setup.get_term(db, term_id)))


@router.post("/exam-runs")
def start_exam_run(body: ExamRunBody, identity: Me, db: Db) -> dict[str, Any]:
    term = setup.get_term(db, str(body.term_id))
    return ok(runs.run_dict(exam_runs.create_exam_run(db, identity, term, body.weights, body.time_limit_s, None)))


@router.get("/exam-drafts/{draft_id}")
def get_exam_draft(draft_id: str, _me: Me, db: Db, teaching: Teaching) -> dict[str, Any]:
    return ok(exam_drafts.grid(db, exam_drafts.get_draft(db, draft_id), teaching))


@router.patch("/exam-drafts/{draft_id}/papers/{paper_id}")
def move_exam_paper(draft_id: str, paper_id: str, body: ExamMoveBody, identity: Me, db: Db) -> dict[str, Any]:
    draft = exam_drafts.get_draft(db, draft_id)
    return ok(exam_drafts.move_paper(db, identity, draft, paper_id, body.day.isoformat(), body.session, body.pinned))


@router.post("/exam-drafts/{draft_id}/resolve")
def resolve_exam_draft(draft_id: str, body: ExamResolveBody, identity: Me, db: Db) -> dict[str, Any]:
    draft = exam_drafts.get_draft(db, draft_id)
    term = setup.get_term(db, str(draft.term_id))
    return ok(runs.run_dict(exam_runs.create_exam_run(db, identity, term, None, body.time_limit_s, draft)))


@router.post("/exam-drafts/{draft_id}/share")
def share_exam_draft(draft_id: str, identity: Me, db: Db) -> dict[str, Any]:
    return ok(exam_drafts.share(db, identity, exam_drafts.get_draft(db, draft_id)))


@router.post("/exam-drafts/{draft_id}/copy")
def copy_exam_draft(draft_id: str, identity: Me, db: Db) -> dict[str, Any]:
    new = exam_drafts.copy_draft(db, identity, exam_drafts.get_draft(db, draft_id))
    return ok(exam_drafts.draft_summary(db, new))


@router.post("/exam-drafts/{draft_id}/publish")
def publish_exam_draft(draft_id: str, identity: Me, db: Db, teaching: Teaching) -> dict[str, Any]:
    return ok(exam_drafts.publish(db, teaching, identity, exam_drafts.get_draft(db, draft_id)))


@router.get("/exam-drafts/{draft_id}/export/{kind}.{fmt}")
def export_exam_draft(draft_id: str, kind: str, fmt: str, identity: Me, db: Db, teaching: Teaching) -> Response:
    """The exam timetable, room sheets or invigilation roster as Word (.docx) or PDF."""
    if (kind, fmt) not in exam_export.BUILDERS:
        raise ApiError(404, "NOT_FOUND", "Downloads are timetable, rooms or roster, as .docx or .pdf.")
    draft = exam_drafts.get_draft(db, draft_id)
    data = exam_drafts.grid(db, draft, teaching)
    term = setup.get_term(db, str(draft.term_id))
    content = exam_export.BUILDERS[(kind, fmt)](term, data, data["version"], identity.full_name)
    filename = f"exam-{kind}-{term.academic_year.replace('/', '-')}-S{term.semester}.{fmt}"
    return Response(
        content,
        media_type=exam_export.MEDIA[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# -- for Smart Attendance's department Teaching page (shared key, no user session) ----------

AttendanceKey = Depends(integration.require_attendance_key)


@router.get("/integrations/attendance/terms", dependencies=[AttendanceKey])
def attendance_terms(db: Db) -> dict[str, Any]:
    return ok(integration.teaching_terms(db))


@router.get("/integrations/attendance/terms/{term_id}/times", dependencies=[AttendanceKey])
def attendance_times(term_id: str, db: Db) -> dict[str, Any]:
    return ok(integration.teaching_times(db, setup.get_term(db, term_id)))


@router.get("/integrations/attendance/terms/{term_id}/exam-draft", dependencies=[AttendanceKey])
def attendance_exam_draft(term_id: str, db: Db) -> dict[str, Any]:
    """The exam draft the Director shared: each paper's date, session and rooms, for departments' invigilators."""
    return ok(exam_drafts.allocator_draft(db, setup.get_term(db, term_id)))
