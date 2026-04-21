from __future__ import annotations

import time

from app.application.dto.auth import AuthRequest, AuthenticatedUserDTO, RfidResolvedUserDTO
from app.application.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.domain.enums import RoleCode, UserStatus
from app.hardware import HardwareFacade
from app.hardware.dto import HardwareOperationStatus, RfidReadResult
from app.persistence.models import Role, User
from app.persistence.repositories.users import UserRepository


class AuthService:
    _RFID_AUTH_WINDOW_SECONDS = 3.5
    _RFID_POLL_INTERVAL_SECONDS = 0.05

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

    def read_and_resolve_rfid(
        self,
        *,
        hardware_facade: HardwareFacade,
        allowed_roles: tuple[RoleCode, ...] = (),
    ) -> RfidResolvedUserDTO:
        read_result = self._read_rfid_for_authorization(hardware_facade)
        if read_result.uid is None:
            raise AuthorizationError(read_result.message or "No valid RFID card present")

        normalized_uid = self._normalize_rfid_uid(read_result.uid)
        user = self.user_repository.get_by_rfid_card_uid(normalized_uid)
        if user is None:
            raise NotFoundError(f"RFID card is not assigned to an active user: {normalized_uid}")

        self._ensure_user_allowed(user)
        role_code = self._resolve_role_code(user)
        if allowed_roles and role_code not in allowed_roles:
            raise AuthorizationError(f"User role is not allowed: {role_code}")
        return RfidResolvedUserDTO(
            rfid_uid=normalized_uid,
            is_duplicate=read_result.is_duplicate,
            user=self._to_dto(user, role_code),
        )

    def _read_rfid_for_authorization(self, hardware_facade: HardwareFacade) -> RfidReadResult:
        deadline = time.monotonic() + self._RFID_AUTH_WINDOW_SECONDS
        while True:
            read_result = hardware_facade.read_rfid_card()
            if read_result.uid is not None:
                return read_result

            remaining_window_seconds = deadline - time.monotonic()
            if remaining_window_seconds <= 0:
                return RfidReadResult(
                    device_type=read_result.device_type,
                    status=HardwareOperationStatus.NO_CARD,
                    ok=True,
                    uid=None,
                    is_duplicate=False,
                    message="No valid RFID card presented within authorization window",
                )
            time.sleep(min(self._RFID_POLL_INTERVAL_SECONDS, remaining_window_seconds))

    def _load_user(self, request: AuthRequest) -> User:
        if request.user_id is None and request.user_code is None:
            raise ValidationError("user_id or user_code is required")
        if request.user_id is not None:
            user = self.user_repository.get_by_id(request.user_id)
        else:
            user = self.user_repository.get_by_user_code(request.user_code or "")
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
    def _normalize_rfid_uid(uid: str) -> str:
        normalized = "".join(character for character in uid if character.isalnum()).upper()
        if not normalized:
            raise ValidationError("RFID uid must contain at least one hexadecimal character")
        return normalized

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
