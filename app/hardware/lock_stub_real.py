from __future__ import annotations

from app.domain.enums import HardwareEndpointType
from app.hardware.dto import HardwareOperationResult, LockStatusResult, UnlockResult, UnlockTimeResult
from app.hardware.exceptions import HardwareUnavailableError


class StubRealLockAdapter:
    device_type = HardwareEndpointType.LOCK_CONTROLLER

    def ping(self) -> HardwareOperationResult:
        raise HardwareUnavailableError(
            "Lock controller real adapter is not implemented for provider 'stub-real'.",
            device_type=self.device_type,
            operation="ping",
        )

    def get_lock_status(self, board_address: int, lock_number: int) -> LockStatusResult:
        raise HardwareUnavailableError(
            "Lock controller real adapter is not implemented for provider 'stub-real'.",
            device_type=self.device_type,
            operation="get_lock_status",
        )

    def unlock_lock(self, board_address: int, lock_number: int) -> UnlockResult:
        raise HardwareUnavailableError(
            "Lock controller real adapter is not implemented for provider 'stub-real'.",
            device_type=self.device_type,
            operation="unlock_lock",
        )

    def get_unlock_time(self, board_address: int) -> UnlockTimeResult:
        raise HardwareUnavailableError(
            "Lock controller real adapter is not implemented for provider 'stub-real'.",
            device_type=self.device_type,
            operation="get_unlock_time",
        )

    def set_unlock_time(self, board_address: int, seconds: int) -> UnlockTimeResult:
        if seconds <= 0:
            raise ValueError("seconds must be positive")
        raise HardwareUnavailableError(
            "Lock controller real adapter is not implemented for provider 'stub-real'.",
            device_type=self.device_type,
            operation="set_unlock_time",
        )
