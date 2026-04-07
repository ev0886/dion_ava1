from __future__ import annotations

from typing import Final

from app.domain.enums import HardwareEndpointType
from app.hardware.dto import HardwareOperationResult, HardwareOperationStatus
from app.hardware.exceptions import (
    HardwareFailureError,
    HardwareProtocolNotImplementedError,
    HardwareTimeoutError,
    HardwareUnavailableError,
)
from app.hardware.transport_config import AnyHardwareEndpointTransportConfig
from app.hardware.transports import SerialRequestResponseTransport, TcpRequestResponseTransport


class RealHardwareAdapterBase:
    """Shared fail-closed behavior for concrete real hardware adapters.

    Real-provider endpoints are allowed to be misconfigured or temporarily offline.
    Adapters surface those cases as per-device unavailability so startup can report
    degraded readiness instead of crashing process startup.
    """

    _PROTOCOL_MESSAGE: Final[str] = "Real hardware protocol is not implemented yet."

    def __init__(
        self,
        *,
        device_type: HardwareEndpointType,
        config: AnyHardwareEndpointTransportConfig | None,
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

    def _send_request(self, payload: bytes, *, operation: str) -> str:
        raw_response = self._send_binary_request(payload, operation=operation)
        try:
            return raw_response.decode("ascii").strip()
        except (AttributeError, TypeError, UnicodeDecodeError) as error:
            raise HardwareFailureError(
                f"{self._device_label.capitalize()} returned a malformed response.",
                device_type=self.device_type,
                operation=operation,
            ) from error

    def _send_binary_request(self, payload: bytes, *, operation: str) -> bytes:
        self._raise_if_unavailable(operation=operation)
        assert self._transport is not None
        timeout_ms = self._config.endpoint.timeouts.read_timeout_ms if self._config is not None else None
        try:
            raw_response = self._transport.request(payload, timeout_ms=timeout_ms)
        except TimeoutError as error:
            raise HardwareTimeoutError(
                f"{self._device_label.capitalize()} transport request timed out: {error}",
                device_type=self.device_type,
                operation=operation,
            ) from error
        except NotImplementedError as error:
            raise HardwareUnavailableError(
                f"{self._device_label.capitalize()} transport I/O is not implemented yet: {error}",
                device_type=self.device_type,
                operation=operation,
            ) from error
        except OSError as error:
            raise HardwareUnavailableError(
                f"{self._device_label.capitalize()} transport request failed: {error}",
                device_type=self.device_type,
                operation=operation,
            ) from error
        if not isinstance(raw_response, (bytes, bytearray)):
            raise HardwareFailureError(
                f"{self._device_label.capitalize()} returned a malformed response.",
                device_type=self.device_type,
                operation=operation,
            )
        return bytes(raw_response)

    def _success_result(self) -> HardwareOperationResult:
        return HardwareOperationResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=True,
        )

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
