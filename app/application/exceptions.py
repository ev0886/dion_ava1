from __future__ import annotations

from app.domain.enums import AuthorizationAction, AuthorizationReasonCode


class ApplicationError(Exception):
    """Base exception for application-layer failures."""


class ValidationError(ApplicationError):
    """Raised when incoming application data is invalid."""


class AuthorizationError(ApplicationError):
    """Raised when a user is not allowed to perform an action."""

    def __init__(
        self,
        detail: str,
        *,
        reason_code: AuthorizationReasonCode | None = None,
        action: AuthorizationAction | None = None,
        actor_user_id: int | None = None,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.reason_code = reason_code
        self.action = action
        self.actor_user_id = actor_user_id


class NotFoundError(ApplicationError):
    """Raised when a required entity is missing."""


class InvalidStateTransitionError(ApplicationError):
    """Raised when an operation moves to a state outside the allowed graph."""


class RecoveryError(ApplicationError):
    """Raised when recovery-specific validation or lookup fails."""
