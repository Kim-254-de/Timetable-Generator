"""
Exam drafts: the date x session grid, room sheets, moving a paper, sharing
the draft with departments (so they name invigilators), and publishing.

A published version is frozen (`record`) so later edits never change it, and
`payload` is what SMARTTT is sent (its generator/exams/publish/): each paper's
codes, date, times and seating, with each class row's programme, year and
stream so SMARTTT can show students their own room, and the practicals.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth import Identity
from app.clients.smarttt import SmartttClient, SmartttMisconfigured, SmartttRefused, SmartttUnavailable
from app.clients.teaching import TeachingClient
from app.errors import ApiError
from app.exam_solver import rooms as seating
from app.exam_solver.model import ExamProblem, Seat
from app.exam_solver.solve import soft_scores
from app.exam_solver.validate import check
from app.models import (
    ClassRow,
    Department,
    DraftStatus,
    ExamDraft,
    ExamPaper,
    ExamPlacement,
    ExamPractical,
    ExamPublication,
    ExamSeat,
    Room,
    Term,
    utcnow,
)
from app.services.drafts import NO_TERM_DATES, _smarttt_can_place
from app.services.exam_runs import build
from app.services.exam_setup import practicals_of
from app.services.setup import audit


def get_draft(db: Session, draft_id: str) -> ExamDraft:
    try:
        found = db.get(ExamDraft, uuid.UUID(draft_id))
    except ValueError:
        found = None
    if found is None:
        raise ApiError(404, "NOT_FOUND", "No such exam draft.")
    return found


@dataclass
class _Built:
    term: Term
    problem: ExamProblem
    slots: dict[str, int]
    seats: list[Seat]


def _built(db: Session, draft: ExamDraft) -> _Built:
    term = db.get(Term, draft.term_id)
    if term is None:
        raise ApiError(404, "NOT_FOUND", "No such term.")
    problem = build(db, term, draft)
    slots: dict[str, int] = {}
    seats: list[Seat] = []
    for pl in draft.placements:
        pid = str(pl.paper_id)
        slot = (
            problem.days.index(pl.day) * problem.sessions + pl.session
            if pl.day in problem.days and 0 <= pl.session < problem.sessions
            else -1
        )
        slots[pid] = slot
        seats.extend(Seat(pid, str(s.class_row_id), s.room_id, s.students, s.part, s.parts) for s in pl.seats)
    return _Built(term, problem, slots, seats)


def draft_summary(db: Session, draft: ExamDraft, built: _Built | None = None) -> dict[str, Any]:
    built = built or _built(db, draft)
    violations = check(built.problem, built.slots, built.seats)
    return {
        "id": str(draft.id),
        "term_id": str(draft.term_id),
        "name": draft.name,
        "status": draft.status.value,
        "shared_at": draft.shared_at.isoformat() if draft.shared_at else None,
        "created_at": draft.created_at.isoformat(),
        "papers": len(built.problem.papers),
        "placed": sum(1 for p in built.problem.papers if built.slots.get(p.id, -1) >= 0),
        "pinned": sum(1 for pl in draft.placements if pl.pinned),
        "soft_scores": soft_scores(built.problem, {k: v for k, v in built.slots.items() if v >= 0}),
        "violations": [v.__dict__ for v in violations[:100]],
        "publishable": not violations and draft.status == DraftStatus.DRAFT,
    }


def record(db: Session, draft: ExamDraft, invigilators: dict[str, Any] | None = None) -> dict[str, Any]:
    """The draft as views, downloads and the departments' invigilator pages see it."""
    built = _built(db, draft)
    term = built.term
    papers = {p.id: p for p in db.scalars(select(ExamPaper).where(ExamPaper.term_id == term.id))}
    rooms = {r.id: r for r in db.scalars(select(Room))}
    labels = {r.id: r.label for r in db.scalars(select(ClassRow).where(ClassRow.term_id == term.id))}
    departments = {d.id: d.code for d in db.scalars(select(Department))}
    odel = {(p.id, r.class_row_id): r.odel for p in papers.values() for r in p.rows}
    placed = {pl.paper_id: pl for pl in draft.placements}
    out = []
    for p in sorted(papers.values(), key=lambda p: p.label):
        pl = placed.get(p.id)
        out.append(
            {
                "id": str(p.id),
                "allocator_ref": p.allocator_ref,
                "codes": p.label,
                "code_list": list(p.codes),
                "sitting": p.sitting,
                "title": p.title,
                "department": departments.get(p.department_id, "?"),
                "examiner": p.examiner_name,
                "examiner_staff_number": p.examiner_staff_number,
                "students": p.students,
                "day": pl.day.isoformat() if pl else None,
                "session": pl.session if pl else None,
                "pinned": bool(pl and pl.pinned),
                "seating": sorted(
                    (
                        {
                            "room_id": s.room_id,
                            "row_id": str(s.class_row_id),
                            "room": rooms[s.room_id].code if s.room_id in rooms else s.room_id,
                            "block": rooms[s.room_id].block if s.room_id in rooms else "",
                            "row": labels.get(s.class_row_id, "?"),
                            "students": s.students,
                            "part": s.part,
                            "parts": s.parts,
                            "odel": odel.get((p.id, s.class_row_id), False),
                        }
                        for s in (pl.seats if pl else [])
                    ),
                    key=lambda s: (s["room"], s["row"]),
                ),
                "invigilators": (invigilators or {}).get(p.allocator_ref, {}),
            }
        )
    return {
        "days": [{"date": d.isoformat(), "label": d.strftime("%a %d/%m/%Y").upper()} for d in built.problem.days],
        "sessions": list(term.exam_sessions or []),
        "papers": out,
        "practicals": practicals_of(db, term),
    }


def room_sheets(rec: dict[str, Any]) -> list[dict[str, Any]]:
    """Per date and session, each room with its papers, class rows, students and invigilator."""
    by_slot: dict[tuple[str, int], dict[str, dict[str, Any]]] = defaultdict(dict)
    for p in rec["papers"]:
        if p["day"] is None:
            continue
        for s in p["seating"]:
            room = by_slot[(p["day"], p["session"])].setdefault(
                s["room"], {"room": s["room"], "students": 0, "papers": {}}
            )
            room["students"] += s["students"]
            entry = room["papers"].setdefault(
                p["codes"],
                {
                    "codes": p["codes"],
                    "title": p["title"],
                    "rows": [],
                    "invigilator": (p["invigilators"].get(s["room"]) or p["invigilators"].get("") or {}).get("name"),
                },
            )
            part = f" (part {s['part']} of {s['parts']})" if s["parts"] > 1 else ""
            entry["rows"].append({"row": f"{s['row']}{part}", "students": s["students"], "odel": s["odel"]})
    out = []
    for (day, session), rooms in sorted(by_slot.items()):
        out.append(
            {
                "day": day,
                "session": session,
                "rooms": [
                    {**r, "papers": list(r["papers"].values())} for r in sorted(rooms.values(), key=lambda r: r["room"])
                ],
            }
        )
    return out


def _invigilators(teaching: TeachingClient | None, draft: ExamDraft) -> dict[str, Any]:
    if teaching is None or draft.shared_at is None:
        return {}
    try:
        return teaching.invigilators(str(draft.term_id))
    except ApiError:
        return {}


def grid(db: Session, draft: ExamDraft, teaching: TeachingClient | None = None) -> dict[str, Any]:
    """The draft, or a published version exactly as approved."""
    publication = db.scalar(
        select(ExamPublication).where(ExamPublication.draft_id == draft.id).order_by(ExamPublication.version.desc())
    )
    rec = publication.record if publication is not None else record(db, draft, _invigilators(teaching, draft))
    return {
        "draft": draft_summary(db, draft),
        "as_approved": publication is not None,
        "version": publication.version if publication else None,
        **rec,
        "rooms": room_sheets(rec),
    }


def _require_editable(draft: ExamDraft) -> None:
    if draft.status != DraftStatus.DRAFT:
        raise ApiError(409, "DRAFT_LOCKED", "A published exam draft can't be changed; copy it first.")


def move_paper(
    db: Session, identity: Identity, draft: ExamDraft, paper_id: str, day: str, session: int, pinned: bool = True
) -> dict[str, Any]:
    """Moves a paper to another date and session (checked), then re-seats both sessions."""
    _require_editable(draft)
    built = _built(db, draft)
    problem = built.problem
    days = [d.isoformat() for d in problem.days]
    if day not in days or not 0 <= session < problem.sessions:
        raise ApiError(422, "VALIDATION_ERROR", "That date and session aren't in the exam period.")
    placement = next((pl for pl in draft.placements if str(pl.paper_id) == paper_id), None)
    if placement is None:
        raise ApiError(404, "NOT_FOUND", "That paper isn't in this draft.")
    old = built.slots.get(paper_id, -1)
    new = days.index(day) * problem.sessions + session
    slots = {**built.slots, paper_id: new}
    unpinned = ExamProblem(
        papers=[p if p.id != paper_id else type(p)(p.id, p.label, p.rows) for p in problem.papers],
        days=problem.days,
        sessions=problem.sessions,
        rooms=problem.rooms,
        row_labels=problem.row_labels,
    )
    broken = [
        v
        for v in check(unpinned, slots)
        if (v.rule in ("H-E1", "H-E2") and paper_id in v.paper_ids) or (v.rule == "H-E3" and not v.paper_ids)
    ]
    if broken:
        raise ApiError(409, "BREAKS_RULE", broken[0].message, {"violations": [v.__dict__ for v in broken]})
    papers = {p.id: p for p in problem.papers}
    by_id = {str(pl.paper_id): pl for pl in draft.placements}
    for slot in {old, new} - {-1}:
        in_slot = [papers[pid] for pid, t in slots.items() if t == slot and pid in papers]
        try:
            new_seats = seating.seat_session(in_slot, problem.rooms)
        except seating.SeatingError as exc:
            raise ApiError(409, "NO_ROOM", str(exc)) from exc
        for pid in {p.id for p in in_slot}:
            by_id[pid].seats = [
                ExamSeat(
                    room_id=s.room_id, class_row_id=uuid.UUID(s.row_id), part=s.part, parts=s.parts, students=s.students
                )
                for s in new_seats
                if s.paper_id == pid
            ]
    placement.day = problem.days[problem.day_of(new)]
    placement.session = session
    placement.pinned = pinned
    draft.updated_at = utcnow()
    audit(db, identity, "exam_draft.move", "exam_draft", str(draft.id), {"paper": paper_id, "slot": old}, {"slot": new})
    db.commit()
    return draft_summary(db, draft)


def share(db: Session, identity: Identity, draft: ExamDraft) -> dict[str, Any]:
    """Departments see this draft's dates, sessions and rooms, and name invigilators on it."""
    db.execute(update(ExamDraft).where(ExamDraft.term_id == draft.term_id).values(shared_at=None))
    draft.shared_at = utcnow()
    audit(db, identity, "exam_draft.share", "exam_draft", str(draft.id), None, None)
    db.commit()
    return draft_summary(db, draft)


def copy_draft(db: Session, identity: Identity, draft: ExamDraft) -> ExamDraft:
    count = len(list(db.scalars(select(ExamDraft.id).where(ExamDraft.term_id == draft.term_id))))
    new = ExamDraft(
        term_id=draft.term_id, name=f"Exam draft {count + 1} (copy of {draft.name})", soft_scores=draft.soft_scores
    )
    for pl in draft.placements:
        new.placements.append(
            ExamPlacement(
                paper_id=pl.paper_id,
                day=pl.day,
                session=pl.session,
                pinned=pl.pinned,
                seats=[
                    ExamSeat(
                        room_id=s.room_id, class_row_id=s.class_row_id, part=s.part, parts=s.parts, students=s.students
                    )
                    for s in pl.seats
                ],
            )
        )
    db.add(new)
    db.flush()
    audit(db, identity, "exam_draft.copy", "exam_draft", str(new.id), None, {"from": str(draft.id)})
    db.commit()
    return new


def publish(
    db: Session, smarttt: SmartttClient, teaching: TeachingClient, identity: Identity, draft: ExamDraft
) -> dict[str, Any]:
    """
    The Director approves the exam draft as the term's next exam version and
    it is sent to SMARTTT. Every paper needs its invigilator. As with the
    teaching timetable, the approval stands when SMARTTT can't be reached (it
    is sent later); SMARTTT refusing it publishes nothing.
    """
    _require_editable(draft)
    summary = draft_summary(db, draft)
    if not summary["publishable"]:
        raise ApiError(
            409,
            "NOT_PUBLISHABLE",
            "This exam draft breaks hard rules or is out of date.",
            {"violations": summary["violations"][:20]},
        )
    if draft.shared_at is None:
        raise ApiError(409, "NOT_SHARED", "Share the draft with departments first, so they name the invigilators.")
    invigilators = teaching.invigilators(str(draft.term_id))
    rec = record(db, draft, invigilators)
    missing = [p["codes"] for p in rec["papers"] if not p["invigilators"].get("")]
    if missing:
        raise ApiError(
            409,
            "NO_INVIGILATOR",
            f"{len(missing)} papers have no invigilator yet: {', '.join(missing[:10])}.",
            {"papers": missing},
        )
    term = db.get(Term, draft.term_id)
    assert term is not None
    last = db.scalar(
        select(ExamPublication)
        .where(ExamPublication.term_id == term.id)
        .order_by(ExamPublication.version.desc())
        .limit(1)
    )
    version = (last.version if last else 0) + 1
    sessions = rec["sessions"]
    class_rows = {r.id: r for r in db.scalars(select(ClassRow).where(ClassRow.term_id == term.id))}

    def row_fields(s: dict[str, Any]) -> dict[str, Any]:
        row = class_rows.get(uuid.UUID(s["row_id"])) if s.get("row_id") else None
        if row is None:
            return {}
        return {
            "program_id": row.smarttt_program_id,
            "program_code": row.program_code,
            "year_of_study": row.study_year,
            "study_semester": row.study_semester,
            "stream": row.sub_class,
        }

    payload = {
        "term_id": term.smarttt_term_id,
        "academic_year": term.academic_year,
        "semester": term.semester,
        "version": version,
        "based_on_version": None,  # set when sent: the latest exam version SMARTTT has
        "published_by": identity.actor,
        "papers": [
            {
                "key": p["allocator_ref"],
                "codes": p.get("code_list") or p["codes"].split("/"),
                "sitting": p.get("sitting") or "regular",
                "title": p["title"],
                "date": p["day"],
                "start_time": sessions[p["session"]]["start"],
                "end_time": sessions[p["session"]]["end"],
                "examiner_staff_number": p["examiner_staff_number"],
                "seating": [
                    {
                        "room_code": s["room"],
                        "class_row": s["row"],
                        **row_fields(s),
                        "part": s["part"],
                        "parts": s["parts"],
                        "students": s["students"],
                        "invigilator_staff_number": (
                            p["invigilators"].get(s["room"]) or p["invigilators"].get("") or {}
                        ).get("staff_number"),
                    }
                    for s in p["seating"]
                ],
            }
            for p in rec["papers"]
        ],
        "practicals": [
            {
                "codes": pr["codes"].split("/"),
                "title": pr["title"],
                "department": pr["department"],
                "date": pr["date"],
                "start_time": pr["start_time"],
                "end_time": pr["end_time"],
            }
            for pr in rec["practicals"]
        ],
    }
    try:
        response = (
            _send(db, smarttt, term, payload) if _smarttt_can_place(term) else {"sent": False, "reason": NO_TERM_DATES}
        )
    except (SmartttUnavailable, SmartttMisconfigured) as down:
        response = {"sent": False, "reason": getattr(down, "message", None) or str(down) or "SMARTTT unavailable."}
    except SmartttRefused as refused:
        audit(
            db,
            identity,
            "exam_draft.publish_refused",
            "exam_draft",
            str(draft.id),
            None,
            {"version": version, "code": refused.code},
        )
        db.commit()
        raise
    db.add(
        ExamPublication(
            term_id=term.id,
            version=version,
            draft_id=draft.id,
            published_by=identity.actor,
            smarttt_response=response,
            payload=payload,
            record=rec,
        )
    )
    db.execute(
        update(ExamDraft)
        .where(ExamDraft.term_id == term.id, ExamDraft.status == DraftStatus.PUBLISHED)
        .values(status=DraftStatus.SUPERSEDED)
    )
    draft.status = DraftStatus.PUBLISHED
    audit(
        db,
        identity,
        "exam_draft.publish",
        "exam_draft",
        str(draft.id),
        None,
        {"version": version, "papers": len(rec["papers"])},
    )
    db.commit()
    return {"version": version, "smarttt": response, "draft": draft_summary(db, draft)}


def _send(db: Session, smarttt: SmartttClient, term: Term, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Sends an exam version to SMARTTT, made from the latest exam version SMARTTT
    received. A term SMARTTT found or created by year and semester is linked
    to its id. Raises the client's errors; the caller commits.
    """
    received = [
        p.version
        for p in db.scalars(select(ExamPublication).where(ExamPublication.term_id == term.id))
        if p.smarttt_response.get("sent")
    ]
    _status, response = smarttt.publish_exams(
        {
            **payload,
            "term_id": term.smarttt_term_id,
            "term_start": term.start_date.isoformat() if term.start_date else None,
            "term_end": term.end_date.isoformat() if term.end_date else None,
            "based_on_version": max(received, default=None),
        }
    )
    smarttt_term = str(response.get("term_id") or "")
    if (
        smarttt_term
        and not term.smarttt_term_id
        and db.scalar(select(Term).where(Term.smarttt_term_id == smarttt_term)) is None
    ):
        term.smarttt_term_id = smarttt_term
    return {"sent": True, **response}


def send_publication(
    db: Session, smarttt: SmartttClient, identity: Identity, term: Term, version: int
) -> dict[str, Any]:
    """
    Sends an approved exam version SMARTTT didn't receive (it was down, or the
    term had no dates), exactly as approved. Only the latest version is sent.
    """
    publication = db.scalar(
        select(ExamPublication).where(ExamPublication.term_id == term.id, ExamPublication.version == version)
    )
    if publication is None:
        raise ApiError(404, "NOT_FOUND", f"No exam version {version} for this term.")
    if publication.smarttt_response.get("sent"):
        raise ApiError(409, "ALREADY_SENT", f"SMARTTT already has exam version {version}.")
    latest = db.scalar(
        select(ExamPublication)
        .where(ExamPublication.term_id == term.id)
        .order_by(ExamPublication.version.desc())
        .limit(1)
    )
    if latest is not None and latest.version != version:
        raise ApiError(409, "NOT_LATEST", f"Exam version {latest.version} replaced version {version}; send that one.")
    if not _smarttt_can_place(term):
        raise ApiError(409, "NO_SMARTTT_TERM", NO_TERM_DATES)
    if not _has_class_rows(publication.payload):
        raise ApiError(
            409,
            "NOT_KEPT",
            "This version was approved before exam seating carried class rows. Copy its draft and approve the copy.",
        )
    try:
        response = _send(db, smarttt, term, publication.payload)
    except (SmartttUnavailable, SmartttMisconfigured) as down:
        reason = getattr(down, "message", None) or str(down) or "SMARTTT unavailable."
        raise ApiError(503, "SMARTTT_UNAVAILABLE", f"SMARTTT could not be reached: {reason} Try again later.") from down
    except SmartttRefused as refused:
        audit(
            db,
            identity,
            "exam_publication.send_refused",
            "exam_publication",
            str(publication.id),
            None,
            {"code": refused.code},
        )
        db.commit()
        raise
    publication.smarttt_response = response
    audit(db, identity, "exam_publication.send", "exam_publication", str(publication.id), None, {"version": version})
    db.commit()
    return next(p for p in publications(db, term) if p["version"] == version)


def _has_class_rows(payload: dict[str, Any] | None) -> bool:
    """Versions approved before seating carried each class row's programme can't show students their room."""
    if not payload:
        return False
    seats = [s for p in payload.get("papers") or [] for s in p.get("seating") or []]
    return all("program_code" in s for s in seats) and all(
        isinstance(pr.get("codes"), list) for pr in payload.get("practicals") or []
    )


def drafts_of(db: Session, term: Term) -> list[dict[str, Any]]:
    found = db.scalars(select(ExamDraft).where(ExamDraft.term_id == term.id).order_by(ExamDraft.created_at.desc()))
    return [
        {
            "id": str(d.id),
            "name": d.name,
            "status": d.status.value,
            "shared_at": d.shared_at.isoformat() if d.shared_at else None,
            "created_at": d.created_at.isoformat(),
        }
        for d in found
    ]


def publications(db: Session, term: Term) -> list[dict[str, Any]]:
    found = list(
        db.scalars(
            select(ExamPublication).where(ExamPublication.term_id == term.id).order_by(ExamPublication.version.desc())
        )
    )
    latest = found[0].version if found else None
    return [
        {
            "version": p.version,
            "draft_id": str(p.draft_id),
            "published_by": p.published_by,
            "published_at": p.published_at.isoformat(),
            "sent_to_smarttt": bool(p.smarttt_response.get("sent")),
            "not_sent_reason": p.smarttt_response.get("reason"),
            "can_send": (
                not p.smarttt_response.get("sent")
                and p.version == latest
                and _has_class_rows(p.payload)
                and _smarttt_can_place(term)
            ),
        }
        for p in found
    ]


def allocator_draft(db: Session, term: Term) -> dict[str, Any]:
    """The draft the Director shared, for departments to name invigilators on: papers by Attendance's ids."""
    draft = db.scalar(
        select(ExamDraft)
        .where(ExamDraft.term_id == term.id, ExamDraft.shared_at.is_not(None))
        .order_by(ExamDraft.shared_at.desc())
        .limit(1)
    )
    if draft is None:
        return {"draft": None, "papers": []}
    rec = record(db, draft)
    sessions = rec["sessions"]
    return {
        "draft": {
            "id": str(draft.id),
            "name": draft.name,
            "shared_at": draft.shared_at.isoformat() if draft.shared_at else None,
            "status": draft.status.value,
        },
        "papers": [
            {
                "paper_ref": p["allocator_ref"],
                # A list, as Smart Attendance reads it (the label, with "(ODEL)", is not a code).
                "codes": p["code_list"],
                "sitting": p["sitting"],
                "date": p["day"],
                "session": p["session"],
                "start_time": sessions[p["session"]]["start"] if p["session"] is not None else None,
                "end_time": sessions[p["session"]]["end"] if p["session"] is not None else None,
                "rooms": sorted({s["room"] for s in p["seating"]}),
            }
            for p in rec["papers"]
        ],
    }


def practical_count(db: Session, term: Term) -> int:
    return len(list(db.scalars(select(ExamPractical.id).where(ExamPractical.term_id == term.id))))
