from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from app.domain.enums import UserStatus
from app.persistence.models import User
from app.persistence.repositories.base import Repository


class UserRepository(Repository):
    def get_by_id(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def get_by_user_code(self, user_code: str) -> User | None:
        statement = select(User).where(User.user_code == user_code)
        return self.session.execute(statement).scalar_one_or_none()

    def list_users(
        self,
        *,
        limit: int,
        offset: int,
        status: UserStatus | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> list[User]:
        statement = select(User).order_by(User.id.asc()).limit(limit).offset(offset)
        if status is not None:
            statement = statement.where(User.status == status)
        if created_from is not None:
            statement = statement.where(User.created_at >= created_from)
        if created_to is not None:
            statement = statement.where(User.created_at <= created_to)
        return list(self.session.execute(statement).scalars())

    def count_users(
        self,
        *,
        status: UserStatus | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> int:
        statement = select(func.count()).select_from(User)
        if status is not None:
            statement = statement.where(User.status == status)
        if created_from is not None:
            statement = statement.where(User.created_at >= created_from)
        if created_to is not None:
            statement = statement.where(User.created_at <= created_to)
        return int(self.session.execute(statement).scalar_one())
