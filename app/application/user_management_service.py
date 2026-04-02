from __future__ import annotations

from dataclasses import dataclass

from app.application.audit import record_audit
from app.application.dto.management import UserDetailDTO, UserListResultDTO, UserRfidBindingDTO, UserSummaryDTO
from app.application.exceptions import ConflictError, InvalidStateTransitionError, NotFoundError, ValidationError
from app.domain.enums import RoleCode, UserStatus
from app.persistence.models import Role, User, UserRfidCard
from app.persistence.repositories.logs import AuditLogRepository
from app.persistence.repositories.users import UserRepository


@dataclass(slots=True)
class UserManagementService:
    user_repository: UserRepository
    audit_log_repository: AuditLogRepository

    def create_user(
        self,
        *,
        user_code: str,
        full_name: str,
        role_id: int,
        actor_user_id: int | None = None,
        comment: str | None = None,
    ) -> UserDetailDTO:
        normalized_user_code = self._require_text(user_code, "user_code")
        normalized_full_name = self._require_text(full_name, "full_name")
        role = self._require_role(role_id)
        if self.user_repository.get_by_user_code(normalized_user_code) is not None:
            raise ConflictError(f"user_code already exists: {normalized_user_code}")

        user = User(
            role_id=role.id,
            user_code=normalized_user_code,
            full_name=normalized_full_name,
            status=UserStatus.ACTIVE,
            is_active=True,
        )
        self.user_repository.add(user)
        self.user_repository.session.flush()
        record_audit(
            self.audit_log_repository,
            entity_type="user",
            entity_id=str(user.id),
            action="create",
            actor_user_id=actor_user_id,
            comment=comment,
            before=None,
            after=self._snapshot_user(user, role),
        )
        self.user_repository.session.commit()
        return self.get_user_details(user.id)

    def update_user(
        self,
        *,
        user_id: int,
        user_code: str | None = None,
        full_name: str | None = None,
        role_id: int | None = None,
        actor_user_id: int | None = None,
        comment: str | None = None,
    ) -> UserDetailDTO:
        user = self._require_user(user_id)
        role = self._require_role(role_id if role_id is not None else user.role_id)
        before = self._snapshot_user(user, self._require_role(user.role_id))
        changed = False

        if user_code is not None:
            normalized_user_code = self._require_text(user_code, "user_code")
            existing = self.user_repository.get_by_user_code(normalized_user_code)
            if existing is not None and existing.id != user.id:
                raise ConflictError(f"user_code already exists: {normalized_user_code}")
            user.user_code = normalized_user_code
            changed = True

        if full_name is not None:
            user.full_name = self._require_text(full_name, "full_name")
            changed = True

        if role_id is not None:
            user.role_id = role.id
            changed = True

        if changed:
            self.user_repository.session.flush()
            record_audit(
                self.audit_log_repository,
                entity_type="user",
                entity_id=str(user.id),
                action="update",
                actor_user_id=actor_user_id,
                comment=comment,
                before=before,
                after=self._snapshot_user(user, role),
            )
            self.user_repository.session.commit()
        return self.get_user_details(user.id)

    def set_user_active(
        self,
        *,
        user_id: int,
        is_active: bool,
        actor_user_id: int | None = None,
        comment: str | None = None,
    ) -> UserDetailDTO:
        user = self._require_user(user_id)
        role = self._require_role(user.role_id)
        before = self._snapshot_user(user, role)
        if is_active:
            if user.status is UserStatus.BLOCKED:
                raise InvalidStateTransitionError("Blocked user cannot be activated through this workflow")
            if user.is_active and user.status is UserStatus.ACTIVE:
                raise InvalidStateTransitionError(f"User is already active: {user_id}")
            user.is_active = True
            user.status = UserStatus.ACTIVE
            action = "activate"
        else:
            if user.status is UserStatus.BLOCKED:
                raise InvalidStateTransitionError("Blocked user cannot be deactivated through this workflow")
            if not user.is_active and user.status is UserStatus.INACTIVE:
                raise InvalidStateTransitionError(f"User is already inactive: {user_id}")
            user.is_active = False
            user.status = UserStatus.INACTIVE
            action = "deactivate"

        self.user_repository.session.flush()
        record_audit(
            self.audit_log_repository,
            entity_type="user",
            entity_id=str(user.id),
            action=action,
            actor_user_id=actor_user_id,
            comment=comment,
            before=before,
            after=self._snapshot_user(user, role),
        )
        self.user_repository.session.commit()
        return self.get_user_details(user.id)

    def get_user_details(self, user_id: int) -> UserDetailDTO:
        user = self._require_user(user_id)
        role = self._require_role(user.role_id)
        summary = self._to_summary_dto(user, role)
        rfid_bindings = tuple(self._to_rfid_dto(binding) for binding in self.user_repository.list_rfid_cards_for_user(user.id))
        return UserDetailDTO(
            user_id=summary.user_id,
            user_code=summary.user_code,
            full_name=summary.full_name,
            role_id=summary.role_id,
            role_code=summary.role_code,
            role_name=summary.role_name,
            status=summary.status,
            is_active=summary.is_active,
            created_at=summary.created_at,
            updated_at=summary.updated_at,
            rfid_bindings=rfid_bindings,
        )

    def list_users(
        self,
        *,
        role_id: int | None = None,
        status: UserStatus | None = None,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> UserListResultDTO:
        if role_id is not None:
            self._require_role(role_id)
        users = self.user_repository.list_users(role_id=role_id, status=status, is_active=is_active, search=search)
        summaries = tuple(self._to_summary_dto(user, self.user_repository.get_role_by_id(user.role_id)) for user in users)
        return UserListResultDTO(users=summaries)

    @staticmethod
    def _require_text(value: str, field_name: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValidationError(f"{field_name} is required")
        return normalized

    def _require_user(self, user_id: int) -> User:
        if user_id <= 0:
            raise ValidationError("user_id must be positive")
        user = self.user_repository.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User not found: {user_id}")
        return user

    def _require_role(self, role_id: int) -> Role:
        if role_id <= 0:
            raise ValidationError("role_id must be positive")
        role = self.user_repository.get_role_by_id(role_id)
        if role is None:
            raise NotFoundError(f"Role not found: {role_id}")
        return role

    @staticmethod
    def _to_summary_dto(user: User, role: Role | None) -> UserSummaryDTO:
        return UserSummaryDTO(
            user_id=user.id,
            user_code=user.user_code,
            full_name=user.full_name,
            role_id=user.role_id,
            role_code=role.code if role is not None else None,
            role_name=role.name if role is not None else None,
            status=user.status,
            is_active=user.is_active,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )

    @staticmethod
    def _to_rfid_dto(binding: UserRfidCard) -> UserRfidBindingDTO:
        return UserRfidBindingDTO(
            card_uid=binding.card_uid,
            is_active=binding.is_active,
            issued_at=binding.issued_at,
            revoked_at=binding.revoked_at,
        )

    def _snapshot_user(self, user: User, role: Role | None) -> dict[str, object]:
        return {
            "user_code": user.user_code,
            "full_name": user.full_name,
            "role_id": user.role_id,
            "role_code": role.code.value if role is not None and isinstance(role.code, RoleCode) else None,
            "status": user.status.value,
            "is_active": user.is_active,
        }
