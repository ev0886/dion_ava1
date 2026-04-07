from __future__ import annotations

from app.application.dto.auth import AuthRequest, AuthenticatedUserDTO
from app.application.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.domain.enums import RoleCode, UserStatus
from app.persistence.models import Role, User
from app.persistence.repositories.users import UserRepository


class AuthService:
    def __init__(self, user_repository: UserRepository) -> None:
        self.user_repository = user_repository

    def authorize(self, request: AuthRequest) -> AuthenticatedUserDTO:
        user = self._load_user(request)
        self._ensure_user_allowed(user)
        role_code = self._resolve_role_code(user)
        if request.allowed_roles and role_code not in request.allowed_roles:
            raise AuthorizationError(f"User role is not allowed: {role_code}")
        return self._to_dto(user, role_code)

    def get_user_by_id(self, user_id: int) -> AuthenticatedUserDTO:
        if user_id <= 0:
            raise ValidationError("user_id must be positive")
        user = self.user_repository.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User not found: {user_id}")
        return self._to_dto(user, self._resolve_role_code(user))

    def get_user_by_code(self, user_code: str) -> AuthenticatedUserDTO:
        if not user_code.strip():
            raise ValidationError("user_code must not be empty")
        user = self.user_repository.get_by_user_code(user_code)
        if user is None:
            raise NotFoundError(f"User not found: {user_code}")
        return self._to_dto(user, self._resolve_role_code(user))

    def get_user_by_rfid_uid(self, rfid_uid: str) -> AuthenticatedUserDTO:
        normalized_uid = rfid_uid.strip()
        if not normalized_uid:
            raise ValidationError("rfid_uid must not be empty")
        user = self.user_repository.get_by_rfid_uid(normalized_uid)
        if user is None:
            raise NotFoundError(f"User not found: {normalized_uid}")
        return self._to_dto(user, self._resolve_role_code(user))

    def _load_user(self, request: AuthRequest) -> User:
        provided_identifiers = sum(
            value is not None for value in (request.user_id, request.user_code, request.rfid_uid)
        )
        if provided_identifiers == 0:
            raise ValidationError("user_id, user_code, or rfid_uid is required")
        if provided_identifiers > 1:
            raise ValidationError("Provide only one of user_id, user_code, or rfid_uid")
        if request.user_id is not None:
            user = self.user_repository.get_by_id(request.user_id)
        elif request.user_code is not None:
            user = self.user_repository.get_by_user_code(request.user_code)
        else:
            normalized_uid = (request.rfid_uid or "").strip()
            if not normalized_uid:
                raise ValidationError("rfid_uid must not be empty")
            user = self.user_repository.get_by_rfid_uid(normalized_uid)
        if user is None:
            raise NotFoundError("User not found")
        return user

    def _ensure_user_allowed(self, user: User) -> None:
        if not user.is_active:
            raise AuthorizationError("User is inactive")
        if user.status is UserStatus.INACTIVE:
            raise AuthorizationError("User status is inactive")
        if user.status is UserStatus.BLOCKED:
            raise AuthorizationError("User is blocked")

    def _resolve_role_code(self, user: User) -> RoleCode | None:
        role = self.user_repository.session.get(Role, user.role_id)
        if role is None:
            return None
        return role.code

    @staticmethod
    def _to_dto(user: User, role_code: RoleCode | None) -> AuthenticatedUserDTO:
        return AuthenticatedUserDTO(
            user_id=user.id,
            user_code=user.user_code,
            full_name=user.full_name,
            status=user.status,
            is_active=user.is_active,
            role_code=role_code,
        )
