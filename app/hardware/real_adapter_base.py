from __future__ import annotations

from typing import Final

from app.domain.enums import HardwareEndpointType
from app.hardware.dto import HardwareOperationResult
from app.hardware.exceptions import HardwareProtocolNotImplementedError, HardwareUnavailableError
from app.hardware.transport_config import HardwareEndpointTransportConfig
from app.hardware.transports import SerialRequestResponseTransport, TcpRequestResponseTransport


class RealHardwareAdapterBase:
    _PROTOCOL_MESSAGE: Final[str] = "Real hardware protocol is not implemented yet."

    def __init__(
        self,
        *,
        device_type: HardwareEndpointType,
        config: HardwareEndpointTransportConfig | None,
        transport: SerialRequestResponseTransport | TcpRequestResponseTransport | None,
        config_error: str | None = None,
    ) -> None:
        self.device_type = device_type
        self._config = config
        self._transport = transport
        self._config_error = config_error

    def ping(self) -> HardwareOperationResult:
        self._raise_if_unavailable(operation="ping")
        raise HardwareProtocolNotImplementedError(
            f"{self._device_label} transport skeleton is configured but ping protocol is not implemented yet.",
            device_type=self.device_type,
            operation="ping",
        )

    @property
    def _device_label(self) -> str:
        return self.device_type.value.replace("_", " ")

    def _raise_if_unavailable(self, *, operation: str) -> None:
        if self._config_error:
            raise HardwareUnavailableError(
                self._config_error,
                device_type=self.device_type,
                operation=operation,
            )
        if self._config is None:
            raise HardwareUnavailableError(
                f"{self._device_label.capitalize()} real transport config is missing.",
                device_type=self.device_type,
                operation=operation,
            )
        if not self._config.endpoint.enabled:
            raise HardwareUnavailableError(
                f"{self._device_label.capitalize()} real endpoint is disabled.",
                device_type=self.device_type,
                operation=operation,
            )
        if self._transport is None:
            raise HardwareUnavailableError(
                f"{self._device_label.capitalize()} transport client is not configured.",
                device_type=self.device_type,
                operation=operation,
            )
