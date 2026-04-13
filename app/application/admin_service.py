from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO

from app.application.dto.admin import AdminUserImportResultDTO, AdminUserRecordDTO
from app.application.exceptions import NotFoundError, ValidationError
from app.domain.enums import DispenseRestrictionPolicy, RoleCode, UserStatus
from app.persistence.models import User
from app.persistence.repositories.users import UserRepository


@dataclass(frozen=True, slots=True)
class _ImportedUserRow:
    row_number: int
    user_code: str
    full_name: str
    role_code: RoleCode
    rfid_uid: str | None
    dispense_restriction_policy: DispenseRestrictionPolicy


class AdminUserService:
    _CSV_COLUMNS = (
        "user_code",
        "full_name",
        "role_code",
        "rfid_uid",
        "dispense_restriction_policy",
    )
    _CSV_HEADER_TEXT = ",".join(_CSV_COLUMNS)

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

    def import_users_csv(self, csv_text: str) -> AdminUserImportResultDTO:
        rows = self._parse_csv_rows(csv_text)
        created_count = 0
        updated_count = 0

        try:
            for row in rows:
                try:
                    role = self.user_repository.get_role_by_code(row.role_code)
                    if role is None:
                        raise ValidationError(f"unknown role_code '{row.role_code.value}'")

                    user = self.user_repository.get_by_user_code(row.user_code)
                    if user is None:
                        user = User(
                            role_id=role.id,
                            user_code=row.user_code,
                            full_name=row.full_name,
                            status=UserStatus.ACTIVE,
                            dispense_restriction_policy=row.dispense_restriction_policy,
                            is_active=True,
                        )
                        self.user_repository.session.add(user)
                        self.user_repository.session.flush()
                        created_count += 1
                    else:
                        user.role_id = role.id
                        user.full_name = row.full_name
                        user.dispense_restriction_policy = row.dispense_restriction_policy
                        updated_count += 1

                    self._apply_rfid_assignment(user=user, normalized_rfid_uid=row.rfid_uid)
                except ValidationError as exc:
                    raise self._with_csv_row_context(row.row_number, exc) from exc

            self.user_repository.session.commit()
        except Exception:
            self.user_repository.session.rollback()
            raise

        return AdminUserImportResultDTO(
            created_count=created_count,
            updated_count=updated_count,
            total_rows=len(rows),
        )

    def _apply_rfid_assignment(self, *, user: User, normalized_rfid_uid: str | None) -> None:
        active_cards = self.user_repository.list_active_rfid_cards_for_user(user.id)

        if normalized_rfid_uid is None:
            self.user_repository.revoke_rfid_cards(active_cards)
            return

        existing_card = self.user_repository.get_rfid_card_by_uid(normalized_rfid_uid)
        if existing_card is not None and existing_card.user_id != user.id and existing_card.revoked_at is None:
            raise ValidationError(self._build_rfid_conflict_message(normalized_rfid_uid, existing_card.user_id))

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

    def _build_rfid_conflict_message(self, normalized_rfid_uid: str, owner_user_id: int) -> str:
        owner = self.user_repository.get_by_id(owner_user_id)
        if owner is None:
            return f"RFID UID '{normalized_rfid_uid}' is already assigned to another user"
        return (
            f"RFID UID '{normalized_rfid_uid}' is already assigned to user_code "
            f"'{owner.user_code}' ({owner.full_name})"
        )

    @staticmethod
    def _with_csv_row_context(row_number: int, exc: ValidationError) -> ValidationError:
        detail = str(exc)
        prefix = f"CSV row {row_number}: "
        if detail.startswith(prefix):
            return exc
        return ValidationError(f"{prefix}{detail}")

    @classmethod
    def _parse_csv_rows(cls, csv_text: str) -> list[_ImportedUserRow]:
        if not csv_text.strip():
            raise ValidationError("CSV payload must not be empty")

        reader = csv.DictReader(StringIO(csv_text))
        if reader.fieldnames is None:
            raise ValidationError("CSV header row is required")

        fieldnames = [fieldname.strip() for fieldname in reader.fieldnames]
        if tuple(fieldnames) != cls._CSV_COLUMNS:
            received_header = ",".join(fieldnames)
            raise ValidationError(
                f"CSV header mismatch. Expected: {cls._CSV_HEADER_TEXT}. Got: {received_header}"
            )

        rows: list[_ImportedUserRow] = []
        seen_user_codes: set[str] = set()
        for row_number, raw_row in enumerate(reader, start=2):
            if raw_row is None:
                continue
            user_code = cls._require_csv_value(raw_row, "user_code", row_number)
            if user_code in seen_user_codes:
                raise ValidationError(f"CSV row {row_number}: duplicate user_code {user_code} in import file")
            seen_user_codes.add(user_code)
            rows.append(
                _ImportedUserRow(
                    row_number=row_number,
                    user_code=user_code,
                    full_name=cls._require_csv_value(raw_row, "full_name", row_number),
                    role_code=cls._parse_role_code(raw_row.get("role_code"), row_number),
                    rfid_uid=cls._normalize_optional_rfid_uid(raw_row.get("rfid_uid")),
                    dispense_restriction_policy=cls._parse_policy(raw_row.get("dispense_restriction_policy"), row_number),
                )
            )

        if not rows:
            raise ValidationError("CSV must contain at least one data row")
        return rows

    @staticmethod
    def _require_csv_value(raw_row: dict[str, str | None], column_name: str, row_number: int) -> str:
        value = (raw_row.get(column_name) or "").strip()
        if not value:
            raise ValidationError(f"CSV row {row_number}: {column_name} must not be empty")
        return value

    @staticmethod
    def _parse_role_code(raw_role_code: str | None, row_number: int) -> RoleCode:
        normalized = (raw_role_code or "").strip().lower()
        if not normalized:
            raise ValidationError(f"CSV row {row_number}: role_code must not be empty")
        try:
            return RoleCode(normalized)
        except ValueError as exc:
            allowed_role_codes = ", ".join(role_code.value for role_code in RoleCode)
            raise ValidationError(
                f"CSV row {row_number}: invalid role_code '{raw_role_code}'. "
                f"Allowed role_code values: {allowed_role_codes}"
            ) from exc

    @staticmethod
    def _parse_policy(raw_policy: str | None, row_number: int) -> DispenseRestrictionPolicy:
        normalized = (raw_policy or "").strip().lower()
        if not normalized:
            raise ValidationError(f"CSV row {row_number}: dispense_restriction_policy must not be empty")
        try:
            return DispenseRestrictionPolicy(normalized)
        except ValueError as exc:
            raise ValidationError(
                f"CSV row {row_number}: invalid dispense_restriction_policy '{raw_policy}'"
            ) from exc


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
