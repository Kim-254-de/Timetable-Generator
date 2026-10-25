"""
Client for what departments publish in Smart Attendance's Teaching page
(GET /api/v1/integrations/generator/terms/{term}/submissions), with the
same shared key as the departments (X-API-Key = ATTENDANCE_API_KEY here,
GENERATOR_API_KEY there).

Departments enter their courses, units and groups (with lecturers) in
Attendance's department portal and publish them; the Director imports what
is published (app.services.allocator_import, named for the Timetable
Allocator that used to serve it, in the same shape).
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.errors import ApiError

logger = logging.getLogger(__name__)

PREFIX = "/api/v1/integrations/generator"


class TeachingClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self._configured = bool(settings.attendance_base_url and settings.attendance_api_key)
        self._http = httpx.Client(
            base_url=settings.attendance_base_url.rstrip("/") or "http://attendance.invalid",
            timeout=settings.attendance_timeout_seconds,
            headers={"X-API-Key": settings.attendance_api_key, "Accept": "application/json"},
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def _get(self, path: str) -> Any:
        if not self._configured:
            raise ApiError(
                503,
                "ATTENDANCE_MISCONFIGURED",
                "The Generator is not set up to reach Smart Attendance (ATTENDANCE_BASE_URL, ATTENDANCE_API_KEY), "
                "where departments publish their teaching.",
            )
        try:
            response = self._http.get(PREFIX + path)
        except httpx.HTTPError as exc:
            logger.warning("Attendance GET %s failed: %s", path, exc)
            raise ApiError(
                503, "ATTENDANCE_UNAVAILABLE", "Smart Attendance could not be reached. Try again shortly."
            ) from exc
        if response.status_code in (401, 403):
            logger.error("Attendance refused the Generator's key (%s -> %s)", path, response.status_code)
            raise ApiError(
                503,
                "ATTENDANCE_MISCONFIGURED",
                "The Generator is not connected to Smart Attendance correctly. Contact the administrator.",
            )
        if response.status_code >= 400:
            logger.warning("Attendance GET %s answered %s", path, response.status_code)
            raise ApiError(503, "ATTENDANCE_UNAVAILABLE", "Smart Attendance could not answer. Try again.")
        body = response.json()
        return body.get("data") if isinstance(body, dict) and "success" in body else body

    def submissions(self, term_id: str) -> dict[str, Any]:
        """Published departments (courses, units, groups with lecturers) and the ones not published yet."""
        return dict(self._get(f"/terms/{term_id}/submissions") or {})


_client: TeachingClient | None = None
_client_lock = threading.Lock()


def get_teaching() -> TeachingClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = TeachingClient(get_settings())
        return _client


def set_teaching(client: TeachingClient | None) -> None:
    """Swaps the shared client (tests)."""
    global _client
    with _client_lock:
        _client = client
