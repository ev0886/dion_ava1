from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ImportExecutionMode = Literal["dry_run", "apply"]
ImportTargetType = Literal["users", "items"]
ImportRowAction = Literal["create", "update", "skip", "error"]


@dataclass(frozen=True, slots=True)
class ImportExecutionRequestDTO:
    target_type: ImportTargetType
    mode: ImportExecutionMode
    source_path: str
    requested_by_user_id: int | None = None


@dataclass(frozen=True, slots=True)
class ImportRowMessageDTO:
    code: str
    message: str


@dataclass(frozen=True, slots=True)
class ImportRowResultDTO:
    row_number: int
    target_type: ImportTargetType
    key: str | None
    action: ImportRowAction
    valid: bool
    messages: tuple[ImportRowMessageDTO, ...]


@dataclass(frozen=True, slots=True)
class ImportAppliedChangeCountersDTO:
    created_count: int
    updated_count: int
    skipped_count: int


@dataclass(frozen=True, slots=True)
class ImportSummaryDTO:
    total_rows: int
    valid_rows: int
    invalid_rows: int
    created_count: int
    updated_count: int
    skipped_count: int
    error_count: int
    mode: ImportExecutionMode
    source_path: str
    target_type: ImportTargetType


@dataclass(frozen=True, slots=True)
class ImportExecutionResultDTO:
    target_type: ImportTargetType
    mode: ImportExecutionMode
    source_path: str
    rows: tuple[ImportRowResultDTO, ...]
    summary: ImportSummaryDTO
    applied_changes: ImportAppliedChangeCountersDTO


@dataclass(frozen=True, slots=True)
class ImportFormatsDTO:
    formats: tuple[str, ...]
    target_types: tuple[ImportTargetType, ...]
    modes: tuple[ImportExecutionMode, ...]
