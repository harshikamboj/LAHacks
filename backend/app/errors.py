"""One error shape for every API response: {"error": {"code", "message", "details"}}."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.services.simulator_clients import (
    SimulatorError,
    SimulatorHttpError,
    SimulatorTimeout,
)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


def error_body(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content=error_body(exc.code, exc.message, exc.details))


async def simulator_error_handler(_: Request, exc: SimulatorError) -> JSONResponse:
    if isinstance(exc, SimulatorHttpError):
        code = exc.code
    elif isinstance(exc, SimulatorTimeout):
        code = "SIMULATOR_TIMEOUT"
    else:
        code = "SIMULATOR_UNAVAILABLE"
    return JSONResponse(status_code=502, content=error_body(code, str(exc), {"system": exc.system}))
