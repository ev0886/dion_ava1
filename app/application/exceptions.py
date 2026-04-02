from __future__ import annotations


class ApplicationError(Exception):
    """Base exception for application-layer failures."""


class ValidationError(ApplicationError):
    """Raised when incoming application data is invalid."""


class AuthorizationError(ApplicationError):
    """Raised when a user is not allowed to perform an action."""


class NotFoundError(ApplicationError):
    """Raised when a required entity is missing."""


class ConflictError(ApplicationError):
    """Raised when a mutation conflicts with existing data."""


class InvalidStateTransitionError(ApplicationError):
    """Raised when an operation moves to a state outside the allowed graph."""


class RecoveryError(ApplicationError):
    """Raised when recovery-specific validation or lookup fails."""
