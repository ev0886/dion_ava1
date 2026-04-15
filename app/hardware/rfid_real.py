from __future__ import annotations

from app.domain.constants import DEFAULT_RFID_UID_FORMAT
from app.domain.enums import HardwareEndpointType
from app.hardware.dto import HardwareOperationResult, HardwareOperationStatus, RfidReadResult
from app.hardware.exceptions import HardwareFailureError
from app.hardware.exceptions import HardwareTimeoutError, HardwareUnavailableError
from app.hardware.real_adapter_base import RealHardwareAdapterBase
from app.hardware.rfid_rusguard import RfidStatusTransport
from app.hardware.transport_config import HardwareEndpointTransportConfig, RfidHardwareEndpointTransportConfig
from app.hardware.transports import SerialRequestResponseTransport, TcpRequestResponseTransport


class RealRfidAdapter(RealHardwareAdapterBase):
    _FULL_UID_SIZE_BYTES = 7
    _PING_REQUEST = b"PING\n"
    _READ_REQUEST = b"READ\n"
    _CLEAR_REQUEST = b"CLEAR\n"
    _PONG_RESPONSE = "PONG"
    _READ_RESPONSE = "READ"
    _NO_CARD_RESPONSE = "NO_CARD"
    _CLEARED_RESPONSE = "CLEARED"
    _UID_PREFIX = "UID:"
    _MAX_READ_ATTEMPTS = 2

    def __init__(
        self,
        *,
        config: HardwareEndpointTransportConfig | None,
        transport: SerialRequestResponseTransport | TcpRequestResponseTransport | RfidStatusTransport | None,
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
        if self._uses_rusguard_sdk_transport():
            return self._ping_via_sdk_transport()
        response = self._send_request(self._PING_REQUEST, operation="ping")
        if response != self._PONG_RESPONSE:
            raise HardwareFailureError(
                f"RFID reader returned unsupported ping response: {response!r}",
                device_type=self.device_type,
                operation="ping",
            )
        return self._success_result()

    def read_card(self) -> RfidReadResult:
        if self._uses_rusguard_sdk_transport():
            return self._read_card_via_sdk_transport()
        last_response: str | None = None
        for _attempt in range(self._MAX_READ_ATTEMPTS):
            response = self._send_request(self._READ_REQUEST, operation="read_card")
            last_response = response
            parsed_response = self._parse_read_response(response)
            if parsed_response == self._READ_RESPONSE:
                continue
            if parsed_response == self._NO_CARD_RESPONSE:
                return RfidReadResult(
                    device_type=self.device_type,
                    status=HardwareOperationStatus.NO_CARD,
                    ok=True,
                    uid=None,
                    is_duplicate=False,
                    message=f"No RFID card present ({DEFAULT_RFID_UID_FORMAT})",
                )
            if not parsed_response.startswith(self._UID_PREFIX):
                raise HardwareFailureError(
                    f"RFID reader returned unsupported read response: {response!r}",
                    device_type=self.device_type,
                    operation="read_card",
                )
            uid = self._normalize_uid(parsed_response.removeprefix(self._UID_PREFIX))
            is_duplicate = uid == self._last_uid
            self._last_uid = uid
            return RfidReadResult(
                device_type=self.device_type,
                status=HardwareOperationStatus.SUCCESS,
                ok=True,
                uid=uid,
                is_duplicate=is_duplicate,
            )
        raise HardwareFailureError(
            f"RFID reader returned unsupported read response: {last_response!r}",
            device_type=self.device_type,
            operation="read_card",
        )

    def clear_buffer(self) -> HardwareOperationResult:
        if self._uses_rusguard_sdk_transport():
            self._last_uid = None
            return self._success_result()
        response = self._send_request(self._CLEAR_REQUEST, operation="clear_buffer")
        if response != self._CLEARED_RESPONSE:
            raise HardwareFailureError(
                f"RFID reader returned unsupported clear response: {response!r}",
                device_type=self.device_type,
                operation="clear_buffer",
            )
        return HardwareOperationResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=True,
        )

    @staticmethod
    def _normalize_uid(uid: str) -> str:
        cleaned = "".join(character for character in uid if character.isalnum()).upper()
        if not cleaned:
            raise HardwareFailureError(
                "RFID reader returned an empty card UID.",
                device_type=HardwareEndpointType.RFID_READER,
                operation="read_card",
            )
        return cleaned

    @classmethod
    def _parse_read_response(cls, response: str) -> str:
        lines = [line.strip() for line in response.splitlines() if line.strip()]
        if not lines:
            return response
        for line in lines:
            if line == cls._READ_RESPONSE:
                continue
            return line
        return cls._READ_RESPONSE

    def _ping_via_sdk_transport(self) -> HardwareOperationResult:
        config = self._require_rfid_config(operation="ping")
        transport = self._require_rusguard_transport(operation="ping")
        try:
            transport.ping(timeout_ms=config.endpoint.timeouts.read_timeout_ms)
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

    def _read_card_via_sdk_transport(self) -> RfidReadResult:
        config = self._require_rfid_config(operation="read_card")
        transport = self._require_rusguard_transport(operation="read_card")
        try:
            result = transport.read_card(timeout_ms=config.endpoint.timeouts.read_timeout_ms)
        except TimeoutError as error:
            raise HardwareTimeoutError(
                f"RFID reader card read timed out: {error}",
                device_type=self.device_type,
                operation="read_card",
            ) from error
        except OSError as error:
            raise HardwareUnavailableError(
                f"RFID reader card read failed: {error}",
                device_type=self.device_type,
                operation="read_card",
            ) from error
        except Exception as error:
            raise HardwareFailureError(
                f"RFID reader returned an unexpected card-read failure: {error}",
                device_type=self.device_type,
                operation="read_card",
            ) from error
        if result.uid is None or result.uid_size == 0 or result.uid_size < self._FULL_UID_SIZE_BYTES:
            self._last_uid = None
            return RfidReadResult(
                device_type=self.device_type,
                status=HardwareOperationStatus.NO_CARD,
                ok=True,
                uid=None,
                is_duplicate=False,
                message=(
                    f"No valid RFID card present ({DEFAULT_RFID_UID_FORMAT})"
                    if result.uid_size == 0 or result.uid is None
                    else (
                        "Ignoring transient partial RFID read "
                        f"({result.uid_size}/{self._FULL_UID_SIZE_BYTES} bytes)."
                    )
                ),
            )
        normalized_uid = self._normalize_uid(result.uid)
        is_duplicate = normalized_uid == self._last_uid
        self._last_uid = normalized_uid
        return RfidReadResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=True,
            uid=normalized_uid,
            is_duplicate=is_duplicate,
        )

    def _uses_rusguard_sdk_transport(self) -> bool:
        if self._config is None or self._transport is None:
            return False
        transport_settings = getattr(self._config, "transport", None)
        return bool(getattr(transport_settings, "sdk_library", None))

    def _require_rusguard_transport(self, *, operation: str) -> RfidStatusTransport:
        self._raise_if_unavailable(operation=operation)
        transport = self._transport
        if transport is None or not isinstance(transport, RfidStatusTransport):
            raise HardwareUnavailableError(
                "RFID reader RusGuard transport client is not configured.",
                device_type=self.device_type,
                operation=operation,
            )
        return transport

    def _require_rfid_config(self, *, operation: str) -> RfidHardwareEndpointTransportConfig:
        self._raise_if_unavailable(operation=operation)
        config = self._config
        if config is None or not isinstance(config, RfidHardwareEndpointTransportConfig):
            raise HardwareUnavailableError(
                "RFID reader real transport config is missing.",
                device_type=self.device_type,
                operation=operation,
            )
        return config
