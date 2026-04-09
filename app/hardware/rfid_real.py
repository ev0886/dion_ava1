from __future__ import annotations

from app.domain.constants import DEFAULT_RFID_UID_FORMAT
from app.domain.enums import HardwareEndpointType
from app.hardware.dto import HardwareOperationResult, HardwareOperationStatus, RfidReadResult
from app.hardware.exceptions import HardwareFailureError
from app.hardware.real_adapter_base import RealHardwareAdapterBase
from app.hardware.exceptions import HardwareProtocolNotImplementedError, HardwareTimeoutError, HardwareUnavailableError
from app.hardware.rfid_rusguard import RfidStatusTransport
from app.hardware.transport_config import RfidHardwareEndpointTransportConfig


class RealRfidAdapter(RealHardwareAdapterBase):
    def __init__(
        self,
        *,
        config: RfidHardwareEndpointTransportConfig | None,
        transport: RfidStatusTransport | None,
        config_error: str | None = None,
    ) -> None:
        super().__init__(
            device_type=HardwareEndpointType.RFID_READER,
            config=config,
            transport=transport,
            config_error=config_error,
        )
        self._last_uid: str | None = None

    def ping(self) -> HardwareOperationResult:
        config = self._require_config(operation="ping")
        status_transport = self._transport
        if status_transport is None:
            raise HardwareUnavailableError(
                "RFID reader transport client is not configured.",
                device_type=self.device_type,
                operation="ping",
            )
        try:
            status_transport.ping(timeout_ms=config.endpoint.timeouts.read_timeout_ms)
        except TimeoutError as error:
            raise HardwareTimeoutError(
                f"RFID reader status check timed out: {error}",
                device_type=self.device_type,
                operation="ping",
            ) from error
        except OSError as error:
            raise HardwareUnavailableError(
                f"RFID reader status check failed: {error}",
                device_type=self.device_type,
                operation="ping",
            ) from error
        except Exception as error:
            raise HardwareFailureError(
                f"RFID reader returned an unexpected status failure: {error}",
                device_type=self.device_type,
                operation="ping",
            ) from error
        return self._success_result()

    def read_card(self) -> RfidReadResult:
        self._require_config(operation="read_card")
        raise HardwareProtocolNotImplementedError(
            f"RFID UID read is intentionally not implemented in the real provider yet ({DEFAULT_RFID_UID_FORMAT}).",
            device_type=self.device_type,
            operation="read_card",
        )

    def clear_buffer(self) -> HardwareOperationResult:
        self._require_config(operation="clear_buffer")
        raise HardwareProtocolNotImplementedError(
            "RFID buffer clear is intentionally not implemented in the real provider yet.",
            device_type=self.device_type,
            operation="clear_buffer",
        )

    def _require_config(self, *, operation: str) -> RfidHardwareEndpointTransportConfig:
        if self._config_error:
            raise HardwareUnavailableError(
                self._config_error,
                device_type=self.device_type,
                operation=operation,
            )
        if self._config is None:
            raise HardwareUnavailableError(
                "RFID reader real transport config is missing.",
                device_type=self.device_type,
                operation=operation,
            )
        if not self._config.endpoint.enabled:
            raise HardwareUnavailableError(
                "RFID reader real endpoint is disabled.",
                device_type=self.device_type,
                operation=operation,
            )
        return self._config
