from __future__ import annotations

from typing import Final

from app.domain.enums import HardwareEndpointType
from app.hardware.dto import HardwareEndpointDescriptor, HardwareOperationResult, HardwareOperationStatus
from app.hardware.exceptions import (
    HardwareBusyError,
    HardwareFailureError,
    HardwareProtocolNotImplementedError,
    HardwareTimeoutError,
    HardwareUnavailableError,
)
from app.hardware.transport_config import HardwareEndpointTransportConfig
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
        config: HardwareEndpointTransportConfig | None,
        transport: SerialRequestResponseTransport | TcpRequestResponseTransport | None,
        config_error: str | None = None,
    ) -> None:
        self.device_type = device_type
        self._config = config
        self._transport = transport
        self._config_error = config_error

    def describe_endpoint(self) -> HardwareEndpointDescriptor:
        configured_mode = self._config.transport.transport if self._config is not None else None
        active_mode = configured_mode if self._transport is not None and configured_mode is not None else "unconfigured"
        return HardwareEndpointDescriptor(
            endpoint_kind="real",
            configured_transport_mode=configured_mode,
            active_transport_mode=active_mode,
        )

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
        if not raw_response.endswith(b"\n"):
            raise HardwareFailureError(
                f"{self._device_label.capitalize()} returned a truncated response.",
                device_type=self.device_type,
                operation=operation,
            )
        try:
            response = bytes(raw_response).decode("ascii").strip()
        except (AttributeError, TypeError, UnicodeDecodeError) as error:
            raise HardwareFailureError(
                f"{self._device_label.capitalize()} returned a malformed response.",
                device_type=self.device_type,
                operation=operation,
            ) from error
        if not response:
            raise HardwareFailureError(
                f"{self._device_label.capitalize()} returned an empty response.",
                device_type=self.device_type,
                operation=operation,
            )
        return self._normalize_response(response, operation=operation)

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

    def _normalize_response(self, response: str, *, operation: str) -> str:
        normalized = response.strip()
        response_upper = normalized.upper()
        if response_upper == "BUSY":
            raise HardwareBusyError(
                f"{self._device_label.capitalize()} reported busy status.",
                device_type=self.device_type,
                operation=operation,
            )
        if response_upper in {"UNAVAILABLE", "OFFLINE"}:
            raise HardwareUnavailableError(
                f"{self._device_label.capitalize()} reported unavailable status.",
                device_type=self.device_type,
                operation=operation,
            )
        if response_upper == "TIMEOUT":
            raise HardwareTimeoutError(
                f"{self._device_label.capitalize()} reported timeout status.",
                device_type=self.device_type,
                operation=operation,
            )
        if response_upper.startswith("ERR") or response_upper.startswith("ERROR"):
            detail = normalized.split(":", 1)[1].strip() if ":" in normalized else "device reported failure"
            raise HardwareFailureError(
                f"{self._device_label.capitalize()} reported failure: {detail}",
                device_type=self.device_type,
                operation=operation,
            )
        return normalized
