from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.domain.enums import ExportStatus, RoleCode, SessionStatus, SessionType
from app.hardware.dto import HardwareOperationStatus

DiagnosticCommandName = Literal[
    "hardware_snapshot",
    "test_drum_positioning",
    "test_lock_open",
    "get_lock_status",
    "get_unlock_time",
    "set_unlock_time",
    "read_rfid",
    "clear_rfid_buffer",
]

ExportCategory = Literal[
    "event_logs",
    "audit_logs",
    "inventory_report",
    "diagnostic_dump",
]


@dataclass(frozen=True, slots=True)
class ServiceModeSessionDTO:
    session_id: int | None
    session_type: SessionType
    status: SessionStatus
    started_by_user_id: int
    operator_role: RoleCode | None
    started_at: datetime | None
    finished_at: datetime | None
    comment: str | None
    context: dict[str, object]


@dataclass(frozen=True, slots=True)
class DiagnosticHardwareEntryDTO:
    device_type: str
    is_available: bool
    status: HardwareOperationStatus
    message: str | None


@dataclass(frozen=True, slots=True)
class DiagnosticCommandResultDTO:
    command_name: DiagnosticCommandName
    ok: bool
    device_type: str | None
    status: str
    message: str | None
    payload: dict[str, object]


@dataclass(frozen=True, slots=True)
class DiagnosticSnapshotDTO:
    session_id: int | None
    captured_at: datetime
    overall_ok: bool
    entries: tuple[DiagnosticHardwareEntryDTO, ...]


@dataclass(frozen=True, slots=True)
class DiagnosticDumpManifestDTO:
    session_id: int | None
    generated_at: datetime
    sections: tuple[str, ...]
    file_names: tuple[str, ...]
    snapshot: DiagnosticSnapshotDTO
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class ExportArtifactPlanDTO:
    category: ExportCategory
    file_name: str
    content_kind: str
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class ExportPreparationResultDTO:
    export_id: int | None
    requested_by_user_id: int
    destination_type: str
    destination_path: str
    export_type: str
    status: ExportStatus
    artifact_count: int
    manifest_included: bool
    artifact_plan: tuple[ExportArtifactPlanDTO, ...]
    manifest: DiagnosticDumpManifestDTO | None
    comment: str | None
