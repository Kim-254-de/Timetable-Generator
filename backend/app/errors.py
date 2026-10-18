"""
Every response is wrapped the same way as the Smart Attendance API, so the
web app unwraps it in one place:

  {"success": true, "data": ...}
  {"success": false, "error": {"code": "...", "message": "...", "details": ...}}

`message` is always safe to show to users.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.clients.smarttt import SmartttError, SmartttMisconfigured, SmartttNotFound, SmartttRefused

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def ok(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data}


def _error(status: int, code: str, message: str, details: Any = None) -> JSONResponse:
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return JSONResponse({"success": False, "error": error}, status_code=status)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_request: Request, exc: ApiError) -> JSONResponse:
        return _error(exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(SmartttError)
    async def _smarttt_error(_request: Request, exc: SmartttError) -> JSONResponse:
        if isinstance(exc, SmartttNotFound):
            return _error(404, "NOT_FOUND", exc.message)
        if isinstance(exc, SmartttRefused):
            status = exc.status if exc.status in (400, 409, 422) else 400
            details = {k: v for k, v in exc.body.items() if k not in ("detail", "code")} or None
            return _error(status, exc.code.upper(), exc.message, details)
        if isinstance(exc, SmartttMisconfigured):
            return _error(502, "SMARTTT_MISCONFIGURED", exc.message)
        return _error(503, "SMARTTT_UNAVAILABLE", exc.message)

    @app.exception_handler(RequestValidationError)
    async def _validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(str(p) for p in err.get("loc", ()) if p != "body"), "message": err.get("msg")}
            for err in exc.errors()
        ]
        return _error(422, "VALIDATION_ERROR", "Some fields are missing or invalid.", details)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
        message = exc.detail if isinstance(exc.detail, str) else "Request failed."
        return _error(exc.status_code, code, message)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
        return _error(500, "INTERNAL_ERROR", "Something went wrong on our side. Please try again.")
