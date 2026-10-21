"""
Drafts: reviewing them as grids (per class row, room or department), moving
sessions by hand with every hard rule checked, and publishing one to SMARTTT
once the Director approves it.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth import Identity
from app.clients.smarttt import SmartttClient, SmartttMisconfigured, SmartttRefused, SmartttUnavailable
from app.errors import ApiError
from app.models import Department, Draft, DraftSession, DraftStatus, Publication, RunMode, Term, UnitOffering
from app.services.problem import Built, build_problem, placements_of, times
from app.services.setup import audit, latest_snapshot
from app.solver.model import DAYS, Placement, Weights, slot, valid_start
from app.solver.scoring import score
from app.solver.validate import check

VIEWS = ("row", "room", "department")


def get_draft(db: Session, draft_id: str) -> Draft:
    try:
        draft = db.get(Draft, uuid.UUID(str(draft_id)))
    except ValueError:
        draft = None
    if draft is None:
        raise ApiError(404, "NOT_FOUND", "No such draft.")
    return draft


def _built(db: Session, draft: Draft) -> Built:
    term = db.get(Term, draft.term_id)
    snapshot = latest_snapshot(db, term) if term else None
    if term is None or snapshot is None:
        raise ApiError(409, "NO_SNAPSHOT", "The term has no snapshot.")
    return build_problem(db, term, snapshot, Weights(), RunMode.RESOLVE, draft)


def _staleness(built: Built, draft: Draft) -> dict[str, list[str]]:
    """Sessions the draft lacks or has extra, after groups or hours changed since it was made."""
    wanted = {s.key for s in built.problem.sessions}
    have = {s.key for s in draft.sessions}
    return {"missing": sorted(wanted - have)[:100], "extra": sorted(have - wanted)[:100]}


def draft_summary(db: Session, draft: Draft) -> dict[str, Any]:
    built = _built(db, draft)
    placements = placements_of(draft)
    violations = check(built.problem, placements)
    stale = _staleness(built, draft)
    return {
        "id": str(draft.id),
        "term_id": str(draft.term_id),
        "name": draft.name,
        "status": draft.status.value,
        "run_id": str(draft.run_id) if draft.run_id else None,
        "parent_draft_id": str(draft.parent_draft_id) if draft.parent_draft_id else None,
        "created_at": draft.created_at.isoformat(),
        "updated_at": draft.updated_at.isoformat(),
        "session_count": len(draft.sessions),
        "pinned": sum(1 for s in draft.sessions if s.pinned),
        "soft_scores": score(built.problem, placements),
        "violations": [v.__dict__ for v in violations[:100]],
        "violation_count": len(violations),
        "stale": stale,
        "publishable": not violations
        and not stale["missing"]
        and not stale["extra"]
        and draft.status == DraftStatus.DRAFT,
    }


# What a timetable cell shows; the other fields of a class only place it in a view.
CELL_FIELDS = (
    "key",
    "unit_code",
    "group",
    "room_id",
    "room",
    "day",
    "start_time",
    "end_time",
    "start_slot",
    "length",
    "pinned",
    "students",
)


def _cells(db: Session, draft: Draft) -> list[dict[str, Any]]:
    """Every class in the draft, with what each view needs, from the term's current data."""
    built = _built(db, draft)
    by_key = {s.key: s for s in built.problem.sessions}
    snapshot = latest_snapshot(db, db.get(Term, draft.term_id))  # type: ignore[arg-type]
    department_names = {str(d["id"]): d["name"] for d in (snapshot.data["departments"] if snapshot else [])}
    cells = []
    for ds in draft.sessions:
        s = by_key.get(ds.key)
        group = built.groups.get(ds.key)
        offering = built.offerings.get(ds.key)
        room = built.rooms.get(ds.smarttt_room_id, {})
        day, start, end = times(ds.start_slot, ds.length)
        department = str(offering.owning_department_id if offering else 0)
        class_rows = []
        for row_id in s.class_row_ids if s else []:
            row = built.rows.get(uuid.UUID(row_id))
            class_rows.append({"id": row_id, "label": row.label if row else row_id})
        cells.append(
            {
                "key": ds.key,
                "unit_code": offering.unit_code if offering else ds.key,
                "group": group.label if group else "",
                "room_id": ds.smarttt_room_id,
                "room": room.get("code", "?"),
                "day": day,
                "start_time": start,
                "end_time": end,
                "start_slot": ds.start_slot,
                "length": ds.length,
                "pinned": ds.pinned,
                "students": s.students if s else None,
                "class_rows": class_rows,
                "department": {"id": department, "name": department_names.get(department, f"Department {department}")},
                "room_capacity": room.get("capacity"),
                "room_building": room.get("building"),
            }
        )
    return cells


def _layout(cells: list[dict[str, Any]], view: str) -> list[dict[str, Any]]:
    entities: dict[str, dict[str, Any]] = {}

    def entity(eid: str, label: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        if eid not in entities:
            entities[eid] = {"id": eid, "label": label, "cells": [], **(extra or {})}
        return entities[eid]

    for c in cells:
        cell = {k: c.get(k) for k in CELL_FIELDS}
        if view == "room":
            extra = {"capacity": c.get("room_capacity"), "building": c.get("room_building")}
            entity(c["room_id"], c["room"], extra)["cells"].append(cell)
        elif view == "department":
            entity(c["department"]["id"], c["department"]["name"])["cells"].append(cell)
        else:
            for row in c["class_rows"]:
                entity(row["id"], row["label"])["cells"].append(cell)
    ordered = sorted(entities.values(), key=lambda e: e["label"])
    for e in ordered:
        e["cells"].sort(key=lambda c: (c["start_slot"], c["unit_code"]))
    return ordered


def publication_of(db: Session, draft: Draft) -> Publication | None:
    """The version this draft was approved as, if it was."""
    if draft.status == DraftStatus.DRAFT:
        return None
    return db.scalar(
        select(Publication).where(Publication.draft_id == draft.id).order_by(Publication.version.desc()).limit(1)
    )


def grid(db: Session, draft: Draft, view: str) -> dict[str, Any]:
    """
    The draft laid out like the printed timetable: one grid per class row,
    room or department. An approved version shows (and downloads) exactly as
    it was approved, whatever has been edited since.
    """
    if view not in VIEWS:
        raise ApiError(422, "VALIDATION_ERROR", f"view must be one of {', '.join(VIEWS)}.")
    publication = publication_of(db, draft)
    frozen = publication.record if publication is not None else None
    return {
        "draft": draft_summary(db, draft),
        "view": view,
        "days": list(DAYS),
        "first_hour": 7,
        "hours": 12,
        "as_approved": frozen is not None,
        "entities": _layout(frozen if frozen is not None else _cells(db, draft), view),
    }


def _require_editable(draft: Draft) -> None:
    if draft.status != DraftStatus.DRAFT:
        raise ApiError(409, "DRAFT_LOCKED", "A published draft can't be changed; copy it to a new draft first.")


def move_session(
    db: Session,
    identity: Identity,
    draft: Draft,
    key: str,
    day: str | None,
    start_time: str | None,
    room_id: str | None,
    pinned: bool | None,
) -> dict[str, Any]:
    """
    Moves (and by default pins) one session. Refused with 409 when the move
    would break a hard rule that the draft didn't already break, so the
    Director gets the reason and nothing changes.
    """
    _require_editable(draft)
    ds = next((s for s in draft.sessions if s.key == key), None)
    if ds is None:
        raise ApiError(404, "NOT_FOUND", "No such session in this draft.")
    built = _built(db, draft)
    before = placements_of(draft)
    new_start = ds.start_slot
    if day is not None or start_time is not None:
        cur_day, cur_start, _end = times(ds.start_slot, ds.length)
        d = day or cur_day
        hour = int((start_time or cur_start).split(":")[0])
        new_start = slot(DAYS.index(d), hour)
        if not valid_start(new_start, ds.length):
            raise ApiError(
                409,
                "HARD_RULE",
                f"{key} must fit in one day between 07:00 and 19:00.",
                {"violations": [{"rule": "H6", "message": "Outside teaching hours."}]},
            )
    new_room = room_id or ds.smarttt_room_id
    after = {**before, key: Placement(start=new_start, room_id=new_room)}

    # A pin the Director placed is not a rule the move itself breaks.
    built.problem.sessions = [replace(s, pinned=None) if s.key == key else s for s in built.problem.sessions]
    old = {(v.rule, v.message) for v in check(built.problem, before)}
    new = [v for v in check(built.problem, after) if (v.rule, v.message) not in old]
    if new:
        raise ApiError(409, "HARD_RULE", new[0].message, {"violations": [v.__dict__ for v in new[:20]]})

    previous = {"start_slot": ds.start_slot, "room_id": ds.smarttt_room_id, "pinned": ds.pinned}
    ds.start_slot = new_start
    ds.smarttt_room_id = new_room
    ds.pinned = True if pinned is None else pinned
    audit(
        db,
        identity,
        "draft.move",
        "draft_session",
        f"{draft.id}:{key}",
        previous,
        {"start_slot": new_start, "room_id": new_room, "pinned": ds.pinned},
    )
    db.commit()
    return draft_summary(db, draft)


def copy_draft(db: Session, identity: Identity, draft: Draft) -> Draft:
    count = db.query(Draft).filter(Draft.term_id == draft.term_id).count()
    copy = Draft(
        term_id=draft.term_id,
        run_id=None,
        parent_draft_id=draft.id,
        name=f"Draft {count + 1} (copy)",
        soft_scores=draft.soft_scores,
    )
    for s in draft.sessions:
        copy.sessions.append(
            DraftSession(
                key=s.key,
                group_id=s.group_id,
                index=s.index,
                smarttt_room_id=s.smarttt_room_id,
                start_slot=s.start_slot,
                length=s.length,
                pinned=s.pinned,
            )
        )
    db.add(copy)
    db.flush()
    audit(db, identity, "draft.copy", "draft", str(copy.id), None, {"from": str(draft.id)})
    db.commit()
    return copy


def publish(
    db: Session, smarttt: SmartttClient, identity: Identity, draft: Draft, replace_unpublished: bool
) -> dict[str, Any]:
    """
    The Director approves the draft and it becomes the term's next published
    version in SMARTTT. Only a complete draft that breaks no hard rule can be
    published; SMARTTT re-validates it, refuses it if someone published in
    between, and pushes the changes on to Smart Attendance.
    """
    _require_editable(draft)
    summary = draft_summary(db, draft)
    if not summary["publishable"]:
        raise ApiError(
            409,
            "NOT_PUBLISHABLE",
            "This draft breaks hard rules or is out of date with the groups.",
            {"violations": summary["violations"][:20], "stale": summary["stale"]},
        )
    term = db.get(Term, draft.term_id)
    if term is None:
        raise ApiError(404, "NOT_FOUND", "No such term.")
    built = _built(db, draft)
    last = db.scalar(
        select(Publication).where(Publication.term_id == term.id).order_by(Publication.version.desc()).limit(1)
    )
    version = (last.version if last else 0) + 1
    sessions = _sessions_payload(db, draft, built)
    payload: dict[str, Any] = {
        "term_id": term.smarttt_term_id,
        "academic_year": term.academic_year,
        "semester": term.semester,
        # SMARTTT creates the term from these when it doesn't have it yet.
        "term_start": term.start_date.isoformat() if term.start_date else None,
        "term_end": term.end_date.isoformat() if term.end_date else None,
        "version": version,
        "based_on_version": None,  # set when sent: the latest version SMARTTT has
        "published_by": identity.actor,
        "replace_unpublished": replace_unpublished,
        "sessions": sessions,
    }
    # The Director's approval stands even when SMARTTT can't be told yet
    # (SMARTTT down): the version is recorded here, downloads and the Allocator
    # use it, and `sent` says it still has to reach SMARTTT. SMARTTT refusing
    # the timetable (409/422) is different: it is reported and nothing is
    # published.
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
            "draft.publish_refused",
            "draft",
            str(draft.id),
            None,
            {"version": version, "code": refused.code},
        )
        db.commit()
        raise

    publication = Publication(
        term_id=term.id,
        version=version,
        draft_id=draft.id,
        published_by=identity.actor,
        smarttt_response=response,
        payload=payload,
        record=_cells(db, draft),
    )
    db.add(publication)
    db.execute(
        update(Draft)
        .where(Draft.term_id == term.id, Draft.status == DraftStatus.PUBLISHED)
        .values(status=DraftStatus.SUPERSEDED)
    )
    draft.status = DraftStatus.PUBLISHED
    audit(
        db,
        identity,
        "draft.publish",
        "draft",
        str(draft.id),
        None,
        {"version": version, "sessions": len(sessions), "changes": response.get("changes")},
    )
    db.commit()
    return {"version": version, "smarttt": response, "draft": draft_summary(db, draft)}


NO_TERM_DATES = "SMARTTT doesn't have this term yet: give it its start and end dates, then send this version."


def _smarttt_can_place(term: Term) -> bool:
    """SMARTTT has the term, or can create it from its dates."""
    return bool(term.smarttt_term_id or (term.start_date and term.end_date))


def _sessions_payload(db: Session, draft: Draft, built: Built) -> list[dict[str, Any]]:
    """
    Each session as SMARTTT's publish endpoint takes it: ids where the
    Generator has SMARTTT's, and always the codes, names, owning department,
    room details and class rows, so SMARTTT can match (or create) units, rooms
    and programmes entered in the Generator.
    """
    departments = {d.id: d for d in db.scalars(select(Department))}

    def department(department_id: int | None) -> dict[str, Any]:
        d = departments.get(department_id) if department_id is not None else None
        if d is None:
            return {"smarttt_id": None, "code": "", "name": ""}
        return {"smarttt_id": d.smarttt_department_id, "code": d.code, "name": d.name}

    sessions = []
    for ds in draft.sessions:
        group = built.groups[ds.key]
        offering = built.offerings[ds.key]
        day, start, end = times(ds.start_slot, ds.length)
        room = built.rooms.get(ds.smarttt_room_id, {})
        rows = [built.rows[m.class_row_id] for m in group.members]
        sessions.append(
            {
                "key": ds.key,
                "unit_id": offering.smarttt_unit_id,
                "unit_code": offering.unit_code,
                "unit_name": offering.unit_name,
                "weekly_hours": offering.weekly_hours,
                "department": department(offering.owning_department_id),
                "group_label": group.label or None,
                "room_id": ds.smarttt_room_id,
                "room": {
                    "code": room.get("code") or str(ds.smarttt_room_id),
                    "building": room.get("building") or "",
                    "capacity": room.get("capacity") or 1,
                    "room_type": room.get("room_type") or "lecture_hall",
                },
                "class_rows": [
                    {
                        "label": r.label,
                        "program_id": r.smarttt_program_id,
                        "program_code": r.program_code,
                        "year_of_study": r.study_year,
                        "study_semester": r.study_semester,
                        "stream": r.sub_class,
                        "department_smarttt_id": department(r.department_id)["smarttt_id"],
                    }
                    for r in rows
                ],
                "day_of_week": day,
                "start_time": start,
                "end_time": end,
            }
        )
    return sessions


def _send(db: Session, smarttt: SmartttClient, term: Term, payload: dict[str, Any]) -> dict[str, Any]:
    """
    Sends a version to SMARTTT, made from the latest version SMARTTT has
    received (a version it missed is not its base). A term created here is
    found or created there by year and semester, then linked to SMARTTT's id,
    and units SMARTTT matched or created are linked to theirs. Raises the
    client's errors; the caller commits.
    """
    received = [
        p.version
        for p in db.scalars(select(Publication).where(Publication.term_id == term.id))
        if p.smarttt_response.get("sent", True)
    ]
    _status, response = smarttt.publish(
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
    unit_ids: dict[str, Any] = response.get("units") or {}
    linked = {o.smarttt_unit_id for o in db.scalars(select(UnitOffering).where(UnitOffering.term_id == term.id))}
    for offering in db.scalars(
        select(UnitOffering).where(UnitOffering.term_id == term.id, UnitOffering.smarttt_unit_id.is_(None))
    ):
        unit_id = unit_ids.get(offering.unit_code)
        if isinstance(unit_id, int) and unit_id not in linked:
            offering.smarttt_unit_id = unit_id
            linked.add(unit_id)
    return {"sent": True, **response}


def publications(db: Session, term: Term) -> list[dict[str, Any]]:
    rows = list(
        db.scalars(select(Publication).where(Publication.term_id == term.id).order_by(Publication.version.desc()))
    )
    latest = rows[0].version if rows else None
    return [
        {
            "version": p.version,
            "draft_id": str(p.draft_id),
            "published_by": p.published_by,
            "published_at": p.published_at.isoformat(),
            "changes": p.smarttt_response.get("changes"),
            # False: approved here but not (yet) received by SMARTTT.
            "sent_to_smarttt": bool(p.smarttt_response.get("sent", True)),
            "not_sent_reason": p.smarttt_response.get("reason"),
            "can_send": (
                not p.smarttt_response.get("sent", True)
                and p.version == latest
                and p.payload is not None
                and _smarttt_can_place(term)
            ),
        }
        for p in rows
    ]


def send_publication(
    db: Session, smarttt: SmartttClient, identity: Identity, term: Term, version: int
) -> dict[str, Any]:
    """
    Sends an approved version that SMARTTT didn't receive (it was down, or the
    term wasn't linked yet) exactly as it was approved. Only the term's latest
    version can be sent, so SMARTTT never moves back to an older timetable.
    """
    publication = db.scalar(select(Publication).where(Publication.term_id == term.id, Publication.version == version))
    if publication is None:
        raise ApiError(404, "NOT_FOUND", f"No version {version} for this term.")
    if publication.smarttt_response.get("sent", True):
        raise ApiError(409, "ALREADY_SENT", f"SMARTTT already has version {version}.")
    latest = db.scalar(
        select(Publication).where(Publication.term_id == term.id).order_by(Publication.version.desc()).limit(1)
    )
    if latest is not None and latest.version != version:
        raise ApiError(409, "NOT_LATEST", f"Version {latest.version} replaced version {version}; send that one.")
    if not _smarttt_can_place(term):
        raise ApiError(409, "NO_SMARTTT_TERM", NO_TERM_DATES)
    if publication.payload is None:
        raise ApiError(
            409,
            "NOT_KEPT",
            "This version was approved before versions were kept as approved. Copy its draft and approve the copy.",
        )
    try:
        response = _send(db, smarttt, term, publication.payload)
    except (SmartttUnavailable, SmartttMisconfigured) as down:
        reason = getattr(down, "message", None) or str(down) or "SMARTTT unavailable."
        raise ApiError(503, "SMARTTT_UNAVAILABLE", f"SMARTTT could not be reached: {reason} Try again later.") from down
    except SmartttRefused as refused:
        audit(
            db, identity, "publication.send_refused", "publication", str(publication.id), None, {"code": refused.code}
        )
        db.commit()
        raise
    publication.smarttt_response = response
    audit(db, identity, "publication.send", "publication", str(publication.id), None, {"version": version})
    db.commit()
    return next(p for p in publications(db, term) if p["version"] == version)


def drafts_of(db: Session, term: Term) -> list[dict[str, Any]]:
    rows = db.scalars(select(Draft).where(Draft.term_id == term.id).order_by(Draft.created_at.desc()))
    return [
        {
            "id": str(d.id),
            "name": d.name,
            "status": d.status.value,
            "created_at": d.created_at.isoformat(),
            "soft_scores": d.soft_scores,
            "session_count": len(d.sessions),
        }
        for d in rows
    ]
