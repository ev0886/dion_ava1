from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import (
    DispenseRestrictionPolicy,
    OperationState,
    OperationType,
    RoleCode,
    UserStatus,
)


@dataclass(frozen=True, slots=True)
class AdminUserRecordDTO:
    user_id: int
    user_code: str
    full_name: str
    status: UserStatus
    is_active: bool
    role_code: RoleCode | None
    rfid_uid: str | None
    dispense_restriction_policy: DispenseRestrictionPolicy


@dataclass(frozen=True, slots=True)
class AdminUserImportResultDTO:
    created_count: int
    updated_count: int
    total_rows: int


@dataclass(frozen=True, slots=True)
class AdminNomenclatureRecordDTO:
    id: int
    name: str
    is_active: bool


@dataclass(frozen=True, slots=True)
class AdminNomenclatureUpsertResultDTO:
    record: AdminNomenclatureRecordDTO
    reactivated_existing: bool


@dataclass(frozen=True, slots=True)
class AdminRecentOperationDTO:
    operation_id: int
    started_at: datetime | None
    operation_type: OperationType
    quantity_delta: int | None
    operation_state: OperationState
    user_code: str | None
    user_full_name: str | None
    item_name: str | None
    quantity: int | None
    slot_code: str | None
    cell_number: int | None


@dataclass(frozen=True, slots=True)
class AdminOperationExportRowDTO:
    operation_id: int
    started_at: datetime | None
    finished_at: datetime | None
    operation_type: OperationType
    quantity_delta: int | None
    operation_state: OperationState
    user_code: str | None
    user_full_name: str | None
    item_name: str | None
    quantity: int | None
    slot_code: str | None
    result: str | None
    error_code: str | None
    error_message: str | None


@dataclass(frozen=True, slots=True)
class AdminSystemStatusDTO:
    api_available: bool
    hardware_status: str
    hardware_mode: str
    open_cells: bool
    checked_at: datetime
