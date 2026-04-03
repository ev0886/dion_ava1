from __future__ import annotations

from typing import Final

from app.domain.enums import HardwareEndpointType
from app.hardware.dto import HardwareOperationResult, HardwareOperationStatus
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
                f"{self._device_label.capitalize()} transport request timed out.",
                device_type=self.device_type,
                operation=operation,
                detail=self._transport_detail(
                    kind="timeout",
                    transport_message=str(error) or type(error).__name__,
                ),
            ) from error
        except NotImplementedError as error:
            raise HardwareUnavailableError(
                f"{self._device_label.capitalize()} transport I/O is not implemented yet.",
                device_type=self.device_type,
                operation=operation,
                detail=self._transport_detail(
                    kind="not_implemented",
                    transport_message=str(error) or type(error).__name__,
                ),
            ) from error
        except OSError as error:
            raise HardwareUnavailableError(
                f"{self._device_label.capitalize()} transport request failed.",
                device_type=self.device_type,
                operation=operation,
                detail=self._transport_detail(
                    kind="io_error",
                    transport_message=str(error) or type(error).__name__,
                ),
            ) from error
        try:
            response = raw_response.decode("ascii").strip()
        except (AttributeError, TypeError, UnicodeDecodeError) as error:
            raise HardwareFailureError(
                f"{self._device_label.capitalize()} returned a malformed response.",
                device_type=self.device_type,
                operation=operation,
                detail={"response_type": type(raw_response).__name__},
            ) from error
        self._raise_if_normalized_protocol_error(response, operation=operation)
        return response

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
                detail={"kind": "config_error"},
            )
        if self._config is None:
            raise HardwareUnavailableError(
                f"{self._device_label.capitalize()} real transport config is missing.",
                device_type=self.device_type,
                operation=operation,
                detail={"kind": "missing_config"},
            )
        if not self._config.endpoint.enabled:
            raise HardwareUnavailableError(
                f"{self._device_label.capitalize()} real endpoint is disabled.",
                device_type=self.device_type,
                operation=operation,
                detail={"kind": "endpoint_disabled", "endpoint_code": self._config.endpoint.code},
            )
        if self._transport is None:
            raise HardwareUnavailableError(
                f"{self._device_label.capitalize()} transport client is not configured.",
                device_type=self.device_type,
                operation=operation,
                detail={"kind": "missing_transport", "endpoint_code": self._config.endpoint.code},
            )

    def _raise_if_normalized_protocol_error(self, response: str, *, operation: str) -> None:
        normalized = response.strip().upper()
        if normalized == "BUSY":
            raise HardwareBusyError(
                f"{self._device_label.capitalize()} reported busy.",
                device_type=self.device_type,
                operation=operation,
                detail={"kind": "protocol_busy", "raw_response": response},
            )
        if normalized == "TIMEOUT":
            raise HardwareTimeoutError(
                f"{self._device_label.capitalize()} reported timeout.",
                device_type=self.device_type,
                operation=operation,
                detail={"kind": "protocol_timeout", "raw_response": response},
            )
        if normalized == "UNAVAILABLE":
            raise HardwareUnavailableError(
                f"{self._device_label.capitalize()} reported unavailable.",
                device_type=self.device_type,
                operation=operation,
                detail={"kind": "protocol_unavailable", "raw_response": response},
            )
        if normalized == "ERROR" or normalized.startswith("ERROR:"):
            raise HardwareFailureError(
                f"{self._device_label.capitalize()} reported failure.",
                device_type=self.device_type,
                operation=operation,
                detail={"kind": "protocol_failure", "raw_response": response},
            )

    def _transport_detail(self, *, kind: str, transport_message: str) -> dict[str, object]:
        transport_kind = self._config.transport.transport if self._config is not None else None
        endpoint_code = self._config.endpoint.code if self._config is not None else None
        return {
            "kind": kind,
            "transport": transport_kind,
            "endpoint_code": endpoint_code,
            "transport_message": transport_message,
        }
