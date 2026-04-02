from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from app.application.dto.exports import (
    AuditLogsReportFiltersDTO,
    AuditLogsReportRowDTO,
    EventLogsReportFiltersDTO,
    EventLogsReportRowDTO,
    ExportExecutionRequestDTO,
    ExportExecutionResultDTO,
    ExportStatusResultDTO,
    InventoryBalancesSnapshotFiltersDTO,
    InventoryBalancesSnapshotRowDTO,
    OperationsReportFiltersDTO,
    OperationsReportRowDTO,
    RecoveryCasesReportFiltersDTO,
    RecoveryCasesReportRowDTO,
    SupportedExportType,
)
from app.application.dto.service_mode import (
    DiagnosticDumpManifestDTO,
    DiagnosticSnapshotDTO,
    ExportArtifactPlanDTO,
    ExportPreparationResultDTO,
)
from app.application.exceptions import NotFoundError, ValidationError
from app.application.time import utc_now
from app.config import AppSettings
from app.domain.enums import ExportStatus
from app.persistence.models import Export
from app.persistence.repositories.inventory import InventoryRepository
from app.persistence.repositories.logs import AuditLogRepository, EventLogRepository
from app.persistence.repositories.operations import OperationRepository
from app.persistence.repositories.recovery import RecoveryRepository
from app.persistence.repositories.service import ExportRepository

_SUPPORTED_EXPORT_TYPES: tuple[SupportedExportType, ...] = (
    "operations_report",
    "recovery_cases_report",
    "audit_logs_report",
    "event_logs_report",
    "inventory_balances_snapshot_report",
)


def build_export_execution_request(
    *,
    requested_by_user_id: int | None,
    export_type: str,
    destination_type: str,
    destination_path: str,
    limit: int | None = None,
    operation_type: Any = None,
    operation_state: Any = None,
    recovery_status: Any = None,
    recovery_classification: Any = None,
    event_type: str | None = None,
    level: str | None = None,
    entity_type: str | None = None,
    actor_user_id: int | None = None,
    slot_id: int | None = None,
    item_id: int | None = None,
    user_id: int | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    comment: str | None = None,
) -> ExportExecutionRequestDTO:
    if export_type == "operations_report":
        filters = OperationsReportFiltersDTO(
            limit=limit,
            operation_type=operation_type,
            operation_state=operation_state,
            slot_id=slot_id,
            item_id=item_id,
            user_id=user_id,
            created_from=created_from,
            created_to=created_to,
        )
    elif export_type == "recovery_cases_report":
        filters = RecoveryCasesReportFiltersDTO(
            limit=limit,
            status=recovery_status,
            classification=recovery_classification,
            created_from=created_from,
            created_to=created_to,
        )
    elif export_type == "audit_logs_report":
        filters = AuditLogsReportFiltersDTO(
            limit=limit,
            entity_type=entity_type,
            actor_user_id=actor_user_id,
            created_from=created_from,
            created_to=created_to,
        )
    elif export_type == "event_logs_report":
        filters = EventLogsReportFiltersDTO(
            limit=limit,
            event_type=event_type,
            level=level,
            slot_id=slot_id,
            item_id=item_id,
            user_id=user_id,
            created_from=created_from,
            created_to=created_to,
        )
    elif export_type == "inventory_balances_snapshot_report":
        filters = InventoryBalancesSnapshotFiltersDTO(
            limit=limit,
            slot_id=slot_id,
            item_id=item_id,
            created_from=created_from,
            created_to=created_to,
        )
    else:
        filters = InventoryBalancesSnapshotFiltersDTO(limit=limit, created_from=created_from, created_to=created_to)

    return ExportExecutionRequestDTO(
        requested_by_user_id=requested_by_user_id,
        export_type=export_type,  # validated in service
        destination_type=destination_type,
        destination_path=destination_path,
        filters=filters,
        comment=comment,
    )


@dataclass(slots=True)
class ExportService:
    settings: AppSettings
    export_repository: ExportRepository
    operation_repository: OperationRepository
    recovery_repository: RecoveryRepository
    inventory_repository: InventoryRepository
    event_log_repository: EventLogRepository
    audit_log_repository: AuditLogRepository

    def prepare_export(
        self,
        *,
        requested_by_user_id: int,
        destination_type: str,
        destination_path: str,
        diagnostic_manifest: DiagnosticDumpManifestDTO | None = None,
        comment: str | None = None,
    ) -> ExportPreparationResultDTO:
        recent_event_count = len(self.event_log_repository.list_recent(limit=100))
        recent_audit_count = len(self.audit_log_repository.list_recent(limit=100))
        artifact_plan = self._artifact_plan(
            requested_by_user_id=requested_by_user_id,
            diagnostic_manifest=diagnostic_manifest,
            recent_event_count=recent_event_count,
            recent_audit_count=recent_audit_count,
        )
        export = Export(
            requested_by_user_id=requested_by_user_id,
            export_type="service_diagnostics_bundle",
            destination_type=destination_type,
            destination_path=destination_path,
            status=ExportStatus.PENDING,
            completed_at=None,
            file_path=None,
            error_message=None,
            comment=comment,
        )
        self.export_repository.add(export)
        self.export_repository.session.commit()
        return ExportPreparationResultDTO(
            export_id=export.id,
            requested_by_user_id=requested_by_user_id,
            destination_type=destination_type,
            destination_path=destination_path,
            export_type=export.export_type,
            status=export.status,
            artifact_plan=artifact_plan,
            manifest=diagnostic_manifest,
            comment=comment,
        )

    def execute_export(self, request: ExportExecutionRequestDTO) -> ExportExecutionResultDTO:
        self._validate_request(request)
        export = Export(
            requested_by_user_id=request.requested_by_user_id,
            export_type=request.export_type,
            destination_type=request.destination_type,
            destination_path=request.destination_path,
            status=ExportStatus.PENDING,
            completed_at=None,
            file_path=None,
            error_message=None,
            comment=request.comment,
        )
        self.export_repository.add(export)
        self.export_repository.session.flush()

        try:
            artifact_dir = self._resolve_artifact_dir(request.destination_path, export.id)
            artifact_dir.mkdir(parents=True, exist_ok=True)
            rows = self._build_rows(request)
            json_path = artifact_dir / f"{request.export_type}.json"
            csv_path = artifact_dir / f"{request.export_type}.csv"
            manifest_path = artifact_dir / "manifest.json"
            self._write_json_export(json_path, request=request, export_id=export.id or 0, rows=rows)
            self._write_csv_export(csv_path, rows=rows)
            self._write_manifest(
                manifest_path,
                export_id=export.id or 0,
                export_type=request.export_type,
                destination_path=artifact_dir,
                produced_files=(json_path, csv_path),
                row_count=len(rows),
                requested_by_user_id=request.requested_by_user_id,
                filters=request.filters,
                comment=request.comment,
            )
            export.file_path = str(manifest_path)
            export.status = ExportStatus.COMPLETED
            export.completed_at = utc_now()
            export.error_message = None
            self.export_repository.session.commit()
        except Exception as error:
            export.status = ExportStatus.FAILED
            export.completed_at = utc_now()
            export.error_message = str(error)
            self.export_repository.session.commit()
            raise

        produced_paths = (json_path, csv_path, manifest_path)
        return ExportExecutionResultDTO(
            export_id=export.id,
            export_type=request.export_type,
            destination_path=artifact_dir,
            produced_file_paths=produced_paths,
            row_count=len(rows),
            status=export.status,
            filters=request.filters,
            requested_by_user_id=request.requested_by_user_id,
            comment=request.comment,
        )

    def get_export(self, export_id: int) -> ExportStatusResultDTO:
        export = self.export_repository.get_by_id(export_id)
        if export is None:
            raise NotFoundError(f"Export {export_id} was not found")
        return ExportStatusResultDTO(
            export_id=export.id,
            export_type=export.export_type,
            destination_type=export.destination_type,
            destination_path=export.destination_path,
            file_path=export.file_path,
            produced_file_paths=self.export_repository.list_artifacts(export.file_path),
            status=export.status,
            requested_by_user_id=export.requested_by_user_id,
            completed_at=export.completed_at,
            error_message=export.error_message,
            comment=export.comment,
        )

    @staticmethod
    def build_diagnostic_dump_manifest(
        *,
        session_id: int | None,
        snapshot: DiagnosticSnapshotDTO,
    ) -> DiagnosticDumpManifestDTO:
        return DiagnosticDumpManifestDTO(
            session_id=session_id,
            generated_at=snapshot.captured_at,
            sections=("hardware_snapshot", "event_log_metadata", "audit_log_metadata"),
            file_names=("hardware_snapshot.json", "event_logs.meta.json", "audit_logs.meta.json"),
            snapshot=snapshot,
            metadata={
                "overall_ok": snapshot.overall_ok,
                "entry_count": len(snapshot.entries),
            },
        )

    @staticmethod
    def _artifact_plan(
        *,
        requested_by_user_id: int,
        diagnostic_manifest: DiagnosticDumpManifestDTO | None,
        recent_event_count: int,
        recent_audit_count: int,
    ) -> tuple[ExportArtifactPlanDTO, ...]:
        plan: list[ExportArtifactPlanDTO] = [
            ExportArtifactPlanDTO(
                category="event_logs",
                file_name="event_logs.meta.json",
                content_kind="metadata",
                metadata={"requested_by_user_id": requested_by_user_id, "recent_row_count": recent_event_count},
            ),
            ExportArtifactPlanDTO(
                category="audit_logs",
                file_name="audit_logs.meta.json",
                content_kind="metadata",
                metadata={"requested_by_user_id": requested_by_user_id, "recent_row_count": recent_audit_count},
            ),
            ExportArtifactPlanDTO(
                category="inventory_report",
                file_name="inventory_report.meta.json",
                content_kind="metadata",
                metadata={"requested_by_user_id": requested_by_user_id, "scope": "inventory_summary_placeholder"},
            ),
        ]
        if diagnostic_manifest is not None:
            plan.append(
                ExportArtifactPlanDTO(
                    category="diagnostic_dump",
                    file_name="diagnostic_dump_manifest.json",
                    content_kind="manifest",
                    metadata={
                        "session_id": diagnostic_manifest.session_id,
                        "section_count": len(diagnostic_manifest.sections),
                    },
                )
            )
        return tuple(plan)

    def _build_rows(
        self,
        request: ExportExecutionRequestDTO,
    ) -> list[
        OperationsReportRowDTO
        | RecoveryCasesReportRowDTO
        | AuditLogsReportRowDTO
        | EventLogsReportRowDTO
        | InventoryBalancesSnapshotRowDTO
    ]:
        if request.export_type == "operations_report":
            filters = request.filters
            assert isinstance(filters, OperationsReportFiltersDTO)
            return [
                OperationsReportRowDTO(
                    operation_id=row.id,
                    session_id=row.session_id,
                    operation_type=row.operation_type.value,
                    operation_state=row.operation_state.value,
                    user_id=row.user_id,
                    item_id=row.item_id,
                    slot_id=row.slot_id,
                    qty_requested=row.qty_requested,
                    qty_confirmed=row.qty_confirmed,
                    result=row.result,
                    error_code=row.error_code,
                    error_message=row.error_message,
                    started_at=row.started_at,
                    finished_at=row.finished_at,
                )
                for row in self.operation_repository.list_for_report(
                    limit=filters.limit,
                    operation_type=filters.operation_type.value if filters.operation_type is not None else None,
                    operation_state=filters.operation_state.value if filters.operation_state is not None else None,
                    slot_id=filters.slot_id,
                    item_id=filters.item_id,
                    user_id=filters.user_id,
                    created_from=filters.created_from,
                    created_to=filters.created_to,
                )
            ]

        if request.export_type == "recovery_cases_report":
            filters = request.filters
            assert isinstance(filters, RecoveryCasesReportFiltersDTO)
            return [
                RecoveryCasesReportRowDTO(
                    recovery_case_id=row.id,
                    classification=row.classification.value,
                    status=row.status.value,
                    summary=row.summary,
                    resolved_at=row.resolved_at,
                    created_at=row.created_at,
                )
                for row in self.recovery_repository.list_for_report(
                    limit=filters.limit,
                    status=filters.status.value if filters.status is not None else None,
                    classification=filters.classification.value if filters.classification is not None else None,
                    created_from=filters.created_from,
                    created_to=filters.created_to,
                )
            ]

        if request.export_type == "audit_logs_report":
            filters = request.filters
            assert isinstance(filters, AuditLogsReportFiltersDTO)
            return [
                AuditLogsReportRowDTO(
                    audit_log_id=row.id,
                    entity_type=row.entity_type,
                    entity_id=row.entity_id,
                    action=row.action,
                    actor_user_id=row.actor_user_id,
                    reason_code=row.reason_code,
                    comment=row.comment,
                    created_at=row.created_at,
                )
                for row in self.audit_log_repository.list_for_report(
                    limit=filters.limit,
                    entity_type=filters.entity_type,
                    actor_user_id=filters.actor_user_id,
                    created_from=filters.created_from,
                    created_to=filters.created_to,
                )
            ]

        if request.export_type == "event_logs_report":
            filters = request.filters
            assert isinstance(filters, EventLogsReportFiltersDTO)
            return [
                EventLogsReportRowDTO(
                    event_log_id=row.id,
                    event_type=row.event_type,
                    level=row.level,
                    source=row.source,
                    operation_id=row.operation_id,
                    session_id=row.session_id,
                    user_id=row.user_id,
                    slot_id=row.slot_id,
                    item_id=row.item_id,
                    qty=float(row.qty) if row.qty is not None else None,
                    result=row.result,
                    comment=row.comment,
                    message=row.message,
                    created_at=row.created_at,
                )
                for row in self.event_log_repository.list_for_report(
                    limit=filters.limit,
                    event_type=filters.event_type,
                    level=filters.level,
                    slot_id=filters.slot_id,
                    item_id=filters.item_id,
                    user_id=filters.user_id,
                    created_from=filters.created_from,
                    created_to=filters.created_to,
                )
            ]

        filters = request.filters
        assert isinstance(filters, InventoryBalancesSnapshotFiltersDTO)
        return [
            InventoryBalancesSnapshotRowDTO(
                inventory_balance_id=row.id,
                slot_id=row.slot_id,
                item_id=row.item_id,
                quantity=row.quantity,
                updated_at=row.updated_at,
            )
            for row in self.inventory_repository.list_balances_for_report(
                limit=filters.limit,
                slot_id=filters.slot_id,
                item_id=filters.item_id,
                created_from=filters.created_from,
                created_to=filters.created_to,
            )
        ]

    def _resolve_artifact_dir(self, destination_path: str, export_id: int | None) -> Path:
        raw_path = Path(destination_path)
        if raw_path.is_absolute():
            raise ValidationError("destination_path must be relative to the configured data_dir")
        if ".." in raw_path.parts:
            raise ValidationError("destination_path must stay inside the configured data_dir")
        base_dir = (self.settings.data_dir / raw_path).resolve()
        data_dir = self.settings.data_dir.resolve()
        if data_dir not in (base_dir, *base_dir.parents):
            raise ValidationError("destination_path must stay inside the configured data_dir")
        export_dir = base_dir / f"export_{export_id:06d}"
        return export_dir

    def _validate_request(self, request: ExportExecutionRequestDTO) -> None:
        if request.destination_type != "filesystem":
            raise ValidationError("Only filesystem destination_type is supported")
        if request.export_type not in _SUPPORTED_EXPORT_TYPES:
            raise ValidationError(f"Unsupported export_type: {request.export_type}")
        if request.filters.limit is not None and request.filters.limit <= 0:
            raise ValidationError("limit must be greater than zero")
        if (
            request.filters.created_from is not None
            and request.filters.created_to is not None
            and request.filters.created_from > request.filters.created_to
        ):
            raise ValidationError("created_from must be less than or equal to created_to")

    def _write_json_export(
        self,
        path: Path,
        *,
        request: ExportExecutionRequestDTO,
        export_id: int,
        rows: list[Any],
    ) -> None:
        payload = {
            "export_id": export_id,
            "export_type": request.export_type,
            "filters": self._to_jsonable(request.filters),
            "row_count": len(rows),
            "rows": [self._to_jsonable(row) for row in rows],
        }
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _write_csv_export(self, path: Path, *, rows: list[Any]) -> None:
        if not rows:
            path.write_text("", encoding="utf-8")
            return
        header = list(asdict(rows[0]).keys())
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=header)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: self._to_csv_value(value) for key, value in asdict(row).items()})

    def _write_manifest(
        self,
        path: Path,
        *,
        export_id: int,
        export_type: SupportedExportType,
        destination_path: Path,
        produced_files: tuple[Path, ...],
        row_count: int,
        requested_by_user_id: int | None,
        filters: Any,
        comment: str | None,
    ) -> None:
        manifest = {
            "comment": comment,
            "destination_path": str(destination_path),
            "export_id": export_id,
            "export_type": export_type,
            "filters": self._to_jsonable(filters),
            "produced_file_paths": [str(item) for item in produced_files],
            "requested_by_user_id": requested_by_user_id,
            "row_count": row_count,
            "status": ExportStatus.COMPLETED.value,
        }
        path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

    def _to_jsonable(self, value: Any) -> Any:
        if hasattr(value, "__dataclass_fields__"):
            return self._to_jsonable(asdict(value))
        if isinstance(value, dict):
            return {str(key): self._to_jsonable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._to_jsonable(item) for item in value]
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if hasattr(value, "value"):
            return value.value
        return value

    def _to_csv_value(self, value: Any) -> Any:
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        if hasattr(value, "value"):
            return value.value
        if isinstance(value, (dict, list, tuple)):
            return json.dumps(self._to_jsonable(value), sort_keys=True)
        return value
