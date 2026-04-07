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

    def get_by_rfid_uid(self, rfid_uid: str) -> User | None:
        exact_match_statement = (
            select(User)
            .join(UserRfidCard, UserRfidCard.user_id == User.id)
            .where(
                UserRfidCard.card_uid == rfid_uid,
                UserRfidCard.is_active.is_(True),
                UserRfidCard.revoked_at.is_(None),
            )
        )
        user = self.session.execute(exact_match_statement).scalar_one_or_none()
        if user is not None:
            return user

        normalized_uid = self._normalize_rfid_uid(rfid_uid)
        normalized_match_statement = (
            select(User, UserRfidCard.card_uid)
            .join(UserRfidCard, UserRfidCard.user_id == User.id)
            .where(
                UserRfidCard.is_active.is_(True),
                UserRfidCard.revoked_at.is_(None),
            )
        )
        for candidate_user, candidate_uid in self.session.execute(normalized_match_statement).all():
            if self._normalize_rfid_uid(candidate_uid) == normalized_uid:
                return candidate_user
        return None

    @staticmethod
    def _normalize_rfid_uid(rfid_uid: str) -> str:
        return "".join(character for character in rfid_uid if character.isalnum()).upper()
