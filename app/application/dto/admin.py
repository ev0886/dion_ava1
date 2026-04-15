from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.config.settings import HardwareProvider
from app.domain.enums import (
    DispenseRestrictionPolicy,
    OperationState,
    OperationType,
    RoleCode,
    StartupReadinessStatus,
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
class AdminRecentOperationDTO:
    operation_id: int
    started_at: datetime | None
    operation_type: OperationType
    operation_state: OperationState
    user_code: str | None
    user_full_name: str | None
    item_name: str | None
    quantity: int | None
    slot_code: str | None


@dataclass(frozen=True, slots=True)
class AdminOperationExportRowDTO:
    operation_id: int
    started_at: datetime | None
    finished_at: datetime | None
    operation_type: OperationType
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
    health_status: str
    readiness_status: StartupReadinessStatus
    hardware_provider: HardwareProvider
    app_environment: str
    app_name: str
    api_host: str
    api_port: int
