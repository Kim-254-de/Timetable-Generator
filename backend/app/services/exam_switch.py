"""
Switching SMARTTT from teaching to exams, as the Director schedules it.

Once an exam version is published, the Director sets when SMARTTT switches
the term to exam mode (by default the first exam day at 00:00, campus time),
can move or cancel it, or switch now; and likewise schedule or do the close of
the exam period (by default the day after the last exam day). SMARTTT holds
the mode and flips it when the time comes; every action here calls SMARTTT,
keeps the state it confirms, and is audited.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Identity
from app.clients.smarttt import SmartttClient, SmartttError
from app.errors import ApiError
from app.models import ExamPublication, Term, utcnow
from app.services.exam_setup import exam_days
from app.services.setup import audit

# Campus time (Africa/Nairobi, UTC+3 all year).
CAMPUS = timezone(timedelta(hours=3), "EAT")
SWITCH_ACTIONS = ("schedule_switch", "cancel_switch", "switch_now")
CLOSE_ACTIONS = ("schedule_close", "cancel_close", "close_now")


def _parse(value: Any) -> datetime | None:
    if not value:
        return None
    moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _iso(moment: datetime | None) -> str | None:
    return moment.astimezone(CAMPUS).isoformat() if moment else None


def _aware(moment: datetime | None) -> datetime | None:
    return moment.replace(tzinfo=UTC) if moment is not None and moment.tzinfo is None else moment


def defaults(term: Term) -> dict[str, str | None]:
    """The first exam day at 00:00, and the day after the last one, campus time."""
    days = exam_days(term)
    if not days:
        return {"switch_at": None, "close_at": None}
    return {
        "switch_at": datetime.combine(days[0], time(0), CAMPUS).isoformat(),
        "close_at": datetime.combine(days[-1] + timedelta(days=1), time(0), CAMPUS).isoformat(),
    }


def _published(db: Session, term: Term) -> ExamPublication | None:
    return db.scalar(
        select(ExamPublication)
        .where(ExamPublication.term_id == term.id)
        .order_by(ExamPublication.version.desc())
        .limit(1)
    )


def _keep(term: Term, data: dict[str, Any]) -> None:
    """Keeps the state SMARTTT confirmed."""
    term.exam_switch_at = _parse(data.get("exam_switch_at"))
    term.exam_switched_at = _parse(data.get("switched_at"))
    term.exam_switched_by = data.get("switched_by")
    term.exam_close_at = _parse(data.get("exam_close_at"))
    term.exam_closed_at = _parse(data.get("exam_closed_at"))
    term.exam_closed_by = data.get("closed_by")


def state(db: Session, smarttt: SmartttClient | None, term: Term) -> dict[str, Any]:
    """The switch as SMARTTT has it (as last confirmed, when SMARTTT can't be reached)."""
    reachable = None
    if smarttt is not None and term.smarttt_term_id:
        try:
            _keep(term, smarttt.exam_mode(term.smarttt_term_id))
            db.commit()
            reachable = True
        except SmartttError:
            reachable = False
    now = utcnow()
    switch_at, switched_at = _aware(term.exam_switch_at), _aware(term.exam_switched_at)
    close_at, closed_at = _aware(term.exam_close_at), _aware(term.exam_closed_at)
    if closed_at is not None or (close_at is not None and close_at <= now):
        status, label = (
            "closed",
            f"Closed on {_label(closed_at or close_at)}"
            + (f" by {term.exam_closed_by}" if term.exam_closed_by else ""),
        )
    elif switched_at is not None or (switch_at is not None and switch_at <= now):
        status = "switched"
        label = f"Switched on {_label(switched_at or switch_at)}" + (
            f" by {term.exam_switched_by}" if term.exam_switched_by else ""
        )
        if close_at is not None:
            label += f"; closes {_label(close_at)}"
    elif switch_at is not None:
        status, label = "scheduled", f"Scheduled for {_label(switch_at)}"
    else:
        status, label = "teaching", "SMARTTT shows the teaching timetable."
    return {
        "status": status,
        "label": label,
        "switch_at": _iso(switch_at),
        "switched_at": _iso(switched_at),
        "switched_by": term.exam_switched_by,
        "close_at": _iso(close_at),
        "closed_at": _iso(closed_at),
        "closed_by": term.exam_closed_by,
        "published_version": (p.version if (p := _published(db, term)) else None),
        "in_smarttt": bool(term.smarttt_term_id),
        "smarttt_reachable": reachable,
        "defaults": defaults(term),
    }


def _label(moment: datetime | None) -> str:
    return moment.astimezone(CAMPUS).strftime("%a %d %b %Y %H:%M") if moment else ""


def act(
    db: Session, smarttt: SmartttClient, identity: Identity, term: Term, action: str, at: datetime | None
) -> dict[str, Any]:
    if action not in SWITCH_ACTIONS + CLOSE_ACTIONS:
        raise ApiError(422, "VALIDATION_ERROR", "Unknown action.")
    if not term.smarttt_term_id:
        raise ApiError(409, "NOT_IN_SMARTTT", "This term exists only in the Generator, so SMARTTT can't switch it.")
    if action in ("schedule_switch", "switch_now") and _published(db, term) is None:
        raise ApiError(409, "NO_EXAM_VERSION", "Publish an exam timetable first; there is nothing to switch to.")
    current = state(db, None, term)
    if action in CLOSE_ACTIONS and current["status"] == "teaching":
        raise ApiError(409, "NOT_SWITCHED", "Schedule or do the switch to exams before closing the exam period.")
    when: datetime | None = None
    if action in ("schedule_switch", "schedule_close"):
        default = defaults(term)["switch_at" if action == "schedule_switch" else "close_at"]
        when = _parse(at) if at is not None else _parse(default)
        if when is None:
            raise ApiError(422, "VALIDATION_ERROR", "Give the date and time, or set the exam period first.")
        if when <= utcnow():
            raise ApiError(422, "VALIDATION_ERROR", "Pick a time in the future, or use the 'now' action.")
        switch_at = _aware(term.exam_switch_at)
        if action == "schedule_close" and switch_at is not None and when <= switch_at:
            raise ApiError(422, "VALIDATION_ERROR", "The exam period must close after the switch to exams.")
    before = {k: current[k] for k in ("status", "switch_at", "switched_at", "close_at", "closed_at")}
    data = smarttt.set_exam_mode(term.smarttt_term_id, action, _iso(when), identity.actor)
    _keep(term, data)
    after = state(db, None, term)
    audit(
        db,
        identity,
        f"exam_mode.{action}",
        "term",
        str(term.id),
        before,
        {**{k: after[k] for k in before}, "at": _iso(when)},
    )
    db.commit()
    return after
