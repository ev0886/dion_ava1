from __future__ import annotations

from sqlalchemy import select

from app.persistence.models import User, UserRfidCard
from app.persistence.repositories.base import Repository


class UserRepository(Repository):
    def get_by_id(self, user_id: int) -> User | None:
        return self.session.get(User, user_id)

    def get_by_user_code(self, user_code: str) -> User | None:
        statement = select(User).where(User.user_code == user_code)
        return self.session.execute(statement).scalar_one_or_none()

    def get_by_rfid_card_uid(self, card_uid: str) -> User | None:
        statement = (
            select(User)
            .join(UserRfidCard, UserRfidCard.user_id == User.id)
            .where(UserRfidCard.card_uid == card_uid)
            .where(UserRfidCard.is_active.is_(True))
            .where(UserRfidCard.revoked_at.is_(None))
        )
        return self.session.execute(statement).scalar_one_or_none()
