from __future__ import annotations

from sqlalchemy import Select, select

from app.domain.enums import UserStatus
from app.persistence.models import Role, User, UserRfidCard
from app.persistence.repositories.base import Repository


class UserRepository(Repository):
    def add(self, user: User) -> None:
        self.session.add(user)

    def get_by_id(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def get_by_user_code(self, user_code: str) -> User | None:
        statement = select(User).where(User.user_code == user_code)
        return self.session.execute(statement).scalar_one_or_none()

    def get_role_by_id(self, role_id: int) -> Role | None:
        return self.session.get(Role, role_id)

    def list_users(
        self,
        *,
        role_id: int | None = None,
        status: UserStatus | None = None,
        is_active: bool | None = None,
        search: str | None = None,
    ) -> list[User]:
        statement: Select[tuple[User]] = select(User).order_by(User.id.asc())
        if role_id is not None:
            statement = statement.where(User.role_id == role_id)
        if status is not None:
            statement = statement.where(User.status == status)
        if is_active is not None:
            statement = statement.where(User.is_active.is_(is_active))
        if search:
            pattern = f"%{search.strip()}%"
            statement = statement.where((User.user_code.ilike(pattern)) | (User.full_name.ilike(pattern)))
        return list(self.session.execute(statement).scalars())

    def list_rfid_cards_for_user(self, user_id: int) -> list[UserRfidCard]:
        statement = select(UserRfidCard).where(UserRfidCard.user_id == user_id).order_by(UserRfidCard.id.asc())
        return list(self.session.execute(statement).scalars())
