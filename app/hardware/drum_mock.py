from __future__ import annotations

from app.domain.enums import HardwareEndpointType
from app.hardware.dto import (
    DrumPositionResult,
    HardwareEndpointDescriptor,
    HardwareOperationResult,
    HardwareOperationStatus,
    MockHardwareMode,
)
from app.hardware.exceptions import HardwareBusyError, HardwareFailureError, HardwareTimeoutError


class MockDrumAdapter:
    device_type = HardwareEndpointType.DRUM_CONTROLLER

    def __init__(
        self,
        *,
        initial_position: int = 0,
        ping_mode: MockHardwareMode = MockHardwareMode.SUCCESS,
        move_mode: MockHardwareMode = MockHardwareMode.SUCCESS,
    ) -> None:
        self._current_position = initial_position
        self._ping_mode = ping_mode
        self._move_mode = move_mode

    def set_ping_mode(self, mode: MockHardwareMode) -> None:
        self._ping_mode = mode

    def set_move_mode(self, mode: MockHardwareMode) -> None:
        self._move_mode = mode

    def describe_endpoint(self) -> HardwareEndpointDescriptor:
        return HardwareEndpointDescriptor(
            endpoint_kind="mock",
            configured_transport_mode=None,
            active_transport_mode="mock",
        )

    def ping(self) -> HardwareOperationResult:
        self._raise_for_mode(self._ping_mode, operation="ping")
        return HardwareOperationResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=True,
        )

    def get_position(self) -> DrumPositionResult:
        return DrumPositionResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=True,
            position=self._current_position,
        )

    def move_to_position(self, position: int) -> DrumPositionResult:
        if position < 0:
            raise ValueError("position must be non-negative")
        self._raise_for_mode(self._move_mode, operation="move_to_position")
        self._current_position = position
        return DrumPositionResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=True,
            position=self._current_position,
        )

    def _raise_for_mode(self, mode: MockHardwareMode, *, operation: str) -> None:
        if mode is MockHardwareMode.SUCCESS:
            return
        if mode is MockHardwareMode.BUSY:
            raise HardwareBusyError("Drum controller is busy", device_type=self.device_type, operation=operation)
        if mode is MockHardwareMode.TIMEOUT:
            raise HardwareTimeoutError("Drum controller timed out", device_type=self.device_type, operation=operation)
        raise HardwareFailureError("Drum controller failed", device_type=self.device_type, operation=operation)
