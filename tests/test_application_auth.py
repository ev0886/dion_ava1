from __future__ import annotations

import pytest

from app.application.auth_service import AuthService
from app.application.dto.auth import AuthRequest
from app.application.exceptions import AuthorizationError, NotFoundError
from app.domain.enums import HardwareEndpointType, RoleCode, UserStatus
from app.hardware.dto import HardwareOperationStatus, RfidReadResult
from app.persistence.models import User


class _FakeSession:
    def get(self, *_args: object, **_kwargs: object) -> None:
        return None


class _FakeUserRepository:
    def __init__(self, user: User | None) -> None:
        self.user = user
        self.session = _FakeSession()

    def get_by_id(self, _user_id: int) -> User | None:
        return self.user

    def get_by_user_code(self, _user_code: str) -> User | None:
        return self.user

    def get_by_rfid_card_uid(self, _card_uid: str) -> User | None:
        return self.user


class _FakeHardwareFacade:
    def __init__(self, result: RfidReadResult) -> None:
        self.result = result

    def read_rfid_card(self) -> RfidReadResult:
        return self.result


def _build_user(*, status: UserStatus, is_active: bool) -> User:
    user = User(
        role_id=1,
        user_code="u-1",
        full_name="Test User",
        status=status,
        is_active=is_active,
    )
    user.id = 1
    return user


def test_auth_rejects_inactive_flag() -> None:
    service = AuthService(_FakeUserRepository(_build_user(status=UserStatus.ACTIVE, is_active=False)))

    with pytest.raises(AuthorizationError, match="inactive"):
        service.authorize(AuthRequest(user_id=1))


def test_auth_rejects_blocked_user() -> None:
    service = AuthService(_FakeUserRepository(_build_user(status=UserStatus.BLOCKED, is_active=True)))

    with pytest.raises(AuthorizationError, match="blocked"):
        service.authorize(AuthRequest(user_id=1))


def test_auth_read_and_resolve_rfid_returns_user_and_normalized_uid() -> None:
    user = _build_user(status=UserStatus.ACTIVE, is_active=True)
    service = AuthService(_FakeUserRepository(user))

    result = service.read_and_resolve_rfid(
        hardware_facade=_FakeHardwareFacade(
            RfidReadResult(
                device_type=HardwareEndpointType.RFID_READER,
                status=HardwareOperationStatus.SUCCESS,
                ok=True,
                uid="00 0f-e2 76 7c 00 45",
                is_duplicate=False,
            )
        ),
        allowed_roles=(),
    )

    assert result.rfid_uid == "000FE2767C0045"
    assert result.user.user_id == 1


def test_auth_read_and_resolve_rfid_rejects_unassigned_card() -> None:
    service = AuthService(_FakeUserRepository(None))

    with pytest.raises(NotFoundError, match="RFID card is not assigned"):
        service.read_and_resolve_rfid(
            hardware_facade=_FakeHardwareFacade(
                RfidReadResult(
                    device_type=HardwareEndpointType.RFID_READER,
                    status=HardwareOperationStatus.SUCCESS,
                    ok=True,
                    uid="000FE2767C0045",
                    is_duplicate=False,
                )
            ),
            allowed_roles=(RoleCode.USER,),
        )
