"""
What the Timetable Allocator reads from the Generator: the terms (departments
enter their teaching against them) and, once the Director has published a
version, when and where each class meets, which departments see on their
pages and downloads.

Read-only, behind the Allocator's own shared key (X-API-Key = ALLOCATOR_API_KEY).
"""

from __future__ import annotations

import hmac
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.errors import ApiError
from app.models import DraftSession, Publication, Room, Term, UnitOffering
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


def allocator_times(db: Session, term: Term) -> dict[str, Any]:
    """When and where each class meets in the latest approved version, by class key ('COSC103-GRA')."""
    publication = latest_publication(db, term)
    if publication is None:
        return {"published_version": None, "classes": {}}
    classes: dict[str, list[dict[str, str]]] = {}
    if publication.record is not None:
        for c in publication.record:
            classes.setdefault(section_key(c["unit_code"], c["group"]), []).append(
                {"day_of_week": c["day"], "start_time": c["start_time"], "end_time": c["end_time"], "room": c["room"]}
            )
    else:  # approved before versions were kept as approved
        room_codes = {r.id: r.code for r in db.scalars(select(Room))}
        groups = {
            g.id: section_key(o.unit_code, g.label)
            for o in db.scalars(select(UnitOffering).where(UnitOffering.term_id == term.id))
            for g in o.groups
        }
        for ds in db.scalars(select(DraftSession).where(DraftSession.draft_id == publication.draft_id)):
            if ds.group_id not in groups:
                continue
            day, start, end = times(ds.start_slot, ds.length)
            classes.setdefault(groups[ds.group_id], []).append(
                {
                    "day_of_week": day,
                    "start_time": start,
                    "end_time": end,
                    "room": room_codes.get(ds.smarttt_room_id, ds.smarttt_room_id),
                }
            )
    return {
        "published_version": publication.version,
        "classes": {key: sorted(meetings, key=_meeting_order) for key, meetings in classes.items()},
    }
