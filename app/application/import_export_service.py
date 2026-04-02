from __future__ import annotations

from dataclasses import dataclass

from app.application.auth_service import AuthService
from app.application.dto.import_export import (
    ExportPreparationRequest,
    ExportPreparationResultDTO,
    ImportExportArtifactPlanDTO,
    ImportPreparationRequest,
    ImportPreparationResultDTO,
    NormalizedRowFieldDTO,
)
from app.application.exceptions import ValidationError


@dataclass(slots=True)
class ImportExportPreparationService:
    auth_service: AuthService

    def prepare_import(self, request: ImportPreparationRequest) -> ImportPreparationResultDTO:
        requester = self.auth_service.get_user_by_id(request.requested_by_user_id)
        entity_type = self._normalize_entity_type(request.entity_type)
        source_type = self._normalize_source_type(request.source_type)
        source_path = self._normalize_path(request.source_path, field_name="source_path")
        format_type = self._normalize_format_type(request.format_type)
        row_schema = self._row_schema(entity_type)
        required_fields = tuple(field.field_name for field in row_schema if field.required)
        artifact_plan = (
            ImportExportArtifactPlanDTO(
                file_name=f"{entity_type}_import.{format_type}",
                content_kind="source_placeholder",
                metadata={"entity_type": entity_type, "source_type": source_type},
            ),
            ImportExportArtifactPlanDTO(
                file_name=f"{entity_type}_import.schema.json",
                content_kind="row_schema",
                metadata={"field_count": len(row_schema), "requested_by_user_id": requester.user_id},
            ),
        )
        return ImportPreparationResultDTO(
            entity_type=entity_type,
            source_type=source_type,
            source_path=source_path,
            format_type=format_type,
            row_schema=row_schema,
            required_fields=required_fields,
            artifact_plan=artifact_plan,
            validation_messages=(
                "Parsing is not implemented in this MVP step.",
                "Rows must match the normalized schema exactly.",
            ),
        )

    def prepare_export(self, request: ExportPreparationRequest) -> ExportPreparationResultDTO:
        requester = self.auth_service.get_user_by_id(request.requested_by_user_id)
        entity_type = self._normalize_entity_type(request.entity_type)
        destination_type = self._normalize_destination_type(request.destination_type)
        destination_path = self._normalize_path(request.destination_path, field_name="destination_path")
        format_type = self._normalize_format_type(request.format_type)
        row_schema = self._row_schema(entity_type)
        artifact_plan = (
            ImportExportArtifactPlanDTO(
                file_name=f"{entity_type}_export.{format_type}",
                content_kind="data_placeholder",
                metadata={
                    "entity_type": entity_type,
                    "destination_type": destination_type,
                    "include_inactive": request.include_inactive,
                },
            ),
            ImportExportArtifactPlanDTO(
                file_name=f"{entity_type}_export.schema.json",
                content_kind="row_schema",
                metadata={"field_count": len(row_schema), "requested_by_user_id": requester.user_id},
            ),
        )
        return ExportPreparationResultDTO(
            entity_type=entity_type,
            destination_type=destination_type,
            destination_path=destination_path,
            format_type=format_type,
            row_schema=row_schema,
            artifact_plan=artifact_plan,
            validation_messages=(
                "File generation is not implemented in this MVP step.",
                "Export payloads must follow the normalized row schema.",
            ),
            include_inactive=request.include_inactive,
        )

    @staticmethod
    def _row_schema(entity_type: str) -> tuple[NormalizedRowFieldDTO, ...]:
        if entity_type == "users":
            return (
                NormalizedRowFieldDTO("user_code", "user_code", "string", True),
                NormalizedRowFieldDTO("full_name", "full_name", "string", True),
                NormalizedRowFieldDTO("role_code", "role_code", "string", True),
                NormalizedRowFieldDTO("status", "status", "string", True),
                NormalizedRowFieldDTO("is_active", "is_active", "boolean", True),
                NormalizedRowFieldDTO("rfid_uid", "rfid_uid", "string", False),
            )
        return (
            NormalizedRowFieldDTO("sku", "sku", "string", True),
            NormalizedRowFieldDTO("name", "name", "string", True),
            NormalizedRowFieldDTO("unit", "unit", "string", True),
            NormalizedRowFieldDTO("status", "status", "string", True),
            NormalizedRowFieldDTO("return_allowed", "return_allowed", "boolean", True),
            NormalizedRowFieldDTO("min_level", "min_level", "integer", True),
        )

    @staticmethod
    def _normalize_entity_type(entity_type: str) -> str:
        normalized = entity_type.strip().lower()
        if normalized not in {"users", "items"}:
            raise ValidationError(f"Unsupported entity_type: {entity_type}")
        return normalized

    @staticmethod
    def _normalize_format_type(format_type: str) -> str:
        normalized = format_type.strip().lower()
        if normalized not in {"csv", "xlsx"}:
            raise ValidationError(f"Unsupported format_type: {format_type}")
        return normalized

    @staticmethod
    def _normalize_source_type(source_type: str) -> str:
        normalized = source_type.strip().lower()
        if normalized != "filesystem":
            raise ValidationError(f"Unsupported source_type: {source_type}")
        return normalized

    @staticmethod
    def _normalize_destination_type(destination_type: str) -> str:
        normalized = destination_type.strip().lower()
        if normalized != "filesystem":
            raise ValidationError(f"Unsupported destination_type: {destination_type}")
        return normalized

    @staticmethod
    def _normalize_path(path_value: str, *, field_name: str) -> str:
        normalized = path_value.strip()
        if not normalized:
            raise ValidationError(f"{field_name} must not be empty")
        return normalized
