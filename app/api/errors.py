from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.application.exceptions import (
    AuthorizationError,
    InvalidStateTransitionError,
    NotFoundError,
    RecoveryError,
    ValidationError,
)


def _error_payload(
    *,
    error: str,
    message: str,
    reason_code: str | None = None,
    action: str | None = None,
) -> dict[str, str | None]:
    return {
        "error": error,
        "detail": message,
        "message": message,
        "reason_code": reason_code or error,
        "action": action,
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ValidationError)
    async def _validation_error_handler(_: Request, error: ValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content=_error_payload(error="validation_error", message=str(error)),
        )

    @app.exception_handler(NotFoundError)
    async def _not_found_handler(_: Request, error: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content=_error_payload(error="not_found", message=str(error)))

    @app.exception_handler(AuthorizationError)
    async def _authorization_handler(_: Request, error: AuthorizationError) -> JSONResponse:
        return JSONResponse(
            status_code=403,
            content=_error_payload(error="authorization_error", message=str(error)),
        )

    @app.exception_handler(RecoveryError)
    async def _recovery_conflict_handler(_: Request, error: RecoveryError) -> JSONResponse:
        return JSONResponse(status_code=409, content=_error_payload(error="conflict", message=str(error)))

    @app.exception_handler(InvalidStateTransitionError)
    async def _state_conflict_handler(_: Request, error: InvalidStateTransitionError) -> JSONResponse:
        return JSONResponse(status_code=409, content=_error_payload(error="conflict", message=str(error)))

    @app.exception_handler(RequestValidationError)
    async def _request_validation_handler(_: Request, error: RequestValidationError) -> JSONResponse:
        message = "; ".join(
            f"{'.'.join(str(part) for part in issue['loc'])}: {issue['msg']}"
            for issue in error.errors()
        )
        return JSONResponse(
            status_code=422,
            content=_error_payload(error="validation_error", message=message or "Invalid request"),
        )

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(_: Request, error: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content=_error_payload(error="http_error", message=str(error.detail)),
        )

    @app.exception_handler(Exception)
    async def _unexpected_handler(_: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content=_error_payload(error="internal_error", message=str(error)))
