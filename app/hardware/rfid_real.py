from __future__ import annotations

from app.domain.constants import DEFAULT_RFID_UID_FORMAT
from app.domain.enums import HardwareEndpointType
from app.hardware.dto import HardwareOperationResult, HardwareOperationStatus, RfidReadResult
from app.hardware.exceptions import HardwareFailureError
from app.hardware.real_adapter_base import RealHardwareAdapterBase
from app.hardware.transport_config import HardwareEndpointTransportConfig
from app.hardware.transports import SerialRequestResponseTransport, TcpRequestResponseTransport


class RealRfidAdapter(RealHardwareAdapterBase):
    _PING_REQUEST = b"PING\n"
    _READ_REQUEST = b"READ\n"
    _CLEAR_REQUEST = b"CLEAR\n"
    _PONG_RESPONSE = "PONG"
    _NO_CARD_RESPONSE = "NO_CARD"
    _CLEARED_RESPONSE = "CLEARED"
    _UID_PREFIX = "UID:"

    def __init__(
        self,
        *,
        config: HardwareEndpointTransportConfig | None,
        transport: SerialRequestResponseTransport | TcpRequestResponseTransport | None,
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
        response = self._send_request(self._PING_REQUEST, operation="ping")
        if response != self._PONG_RESPONSE:
            raise HardwareFailureError(
                f"RFID reader returned unsupported ping response: {response!r}",
                device_type=self.device_type,
                operation="ping",
            )
        return self._success_result()

    def read_card(self) -> RfidReadResult:
        response = self._send_request(self._READ_REQUEST, operation="read_card")
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
