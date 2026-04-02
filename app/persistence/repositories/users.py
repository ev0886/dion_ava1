from __future__ import annotations

from sqlalchemy import select

from app.persistence.models import User
from app.persistence.repositories.base import Repository


class UserRepository(Repository):
    def get_by_id(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def get_by_user_code(self, user_code: str) -> User | None:
        statement = select(User).where(User.user_code == user_code)
        return self.session.execute(statement).scalar_one_or_none()
