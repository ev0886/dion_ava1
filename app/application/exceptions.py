from __future__ import annotations

from app.application.dto.rules import RuleEvaluationDTO


class ApplicationError(Exception):
    """Base exception for application-layer failures."""


class ValidationError(ApplicationError):
    """Raised when incoming application data is invalid."""


class AuthorizationError(ApplicationError):
    """Raised when a user is not allowed to perform an action."""


class RuleDeniedError(AuthorizationError):
    """Raised when a rule evaluation denies an operation execution."""

    def __init__(
        self,
        *,
        summary_message: str,
        reason_codes: tuple[str, ...] = (),
        operation_type: str | None = None,
    ) -> None:
        super().__init__(summary_message)
        self.summary_message = summary_message
        self.reason_codes = reason_codes
        self.operation_type = operation_type

    @classmethod
    def from_evaluation(cls, evaluation: RuleEvaluationDTO) -> "RuleDeniedError":
        return cls(
            summary_message=evaluation.summary_message,
            reason_codes=evaluation.reason_codes,
            operation_type=evaluation.operation_type.value,
        )


class NotFoundError(ApplicationError):
    """Raised when a required entity is missing."""


class InvalidStateTransitionError(ApplicationError):
    """Raised when an operation moves to a state outside the allowed graph."""


class RecoveryError(ApplicationError):
    """Raised when recovery-specific validation or lookup fails."""
