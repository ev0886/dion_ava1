from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.application.exceptions import (
    ActorConflictError,
    AuthenticationError,
    AuthorizationError,
    InvalidStateTransitionError,
    NotFoundError,
    RecoveryError,
    ValidationError,
)

def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ValidationError)
    async def _validation_error_handler(_: Request, error: ValidationError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": "validation_error", "detail": str(error)})

    @app.exception_handler(NotFoundError)
    async def _not_found_handler(_: Request, error: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"error": "not_found", "detail": str(error)})

    @app.exception_handler(AuthorizationError)
    async def _authorization_handler(_: Request, error: AuthorizationError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"error": "authorization_error", "detail": str(error)})

    @app.exception_handler(AuthenticationError)
    async def _authentication_handler(_: Request, error: AuthenticationError) -> JSONResponse:
        return JSONResponse(status_code=401, content={"error": "authentication_error", "detail": str(error)})

    @app.exception_handler(ActorConflictError)
    async def _actor_conflict_handler(_: Request, error: ActorConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"error": "actor_conflict", "detail": str(error)})

    @app.exception_handler(RecoveryError)
    async def _recovery_conflict_handler(_: Request, error: RecoveryError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"error": "conflict", "detail": str(error)})

    @app.exception_handler(InvalidStateTransitionError)
    async def _state_conflict_handler(_: Request, error: InvalidStateTransitionError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"error": "conflict", "detail": str(error)})

    @app.exception_handler(Exception)
    async def _unexpected_handler(_: Request, error: Exception) -> JSONResponse:
        return JSONResponse(status_code=500, content={"error": "internal_error", "detail": str(error)})
