from __future__ import annotations

from app.domain.enums import HardwareEndpointType
from app.hardware.dto import DrumPositionResult, HardwareOperationResult, HardwareOperationStatus
from app.hardware.exceptions import HardwareUnavailableError


class StubRealDrumAdapter:
    device_type = HardwareEndpointType.DRUM_CONTROLLER

    def ping(self) -> HardwareOperationResult:
        raise HardwareUnavailableError(
            "Drum controller real adapter is not implemented for provider 'stub-real'.",
            device_type=self.device_type,
            operation="ping",
        )

    def get_position(self) -> DrumPositionResult:
        raise HardwareUnavailableError(
            "Drum controller real adapter is not implemented for provider 'stub-real'.",
            device_type=self.device_type,
            operation="get_position",
        )

    def move_to_position(self, position: int) -> DrumPositionResult:
        if position < 0:
            raise ValueError("position must be non-negative")
        raise HardwareUnavailableError(
            "Drum controller real adapter is not implemented for provider 'stub-real'.",
            device_type=self.device_type,
            operation="move_to_position",
        )
