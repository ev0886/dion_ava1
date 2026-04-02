from __future__ import annotations

import pytest

from app.application.auth_service import AuthService
from app.application.dto.auth import AuthRequest
from app.application.exceptions import AuthorizationError
from app.domain.enums import UserStatus
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
