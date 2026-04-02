from __future__ import annotations

from dataclasses import dataclass

from app.application.dto.service_mode import (
    DiagnosticDumpManifestDTO,
    DiagnosticSnapshotDTO,
    ExportArtifactPlanDTO,
    ExportPreparationResultDTO,
)
from app.domain.enums import ExportStatus
from app.persistence.models import Export
from app.persistence.repositories.logs import AuditLogRepository, EventLogRepository
from app.persistence.repositories.service import ExportRepository


@dataclass(slots=True)
class ExportService:
    export_repository: ExportRepository
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
