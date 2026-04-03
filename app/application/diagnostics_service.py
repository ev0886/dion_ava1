from __future__ import annotations

from dataclasses import dataclass

from app.application.dto.diagnostics import (
    DiagnosticsAuditSignalDTO,
    DiagnosticsEventSignalDTO,
    DiagnosticsExportIssueDTO,
    DiagnosticsHardwareIssueDTO,
    DiagnosticsOperationIssueDTO,
    DiagnosticsRecoveryIssueDTO,
    DiagnosticsSummaryDTO,
    TroubleshootingSnapshotDTO,
)
from app.application.service_mode_service import ServiceModeService
from app.application.startup_service import StartupOrchestrationService
from app.persistence.models import AuditLog, EventLog, Export, Operation, RecoveryCase
from app.persistence.repositories.logs import AuditLogRepository, EventLogRepository
from app.persistence.repositories.operations import OperationRepository
from app.persistence.repositories.recovery import RecoveryRepository
from app.persistence.repositories.service import ExportRepository


@dataclass(frozen=True, slots=True)
class DiagnosticsCaps:
    failed_operations: int = 5
    recovery_cases: int = 5
    denials: int = 5
    export_failures: int = 5
    important_events: int = 5
    audit_snapshot: int = 10
    event_snapshot: int = 10


@dataclass(slots=True)
class DiagnosticsService:
    startup_service: StartupOrchestrationService
    service_mode_service: ServiceModeService
    operation_repository: OperationRepository
    recovery_repository: RecoveryRepository
    event_log_repository: EventLogRepository
    audit_log_repository: AuditLogRepository
    export_repository: ExportRepository
    caps: DiagnosticsCaps = DiagnosticsCaps()

    def get_summary(self) -> DiagnosticsSummaryDTO:
        readiness = self.startup_service.run_startup_checks()
        return DiagnosticsSummaryDTO(
            readiness_status=readiness.readiness_status,
            message=readiness.message,
            hardware_issues=tuple(
                DiagnosticsHardwareIssueDTO(
                    device_type=entry.device_type,
                    is_available=entry.is_available,
                    status=entry.status,
                    message=entry.message,
                )
                for entry in readiness.hardware.entries
                if not entry.is_available
            ),
            recent_failed_operations=tuple(
                self._to_operation_issue(operation)
                for operation in self.operation_repository.list_recent_failures(limit=self.caps.failed_operations)
            ),
            recent_recovery_activity=tuple(
                self._to_recovery_issue(case)
                for case in self.recovery_repository.list_recent_cases(limit=self.caps.recovery_cases)
            ),
            recent_denials=tuple(
                self._to_audit_signal(log)
                for log in self.audit_log_repository.list_recent_filtered(
                    limit=self.caps.denials,
                    actions=("authorization_denied", "authentication_denied", "auth_denied"),
                    reason_codes=("authorization_denied", "authentication_denied", "auth_denied"),
                )
            ),
            recent_export_failures=tuple(
                self._to_export_issue(export)
                for export in self.export_repository.list_recent_failures(limit=self.caps.export_failures)
            ),
            recent_important_events=tuple(
                self._to_event_signal(log)
                for log in self.event_log_repository.list_recent_filtered(
                    limit=self.caps.important_events,
                    levels=("error",),
                    event_types=("service_mode_entered", "service_mode_exited"),
                )
            ),
        )

    def get_troubleshooting_snapshot(self) -> TroubleshootingSnapshotDTO:
        readiness = self.startup_service.run_startup_checks()
        snapshot = self.service_mode_service.get_hardware_snapshot(session_id=None)
        return TroubleshootingSnapshotDTO(
            readiness=readiness,
            hardware_snapshot=snapshot,
            recent_failed_operations=tuple(
                self._to_operation_issue(operation)
                for operation in self.operation_repository.list_recent_failures(limit=self.caps.failed_operations)
            ),
            recent_recovery_cases=tuple(
                self._to_recovery_issue(case)
                for case in self.recovery_repository.list_recent_cases(limit=self.caps.recovery_cases)
            ),
            recent_audit_signals=tuple(
                self._to_audit_signal(log) for log in self.audit_log_repository.list_recent(limit=self.caps.audit_snapshot)
            ),
            recent_event_signals=tuple(
                self._to_event_signal(log) for log in self.event_log_repository.list_recent(limit=self.caps.event_snapshot)
            ),
            recent_export_failures=tuple(
                self._to_export_issue(export)
                for export in self.export_repository.list_recent_failures(limit=self.caps.export_failures)
            ),
        )

    @staticmethod
    def _to_operation_issue(operation: Operation) -> DiagnosticsOperationIssueDTO:
        return DiagnosticsOperationIssueDTO(
            operation_id=operation.id,
            operation_type=operation.operation_type.value,
            operation_state=operation.operation_state.value,
            result=operation.result,
            error_code=operation.error_code,
            message=operation.error_message,
            started_at=operation.started_at,
            finished_at=operation.finished_at,
        )

    @staticmethod
    def _to_recovery_issue(case: RecoveryCase) -> DiagnosticsRecoveryIssueDTO:
        return DiagnosticsRecoveryIssueDTO(
            recovery_case_id=case.id,
            classification=case.classification.value,
            status=case.status.value,
            summary=case.summary,
            created_at=case.created_at,
            resolved_at=case.resolved_at,
        )

    @staticmethod
    def _to_export_issue(export: Export) -> DiagnosticsExportIssueDTO:
        return DiagnosticsExportIssueDTO(
            export_id=export.id,
            export_type=export.export_type,
            destination_type=export.destination_type,
            status=export.status,
            message=export.error_message or export.comment,
            created_at=export.created_at,
            completed_at=export.completed_at,
        )

    def _to_audit_signal(self, log: AuditLog) -> DiagnosticsAuditSignalDTO:
        return DiagnosticsAuditSignalDTO(
            occurred_at=log.created_at,
            entity_type=log.entity_type,
            entity_id=log.entity_id,
            action=log.action,
            action_label=self._friendly_label(log.action),
            actor_user_id=log.actor_user_id,
            reason_code=log.reason_code,
            comment=log.comment,
        )

    def _to_event_signal(self, log: EventLog) -> DiagnosticsEventSignalDTO:
        return DiagnosticsEventSignalDTO(
            occurred_at=log.created_at,
            event_type=log.event_type,
            event_label=self._friendly_label(log.event_type),
            level=log.level,
            source=log.source,
            operation_id=log.operation_id,
            session_id=log.session_id,
            user_id=log.user_id,
            result=log.result,
            message=log.message or log.comment,
        )

    @staticmethod
    def _friendly_label(value: str) -> str:
        return value.replace("_", " ").strip()
