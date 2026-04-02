from __future__ import annotations

import re
from dataclasses import dataclass

from app.application.auth_service import AuthService
from app.application.dto.auth import AuthRequest
from app.application.dto.rfid import RfidBindingResultDTO
from app.application.exceptions import InvalidStateTransitionError, NotFoundError, ValidationError
from app.application.time import utc_now
from app.persistence.models import AuditLog, EventLog, UserRfidCard
from app.persistence.repositories.logs import AuditLogRepository, EventLogRepository
from app.persistence.repositories.users import UserRepository


@dataclass(slots=True)
class RfidBindingService:
    auth_service: AuthService
    user_repository: UserRepository
    event_log_repository: EventLogRepository
    audit_log_repository: AuditLogRepository

    def bind_card(
        self,
        *,
        actor_user_id: int,
        user_id: int,
        card_uid: str,
        comment: str | None = None,
    ) -> RfidBindingResultDTO:
        actor = self.auth_service.get_user_by_id(actor_user_id)
        target = self.auth_service.authorize(AuthRequest(user_id=user_id))
        normalized_uid = self._normalize_uid(card_uid)
        normalized_comment = self._normalize_comment(comment)
        existing_for_user = self.user_repository.get_active_rfid_card_for_user(target.user_id)
        if existing_for_user is not None:
            raise InvalidStateTransitionError(f"User {target.user_id} already has an active RFID card.")
        self._ensure_uid_not_assigned(normalized_uid, expected_user_id=None)
        issued_at = utc_now()
        card = UserRfidCard(
            user_id=target.user_id,
            card_uid=normalized_uid,
            is_active=True,
            issued_at=issued_at,
            revoked_at=None,
        )
        self.user_repository.add_rfid_card(card)
        self.user_repository.session.flush()
        self._record_event(
            event_type="rfid_card_bound",
            actor_user_id=actor.user_id,
            user_id=target.user_id,
            result="bound",
            comment=normalized_comment,
            payload={"card_uid": normalized_uid},
        )
        self._record_audit(
            entity_id=str(card.id),
            actor_user_id=actor.user_id,
            action="rfid_bind",
            comment=normalized_comment,
            before_json=None,
            after_json=self._card_snapshot(card),
        )
        self.user_repository.session.commit()
        return self._result(
            user_id=target.user_id,
            actor_user_id=actor.user_id,
            action="bind",
            card=card,
            previous_card_uid=None,
            active_card_count=1,
            comment=normalized_comment,
        )

    def rebind_card(
        self,
        *,
        actor_user_id: int,
        user_id: int,
        card_uid: str,
        comment: str | None = None,
    ) -> RfidBindingResultDTO:
        actor = self.auth_service.get_user_by_id(actor_user_id)
        target = self.auth_service.authorize(AuthRequest(user_id=user_id))
        normalized_uid = self._normalize_uid(card_uid)
        normalized_comment = self._normalize_comment(comment)
        existing_for_user = self.user_repository.get_active_rfid_card_for_user(target.user_id)
        if existing_for_user is None:
            raise NotFoundError(f"Active RFID card not found for user: {target.user_id}")
        if existing_for_user.card_uid == normalized_uid:
            raise ValidationError("New RFID UID must differ from the currently active card.")
        self._ensure_uid_not_assigned(normalized_uid, expected_user_id=target.user_id)
        revoked_at = utc_now()
        before_snapshot = self._card_snapshot(existing_for_user)
        existing_for_user.is_active = False
        existing_for_user.revoked_at = revoked_at
        replacement = UserRfidCard(
            user_id=target.user_id,
            card_uid=normalized_uid,
            is_active=True,
            issued_at=revoked_at,
            revoked_at=None,
        )
        self.user_repository.add_rfid_card(replacement)
        self.user_repository.session.flush()
        self._record_event(
            event_type="rfid_card_rebound",
            actor_user_id=actor.user_id,
            user_id=target.user_id,
            result="rebound",
            comment=normalized_comment,
            payload={"previous_card_uid": existing_for_user.card_uid, "card_uid": normalized_uid},
        )
        self._record_audit(
            entity_id=str(replacement.id),
            actor_user_id=actor.user_id,
            action="rfid_rebind",
            comment=normalized_comment,
            before_json=before_snapshot,
            after_json=self._card_snapshot(replacement),
        )
        self.user_repository.session.commit()
        return self._result(
            user_id=target.user_id,
            actor_user_id=actor.user_id,
            action="rebind",
            card=replacement,
            previous_card_uid=existing_for_user.card_uid,
            active_card_count=1,
            comment=normalized_comment,
        )

    def unbind_card(
        self,
        *,
        actor_user_id: int,
        user_id: int,
        comment: str | None = None,
    ) -> RfidBindingResultDTO:
        actor = self.auth_service.get_user_by_id(actor_user_id)
        target = self.auth_service.get_user_by_id(user_id)
        normalized_comment = self._normalize_comment(comment)
        existing_for_user = self.user_repository.get_active_rfid_card_for_user(target.user_id)
        if existing_for_user is None:
            raise NotFoundError(f"Active RFID card not found for user: {target.user_id}")
        before_snapshot = self._card_snapshot(existing_for_user)
        revoked_at = utc_now()
        existing_for_user.is_active = False
        existing_for_user.revoked_at = revoked_at
        self._record_event(
            event_type="rfid_card_unbound",
            actor_user_id=actor.user_id,
            user_id=target.user_id,
            result="unbound",
            comment=normalized_comment,
            payload={"previous_card_uid": existing_for_user.card_uid},
        )
        self._record_audit(
            entity_id=str(existing_for_user.id),
            actor_user_id=actor.user_id,
            action="rfid_unbind",
            comment=normalized_comment,
            before_json=before_snapshot,
            after_json=self._card_snapshot(existing_for_user),
        )
        self.user_repository.session.commit()
        return RfidBindingResultDTO(
            user_id=target.user_id,
            actor_user_id=actor.user_id,
            card_uid=None,
            previous_card_uid=existing_for_user.card_uid,
            action="unbind",
            active_card_count=0,
            issued_at=None,
            revoked_at=revoked_at,
            comment=normalized_comment,
        )

    def _ensure_uid_not_assigned(self, card_uid: str, *, expected_user_id: int | None) -> None:
        existing_card = self.user_repository.get_active_rfid_card_by_uid(card_uid)
        if existing_card is None:
            return
        if expected_user_id is not None and existing_card.user_id == expected_user_id:
            raise ValidationError("RFID UID is already assigned to this user.")
        raise InvalidStateTransitionError(f"RFID UID is already assigned to user {existing_card.user_id}.")

    @staticmethod
    def _normalize_uid(card_uid: str) -> str:
        normalized = re.sub(r"[\s:\-]", "", card_uid).upper()
        if not normalized:
            raise ValidationError("card_uid must not be empty")
        if len(normalized) > 64:
            raise ValidationError("card_uid must not exceed 64 characters")
        if re.fullmatch(r"[0-9A-F]+", normalized) is None:
            raise ValidationError("card_uid must contain only hexadecimal characters")
        return normalized

    @staticmethod
    def _normalize_comment(comment: str | None) -> str | None:
        if comment is None:
            return None
        normalized = comment.strip()
        return normalized or None

    @staticmethod
    def _card_snapshot(card: UserRfidCard) -> dict[str, object]:
        return {
            "id": card.id,
            "user_id": card.user_id,
            "card_uid": card.card_uid,
            "is_active": card.is_active,
            "issued_at": card.issued_at.isoformat() if card.issued_at else None,
            "revoked_at": card.revoked_at.isoformat() if card.revoked_at else None,
        }

    def _record_event(
        self,
        *,
        event_type: str,
        actor_user_id: int,
        user_id: int,
        result: str,
        comment: str | None,
        payload: dict[str, object],
    ) -> None:
        self.event_log_repository.add(
            EventLog(
                event_type=event_type,
                level="info",
                source="rfid_binding_service",
                operation_id=None,
                session_id=None,
                user_id=user_id,
                slot_id=None,
                item_id=None,
                qty=None,
                result=result,
                comment=comment,
                message=comment,
                payload_json={"actor_user_id": actor_user_id, **payload},
            )
        )

    def _record_audit(
        self,
        *,
        entity_id: str,
        actor_user_id: int,
        action: str,
        comment: str | None,
        before_json: dict[str, object] | None,
        after_json: dict[str, object] | None,
    ) -> None:
        self.audit_log_repository.add(
            AuditLog(
                entity_type="user_rfid_card",
                entity_id=entity_id,
                action=action,
                actor_user_id=actor_user_id,
                reason_code=None,
                comment=comment,
                before_json=before_json,
                after_json=after_json,
            )
        )

    @staticmethod
    def _result(
        *,
        user_id: int,
        actor_user_id: int,
        action: str,
        card: UserRfidCard,
        previous_card_uid: str | None,
        active_card_count: int,
        comment: str | None,
    ) -> RfidBindingResultDTO:
        return RfidBindingResultDTO(
            user_id=user_id,
            actor_user_id=actor_user_id,
            card_uid=card.card_uid,
            previous_card_uid=previous_card_uid,
            action=action,
            active_card_count=active_card_count,
            issued_at=card.issued_at,
            revoked_at=card.revoked_at,
            comment=comment,
        )
