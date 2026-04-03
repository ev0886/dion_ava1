from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.application.dto.service_mode import DiagnosticSnapshotDTO
from app.application.dto.startup import StartupReadinessDTO
from app.domain.enums import ExportStatus, StartupReadinessStatus
from app.hardware.dto import HardwareOperationStatus


@dataclass(frozen=True, slots=True)
class DiagnosticsHardwareIssueDTO:
    device_type: str
    is_available: bool
    status: HardwareOperationStatus
    message: str | None


@dataclass(frozen=True, slots=True)
class DiagnosticsOperationIssueDTO:
    operation_id: int | None
    operation_type: str
    operation_state: str
    result: str | None
    error_code: str | None
    message: str | None
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class DiagnosticsRecoveryIssueDTO:
    recovery_case_id: int | None
    classification: str
    status: str
    summary: str
    created_at: datetime | None
    resolved_at: datetime | None


@dataclass(frozen=True, slots=True)
class DiagnosticsExportIssueDTO:
    export_id: int | None
    export_type: str
    destination_type: str
    status: ExportStatus
    message: str | None
    created_at: datetime | None
    completed_at: datetime | None


@dataclass(frozen=True, slots=True)
class DiagnosticsAuditSignalDTO:
    occurred_at: datetime | None
    entity_type: str
    entity_id: str
    action: str
    action_label: str
    actor_user_id: int | None
    reason_code: str | None
    comment: str | None


@dataclass(frozen=True, slots=True)
class DiagnosticsEventSignalDTO:
    occurred_at: datetime | None
    event_type: str
    event_label: str
    level: str
    source: str
    operation_id: int | None
    session_id: int | None
    user_id: int | None
    result: str | None
    message: str | None


@dataclass(frozen=True, slots=True)
class DiagnosticsSummaryDTO:
    readiness_status: StartupReadinessStatus
    message: str | None
    hardware_issues: tuple[DiagnosticsHardwareIssueDTO, ...]
    recent_failed_operations: tuple[DiagnosticsOperationIssueDTO, ...]
    recent_recovery_activity: tuple[DiagnosticsRecoveryIssueDTO, ...]
    recent_denials: tuple[DiagnosticsAuditSignalDTO, ...]
    recent_export_failures: tuple[DiagnosticsExportIssueDTO, ...]
    recent_important_events: tuple[DiagnosticsEventSignalDTO, ...]


@dataclass(frozen=True, slots=True)
class TroubleshootingSnapshotDTO:
    readiness: StartupReadinessDTO
    hardware_snapshot: DiagnosticSnapshotDTO
    recent_failed_operations: tuple[DiagnosticsOperationIssueDTO, ...]
    recent_recovery_cases: tuple[DiagnosticsRecoveryIssueDTO, ...]
    recent_audit_signals: tuple[DiagnosticsAuditSignalDTO, ...]
    recent_event_signals: tuple[DiagnosticsEventSignalDTO, ...]
    recent_export_failures: tuple[DiagnosticsExportIssueDTO, ...]
