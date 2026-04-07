from __future__ import annotations

from app.domain.constants import DEFAULT_RFID_UID_FORMAT
from app.domain.enums import HardwareEndpointType
from app.hardware.dto import HardwareOperationResult, HardwareOperationStatus, RfidReadResult
from app.hardware.exceptions import HardwareFailureError
from app.hardware.real_adapter_base import RealHardwareAdapterBase
from app.hardware.rfid_input_transport import LinuxInputEventTransport
from app.hardware.transport_config import RfidHardwareEndpointTransportConfig
from app.hardware.transports import SerialRequestResponseTransport, TcpRequestResponseTransport


class RealRfidAdapter(RealHardwareAdapterBase):
    _PING_REQUEST = b"PING\n"
    _READ_REQUEST = b"READ\n"
    _CLEAR_REQUEST = b"CLEAR\n"
    _RUSGUARD_ACM_READ_REQUEST = b""
    _PONG_RESPONSE = "PONG"
    _NO_CARD_RESPONSE = "NO_CARD"
    _CLEARED_RESPONSE = "CLEARED"
    _UID_PREFIX = "UID:"
    _RUSGUARD_ACM_DRIVER_NAMES = frozenset({"rusguard-acm", "rusguard-r5-usb-acm"})
    _RUSGUARD_ACM_PING_RESPONSES = frozenset({"PING", "PONG"})
    _RUSGUARD_ACM_UNSUPPORTED_READ_RESPONSES = frozenset({"PING", "PONG", "READ", "CLEAR", "CLEARED"})

    def __init__(
        self,
        *,
        config: RfidHardwareEndpointTransportConfig | None,
        transport: SerialRequestResponseTransport | TcpRequestResponseTransport | LinuxInputEventTransport | None,
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
        if self._uses_rusguard_acm_protocol():
            return self._ping_rusguard_acm()
        response = self._send_request(self._PING_REQUEST, operation="ping")
        if response != self._PONG_RESPONSE:
            raise HardwareFailureError(
                f"RFID reader returned unsupported ping response: {response!r}",
                device_type=self.device_type,
                operation="ping",
            )
        return self._success_result()

    def read_card(self, *, timeout_ms: int | None = None) -> RfidReadResult:
        if self._uses_rusguard_acm_protocol():
            return self._read_card_rusguard_acm(timeout_ms=timeout_ms)
        response = self._send_request(self._READ_REQUEST, operation="read_card", timeout_ms=timeout_ms)
        if response == self._NO_CARD_RESPONSE:
            return RfidReadResult(
                device_type=self.device_type,
                status=HardwareOperationStatus.NO_CARD,
                ok=True,
                uid=None,
                is_duplicate=False,
                message=f"No RFID card present ({DEFAULT_RFID_UID_FORMAT})",
            )
        if not response.startswith(self._UID_PREFIX):
            raise HardwareFailureError(
                f"RFID reader returned unsupported read response: {response!r}",
                device_type=self.device_type,
                operation="read_card",
            )
        uid = self._normalize_uid(response.removeprefix(self._UID_PREFIX))
        is_duplicate = uid == self._last_uid
        self._last_uid = uid
        return RfidReadResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=True,
            uid=uid,
            is_duplicate=is_duplicate,
        )

    def clear_buffer(self) -> HardwareOperationResult:
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

    def _ping_rusguard_acm(self) -> HardwareOperationResult:
        response = self._send_request(self._PING_REQUEST, operation="ping")
        if response not in self._RUSGUARD_ACM_PING_RESPONSES:
            raise HardwareFailureError(
                f"RFID reader returned unsupported ping response: {response!r}",
                device_type=self.device_type,
                operation="ping",
            )
        return self._success_result()

    def _read_card_rusguard_acm(self, *, timeout_ms: int | None) -> RfidReadResult:
        raw_response = self._send_binary_request(self._RUSGUARD_ACM_READ_REQUEST, operation="read_card", timeout_ms=timeout_ms)
        response = self._decode_rusguard_acm_read_response(raw_response)
        if response == self._NO_CARD_RESPONSE:
            return RfidReadResult(
                device_type=self.device_type,
                status=HardwareOperationStatus.NO_CARD,
                ok=True,
                uid=None,
                is_duplicate=False,
                message=f"No RFID card present ({DEFAULT_RFID_UID_FORMAT})",
            )
        if response in self._RUSGUARD_ACM_UNSUPPORTED_READ_RESPONSES:
            raise HardwareFailureError(
                f"RFID reader returned unsupported read response: {response!r}",
                device_type=self.device_type,
                operation="read_card",
            )
        uid = self._normalize_uid(response)
        is_duplicate = uid == self._last_uid
        self._last_uid = uid
        return RfidReadResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=True,
            uid=uid,
            is_duplicate=is_duplicate,
        )

    @classmethod
    def _decode_rusguard_acm_read_response(cls, raw_response: bytes) -> str:
        stripped_response = raw_response.strip()
        if not stripped_response:
            raise HardwareFailureError(
                "RFID reader returned an empty card UID.",
                device_type=HardwareEndpointType.RFID_READER,
                operation="read_card",
            )
        try:
            decoded_response = stripped_response.decode("ascii")
        except UnicodeDecodeError:
            return stripped_response.hex().upper()
        return decoded_response.strip()

    def _uses_rusguard_acm_protocol(self) -> bool:
        if self._config is None:
            return False
        return self._config.endpoint.driver_name.strip().casefold() in self._RUSGUARD_ACM_DRIVER_NAMES

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
