"""
What the Timetable Allocator reads from the Generator: each term's units and
their groups (the classes departments allocate lecturers to), and, once the
Director has published a version, when and where each class meets.

Read-only, behind the Allocator's own shared key (X-API-Key = ALLOCATOR_API_KEY),
so departments can start allocating as soon as the units and groups exist.
"""

from __future__ import annotations

import hmac
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.errors import ApiError
from app.models import ClassRow, Department, DraftSession, Publication, Room, Term, UnitOffering
from app.services.problem import times
from app.services.setup import compact


def require_allocator_key(request: Request, settings: Annotated[Settings, Depends(get_settings)]) -> None:
    """Fails closed: with ALLOCATOR_API_KEY unset, every request is refused."""
    expected = settings.allocator_api_key
    presented = request.headers.get("X-API-Key", "")
    if not expected or not hmac.compare_digest(presented.encode(), expected.encode()):
        raise ApiError(401, "INVALID_API_KEY", "A valid X-API-Key header is required.")


def section_key(unit_code: str, group_label: str) -> str:
    """'COSC 103', 'GR A' -> 'COSC103-GRA'; a unit that isn't split -> 'COSC103-MAIN'."""
    return f"{compact(unit_code)}-{compact(group_label) or 'MAIN'}"


def smarttt_section_key(offering: UnitOffering, group_label: str) -> str | None:
    """
    The class's key in SMARTTT ('412-GRA': SMARTTT's unit id and the group),
    where the Allocator sends its lecturer. None for a unit SMARTTT doesn't
    have, which SMARTTT can't timetable either.
    """
    if offering.smarttt_unit_id is None:
        return None
    return f"{offering.smarttt_unit_id}-{compact(group_label) or 'MAIN'}"


def in_smarttt(publication: Publication | None) -> bool:
    """Whether SMARTTT has this approved version (approved while SMARTTT was down: not yet)."""
    return publication is not None and bool(publication.smarttt_response.get("sent", True))


def latest_publication(db: Session, term: Term) -> Publication | None:
    return db.scalar(
        select(Publication).where(Publication.term_id == term.id).order_by(Publication.version.desc()).limit(1)
    )


def allocator_terms(db: Session) -> list[dict[str, Any]]:
    out = []
    for t in db.scalars(select(Term).order_by(Term.academic_year.desc(), Term.semester.desc())):
        publication = latest_publication(db, t)
        out.append(
            {
                "id": str(t.id),
                "academic_year": t.academic_year,
                "semester": t.semester,
                "name": t.name,
                "smarttt_term_id": t.smarttt_term_id,
                "published_version": publication.version if publication else None,
                "in_smarttt": in_smarttt(publication),
            }
        )
    return out


def _meeting_order(m: dict[str, str]) -> tuple[int, str]:
    return ("MON", "TUE", "WED", "THU", "FRI").index(m["day_of_week"]), m["start_time"]


def allocator_sections(db: Session, term: Term) -> dict[str, Any]:
    departments = {d.id: d for d in db.scalars(select(Department))}
    rows = {r.id: r for r in db.scalars(select(ClassRow).where(ClassRow.term_id == term.id))}
    publication = latest_publication(db, term)
    meetings: dict[Any, list[dict[str, str]]] = {}
    room_codes: dict[str, str] = {}
    # An approved version's meetings, as approved (by section key).
    approved: dict[str, list[dict[str, str]]] | None = None
    if publication is not None and publication.record is not None:
        approved = {}
        for c in publication.record:
            approved.setdefault(section_key(c["unit_code"], c["group"]), []).append(
                {"day_of_week": c["day"], "start_time": c["start_time"], "end_time": c["end_time"], "room": c["room"]}
            )
    elif publication is not None:  # approved before versions were kept as approved
        room_codes = {r.id: r.code for r in db.scalars(select(Room))}
        for s in db.scalars(select(DraftSession).where(DraftSession.draft_id == publication.draft_id)):
            day, start, end = times(s.start_slot, s.length)
            meetings.setdefault(s.group_id, []).append(
                {
                    "day_of_week": day,
                    "start_time": start,
                    "end_time": end,
                    "room": room_codes.get(s.smarttt_room_id, s.smarttt_room_id),
                }
            )

    def dept(dept_id: int | None) -> dict[str, Any] | None:
        d = departments.get(dept_id) if dept_id is not None else None
        if d is None:
            return None
        return {"id": d.id, "code": d.code, "name": d.name, "smarttt_id": d.smarttt_department_id}

    sections = []
    for o in db.scalars(select(UnitOffering).where(UnitOffering.term_id == term.id).order_by(UnitOffering.unit_code)):
        for g in o.groups:
            members = [rows[m.class_row_id] for m in g.members if m.class_row_id in rows]
            sections.append(
                {
                    "key": section_key(o.unit_code, g.label),
                    "smarttt_key": smarttt_section_key(o, g.label),
                    "unit_code": o.unit_code,
                    "unit_name": o.unit_name,
                    "group": g.label or None,
                    "department": dept(o.owning_department_id),
                    "students": g.student_count,
                    "weekly_hours": o.weekly_hours,
                    "class_rows": [
                        {
                            "label": r.label,
                            "program_code": r.program_code,
                            "study_year": r.study_year,
                            "study_semester": r.study_semester,
                            "students": next((m.students for m in g.members if m.class_row_id == r.id), None),
                            "department": dept(r.department_id),
                        }
                        for r in members
                    ],
                    "meetings": sorted(
                        approved.get(section_key(o.unit_code, g.label), [])
                        if approved is not None
                        else meetings.get(g.id, []),
                        key=_meeting_order,
                    ),
                }
            )
    return {
        "term": {
            "id": str(term.id),
            "academic_year": term.academic_year,
            "semester": term.semester,
            "name": term.name,
            "smarttt_term_id": term.smarttt_term_id,
        },
        "published_version": publication.version if publication else None,
        # The Allocator sends lecturers to SMARTTT only once SMARTTT has the version.
        "in_smarttt": in_smarttt(publication),
        "sections": sections,
    }
