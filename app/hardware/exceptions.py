from __future__ import annotations

from app.domain.enums import HardwareEndpointType


class HardwareError(Exception):
    def __init__(
        self,
        message: str,
        *,
        device_type: HardwareEndpointType,
        operation: str,
    ) -> None:
        super().__init__(message)
        self.device_type = device_type
        self.operation = operation


class HardwareBusyError(HardwareError):
    pass


class HardwareTimeoutError(HardwareError):
    pass


class HardwareFailureError(HardwareError):
    pass


class HardwareUnavailableError(HardwareError):
    pass


class HardwareProtocolNotImplementedError(HardwareUnavailableError):
    pass
