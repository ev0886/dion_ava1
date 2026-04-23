from __future__ import annotations

import csv
import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from io import StringIO

from app.application.dto.admin import (
    AdminBalanceExportRowDTO,
    AdminNomenclatureRecordDTO,
    AdminNomenclatureUpsertResultDTO,
    AdminOperationExportRowDTO,
    AdminRecentOperationDTO,
    AdminSystemStatusDTO,
    AdminUserImportResultDTO,
    AdminUserRecordDTO,
)
from app.application.open_door_guard import OpenDoorGuard
from app.application.startup_service import StartupOrchestrationService
from app.config import AppSettings
from app.config.settings import HardwareProvider
from app.application.exceptions import NotFoundError, ValidationError
from app.domain.enums import DispenseRestrictionPolicy, OperationState, OperationType, RoleCode, UserStatus
from app.persistence.models import User
from app.persistence.repositories.inventory import InventoryRepository
from app.persistence.repositories.logs import EventLogRepository
from app.persistence.repositories.nomenclature import NomenclatureRepository
from app.persistence.repositories.operations import OperationRepository
from app.persistence.repositories.service import SystemSettingRepository
from app.persistence.repositories.users import UserRepository


@dataclass(frozen=True, slots=True)
class _ImportedUserRow:
    row_number: int
    user_code: str
    full_name: str
    role_code: RoleCode
    rfid_uid: str | None
    dispense_restriction_policy: DispenseRestrictionPolicy


class AdminAuthService:
    DEFAULT_LOGIN = "admin"
    DEFAULT_PASSWORD = "dionava"
    SESSION_TTL_SECONDS = 12 * 60 * 60

    _PASSWORD_HASH_KEY = "admin.password_hash"
    _SESSION_KEY = "admin.session"
    _PASSWORD_ALGORITHM = "pbkdf2_sha256"
    _PASSWORD_ITERATIONS = 390_000

    def __init__(self, setting_repository: SystemSettingRepository) -> None:
        self.setting_repository = setting_repository

    def authenticate(self, *, login: str, password: str) -> str:
        if login != self.DEFAULT_LOGIN or not self.verify_password(password):
            raise ValidationError("Invalid admin login or password")
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(seconds=self.SESSION_TTL_SECONDS)
        self.setting_repository.set_value(
            key=self._SESSION_KEY,
            value=json.dumps(
                {
                    "token_hash": self._hash_session_token(token),
                    "expires_at": expires_at.isoformat(),
                },
                separators=(",", ":"),
            ),
            value_type="json",
            description="Current admin web UI session token hash",
        )
        self.setting_repository.session.commit()
        return token

    def is_session_valid(self, token: str | None) -> bool:
        if not token:
            return False
        raw_session = self.setting_repository.get_value(self._SESSION_KEY)
        if raw_session is None:
            return False
        try:
            payload = json.loads(raw_session)
            expected_hash = str(payload["token_hash"])
            expires_at = datetime.fromisoformat(str(payload["expires_at"]))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return False
        if expires_at <= datetime.now(UTC):
            return False
        return hmac.compare_digest(expected_hash, self._hash_session_token(token))

    def logout(self) -> None:
        self.setting_repository.set_value(
            key=self._SESSION_KEY,
            value="",
            value_type="json",
            description="Current admin web UI session token hash",
        )
        self.setting_repository.session.commit()

    def change_password(self, *, current_password: str, new_password: str, confirm_new_password: str) -> None:
        if not self.verify_password(current_password):
            raise ValidationError("Current password is incorrect")
        self._validate_new_password(new_password=new_password, confirm_new_password=confirm_new_password)
        self._set_password(new_password)

    def reset_to_default_password(self) -> None:
        self._set_password(self.DEFAULT_PASSWORD)

    def verify_password(self, password: str) -> bool:
        stored_hash = self._get_or_create_password_hash()
        try:
            algorithm, raw_iterations, raw_salt, raw_digest = stored_hash.split("$", 3)
            iterations = int(raw_iterations)
            salt = base64.b64decode(raw_salt.encode("ascii"))
            expected_digest = base64.b64decode(raw_digest.encode("ascii"))
        except (ValueError, TypeError):
            return False
        if algorithm != self._PASSWORD_ALGORITHM:
            return False
        actual_digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(expected_digest, actual_digest)

    def _get_or_create_password_hash(self) -> str:
        stored_hash = self.setting_repository.get_value(self._PASSWORD_HASH_KEY)
        if stored_hash:
            return stored_hash
        password_hash = self._build_password_hash(self.DEFAULT_PASSWORD)
        self.setting_repository.set_value(
            key=self._PASSWORD_HASH_KEY,
            value=password_hash,
            value_type="password_hash",
            description="Admin web UI password hash",
        )
        self.setting_repository.session.commit()
        return password_hash

    def _set_password(self, password: str) -> None:
        self.setting_repository.set_value(
            key=self._PASSWORD_HASH_KEY,
            value=self._build_password_hash(password),
            value_type="password_hash",
            description="Admin web UI password hash",
        )
        self.setting_repository.set_value(
            key=self._SESSION_KEY,
            value="",
            value_type="json",
            description="Current admin web UI session token hash",
        )
        self.setting_repository.session.commit()

    @classmethod
    def _build_password_hash(cls, password: str) -> str:
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, cls._PASSWORD_ITERATIONS)
        return "$".join(
            (
                cls._PASSWORD_ALGORITHM,
                str(cls._PASSWORD_ITERATIONS),
                base64.b64encode(salt).decode("ascii"),
                base64.b64encode(digest).decode("ascii"),
            )
        )

    @staticmethod
    def _hash_session_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_new_password(*, new_password: str, confirm_new_password: str) -> None:
        if new_password != confirm_new_password:
            raise ValidationError("New password confirmation does not match")
        if len(new_password) < 6:
            raise ValidationError("New password must contain at least 6 characters")


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

    def export_users_csv(self) -> str:
        output = StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(self._CSV_COLUMNS)
        for user in self.user_repository.list_for_admin():
            writer.writerow(
                (
                    user.user_code,
                    user.full_name,
                    user.role_code.value if user.role_code is not None else "",
                    user.rfid_uid or "",
                    user.dispense_restriction_policy.value,
                )
            )
        return output.getvalue()

    def update_user(
        self,
        *,
        user_id: int,
        rfid_uid: str | None,
        is_active: bool,
        dispense_restriction_policy: DispenseRestrictionPolicy,
    ) -> AdminUserRecordDTO:
        user = self.user_repository.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User not found: {user_id}")

        normalized_rfid_uid = self._normalize_optional_rfid_uid(rfid_uid)
        self._apply_rfid_assignment(user=user, normalized_rfid_uid=normalized_rfid_uid)
        user.is_active = is_active
        if is_active:
            if user.status is UserStatus.INACTIVE:
                user.status = UserStatus.ACTIVE
        elif user.status is UserStatus.ACTIVE:
            user.status = UserStatus.INACTIVE
        user.dispense_restriction_policy = dispense_restriction_policy
        self.user_repository.session.commit()
        return self.user_repository.get_admin_record(user.id)

    def create_user(
        self,
        *,
        user_code: str,
        full_name: str,
        role_code: RoleCode,
        rfid_uid: str | None,
        dispense_restriction_policy: DispenseRestrictionPolicy,
        is_active: bool = True,
    ) -> AdminUserRecordDTO:
        normalized_user_code = self._require_field_value(user_code, field_name="user_code")
        normalized_full_name = self._require_field_value(full_name, field_name="full_name")
        role = self.user_repository.get_role_by_code(role_code)
        if role is None:
            raise ValidationError(f"unknown role_code '{role_code.value}'")
        if self.user_repository.get_by_user_code(normalized_user_code) is not None:
            raise ValidationError(f"User with user_code '{normalized_user_code}' already exists")

        user = User(
            role_id=role.id,
            user_code=normalized_user_code,
            full_name=normalized_full_name,
            status=UserStatus.ACTIVE if is_active else UserStatus.INACTIVE,
            dispense_restriction_policy=dispense_restriction_policy,
            is_active=is_active,
        )

        try:
            self.user_repository.session.add(user)
            self.user_repository.session.flush()
            normalized_rfid_uid = self._normalize_optional_rfid_uid(rfid_uid)
            self._apply_rfid_assignment(user=user, normalized_rfid_uid=normalized_rfid_uid)
            self.user_repository.session.commit()
        except Exception:
            self.user_repository.session.rollback()
            raise
        return self.user_repository.get_admin_record(user.id)

    def import_users_csv(self, csv_text: str) -> AdminUserImportResultDTO:
        return self._import_users_csv(csv_text, update_existing=True)

    def import_new_users_csv(self, csv_text: str) -> AdminUserImportResultDTO:
        return self._import_users_csv(csv_text, update_existing=False)

    def _import_users_csv(self, csv_text: str, *, update_existing: bool) -> AdminUserImportResultDTO:
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
                    elif not update_existing:
                        continue
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
    def _require_field_value(value: str | None, *, field_name: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValidationError(f"{field_name} must not be empty")
        return normalized

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


class AdminNomenclatureService:
    def __init__(self, nomenclature_repository: NomenclatureRepository) -> None:
        self.nomenclature_repository = nomenclature_repository

    def list_nomenclature(self) -> list[AdminNomenclatureRecordDTO]:
        return self.nomenclature_repository.list_for_admin()

    def list_active_nomenclature(self) -> list[AdminNomenclatureRecordDTO]:
        return self.nomenclature_repository.list_active()

    def create_nomenclature(self, *, name: str) -> AdminNomenclatureUpsertResultDTO:
        normalized_name = self._normalize_name(name)
        existing = self.nomenclature_repository.get_by_normalized_name(normalized_name)

        try:
            if existing is not None:
                existing.name = self._collapse_name_whitespace(name)
                if existing.is_active:
                    raise ValidationError("Nomenclature name already exists")
                existing.is_active = True
                self.nomenclature_repository.ensure_active_item_for_entry(existing)
                self.nomenclature_repository.session.commit()
                return AdminNomenclatureUpsertResultDTO(
                    record=self.nomenclature_repository.get_admin_record(existing.id),
                    reactivated_existing=True,
                )

            created = self.nomenclature_repository.create(
                name=self._collapse_name_whitespace(name),
                normalized_name=normalized_name,
                is_active=True,
            )
            self.nomenclature_repository.ensure_active_item_for_entry(created)
            self.nomenclature_repository.session.commit()
            return AdminNomenclatureUpsertResultDTO(
                record=self.nomenclature_repository.get_admin_record(created.id),
                reactivated_existing=False,
            )
        except Exception:
            self.nomenclature_repository.session.rollback()
            raise

    def update_nomenclature(self, *, nomenclature_id: int, name: str) -> AdminNomenclatureRecordDTO:
        entry = self.nomenclature_repository.get_by_id(nomenclature_id)
        if entry is None:
            raise NotFoundError(f"Nomenclature entry not found: {nomenclature_id}")

        previous_normalized_name = entry.normalized_name
        normalized_name = self._normalize_name(name)
        existing = self.nomenclature_repository.get_by_normalized_name(normalized_name)
        if existing is not None and existing.id != nomenclature_id:
            if existing.is_active:
                raise ValidationError("Nomenclature name already exists")
            raise ValidationError("Inactive nomenclature entry with this name already exists")

        try:
            entry.name = self._collapse_name_whitespace(name)
            entry.normalized_name = normalized_name
            self.nomenclature_repository.sync_item_for_entry_rename(
                entry,
                previous_normalized_name=previous_normalized_name,
            )
            self.nomenclature_repository.session.commit()
            return self.nomenclature_repository.get_admin_record(entry.id)
        except Exception:
            self.nomenclature_repository.session.rollback()
            raise

    def activate_nomenclature(self, *, nomenclature_id: int) -> AdminNomenclatureRecordDTO:
        return self._set_active(nomenclature_id=nomenclature_id, is_active=True)

    def deactivate_nomenclature(self, *, nomenclature_id: int) -> AdminNomenclatureRecordDTO:
        return self._set_active(nomenclature_id=nomenclature_id, is_active=False)

    def _set_active(self, *, nomenclature_id: int, is_active: bool) -> AdminNomenclatureRecordDTO:
        entry = self.nomenclature_repository.get_by_id(nomenclature_id)
        if entry is None:
            raise NotFoundError(f"Nomenclature entry not found: {nomenclature_id}")

        try:
            entry.is_active = is_active
            if is_active:
                self.nomenclature_repository.ensure_active_item_for_entry(entry)
            self.nomenclature_repository.session.commit()
            return self.nomenclature_repository.get_admin_record(entry.id)
        except Exception:
            self.nomenclature_repository.session.rollback()
            raise

    @classmethod
    def _normalize_name(cls, name: str) -> str:
        collapsed = cls._collapse_name_whitespace(name)
        if not collapsed:
            raise ValidationError("Nomenclature name must not be empty")
        return collapsed.casefold()

    @staticmethod
    def _collapse_name_whitespace(name: str) -> str:
        return " ".join(name.split())


class AdminOperationService:
    _CSV_OPERATION_TYPE_LABELS: dict[OperationType, str] = {
        OperationType.DISPENSE: "Выдача",
        OperationType.RETURN: "Возврат",
        OperationType.REFILL_ITEM: "Пополнение",
        OperationType.RECOVERY: "Восстановление",
    }
    _CSV_OPERATION_STATE_LABELS: dict[OperationState, str] = {
        OperationState.COMPLETED: "Успешно",
        OperationState.FAILED: "Ошибка",
        OperationState.RECOVERY_REQUIRED: "Требуется проверка",
    }
    _CSV_COLUMNS = (
        "operation_id",
        "started_at",
        "finished_at",
        "operation_type",
        "operation_state",
        "user_code",
        "user_full_name",
        "item_name",
        "cell_number",
        "error_code",
        "error_message",
    )

    def __init__(
        self,
        operation_repository: OperationRepository,
        event_log_repository: EventLogRepository | None = None,
    ) -> None:
        self.operation_repository = operation_repository
        self.event_log_repository = event_log_repository

    def list_recent_operations(self, *, limit: int = 20) -> list[AdminRecentOperationDTO]:
        return self.operation_repository.list_recent_for_admin(limit=limit)

    def list_problem_operations(self, *, limit: int = 20) -> list[AdminRecentOperationDTO]:
        return self.operation_repository.list_problem_for_admin(limit=limit)

    def export_operations_csv(self, *, date_from: date, date_to: date) -> str:
        self._validate_export_range(date_from=date_from, date_to=date_to)
        rows = [
            self._csv_row_values(row)
            for row in self.operation_repository.list_for_admin_export(date_from=date_from, date_to=date_to)
        ]
        return self._render_csv(rows)

    def export_operations_csv_for_admin_touch(self, *, date_from: date, date_to: date) -> str:
        self._validate_export_range(date_from=date_from, date_to=date_to)
        rows = [
            self._csv_row_values(row)
            for row in self.operation_repository.list_for_admin_export(date_from=date_from, date_to=date_to)
        ]
        rows.extend(self._data_exchange_csv_rows(date_from=date_from, date_to=date_to))
        rows.sort(key=self._csv_sort_key)
        return self._render_csv(rows)

    @staticmethod
    def _validate_export_range(*, date_from: date, date_to: date) -> None:
        if date_from > date_to:
            raise ValidationError("date_from must be less than or equal to date_to")

    def _render_csv(self, rows: list[tuple[object, ...]]) -> str:
        output = StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(self._CSV_COLUMNS)
        for row in rows:
            writer.writerow(row)
        return output.getvalue()

    def _data_exchange_csv_rows(self, *, date_from: date, date_to: date) -> list[tuple[object, ...]]:
        if self.event_log_repository is None:
            return []

        rows: list[tuple[object, ...]] = []
        for event in self.event_log_repository.list_data_exchange_events(date_from=date_from, date_to=date_to):
            rows.append(
                (
                    "",
                    event.created_at.isoformat(),
                    event.created_at.isoformat(),
                    "data_transfer",
                    "Успешно" if event.result == "success" else "Ошибка",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    event.message or event.comment or "",
                )
            )
        return rows

    @staticmethod
    def _csv_row_values(row: AdminOperationExportRowDTO) -> tuple[object, ...]:
        return (
            row.operation_id,
            row.started_at.isoformat() if row.started_at is not None else "",
            row.finished_at.isoformat() if row.finished_at is not None else "",
            AdminOperationService._csv_operation_type_label(row),
            AdminOperationService._csv_operation_state_label(row.operation_state),
            row.user_code or "",
            row.user_full_name or "",
            row.item_name or "",
            row.cell_number if row.cell_number is not None else "",
            row.error_code or "",
            row.error_message or "",
        )

    @classmethod
    def _csv_operation_type_label(cls, row: AdminOperationExportRowDTO) -> str:
        if row.operation_type is OperationType.INVENTORY_ADJUSTMENT:
            if row.quantity_delta is not None:
                if row.quantity_delta > 0:
                    return "Пополнение"
                if row.quantity_delta < 0:
                    return "Изъятие"
        return cls._CSV_OPERATION_TYPE_LABELS.get(row.operation_type, row.operation_type.value)

    @classmethod
    def _csv_operation_state_label(cls, operation_state: OperationState) -> str:
        return cls._CSV_OPERATION_STATE_LABELS.get(operation_state, operation_state.value)

    @staticmethod
    def _csv_sort_key(row: tuple[object, ...]) -> tuple[str, str]:
        return (str(row[1] or row[2] or ""), str(row[0] or ""))


class AdminBalanceService:
    _CSV_COLUMNS = ("cell_number", "nomenclature", "quantity")

    def __init__(self, inventory_repository: InventoryRepository) -> None:
        self.inventory_repository = inventory_repository

    def list_balances_for_export(self) -> tuple[AdminBalanceExportRowDTO, ...]:
        return self.inventory_repository.list_positive_balances_for_admin_export()

    def export_balances_csv(self) -> str:
        output = StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(self._CSV_COLUMNS)
        for row in self.list_balances_for_export():
            writer.writerow((row.cell_number, row.nomenclature, row.quantity))
        return output.getvalue()


class AdminSystemStatusService:
    def __init__(
        self,
        startup_service: StartupOrchestrationService,
        open_door_guard: OpenDoorGuard,
    ) -> None:
        self.startup_service = startup_service
        self.open_door_guard = open_door_guard

    def get_system_status(self, settings: AppSettings) -> AdminSystemStatusDTO:
        startup_status = self.startup_service.run_startup_checks()
        try:
            open_cells = self.open_door_guard.any_controlled_cell_open(self.startup_service.hardware_facade)
        except Exception:
            open_cells = False
        return AdminSystemStatusDTO(
            api_available=True,
            hardware_status="ready" if startup_status.hardware.ok and not startup_status.hardware.degraded else "error",
            hardware_mode="real" if settings.hardware_provider is HardwareProvider.REAL else "mock",
            open_cells=open_cells,
            checked_at=_utcnow_naive(),
        )


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
