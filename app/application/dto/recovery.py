from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import RecoveryClassification, RecoveryStatus


@dataclass(frozen=True, slots=True)
class RecoveryCaseDTO:
    recovery_case_id: int | None
    classification: RecoveryClassification
    status: RecoveryStatus
    summary: str
    context: dict[str, object]
    created_at: datetime | None
    resolved_at: datetime | None


@dataclass(frozen=True, slots=True)
class RecoveryScanResult:
    open_case_count: int
    open_cases: tuple[RecoveryCaseDTO, ...]
    unfinished_operation_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class RecoveryContextDTO:
    recovery_case_id: int
    summary: str
    context: dict[str, object]
