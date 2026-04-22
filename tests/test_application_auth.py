from __future__ import annotations

from collections.abc import Sequence

import pytest

import app.application.auth_service as auth_service_module
from app.application.auth_service import AuthService
from app.application.dto.auth import AuthRequest
from app.application.exceptions import AuthorizationError, NotFoundError
from app.domain.enums import HardwareEndpointType, RoleCode, UserStatus
from app.hardware.dto import HardwareOperationStatus, RfidReadResult
from app.persistence.models import User


class _AllowAllOpenDoorGuard:
    def assert_all_closed(self, *, action_description: str) -> None:
        return None


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
    def __init__(self, result: RfidReadResult | Sequence[RfidReadResult]) -> None:
        if isinstance(result, Sequence):
            self.results = list(result)
        else:
            self.results = [result]
        self.read_count = 0

    def read_rfid_card(self) -> RfidReadResult:
        index = min(self.read_count, len(self.results) - 1)
        self.read_count += 1
        return self.results[index]


class _FakeClock:
    def __init__(self) -> None:
        self.value = 0.0

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.value += seconds


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
    service = AuthService(_FakeUserRepository(_build_user(status=UserStatus.ACTIVE, is_active=False)), _AllowAllOpenDoorGuard())

    with pytest.raises(AuthorizationError, match="inactive"):
        service.authorize(AuthRequest(user_id=1))


def test_auth_rejects_blocked_user() -> None:
    service = AuthService(_FakeUserRepository(_build_user(status=UserStatus.BLOCKED, is_active=True)), _AllowAllOpenDoorGuard())

    with pytest.raises(AuthorizationError, match="blocked"):
        service.authorize(AuthRequest(user_id=1))


def test_auth_read_and_resolve_rfid_returns_user_and_normalized_uid() -> None:
    user = _build_user(status=UserStatus.ACTIVE, is_active=True)
    service = AuthService(_FakeUserRepository(user), _AllowAllOpenDoorGuard())

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
    service = AuthService(_FakeUserRepository(None), _AllowAllOpenDoorGuard())

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


def test_auth_read_and_resolve_rfid_retries_until_full_uid_within_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _build_user(status=UserStatus.ACTIVE, is_active=True)
    service = AuthService(_FakeUserRepository(user), _AllowAllOpenDoorGuard())
    hardware = _FakeHardwareFacade(
        [
            RfidReadResult(
                device_type=HardwareEndpointType.RFID_READER,
                status=HardwareOperationStatus.NO_CARD,
                ok=True,
                uid=None,
                is_duplicate=False,
                message="Ignoring transient partial RFID read (2/7 bytes).",
            ),
            RfidReadResult(
                device_type=HardwareEndpointType.RFID_READER,
                status=HardwareOperationStatus.SUCCESS,
                ok=True,
                uid="000FE2767C0045",
                is_duplicate=False,
            ),
        ]
    )
    clock = _FakeClock()
    monkeypatch.setattr(auth_service_module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(auth_service_module.time, "sleep", clock.sleep)

    result = service.read_and_resolve_rfid(hardware_facade=hardware)

    assert result.rfid_uid == "000FE2767C0045"
    assert hardware.read_count == 2


def test_auth_read_and_resolve_rfid_returns_clean_failure_after_poll_window_expires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = _build_user(status=UserStatus.ACTIVE, is_active=True)
    service = AuthService(_FakeUserRepository(user), _AllowAllOpenDoorGuard())
    hardware = _FakeHardwareFacade(
        RfidReadResult(
            device_type=HardwareEndpointType.RFID_READER,
            status=HardwareOperationStatus.NO_CARD,
            ok=True,
            uid=None,
            is_duplicate=False,
            message="Ignoring transient partial RFID read (2/7 bytes).",
        )
    )
    clock = _FakeClock()
    monkeypatch.setattr(auth_service_module.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(auth_service_module.time, "sleep", clock.sleep)

    with pytest.raises(AuthorizationError, match="authorization window"):
        service.read_and_resolve_rfid(hardware_facade=hardware)

    assert hardware.read_count > 1
