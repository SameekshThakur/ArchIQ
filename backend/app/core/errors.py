"""Consistent error envelope: {"error": {"code", "message", "request_id", "details"}}."""

import logging
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

log = logging.getLogger("archiq.http")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: object | None = None):
        self.status, self.code, self.message, self.details = status, code, message, details


class NotFound(ApiError):
    def __init__(self, what: str, ident: str | None = None):
        super().__init__(404, "not_found", what if ident is None else f"{what} '{ident}' was not found")


class BadRequest(ApiError):
    def __init__(self, message: str, details: object | None = None):
        super().__init__(400, "bad_request", message, details)


def envelope(status: int, code: str, message: str, details: object | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "request_id": request_id_var.get(), "details": details}},
    )


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(request: Request, call_next):  # noqa: ANN001
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            ms = (time.perf_counter() - start) * 1000
            log.info("%s %s", request.method, request.url.path, extra={"extra_fields": {"duration_ms": round(ms, 1)}})
            request_id_var.reset(token)
        response.headers["x-request-id"] = rid
        return response

    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError):
        return envelope(exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        return envelope(exc.status_code, "http_error", str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        return envelope(422, "validation_error", "Request validation failed", exc.errors())

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        log.exception("unhandled error")
        return envelope(500, "internal_error", "Unexpected server error")
