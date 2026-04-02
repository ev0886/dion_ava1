from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


SupportedEntityType = Literal["users", "items"]
SupportedDataFormat = Literal["csv", "xlsx"]
SupportedSourceType = Literal["filesystem"]
SupportedDestinationType = Literal["filesystem"]
RowFieldType = Literal["string", "integer", "boolean"]


@dataclass(frozen=True, slots=True)
class NormalizedRowFieldDTO:
    field_name: str
    source_column: str
    field_type: RowFieldType
    required: bool


@dataclass(frozen=True, slots=True)
class ImportExportArtifactPlanDTO:
    file_name: str
    content_kind: str
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class ImportPreparationResultDTO:
    entity_type: SupportedEntityType
    source_type: str
    source_path: str
    format_type: str
    row_schema: tuple[NormalizedRowFieldDTO, ...]
    required_fields: tuple[str, ...]
    artifact_plan: tuple[ImportExportArtifactPlanDTO, ...]
    validation_messages: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExportPreparationResultDTO:
    entity_type: SupportedEntityType
    destination_type: str
    destination_path: str
    format_type: str
    row_schema: tuple[NormalizedRowFieldDTO, ...]
    artifact_plan: tuple[ImportExportArtifactPlanDTO, ...]
    validation_messages: tuple[str, ...]
    include_inactive: bool


@dataclass(frozen=True, slots=True)
class ImportPreparationRequest:
    requested_by_user_id: int
    entity_type: SupportedEntityType
    source_type: SupportedSourceType
    source_path: str
    format_type: SupportedDataFormat


@dataclass(frozen=True, slots=True)
class ExportPreparationRequest:
    requested_by_user_id: int
    entity_type: SupportedEntityType
    destination_type: SupportedDestinationType
    destination_path: str
    format_type: SupportedDataFormat
    include_inactive: bool = False
