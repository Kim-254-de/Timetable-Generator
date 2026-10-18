"""
Client for SMARTTT's Generator endpoints (/api/v1/integrations/generator/),
authenticated with this system's own shared key (X-API-Key).
"""

from __future__ import annotations

import logging
import threading
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

PREFIX = "/api/v1/integrations/generator"


class SmartttError(Exception):
    """Base class; `message` is safe to show to users."""

    message = "The timetable system (SMARTTT) could not be reached. Please try again shortly."


class SmartttUnavailable(SmartttError):
    pass


class SmartttMisconfigured(SmartttError):
    """SMARTTT refused our key: GENERATOR_API_KEY there and SMARTTT_API_KEY here differ."""

    message = "The Generator is not connected to SMARTTT correctly. Please contact the system administrator."


class SmartttNotFound(SmartttError):
    def __init__(self, detail: str = "Not found in SMARTTT."):
        super().__init__(detail)
        self.message = detail


class SmartttRefused(SmartttError):
    """SMARTTT refused a request (400/409/422): `code` and `body` say why."""

    def __init__(self, status: int, body: dict[str, Any]):
        super().__init__(body.get("detail") or "SMARTTT refused the request.")
        self.status = status
        self.code = str(body.get("code") or "refused")
        self.body = body
        self.message = str(body.get("detail") or "SMARTTT refused the request.")


class SmartttClient:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self._http = httpx.Client(
            base_url=settings.smarttt_base_url.rstrip("/"),
            timeout=settings.smarttt_timeout_seconds,
            headers={"X-API-Key": settings.smarttt_api_key, "Accept": "application/json"},
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def _request(
        self, method: str, path: str, *, params: dict[str, Any] | None = None, json: dict[str, Any] | None = None
    ) -> httpx.Response:
        clean = {k: str(v) for k, v in (params or {}).items() if v is not None}
        try:
            response = self._http.request(method, PREFIX + path, params=clean, json=json)
        except httpx.HTTPError as exc:
            logger.warning("SMARTTT %s %s failed: %s", method, path, exc)
            raise SmartttUnavailable() from exc
        if response.status_code in (401, 403):
            logger.error("SMARTTT refused the Generator's API key (%s %s -> %s)", method, path, response.status_code)
            raise SmartttMisconfigured()
        if response.status_code >= 500:
            logger.warning("SMARTTT %s %s answered %s", method, path, response.status_code)
            raise SmartttUnavailable()
        return response

    def _json(self, response: httpx.Response) -> Any:
        if response.status_code == 404:
            raise SmartttNotFound(str(_body(response).get("detail") or "Not found in SMARTTT."))
        if response.status_code >= 400:
            raise SmartttRefused(response.status_code, _body(response))
        return response.json()

    def authenticate(self, identifier: str, password: str) -> dict[str, Any] | None:
        response = self._request("POST", "/authenticate/", json={"identifier": identifier, "password": password})
        body = self._json(response)
        if not body.get("authenticated"):
            return None
        body.pop("authenticated", None)
        return dict(body)

    def identity(self, account_id: str) -> dict[str, Any] | None:
        response = self._request("GET", "/identity/", params={"account_id": account_id})
        if response.status_code == 404:
            return None
        return dict(self._json(response))

    def terms(self) -> list[dict[str, Any]]:
        return list(self._json(self._request("GET", "/terms/"))["terms"])

    def snapshot(self, term_id: str) -> dict[str, Any]:
        return dict(self._json(self._request("GET", "/snapshot/", params={"term": term_id})))

    def publish(self, payload: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """(status, publication). 201 = published now, 200 = this version was already published."""
        response = self._request("POST", "/publish/", json=payload)
        body = self._json(response)
        return response.status_code, dict(body)

    def publication(self, term_id: str, version: int) -> dict[str, Any]:
        return dict(self._json(self._request("GET", f"/publish/{int(version)}/", params={"term": term_id})))


def _body(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        return {"detail": response.text[:200]}
    return body if isinstance(body, dict) else {"detail": str(body)[:200]}


_client: SmartttClient | None = None
_client_lock = threading.Lock()


def get_smarttt() -> SmartttClient:
    global _client
    with _client_lock:
        if _client is None:
            _client = SmartttClient(get_settings())
        return _client


def set_smarttt(client: SmartttClient | None) -> None:
    """Swaps the shared client (tests)."""
    global _client
    with _client_lock:
        _client = client
