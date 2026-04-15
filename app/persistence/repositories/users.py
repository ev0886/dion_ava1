from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from app.application.dto.admin import AdminUserRecordDTO
from app.domain.enums import RoleCode
from app.persistence.models import User, UserRfidCard
from app.persistence.models.auth import Role
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

    def get_role_by_code(self, role_code: RoleCode) -> Role | None:
        statement = select(Role).where(Role.code == role_code)
        return self.session.execute(statement).scalar_one_or_none()

    def list_for_admin(self) -> list[AdminUserRecordDTO]:
        statement = (
            select(User, Role.code, UserRfidCard.card_uid)
            .join(Role, Role.id == User.role_id)
            .outerjoin(
                UserRfidCard,
                (UserRfidCard.user_id == User.id)
                & UserRfidCard.is_active.is_(True)
                & UserRfidCard.revoked_at.is_(None),
            )
            .order_by(User.id.asc())
        )
        rows = self.session.execute(statement).all()
        return [
            AdminUserRecordDTO(
                user_id=user.id,
                user_code=user.user_code,
                full_name=user.full_name,
                status=user.status,
                is_active=user.is_active,
                role_code=role_code,
                rfid_uid=card_uid,
                dispense_restriction_policy=user.dispense_restriction_policy,
            )
            for user, role_code, card_uid in rows
        ]

    def get_admin_record(self, user_id: int) -> AdminUserRecordDTO:
        statement = (
            select(User, Role.code, UserRfidCard.card_uid)
            .join(Role, Role.id == User.role_id)
            .outerjoin(
                UserRfidCard,
                (UserRfidCard.user_id == User.id)
                & UserRfidCard.is_active.is_(True)
                & UserRfidCard.revoked_at.is_(None),
            )
            .where(User.id == user_id)
        )
        row = self.session.execute(statement).one_or_none()
        if row is None:
            raise LookupError(f"User not found: {user_id}")
        user, role_code, card_uid = row
        return AdminUserRecordDTO(
            user_id=user.id,
            user_code=user.user_code,
            full_name=user.full_name,
            status=user.status,
            is_active=user.is_active,
            role_code=role_code,
            rfid_uid=card_uid,
            dispense_restriction_policy=user.dispense_restriction_policy,
        )

    def list_active_rfid_cards_for_user(self, user_id: int) -> list[UserRfidCard]:
        statement = (
            select(UserRfidCard)
            .where(UserRfidCard.user_id == user_id)
            .where(UserRfidCard.is_active.is_(True))
            .where(UserRfidCard.revoked_at.is_(None))
            .order_by(UserRfidCard.id.asc())
        )
        return list(self.session.execute(statement).scalars().all())

    def get_rfid_card_by_uid(self, card_uid: str) -> UserRfidCard | None:
        statement = select(UserRfidCard).where(UserRfidCard.card_uid == card_uid)
        return self.session.execute(statement).scalar_one_or_none()

    def revoke_rfid_cards(self, cards: list[UserRfidCard]) -> None:
        if not cards:
            return
        revoked_at = datetime.now(UTC).replace(tzinfo=None)
        for card in cards:
            card.is_active = False
            card.revoked_at = revoked_at

    def create_rfid_card(self, *, user_id: int, card_uid: str, issued_at: datetime) -> UserRfidCard:
        card = UserRfidCard(
            user_id=user_id,
            card_uid=card_uid,
            is_active=True,
            issued_at=issued_at,
            revoked_at=None,
        )
        self.session.add(card)
        self.session.flush()
        return card
