"""
Client for Smart Attendance's Generator endpoint
(/api/v1/integrations/generator/), authenticated with this system's own key
(X-API-Key = ATTENDANCE_API_KEY here, GENERATOR_API_KEY there).

Administrators create the university's departments in Attendance, each with
a name and a code (which Attendance creates in SMARTTT first); the Generator
reads them from there and plans each term's units against them
(app.services.departments). Faculties play no part.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

PREFIX = "/api/v1/integrations/generator"


class AttendanceError(Exception):
    """`message` is safe to show to users."""

    message = "Smart Attendance could not be reached, so the departments are as last read. Try again shortly."


class AttendanceMisconfigured(AttendanceError):
    message = (
        "The Generator is not connected to Smart Attendance correctly (the keys differ), so the departments "
        "are as last read. Contact the system administrator."
    )


class AttendanceSignInError(AttendanceError):
    """Why sign-in could not ask Attendance; `message` says it on the sign-in screen."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


SIGN_IN_NOT_SET_UP = (
    "Sign-in is not set up: the Generator has no Smart Attendance address (ATTENDANCE_BASE_URL). "
    "Contact the system administrator."
)
SIGN_IN_KEY_REFUSED = (
    "Sign-in is not set up correctly: Smart Attendance refused the Generator's key. ATTENDANCE_API_KEY "
    "here must equal GENERATOR_API_KEY in Smart Attendance. Contact the system administrator."
)
SIGN_IN_WRONG_ADDRESS = (
    "Sign-in is not set up correctly: Smart Attendance's sign-in check was not found at the Generator's "
    "ATTENDANCE_BASE_URL, or that Attendance is too old. Contact the system administrator."
)
SIGN_IN_UNREACHABLE = "Smart Attendance could not be reached (it may be starting up). Try again in a minute."
SIGN_IN_FAILED = "Smart Attendance could not check your sign-in just now. Try again in a minute."


def _base_url(url: str) -> str:
    """Attendance's root: PREFIX already starts with /api/v1, so a configured ".../api/v1" is dropped."""
    url = url.strip().rstrip("/")
    if url.endswith("/api/v1"):
        url = url[: -len("/api/v1")]
    return url or "http://attendance.invalid"


@dataclass(frozen=True)
class AttendanceDepartment:
    id: str
    name: str
    # The administrator's code ("DCOMP"), unique across the university; None for one made before codes existed.
    code: str | None
    smarttt_department_id: int | None
    lecturer_count: int


class AttendanceClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.enabled = bool(settings.attendance_base_url)
        self._http = httpx.Client(
            base_url=_base_url(settings.attendance_base_url),
            timeout=settings.attendance_timeout_seconds,
            headers={"X-API-Key": settings.attendance_api_key, "Accept": "application/json"},
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def departments(self) -> list[AttendanceDepartment]:
        try:
            response = self._http.get(PREFIX + "/departments")
        except httpx.HTTPError as exc:
            logger.warning("Attendance departments request failed: %s", exc)
            raise AttendanceError() from exc
        if response.status_code in (401, 403):
            logger.error("Attendance refused the Generator's key (%s)", response.status_code)
            raise AttendanceMisconfigured()
        if response.status_code >= 400:
            logger.warning("Attendance departments answered %s", response.status_code)
            raise AttendanceError()
        try:
            body: Any = response.json()
            data: Any = body.get("data") if isinstance(body, dict) and "success" in body else body
            rows = data["departments"]
            return [
                AttendanceDepartment(
                    id=str(d["id"]),
                    name=" ".join(str(d["name"]).split()),
                    code=" ".join(str(d["code"]).split()).upper() if d.get("code") else None,
                    smarttt_department_id=int(d["smartttDepartmentId"]) if d.get("smartttDepartmentId") else None,
                    lecturer_count=int(d.get("lecturerCount") or 0),
                )
                for d in rows
            ]
        except (ValueError, KeyError, TypeError) as exc:
            logger.error("Attendance departments answer could not be read: %s", exc)
            raise AttendanceError() from exc

    # -- sign-in: the timetabling office is invited in Attendance ------------------------------

    def _auth_request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if not self.enabled:
            logger.error("Sign-in: ATTENDANCE_BASE_URL is not set")
            raise AttendanceSignInError(SIGN_IN_NOT_SET_UP)
        try:
            response = self._http.request(method, PREFIX + path, **kwargs)
        except httpx.HTTPError as exc:
            logger.warning("Sign-in: Attendance %s%s could not be reached: %r", self._http.base_url, PREFIX + path, exc)
            raise AttendanceSignInError(SIGN_IN_UNREACHABLE) from exc
        if response.status_code in (401, 403):
            logger.error("Sign-in: Attendance refused the Generator's key (%s)", response.status_code)
            raise AttendanceSignInError(SIGN_IN_KEY_REFUSED)
        if response.status_code == 404 and path == "/authenticate":
            logger.error("Sign-in: %s%s answered 404; check ATTENDANCE_BASE_URL", self._http.base_url, PREFIX + path)
            raise AttendanceSignInError(SIGN_IN_WRONG_ADDRESS)
        if response.status_code >= 500:
            logger.warning("Sign-in: Attendance %s answered %s", path, response.status_code)
            raise AttendanceSignInError(SIGN_IN_FAILED)
        return response

    @staticmethod
    def _data(response: httpx.Response) -> Any:
        body: Any = response.json()
        return body.get("data") if isinstance(body, dict) and "success" in body else body

    def authenticate(self, identifier: str, password: str) -> dict[str, Any] | None:
        """{account, timetabling_office} for a right login of an active Attendance account, else None."""
        response = self._auth_request("POST", "/authenticate", json={"identifier": identifier, "password": password})
        if response.status_code >= 400:
            logger.warning(
                "Sign-in: Attendance /authenticate answered %s: %s", response.status_code, response.text[:300]
            )
            raise AttendanceSignInError(SIGN_IN_FAILED)
        data = dict(self._data(response) or {})
        if not data.pop("authenticated", False):
            return None
        return data

    def identity(self, account_id: str) -> dict[str, Any] | None:
        """The account's {account, timetabling_office} now; None once it is gone or no longer active."""
        response = self._auth_request("GET", "/identity", params={"account_id": account_id})
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            logger.warning("Sign-in: Attendance /identity answered %s", response.status_code)
            raise AttendanceSignInError(SIGN_IN_FAILED)
        return dict(self._data(response) or {})


_client: AttendanceClient | None = None
_client_lock = threading.Lock()


def get_attendance() -> AttendanceClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = AttendanceClient(get_settings())
        return _client


def set_attendance(client: AttendanceClient | None) -> None:
    """Swaps the shared client (tests)."""
    global _client
    with _client_lock:
        _client = client
