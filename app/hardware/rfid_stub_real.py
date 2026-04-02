from __future__ import annotations

from app.domain.enums import HardwareEndpointType
from app.hardware.dto import HardwareOperationResult, RfidReadResult
from app.hardware.exceptions import HardwareUnavailableError


class StubRealRfidAdapter:
    device_type = HardwareEndpointType.RFID_READER

    def ping(self) -> HardwareOperationResult:
        raise HardwareUnavailableError(
            "RFID reader real adapter is not implemented for provider 'stub-real'.",
            device_type=self.device_type,
            operation="ping",
        )

    def read_card(self) -> RfidReadResult:
        raise HardwareUnavailableError(
            "RFID reader real adapter is not implemented for provider 'stub-real'.",
            device_type=self.device_type,
            operation="read_card",
        )

    def clear_buffer(self) -> HardwareOperationResult:
        raise HardwareUnavailableError(
            "RFID reader real adapter is not implemented for provider 'stub-real'.",
            device_type=self.device_type,
            operation="clear_buffer",
        )
