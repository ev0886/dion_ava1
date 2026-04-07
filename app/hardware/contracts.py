from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.hardware.dto import (
    DrumPositionResult,
    HardwareOperationResult,
    LockStatusResult,
    RfidReadResult,
    UnlockResult,
    UnlockTimeResult,
)


@runtime_checkable
class DrumControllerContract(Protocol):
    def ping(self) -> HardwareOperationResult: ...

    def get_position(self) -> DrumPositionResult: ...

    def move_to_position(self, position: int) -> DrumPositionResult: ...


@runtime_checkable
class LockControllerContract(Protocol):
    def ping(self) -> HardwareOperationResult: ...

    def get_lock_status(self, board_address: int, lock_number: int) -> LockStatusResult: ...

    def unlock_lock(self, board_address: int, lock_number: int) -> UnlockResult: ...

    def get_unlock_time(self, board_address: int) -> UnlockTimeResult: ...

    def set_unlock_time(self, board_address: int, seconds: int) -> UnlockTimeResult: ...


@runtime_checkable
class RfidReaderContract(Protocol):
    def ping(self) -> HardwareOperationResult: ...

    def read_card(self, *, timeout_ms: int | None = None) -> RfidReadResult: ...

    def clear_buffer(self) -> HardwareOperationResult: ...
