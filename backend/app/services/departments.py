"""
Departments come from Smart Attendance.

An administrator creates the university's departments in Attendance, each
with a name and a code (Attendance creates them in SMARTTT first, the owner);
faculties play no part. The Generator reads them over Attendance's Generator
endpoint (app.clients.attendance) and keeps a copy, because units and class
rows hang off it. The name and the code (printed on timetables and how
imported teaching names its department) are Attendance's and are refreshed at every read; a code is
made here only for a department Attendance has none for. The lecturer count
(rule H9) is the Generator's own.

A department in Attendance is matched to one here by Attendance's id, then
by SMARTTT's id, then by name ("Department of Computer Science" = "computer
science"), so departments entered here before keep their code, units and
class rows. New ones are added with SMARTTT's id as their id where possible,
which is what publishing to SMARTTT sends.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import Identity
from app.clients.attendance import AttendanceClient, AttendanceError
from app.config import get_settings
from app.models import Department
from app.services.master import FIRST_LOCAL_DEPARTMENT_ID, department_dict, name_key, new_department_code
from app.services.setup import audit

logger = logging.getLogger(__name__)

_last_sync = 0.0
_lock = threading.Lock()


def _free_id(db: Session, wanted: int | None) -> int:
    if wanted is not None and db.get(Department, wanted) is None:
        return wanted
    return max(int(db.scalar(select(func.max(Department.id))) or 0) + 1, FIRST_LOCAL_DEPARTMENT_ID)


def sync_departments(
    db: Session, attendance: AttendanceClient, identity: Identity, *, force: bool = False
) -> dict[str, Any] | None:
    """
    Brings the departments in line with Attendance. Without `force` it runs at
    most every DEPARTMENT_SYNC_SECONDS and never fails (the copy is used as it
    is); with `force` (the Director asked) an unreachable Attendance raises.
    None when it didn't run.
    """
    global _last_sync
    if not attendance.enabled:
        return None
    with _lock:
        if not force and time.monotonic() - _last_sync < get_settings().department_sync_seconds:
            return None
        _last_sync = time.monotonic()
    try:
        found = attendance.departments()
    except AttendanceError:
        if force:
            raise
        logger.warning("Departments not refreshed from Attendance; using the copy here")
        return None

    report: dict[str, Any] = {"linked": 0, "created": 0, "updated": 0, "skipped": []}
    local = list(db.scalars(select(Department)))
    for a in found:
        d = next((x for x in local if x.attendance_department_id == a.id), None)
        if d is None and a.smarttt_department_id is not None:
            d = next(
                (
                    x
                    for x in local
                    if x.attendance_department_id is None and a.smarttt_department_id in (x.smarttt_department_id, x.id)
                ),
                None,
            )
        if d is None:
            d = next(
                (x for x in local if x.attendance_department_id is None and name_key(x.name) == name_key(a.name)), None
            )
        if d is None:
            d = Department(
                id=_free_id(db, a.smarttt_department_id),
                code=new_department_code(db, a.name),
                name=a.name,
            )
            db.add(d)
            db.flush()
            local.append(d)
            report["created"] += 1
        elif d.attendance_department_id is None:
            report["linked"] += 1

        smarttt_taken = a.smarttt_department_id is not None and any(
            x is not d and x.smarttt_department_id == a.smarttt_department_id for x in local
        )
        if smarttt_taken:
            report["skipped"].append(f"{a.name}: its SMARTTT id is already on another department here.")
        # Attendance's code, unless another department here already holds it.
        code_holder = (
            next((x for x in local if x is not d and x.code.upper() == a.code), None) if a.code is not None else None
        )
        if code_holder is not None:
            report["skipped"].append(f"{a.name}: its code {a.code} is already used by {code_holder.name} here.")
        before = (d.attendance_department_id, d.name, d.code, d.smarttt_department_id, d.attendance_lecturer_count)
        d.attendance_department_id = a.id
        d.name = a.name
        if a.code is not None and code_holder is None:
            d.code = a.code
            d.code_from_attendance = True
        else:
            d.code_from_attendance = False
        if a.smarttt_department_id is not None and not smarttt_taken:
            d.smarttt_department_id = a.smarttt_department_id
        d.attendance_lecturer_count = a.lecturer_count
        if before[0] is not None and before != (
            d.attendance_department_id,
            d.name,
            d.code,
            d.smarttt_department_id,
            d.attendance_lecturer_count,
        ):
            report["updated"] += 1
        db.flush()

    if report["linked"] or report["created"] or report["updated"]:
        audit(db, identity, "departments.sync", "departments", "attendance", None, report)
    db.commit()
    return report


def reset_sync_state() -> None:
    """Forget the throttle (tests)."""
    global _last_sync
    _last_sync = 0.0


def list_departments(db: Session, attendance: AttendanceClient, identity: Identity) -> dict[str, Any]:
    """The departments, read from Attendance first (throttled), and whether Attendance is connected."""
    sync_departments(db, attendance, identity)
    rows = db.scalars(select(Department).order_by(Department.name))
    return {"attendance_connected": attendance.enabled, "departments": [department_dict(d) for d in rows]}
