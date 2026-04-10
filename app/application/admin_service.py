from __future__ import annotations

from datetime import UTC, datetime

from app.application.dto.admin import AdminUserRecordDTO
from app.application.exceptions import NotFoundError, ValidationError
from app.domain.enums import DispenseRestrictionPolicy
from app.persistence.models import User
from app.persistence.repositories.users import UserRepository


class AdminUserService:
    def __init__(self, user_repository: UserRepository) -> None:
        self.user_repository = user_repository

    def list_users(self) -> list[AdminUserRecordDTO]:
        return self.user_repository.list_for_admin()

    def update_user(
        self,
        *,
        user_id: int,
        rfid_uid: str | None,
        dispense_restriction_policy: DispenseRestrictionPolicy,
    ) -> AdminUserRecordDTO:
        user = self.user_repository.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User not found: {user_id}")

        normalized_rfid_uid = self._normalize_optional_rfid_uid(rfid_uid)
        self._apply_rfid_assignment(user=user, normalized_rfid_uid=normalized_rfid_uid)
        user.dispense_restriction_policy = dispense_restriction_policy
        self.user_repository.session.commit()
        return self.user_repository.get_admin_record(user.id)

    def _apply_rfid_assignment(self, *, user: User, normalized_rfid_uid: str | None) -> None:
        active_cards = self.user_repository.list_active_rfid_cards_for_user(user.id)

        if normalized_rfid_uid is None:
            self.user_repository.revoke_rfid_cards(active_cards)
            return

        existing_card = self.user_repository.get_rfid_card_by_uid(normalized_rfid_uid)
        if existing_card is not None and existing_card.user_id != user.id and existing_card.revoked_at is None:
            raise ValidationError(f"RFID UID is already assigned to another user: {normalized_rfid_uid}")

        cards_to_revoke = [card for card in active_cards if existing_card is None or card.id != existing_card.id]
        self.user_repository.revoke_rfid_cards(cards_to_revoke)

        if existing_card is not None:
            existing_card.user_id = user.id
            existing_card.card_uid = normalized_rfid_uid
            existing_card.is_active = True
            existing_card.issued_at = _utcnow_naive()
            existing_card.revoked_at = None
            return

        if active_cards:
            active_cards[0].card_uid = normalized_rfid_uid
            active_cards[0].is_active = True
            active_cards[0].issued_at = _utcnow_naive()
            active_cards[0].revoked_at = None
            return

        self.user_repository.create_rfid_card(user_id=user.id, card_uid=normalized_rfid_uid, issued_at=_utcnow_naive())

    @staticmethod
    def _normalize_optional_rfid_uid(rfid_uid: str | None) -> str | None:
        if rfid_uid is None:
            return None
        normalized = "".join(character for character in rfid_uid if character.isalnum()).upper()
        if not normalized:
            return None
        return normalized


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
