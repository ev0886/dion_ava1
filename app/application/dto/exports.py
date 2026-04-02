from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from app.domain.enums import ExportStatus, OperationState, OperationType, RecoveryClassification, RecoveryStatus

SupportedExportType = Literal[
    "operations_report",
    "recovery_cases_report",
    "audit_logs_report",
    "event_logs_report",
    "inventory_balances_snapshot_report",
]


@dataclass(frozen=True, slots=True)
class ExportFilterBaseDTO:
    limit: int | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None


@dataclass(frozen=True, slots=True)
class OperationsReportFiltersDTO(ExportFilterBaseDTO):
    operation_type: OperationType | None = None
    operation_state: OperationState | None = None
    slot_id: int | None = None
    item_id: int | None = None
    user_id: int | None = None


@dataclass(frozen=True, slots=True)
class RecoveryCasesReportFiltersDTO(ExportFilterBaseDTO):
    status: RecoveryStatus | None = None
    classification: RecoveryClassification | None = None


@dataclass(frozen=True, slots=True)
class AuditLogsReportFiltersDTO(ExportFilterBaseDTO):
    entity_type: str | None = None
    actor_user_id: int | None = None


@dataclass(frozen=True, slots=True)
class EventLogsReportFiltersDTO(ExportFilterBaseDTO):
    event_type: str | None = None
    level: str | None = None
    slot_id: int | None = None
    item_id: int | None = None
    user_id: int | None = None


@dataclass(frozen=True, slots=True)
class InventoryBalancesSnapshotFiltersDTO(ExportFilterBaseDTO):
    slot_id: int | None = None
    item_id: int | None = None


ExportFiltersDTO = (
    OperationsReportFiltersDTO
    | RecoveryCasesReportFiltersDTO
    | AuditLogsReportFiltersDTO
    | EventLogsReportFiltersDTO
    | InventoryBalancesSnapshotFiltersDTO
)


@dataclass(frozen=True, slots=True)
class ExportExecutionRequestDTO:
    requested_by_user_id: int | None
    export_type: SupportedExportType
    destination_type: str
    destination_path: str
    filters: ExportFiltersDTO
    comment: str | None = None


@dataclass(frozen=True, slots=True)
class OperationsReportRowDTO:
    operation_id: int
    session_id: int | None
    operation_type: str
    operation_state: str
    user_id: int | None
    item_id: int | None
    slot_id: int | None
    qty_requested: int
    qty_confirmed: int | None
    result: str | None
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class RecoveryCasesReportRowDTO:
    recovery_case_id: int
    classification: str
    status: str
    summary: str | None
    resolved_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AuditLogsReportRowDTO:
    audit_log_id: int
    entity_type: str
    entity_id: str
    action: str
    actor_user_id: int | None
    reason_code: str | None
    comment: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class EventLogsReportRowDTO:
    event_log_id: int
    event_type: str
    level: str
    source: str
    operation_id: int | None
    session_id: int | None
    user_id: int | None
    slot_id: int | None
    item_id: int | None
    qty: float | None
    result: str | None
    comment: str | None
    message: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class InventoryBalancesSnapshotRowDTO:
    inventory_balance_id: int
    slot_id: int
    item_id: int
    quantity: int
    updated_at: datetime


ReportRowDTO = (
    OperationsReportRowDTO
    | RecoveryCasesReportRowDTO
    | AuditLogsReportRowDTO
    | EventLogsReportRowDTO
    | InventoryBalancesSnapshotRowDTO
)


@dataclass(frozen=True, slots=True)
class ExportExecutionResultDTO:
    export_id: int | None
    export_type: SupportedExportType
    destination_path: Path
    produced_file_paths: tuple[Path, ...]
    row_count: int | None
    status: ExportStatus
    filters: ExportFiltersDTO
    requested_by_user_id: int | None
    comment: str | None


@dataclass(frozen=True, slots=True)
class ExportStatusResultDTO:
    export_id: int
    export_type: str
    destination_type: str
    destination_path: str
    file_path: str | None
    produced_file_paths: tuple[Path, ...]
    status: ExportStatus
    requested_by_user_id: int | None
    completed_at: datetime | None
    error_message: str | None
    comment: str | None
