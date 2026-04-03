from __future__ import annotations

from sqlalchemy import select

from app.domain.enums import RoleCode
from app.persistence.models import Role, User
from app.persistence.repositories.base import Repository


class UserRepository(Repository):
    def get_by_id(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def get_by_user_code(self, user_code: str) -> User | None:
        statement = select(User).where(User.user_code == user_code)
        return self.session.execute(statement).scalar_one_or_none()

    def get_role_by_code(self, role_code: RoleCode) -> Role | None:
        statement = select(Role).where(Role.code == role_code)
        return self.session.execute(statement).scalar_one_or_none()

    def add(self, user: User) -> None:
        self.session.add(user)
