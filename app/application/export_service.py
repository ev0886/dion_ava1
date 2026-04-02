from __future__ import annotations

from dataclasses import dataclass

from app.application.auth_service import AuthService
from app.application.dto.service_mode import (
    DiagnosticDumpManifestDTO,
    DiagnosticSnapshotDTO,
    ExportArtifactPlanDTO,
    ExportPreparationResultDTO,
)
from app.application.exceptions import ValidationError
from app.domain.enums import ExportStatus
from app.persistence.models import Export
from app.persistence.repositories.logs import AuditLogRepository, EventLogRepository
from app.persistence.repositories.service import ExportRepository


@dataclass(slots=True)
class ExportService:
    auth_service: AuthService
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
        requester = self.auth_service.get_user_by_id(requested_by_user_id)
        normalized_destination_type = self._normalize_destination_type(destination_type)
        normalized_destination_path = self._normalize_destination_path(destination_path)
        normalized_comment = self._normalize_comment(comment)
        recent_event_count = len(self.event_log_repository.list_recent(limit=100))
        recent_audit_count = len(self.audit_log_repository.list_recent(limit=100))
        artifact_plan = self._artifact_plan(
            requested_by_user_id=requester.user_id,
            diagnostic_manifest=diagnostic_manifest,
            recent_event_count=recent_event_count,
            recent_audit_count=recent_audit_count,
        )
        export = Export(
            requested_by_user_id=requester.user_id,
            export_type="service_diagnostics_bundle",
            destination_type=normalized_destination_type,
            destination_path=normalized_destination_path,
            status=ExportStatus.PENDING,
            completed_at=None,
            file_path=None,
            error_message=None,
            comment=normalized_comment,
        )
        self.export_repository.add(export)
        self.export_repository.session.commit()
        return ExportPreparationResultDTO(
            export_id=export.id,
            requested_by_user_id=requester.user_id,
            destination_type=normalized_destination_type,
            destination_path=normalized_destination_path,
            export_type=export.export_type,
            status=export.status,
            artifact_count=len(artifact_plan),
            manifest_included=diagnostic_manifest is not None,
            artifact_plan=artifact_plan,
            manifest=diagnostic_manifest,
            comment=normalized_comment,
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

    @staticmethod
    def _normalize_destination_type(destination_type: str) -> str:
        normalized = destination_type.strip().lower()
        if not normalized:
            raise ValidationError("destination_type must not be empty")
        if normalized != "filesystem":
            raise ValidationError(f"Unsupported destination_type: {destination_type}")
        return normalized

    @staticmethod
    def _normalize_destination_path(destination_path: str) -> str:
        normalized = destination_path.strip()
        if not normalized:
            raise ValidationError("destination_path must not be empty")
        return normalized

    @staticmethod
    def _normalize_comment(comment: str | None) -> str | None:
        if comment is None:
            return None
        normalized = comment.strip()
        return normalized or None
