"""
Sign-in. The Directorate of Examinations and Timetabling (the timetabling
office) is invited by an administrator in Smart Attendance, like any other
officer, and signs in here with that email and the password they chose;
Attendance checks it and says whether the account is the timetabling
office's (identity). Only they may use the Generator. The Generator then
keeps its own server-side session:

- an opaque random token in an httpOnly, SameSite=Lax cookie; only its
  SHA-256 is stored, so a database leak can't be replayed as sessions;
- a CSRF token, readable by the web app from the tg_xsrf cookie and
  required back in the X-XSRF-TOKEN header on every state-changing request;
- idle and absolute expiry, and revocation on sign-out;
- the account re-checked with Attendance every IDENTITY_REFRESH_SECONDS, so
  someone the administrator removes loses access quickly.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Any

from fastapi import Depends, Request, Response
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.clients.attendance import AttendanceClient, AttendanceError, get_attendance
from app.config import Settings, get_settings
from app.db import get_db
from app.errors import ApiError
from app.models import AuthSession, LoginAttempt, utcnow

logger = logging.getLogger(__name__)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass(frozen=True)
class Identity:
    account_id: str
    full_name: str
    university_id: str | None
    timetabling_office: bool
    session_id: str

    @classmethod
    def from_attendance(cls, data: dict[str, Any], session_id: str) -> Identity:
        account = data["account"]
        return cls(
            account_id=str(account["id"]),
            full_name=str(account.get("full_name") or account.get("email") or account["id"]),
            university_id=account.get("university_id"),
            timetabling_office=bool(data.get("timetabling_office")),
            session_id=session_id,
        )

    @property
    def actor(self) -> str:
        return f"{self.full_name} ({self.university_id or self.account_id})"

    def public(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "full_name": self.full_name,
            "university_id": self.university_id,
            "timetabling_office": self.timetabling_office,
        }


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _aware(value: datetime) -> datetime:
    # SQLite hands back naive datetimes; everything here is UTC.
    return value if value.tzinfo else value.replace(tzinfo=utcnow().tzinfo)


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def _too_many_attempts(db: Session, keys: list[str], settings: Settings) -> bool:
    since = utcnow() - timedelta(seconds=settings.login_window_seconds)
    count = (
        db.scalar(
            select(func.count()).select_from(LoginAttempt).where(LoginAttempt.key.in_(keys), LoginAttempt.at >= since)
        )
        or 0
    )
    return count >= settings.login_max_attempts


def _record_failure(db: Session, keys: list[str]) -> None:
    for key in keys:
        db.add(LoginAttempt(key=key))
    db.commit()


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def sign_in(
    db: Session,
    response: Response,
    request: Request,
    identifier: str,
    password: str,
    attendance: AttendanceClient,
    settings: Settings,
) -> Identity:
    ip = request.client.host if request.client else "unknown"
    keys = [f"id:{identifier.strip().lower()}", f"ip:{ip}"]
    if _too_many_attempts(db, keys, settings):
        raise ApiError(429, "TOO_MANY_ATTEMPTS", "Too many sign-in attempts. Please wait a few minutes.")

    try:
        data = attendance.authenticate(identifier.strip(), password)
    except AttendanceError as exc:
        raise ApiError(
            503, "ATTENDANCE_UNAVAILABLE", "Sign-in is unavailable right now. Try again in a minute."
        ) from exc
    if data is None:
        _record_failure(db, keys)
        raise ApiError(401, "INVALID_CREDENTIALS", "Wrong email or password.")
    if not data.get("timetabling_office"):
        raise ApiError(
            403,
            "NOT_TIMETABLING_OFFICE",
            "The Timetable Generator is for the Directorate of Examinations and Timetabling. Ask the "
            "Smart Attendance administrator to invite you as the timetabling office.",
        )

    db.execute(delete(LoginAttempt).where(LoginAttempt.key == keys[0]))
    token = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    now = utcnow()
    session = AuthSession(
        token_hash=_hash(token),
        csrf_token=csrf,
        account_id=str(data["account"]["id"]),
        identity=data,
        identity_checked_at=now,
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(hours=settings.session_absolute_hours),
        user_agent=(request.headers.get("user-agent") or "")[:500],
    )
    db.add(session)
    db.commit()
    _set_cookies(response, token, csrf, settings)
    return Identity.from_attendance(data, str(session.id))


def sign_out(db: Session, request: Request, response: Response, settings: Settings) -> None:
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        session = db.scalar(select(AuthSession).where(AuthSession.token_hash == _hash(token)))
        if session and session.revoked_at is None:
            session.revoked_at = utcnow()
            db.commit()
    for name in (settings.session_cookie_name, settings.csrf_cookie_name):
        response.delete_cookie(name, path="/", domain=settings.cookie_domain)


def _set_cookies(response: Response, token: str, csrf: str, settings: Settings) -> None:
    max_age = settings.session_absolute_hours * 3600
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=max_age,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        domain=settings.cookie_domain,
    )
    # Readable by the web app on purpose: it echoes it back as X-XSRF-TOKEN.
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf,
        max_age=max_age,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
        domain=settings.cookie_domain,
    )


def current_identity(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
    attendance: Annotated[AttendanceClient, Depends(get_attendance)],
) -> Identity:
    token = request.cookies.get(settings.session_cookie_name)
    if not token:
        raise ApiError(401, "UNAUTHENTICATED", "Please sign in.")
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == _hash(token)))
    now = utcnow()
    if (
        session is None
        or session.revoked_at is not None
        or _aware(session.expires_at) <= now
        or _aware(session.last_seen_at) + timedelta(minutes=settings.session_idle_minutes) <= now
    ):
        raise ApiError(401, "UNAUTHENTICATED", "Your session has ended. Please sign in again.")

    if request.method not in SAFE_METHODS:
        sent = request.headers.get(settings.csrf_header_name, "")
        if not sent or not hmac.compare_digest(sent, session.csrf_token):
            raise ApiError(403, "CSRF_FAILED", "Your session could not be verified. Please reload the page.")

    if _aware(session.identity_checked_at) + timedelta(seconds=settings.identity_refresh_seconds) <= now:
        try:
            fresh = attendance.identity(session.account_id)
        except AttendanceError:
            # Attendance down: carry on with the roles last confirmed rather than
            # locking everyone out; they are re-checked as soon as it is back.
            logger.warning("Could not refresh identity for %s; using cached roles", session.account_id)
        else:
            if fresh is None:
                session.revoked_at = now
                db.commit()
                raise ApiError(401, "UNAUTHENTICATED", "Your account is no longer active.")
            session.identity = fresh
            session.identity_checked_at = now
            if not fresh.get("timetabling_office"):
                session.revoked_at = now
                db.commit()
                raise ApiError(403, "NOT_TIMETABLING_OFFICE", "You are no longer the timetabling office.")

    # Idle expiry only needs minute precision; don't write on every request.
    if _aware(session.last_seen_at) + timedelta(seconds=60) <= now or db.is_modified(session):
        session.last_seen_at = now
        db.commit()
    return Identity.from_attendance(session.identity, str(session.id))
