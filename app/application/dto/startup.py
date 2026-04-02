from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import StartupReadinessStatus
from app.hardware.dto import HardwareOperationStatus


@dataclass(frozen=True, slots=True)
class DatabaseReadinessDTO:
    ok: bool
    simple_query_ok: bool
    alembic_version_table_present: bool
    message: str | None


@dataclass(frozen=True, slots=True)
class HardwareReadinessEntryDTO:
    device_type: str
    is_available: bool
    status: HardwareOperationStatus
    message: str | None


@dataclass(frozen=True, slots=True)
class HardwareReadinessDTO:
    ok: bool
    degraded: bool
    entries: tuple[HardwareReadinessEntryDTO, ...]
    message: str | None


@dataclass(frozen=True, slots=True)
class RecoveryReadinessDTO:
    ok: bool
    recovery_candidates_found: bool
    recovery_candidate_count: int
    recovery_case_count: int
    candidate_operation_ids: tuple[int, ...]
    message: str | None


@dataclass(frozen=True, slots=True)
class StartupReadinessDTO:
    database: DatabaseReadinessDTO
    hardware: HardwareReadinessDTO
    recovery: RecoveryReadinessDTO
    readiness_status: StartupReadinessStatus
    message: str | None
