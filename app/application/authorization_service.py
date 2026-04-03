from __future__ import annotations

from dataclasses import dataclass

from app.application.dto.auth import AuthenticatedUserDTO, AuthorizationDecisionDTO, AuthorizationRequest
from app.application.exceptions import AuthorizationError
from app.domain.enums import AuthorizationAction, AuthorizationReasonCode, RoleCode, UserStatus
from app.persistence.models import AuditLog, Role
from app.persistence.repositories.logs import AuditLogRepository
from app.persistence.repositories.users import UserRepository

_ADMIN_ACTIONS = {
    AuthorizationAction.USER_MANAGEMENT_MUTATION,
    AuthorizationAction.ITEM_MANAGEMENT_MUTATION,
    AuthorizationAction.INVENTORY_CORRECTION_MUTATION,
    AuthorizationAction.IMPORT_EXECUTION_APPLY,
    AuthorizationAction.EXPORT_EXECUTION,
    AuthorizationAction.SYSTEM_CONFIG_UPDATE,
    AuthorizationAction.RECOVERY_RESOLUTION_ACTION,
}

_OPERATOR_ACTIONS = {
    AuthorizationAction.DISPENSE_EXECUTION,
    AuthorizationAction.RETURN_EXECUTION,
    AuthorizationAction.REFILL_EXECUTION,
    AuthorizationAction.SERVICE_MODE_START,
    AuthorizationAction.SERVICE_MODE_FINISH,
    AuthorizationAction.DASHBOARD_READ,
    AuthorizationAction.RECOVERY_SCAN,
    AuthorizationAction.RECOVERY_READ,
}


@dataclass(slots=True)
class AuthorizationService:
    user_repository: UserRepository
    audit_log_repository: AuditLogRepository | None = None

    def evaluate(self, request: AuthorizationRequest) -> AuthorizationDecisionDTO:
        if request.actor_user_id is None:
            return AuthorizationDecisionDTO(
                action=request.action,
                actor_user_id=None,
                allowed=False,
                reason_code=AuthorizationReasonCode.MISSING_ACTOR,
                detail="actor_user_id is required",
                actor=None,
            )

        user = self.user_repository.get_by_id(request.actor_user_id)
        if user is None:
            return AuthorizationDecisionDTO(
                action=request.action,
                actor_user_id=request.actor_user_id,
                allowed=False,
                reason_code=AuthorizationReasonCode.ACTOR_NOT_FOUND,
                detail=f"Actor user not found: {request.actor_user_id}",
                actor=None,
            )

        actor = self._to_actor(user)
        if not actor.is_active or actor.status is UserStatus.INACTIVE:
            return AuthorizationDecisionDTO(
                action=request.action,
                actor_user_id=actor.user_id,
                allowed=False,
                reason_code=AuthorizationReasonCode.ACTOR_INACTIVE,
                detail="Actor is inactive",
                actor=actor,
            )
        if actor.status is UserStatus.BLOCKED:
            return AuthorizationDecisionDTO(
                action=request.action,
                actor_user_id=actor.user_id,
                allowed=False,
                reason_code=AuthorizationReasonCode.ACTOR_BLOCKED,
                detail="Actor is blocked",
                actor=actor,
            )

        allowed_roles = self._allowed_roles_for_action(request.action)
        if actor.role_code not in allowed_roles:
            return AuthorizationDecisionDTO(
                action=request.action,
                actor_user_id=actor.user_id,
                allowed=False,
                reason_code=AuthorizationReasonCode.ROLE_NOT_ALLOWED,
                detail=f"Actor role is not allowed for action: {request.action.value}",
                actor=actor,
            )

        return AuthorizationDecisionDTO(
            action=request.action,
            actor_user_id=actor.user_id,
            allowed=True,
            reason_code=None,
            detail="authorized",
            actor=actor,
        )

    def require(self, request: AuthorizationRequest) -> AuthenticatedUserDTO:
        decision = self.evaluate(request)
        if not decision.allowed:
            self._record_denial(decision)
            raise AuthorizationError(
                decision.detail,
                reason_code=decision.reason_code,
                action=decision.action,
                actor_user_id=decision.actor_user_id,
            )
        assert decision.actor is not None
        return decision.actor

    @staticmethod
    def _allowed_roles_for_action(action: AuthorizationAction) -> tuple[RoleCode, ...]:
        if action in _ADMIN_ACTIONS:
            return (RoleCode.ADMIN,)
        if action in _OPERATOR_ACTIONS:
            return (RoleCode.ADMIN, RoleCode.OPERATOR)
        return ()

    def _to_actor(self, user) -> AuthenticatedUserDTO:
        role = self.user_repository.session.get(Role, user.role_id)
        role_code = role.code if role is not None else None
        return AuthenticatedUserDTO(
            user_id=user.id,
            user_code=user.user_code,
            full_name=user.full_name,
            status=user.status,
            is_active=user.is_active,
            role_code=role_code,
        )

    def _record_denial(self, decision: AuthorizationDecisionDTO) -> None:
        if self.audit_log_repository is None:
            return
        self.audit_log_repository.add(
            AuditLog(
                entity_type="authorization",
                entity_id=decision.action.value,
                action="authorization_denied",
                actor_user_id=decision.actor_user_id,
                reason_code=decision.reason_code.value if decision.reason_code is not None else None,
                comment=decision.detail,
                before_json=None,
                after_json=None,
            )
        )
        self.audit_log_repository.session.commit()
