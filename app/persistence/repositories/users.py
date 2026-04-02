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

    def get_active_rfid_card_for_user(self, user_id: int) -> UserRfidCard | None:
        statement = (
            select(UserRfidCard)
            .where(
                UserRfidCard.user_id == user_id,
                UserRfidCard.is_active.is_(True),
            )
            .order_by(UserRfidCard.id.desc())
        )
        return self.session.execute(statement).scalars().first()

    def get_active_rfid_card_by_uid(self, card_uid: str) -> UserRfidCard | None:
        statement = select(UserRfidCard).where(
            UserRfidCard.card_uid == card_uid,
            UserRfidCard.is_active.is_(True),
        )
        return self.session.execute(statement).scalar_one_or_none()

    def add_rfid_card(self, card: UserRfidCard) -> None:
        self.session.add(card)
