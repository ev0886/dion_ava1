from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import AuthorizationAction, AuthorizationReasonCode, RoleCode, UserStatus


@dataclass(frozen=True, slots=True)
class AuthRequest:
    user_id: int | None = None
    user_code: str | None = None
    allowed_roles: tuple[RoleCode, ...] = ()


@dataclass(frozen=True, slots=True)
class AuthenticatedUserDTO:
    user_id: int
    user_code: str
    full_name: str
    status: UserStatus
    is_active: bool
    role_code: RoleCode | None


@dataclass(frozen=True, slots=True)
class AuthorizationRequest:
    action: AuthorizationAction
    actor_user_id: int | None


@dataclass(frozen=True, slots=True)
class AuthorizationDecisionDTO:
    action: AuthorizationAction
    actor_user_id: int | None
    allowed: bool
    reason_code: AuthorizationReasonCode | None
    detail: str
    actor: AuthenticatedUserDTO | None
