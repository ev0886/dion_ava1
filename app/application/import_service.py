from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.application.dto.imports import (
    ImportAppliedChangeCountersDTO,
    ImportExecutionRequestDTO,
    ImportExecutionResultDTO,
    ImportFormatsDTO,
    ImportRowMessageDTO,
    ImportRowResultDTO,
    ImportSummaryDTO,
)
from app.application.exceptions import NotFoundError, ValidationError
from app.domain.enums import ItemStatus, RoleCode, UserStatus
from app.persistence.models import AuditLog, Item, Role, User
from app.persistence.repositories.inventory import InventoryRepository
from app.persistence.repositories.logs import AuditLogRepository
from app.persistence.repositories.users import UserRepository

_SUPPORTED_FORMATS = ("json", "csv")
_SUPPORTED_TARGETS = ("users", "items")
_SUPPORTED_MODES = ("dry_run", "apply")


@dataclass(slots=True)
class ImportExecutionService:
    user_repository: UserRepository
    inventory_repository: InventoryRepository
    audit_log_repository: AuditLogRepository

    def get_supported_formats(self) -> ImportFormatsDTO:
        return ImportFormatsDTO(
            formats=_SUPPORTED_FORMATS,
            target_types=_SUPPORTED_TARGETS,
            modes=_SUPPORTED_MODES,
        )

    def execute_user_import(self, request: ImportExecutionRequestDTO) -> ImportExecutionResultDTO:
        return self._execute(request, target_type="users")

    def execute_item_import(self, request: ImportExecutionRequestDTO) -> ImportExecutionResultDTO:
        return self._execute(request, target_type="items")

    def execute(self, request: ImportExecutionRequestDTO) -> ImportExecutionResultDTO:
        if request.target_type == "users":
            return self.execute_user_import(request)
        if request.target_type == "items":
            return self.execute_item_import(request)
        raise ValidationError(f"Unsupported import target type: {request.target_type}")

    def _execute(self, request: ImportExecutionRequestDTO, *, target_type: str) -> ImportExecutionResultDTO:
        self._validate_request(request, target_type=target_type)
        source_path = self._resolve_source_path(request.source_path)
        rows = self._load_rows(source_path)
        if target_type == "users":
            plans = [self._plan_user_row(row_number=index, row=row) for index, row in enumerate(rows, start=1)]
        else:
            plans = [self._plan_item_row(row_number=index, row=row) for index, row in enumerate(rows, start=1)]

        if request.mode == "apply":
            self._apply_plans(plans, request=request, target_type=target_type)

        row_results = tuple(plan.result for plan in plans)
        created_count = sum(1 for plan in plans if plan.result.action == "create" and plan.result.valid)
        updated_count = sum(1 for plan in plans if plan.result.action == "update" and plan.result.valid)
        skipped_count = sum(1 for plan in plans if plan.result.action == "skip")
        error_count = sum(1 for plan in plans if plan.result.action == "error")
        summary = ImportSummaryDTO(
            total_rows=len(row_results),
            valid_rows=sum(1 for result in row_results if result.valid),
            invalid_rows=sum(1 for result in row_results if not result.valid),
            created_count=created_count,
            updated_count=updated_count,
            skipped_count=skipped_count,
            error_count=error_count,
            mode=request.mode,
            source_path=str(source_path),
            target_type=target_type,
        )
        return ImportExecutionResultDTO(
            target_type=target_type,
            mode=request.mode,
            source_path=str(source_path),
            rows=row_results,
            summary=summary,
            applied_changes=ImportAppliedChangeCountersDTO(
                created_count=created_count if request.mode == "apply" else 0,
                updated_count=updated_count if request.mode == "apply" else 0,
                skipped_count=skipped_count,
            ),
        )

    def _validate_request(self, request: ImportExecutionRequestDTO, *, target_type: str) -> None:
        if request.target_type != target_type:
            raise ValidationError(f"Request target type does not match workflow: {request.target_type}")
        if request.mode not in _SUPPORTED_MODES:
            raise ValidationError(f"Unsupported import mode: {request.mode}")
        if not request.source_path.strip():
            raise ValidationError("source_path must not be empty")
        if request.requested_by_user_id is not None and request.requested_by_user_id <= 0:
            raise ValidationError("requested_by_user_id must be positive")

    def _resolve_source_path(self, source_path: str) -> Path:
        path = Path(source_path)
        try:
            resolved = path.resolve(strict=True)
        except FileNotFoundError as error:
            raise NotFoundError(f"Import source file not found: {path}") from error
        if not resolved.is_file():
            raise ValidationError(f"Import source path is not a file: {resolved}")
        return resolved

    def _load_rows(self, source_path: Path) -> list[dict[str, Any]]:
        file_format = source_path.suffix.lower().lstrip(".")
        if file_format not in _SUPPORTED_FORMATS:
            raise ValidationError(f"Unsupported import format: {source_path.suffix or '<none>'}")
        try:
            if file_format == "json":
                return self._load_json_rows(source_path)
            return self._load_csv_rows(source_path)
        except OSError as error:
            raise ValidationError(f"Import source file is unreadable: {source_path}") from error

    def _load_json_rows(self, source_path: Path) -> list[dict[str, Any]]:
        with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
            payload = json.load(handle)
        if isinstance(payload, dict):
            payload = payload.get("rows")
        if not isinstance(payload, list):
            raise ValidationError("JSON import payload must be an array of objects or an object with a rows array")
        rows: list[dict[str, Any]] = []
        for index, row in enumerate(payload, start=1):
            if not isinstance(row, dict):
                raise ValidationError(f"JSON import row {index} must be an object")
            rows.append(dict(row))
        return rows

    def _load_csv_rows(self, source_path: Path) -> list[dict[str, Any]]:
        with source_path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if not reader.fieldnames:
                raise ValidationError("CSV import file must include a header row")
            return [dict(row) for row in reader]

    def _plan_user_row(self, *, row_number: int, row: dict[str, Any]) -> "_PlannedRow":
        messages: list[ImportRowMessageDTO] = []
        user_code = self._required_string(row, "user_code", messages)
        full_name = self._required_string(row, "full_name", messages)
        role_value = self._optional_string(row, "role_code") or self._optional_string(row, "role")
        if not role_value:
            messages.append(ImportRowMessageDTO(code="missing_role_code", message="role_code is required"))
            role = None
        else:
            role_code = self._parse_enum(RoleCode, role_value, "role_code", messages)
            role = self.user_repository.get_role_by_code(role_code) if role_code is not None else None
            if role_code is not None and role is None:
                messages.append(ImportRowMessageDTO(code="unknown_role_code", message=f"Role not found: {role_value}"))
        status = self._parse_optional_enum(UserStatus, row.get("status"), "status", messages) or UserStatus.ACTIVE
        is_active = self._parse_optional_bool(row.get("is_active"), "is_active", messages)
        if is_active is None:
            is_active = True
        if messages:
            return _PlannedRow.invalid(
                row_number=row_number,
                target_type="users",
                key=user_code,
                messages=messages,
            )

        existing = self.user_repository.get_by_user_code(user_code)
        desired = {
            "user_code": user_code,
            "full_name": full_name,
            "role_id": role.id if role is not None else None,
            "role_code": role.code.value if role is not None else None,
            "status": status.value,
            "is_active": is_active,
        }
        if existing is None:
            entity = User(
                role_id=role.id,
                user_code=user_code,
                full_name=full_name,
                status=status,
                is_active=is_active,
            )
            result = ImportRowResultDTO(
                row_number=row_number,
                target_type="users",
                key=user_code,
                action="create",
                valid=True,
                messages=(ImportRowMessageDTO(code="validated_create", message="Row is valid for create"),),
            )
            return _PlannedRow(result=result, entity=entity, before=None, after=desired)

        before = self._user_snapshot(existing)
        if (
            existing.full_name == full_name
            and existing.role_id == role.id
            and existing.status == status
            and existing.is_active is is_active
        ):
            return _PlannedRow.skip(
                row_number=row_number,
                target_type="users",
                key=user_code,
                before=before,
            )

        result = ImportRowResultDTO(
            row_number=row_number,
            target_type="users",
            key=user_code,
            action="update",
            valid=True,
            messages=(ImportRowMessageDTO(code="validated_update", message="Row is valid for update"),),
        )
        return _PlannedRow(
            result=result,
            entity=existing,
            before=before,
            after=desired,
            apply_update=lambda: self._apply_user_update(
                existing,
                full_name=full_name,
                role=role,
                status=status,
                is_active=is_active,
            ),
        )

    def _plan_item_row(self, *, row_number: int, row: dict[str, Any]) -> "_PlannedRow":
        messages: list[ImportRowMessageDTO] = []
        sku = self._required_string(row, "sku", messages)
        name = self._required_string(row, "name", messages)
        unit = self._required_string(row, "unit", messages)
        description = self._optional_string(row, "description")
        return_allowed = self._parse_optional_bool(row.get("return_allowed"), "return_allowed", messages)
        if return_allowed is None:
            return_allowed = False
        min_level = self._parse_optional_int(row.get("min_level"), "min_level", messages)
        if min_level is None:
            min_level = 0
        elif min_level < 0:
            messages.append(
                ImportRowMessageDTO(code="invalid_min_level", message="min_level must be greater than or equal to 0")
            )
        status = self._parse_optional_enum(ItemStatus, row.get("status"), "status", messages) or ItemStatus.ACTIVE
        if messages:
            return _PlannedRow.invalid(
                row_number=row_number,
                target_type="items",
                key=sku,
                messages=messages,
            )

        existing = self.inventory_repository.get_item_by_sku(sku)
        desired = {
            "sku": sku,
            "name": name,
            "description": description,
            "unit": unit,
            "return_allowed": return_allowed,
            "min_level": min_level,
            "status": status.value,
        }
        if existing is None:
            entity = Item(
                item_group_id=None,
                sku=sku,
                name=name,
                description=description,
                unit=unit,
                return_allowed=return_allowed,
                min_level=min_level,
                status=status,
            )
            result = ImportRowResultDTO(
                row_number=row_number,
                target_type="items",
                key=sku,
                action="create",
                valid=True,
                messages=(ImportRowMessageDTO(code="validated_create", message="Row is valid for create"),),
            )
            return _PlannedRow(result=result, entity=entity, before=None, after=desired)

        before = self._item_snapshot(existing)
        if (
            existing.name == name
            and existing.description == description
            and existing.unit == unit
            and existing.return_allowed is return_allowed
            and existing.min_level == min_level
            and existing.status == status
        ):
            return _PlannedRow.skip(
                row_number=row_number,
                target_type="items",
                key=sku,
                before=before,
            )

        result = ImportRowResultDTO(
            row_number=row_number,
            target_type="items",
            key=sku,
            action="update",
            valid=True,
            messages=(ImportRowMessageDTO(code="validated_update", message="Row is valid for update"),),
        )
        return _PlannedRow(
            result=result,
            entity=existing,
            before=before,
            after=desired,
            apply_update=lambda: self._apply_item_update(
                existing,
                name=name,
                description=description,
                unit=unit,
                return_allowed=return_allowed,
                min_level=min_level,
                status=status,
            ),
        )

    def _apply_plans(
        self,
        plans: list["_PlannedRow"],
        *,
        request: ImportExecutionRequestDTO,
        target_type: str,
    ) -> None:
        session = self.user_repository.session
        for plan in plans:
            if not plan.result.valid or plan.result.action == "skip":
                continue
            if plan.result.action == "create":
                if target_type == "users":
                    self.user_repository.add(plan.entity)
                else:
                    self.inventory_repository.add_item(plan.entity)
                session.flush()
                before_json = None
                after_json = dict(plan.after or {})
            else:
                before_json = dict(plan.before or {})
                if plan.apply_update is not None:
                    plan.apply_update()
                after_json = dict(plan.after or {})
            self.audit_log_repository.add(
                AuditLog(
                    entity_type=target_type[:-1],
                    entity_id=str(plan.entity.id),
                    action=f"import_{plan.result.action}",
                    actor_user_id=request.requested_by_user_id,
                    reason_code="import_apply",
                    comment=f"{target_type} import",
                    before_json=before_json,
                    after_json=after_json,
                )
            )
        session.commit()

    @staticmethod
    def _apply_user_update(
        user: User,
        *,
        full_name: str,
        role: Role,
        status: UserStatus,
        is_active: bool,
    ) -> None:
        user.full_name = full_name
        user.role_id = role.id
        user.status = status
        user.is_active = is_active

    @staticmethod
    def _apply_item_update(
        item: Item,
        *,
        name: str,
        description: str | None,
        unit: str,
        return_allowed: bool,
        min_level: int,
        status: ItemStatus,
    ) -> None:
        item.name = name
        item.description = description
        item.unit = unit
        item.return_allowed = return_allowed
        item.min_level = min_level
        item.status = status

    @staticmethod
    def _required_string(
        row: dict[str, Any],
        field_name: str,
        messages: list[ImportRowMessageDTO],
    ) -> str:
        value = row.get(field_name)
        if isinstance(value, str):
            value = value.strip()
        if value in (None, ""):
            messages.append(
                ImportRowMessageDTO(code=f"missing_{field_name}", message=f"{field_name} is required")
            )
            return ""
        return str(value)

    @staticmethod
    def _optional_string(row: dict[str, Any], field_name: str) -> str | None:
        value = row.get(field_name)
        if value is None:
            return None
        string_value = str(value).strip()
        return string_value or None

    @staticmethod
    def _parse_enum(enum_type, raw_value: str, field_name: str, messages: list[ImportRowMessageDTO]):
        try:
            return enum_type(str(raw_value).strip())
        except ValueError:
            messages.append(
                ImportRowMessageDTO(
                    code=f"invalid_{field_name}",
                    message=f"{field_name} must be one of: {', '.join(member.value for member in enum_type)}",
                )
            )
            return None

    def _parse_optional_enum(self, enum_type, raw_value: Any, field_name: str, messages: list[ImportRowMessageDTO]):
        if raw_value in (None, ""):
            return None
        return self._parse_enum(enum_type, str(raw_value), field_name, messages)

    @staticmethod
    def _parse_optional_bool(raw_value: Any, field_name: str, messages: list[ImportRowMessageDTO]) -> bool | None:
        if raw_value in (None, ""):
            return None
        if isinstance(raw_value, bool):
            return raw_value
        normalized = str(raw_value).strip().lower()
        if normalized in {"true", "1", "yes"}:
            return True
        if normalized in {"false", "0", "no"}:
            return False
        messages.append(
            ImportRowMessageDTO(code=f"invalid_{field_name}", message=f"{field_name} must be a boolean value")
        )
        return None

    @staticmethod
    def _parse_optional_int(raw_value: Any, field_name: str, messages: list[ImportRowMessageDTO]) -> int | None:
        if raw_value in (None, ""):
            return None
        try:
            return int(str(raw_value).strip())
        except ValueError:
            messages.append(
                ImportRowMessageDTO(code=f"invalid_{field_name}", message=f"{field_name} must be an integer")
            )
            return None

    def _user_snapshot(self, user: User) -> dict[str, object]:
        role = self.user_repository.session.get(Role, user.role_id)
        return {
            "user_code": user.user_code,
            "full_name": user.full_name,
            "role_id": user.role_id,
            "role_code": role.code.value if role is not None else None,
            "status": user.status.value,
            "is_active": user.is_active,
        }

    @staticmethod
    def _item_snapshot(item: Item) -> dict[str, object]:
        return {
            "sku": item.sku,
            "name": item.name,
            "description": item.description,
            "unit": item.unit,
            "return_allowed": item.return_allowed,
            "min_level": item.min_level,
            "status": item.status.value,
        }


@dataclass(slots=True)
class _PlannedRow:
    result: ImportRowResultDTO
    entity: User | Item | None = None
    before: dict[str, object] | None = None
    after: dict[str, object] | None = None
    apply_update: Any = None

    @classmethod
    def invalid(
        cls,
        *,
        row_number: int,
        target_type: str,
        key: str | None,
        messages: list[ImportRowMessageDTO],
    ) -> "_PlannedRow":
        return cls(
            result=ImportRowResultDTO(
                row_number=row_number,
                target_type=target_type,
                key=key,
                action="error",
                valid=False,
                messages=tuple(messages),
            )
        )

    @classmethod
    def skip(
        cls,
        *,
        row_number: int,
        target_type: str,
        key: str | None,
        before: dict[str, object] | None,
    ) -> "_PlannedRow":
        return cls(
            result=ImportRowResultDTO(
                row_number=row_number,
                target_type=target_type,
                key=key,
                action="skip",
                valid=True,
                messages=(ImportRowMessageDTO(code="no_changes", message="Row matches existing data"),),
            ),
            before=before,
            after=before,
        )
