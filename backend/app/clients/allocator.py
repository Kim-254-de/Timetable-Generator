"""
Client for the Timetable Allocator's read-only Generator endpoint
(/api/integrations/generator/), authenticated with X-API-Key =
ALLOCATOR_CLIENT_KEY here, GENERATOR_INBOUND_KEY there.

Departments enter their courses, units and groups (with lecturers) in the
Allocator and publish them; the Director imports what is published.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import httpx

from app.config import Settings, get_settings
from app.errors import ApiError

logger = logging.getLogger(__name__)

PREFIX = "/api/integrations/generator"


class AllocatorClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self._configured = bool(settings.allocator_client_key)
        self._http = httpx.Client(
            base_url=settings.allocator_base_url.rstrip("/"),
            timeout=settings.allocator_timeout_seconds,
            headers={"X-API-Key": settings.allocator_client_key, "Accept": "application/json"},
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def _get(self, path: str) -> Any:
        if not self._configured:
            raise ApiError(
                503,
                "ALLOCATOR_MISCONFIGURED",
                "The Generator is not set up to reach the Timetable Allocator (ALLOCATOR_CLIENT_KEY).",
            )
        try:
            response = self._http.get(PREFIX + path)
        except httpx.HTTPError as exc:
            logger.warning("Allocator GET %s failed: %s", path, exc)
            raise ApiError(
                503, "ALLOCATOR_UNAVAILABLE", "The Timetable Allocator could not be reached. Try again shortly."
            ) from exc
        if response.status_code in (401, 403):
            logger.error("The Allocator refused the Generator's key (%s -> %s)", path, response.status_code)
            raise ApiError(
                503,
                "ALLOCATOR_MISCONFIGURED",
                "The Generator is not set up to reach the Timetable Allocator. Contact the administrator.",
            )
        if response.status_code >= 400:
            logger.warning("Allocator GET %s answered %s", path, response.status_code)
            raise ApiError(503, "ALLOCATOR_UNAVAILABLE", "The Timetable Allocator could not answer. Try again.")
        body = response.json()
        return body.get("data") if isinstance(body, dict) and "success" in body else body

    def submissions(self, term_id: str) -> dict[str, Any]:
        """Published departments (courses, units, groups with lecturers) and the ones not published yet."""
        return dict(self._get(f"/terms/{term_id}/submissions") or {})

    def exams(self, term_id: str) -> dict[str, Any]:
        """Published exam papers (with the class rows sitting them) and practicals, and who hasn't published."""
        return dict(self._get(f"/terms/{term_id}/exams") or {})

    def invigilators(self, term_id: str) -> dict[str, Any]:
        """Who invigilates each paper of the shared exam draft: {paper ref: {room code or "": {staff_number, name}}}."""
        return dict(self._get(f"/terms/{term_id}/invigilators") or {})


_client: AllocatorClient | None = None
_client_lock = threading.Lock()


def get_allocator() -> AllocatorClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = AllocatorClient(get_settings())
        return _client


def set_allocator(client: AllocatorClient | None) -> None:
    """Swaps the shared client (tests)."""
    global _client
    with _client_lock:
        _client = client
