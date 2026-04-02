from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.enums import HardwareEndpointType


class HardwareOperationStatus(StrEnum):
    SUCCESS = "success"
    BUSY = "busy"
    TIMEOUT = "timeout"
    FAILURE = "failure"
    NO_CARD = "no_card"
    ALREADY_OPEN = "already_open"


class MockHardwareMode(StrEnum):
    SUCCESS = "success"
    BUSY = "busy"
    TIMEOUT = "timeout"
    FAILURE = "failure"


class LockState(StrEnum):
    LOCKED = "locked"
    OPEN = "open"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class HardwareOperationResult:
    device_type: HardwareEndpointType
    status: HardwareOperationStatus
    ok: bool
    message: str | None = None


@dataclass(frozen=True, slots=True)
class DrumPositionResult:
    device_type: HardwareEndpointType
    status: HardwareOperationStatus
    ok: bool
    position: int
    message: str | None = None


@dataclass(frozen=True, slots=True)
class LockStatusResult:
    device_type: HardwareEndpointType
    status: HardwareOperationStatus
    ok: bool
    board_address: int
    lock_number: int
    lock_state: LockState
    message: str | None = None


@dataclass(frozen=True, slots=True)
class UnlockResult:
    device_type: HardwareEndpointType
    status: HardwareOperationStatus
    ok: bool
    board_address: int
    lock_number: int
    lock_state: LockState
    message: str | None = None


@dataclass(frozen=True, slots=True)
class UnlockTimeResult:
    device_type: HardwareEndpointType
    status: HardwareOperationStatus
    ok: bool
    board_address: int
    seconds: int
    message: str | None = None


@dataclass(frozen=True, slots=True)
class RfidReadResult:
    device_type: HardwareEndpointType
    status: HardwareOperationStatus
    ok: bool
    uid: str | None
    is_duplicate: bool
    message: str | None = None


@dataclass(frozen=True, slots=True)
class HardwareHealthEntry:
    device_type: HardwareEndpointType
    is_available: bool
    status: HardwareOperationStatus
    message: str | None = None


@dataclass(frozen=True, slots=True)
class HardwareHealthSnapshot:
    drum: HardwareHealthEntry
    lock: HardwareHealthEntry
    rfid: HardwareHealthEntry

    @property
    def all_ok(self) -> bool:
        return self.drum.is_available and self.lock.is_available and self.rfid.is_available
