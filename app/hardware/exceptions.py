from __future__ import annotations

from app.domain.enums import HardwareEndpointType


class HardwareError(Exception):
    def __init__(
        self,
        message: str,
        *,
        device_type: HardwareEndpointType,
        operation: str,
        detail: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.device_type = device_type
        self.operation = operation
        self.detail = dict(detail or {})

    @property
    def normalized_status(self):
        from app.hardware.dto import HardwareOperationStatus

        if isinstance(self, HardwareUnavailableError):
            return HardwareOperationStatus.UNAVAILABLE
        if isinstance(self, HardwareTimeoutError):
            return HardwareOperationStatus.TIMEOUT
        if isinstance(self, HardwareBusyError):
            return HardwareOperationStatus.BUSY
        return HardwareOperationStatus.FAILURE


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
