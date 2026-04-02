from __future__ import annotations

from app.domain.enums import HardwareEndpointType
from app.hardware.dto import DrumPositionResult, HardwareOperationResult, HardwareOperationStatus
from app.hardware.exceptions import HardwareFailureError
from app.hardware.real_adapter_base import RealHardwareAdapterBase
from app.hardware.transport_config import HardwareEndpointTransportConfig
from app.hardware.transports import SerialRequestResponseTransport, TcpRequestResponseTransport


class RealDrumAdapter(RealHardwareAdapterBase):
    _PING_REQUEST = b"PING\n"
    _GET_POSITION_REQUEST = b"GET_POSITION\n"
    _MOVE_TEMPLATE = "MOVE {position}\n"
    _PONG_RESPONSE = "PONG"
    _POSITION_PREFIX = "POSITION:"
    _MOVED_PREFIX = "MOVED:"

    def __init__(
        self,
        *,
        config: HardwareEndpointTransportConfig | None,
        transport: SerialRequestResponseTransport | TcpRequestResponseTransport | None,
        config_error: str | None = None,
    ) -> None:
        super().__init__(
            device_type=HardwareEndpointType.DRUM_CONTROLLER,
            config=config,
            transport=transport,
            config_error=config_error,
        )

    def ping(self) -> HardwareOperationResult:
        response = self._send_request(self._PING_REQUEST, operation="ping")
        if response != self._PONG_RESPONSE:
            raise HardwareFailureError(
                f"Drum controller returned unsupported ping response: {response!r}",
                device_type=self.device_type,
                operation="ping",
            )
        return self._success_result()

    def get_position(self) -> DrumPositionResult:
        response = self._send_request(self._GET_POSITION_REQUEST, operation="get_position")
        if not response.startswith(self._POSITION_PREFIX):
            raise HardwareFailureError(
                f"Drum controller returned unsupported position response: {response!r}",
                device_type=self.device_type,
                operation="get_position",
            )
        position = self._parse_position(response.removeprefix(self._POSITION_PREFIX), operation="get_position")
        return DrumPositionResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=True,
            position=position,
        )

    def move_to_position(self, position: int) -> DrumPositionResult:
        if position < 0:
            raise ValueError("position must be non-negative")
        response = self._send_request(
            self._MOVE_TEMPLATE.format(position=position).encode("ascii"),
            operation="move_to_position",
        )
        if not response.startswith(self._MOVED_PREFIX):
            raise HardwareFailureError(
                f"Drum controller returned unsupported move response: {response!r}",
                device_type=self.device_type,
                operation="move_to_position",
            )
        actual_position = self._parse_position(response.removeprefix(self._MOVED_PREFIX), operation="move_to_position")
        return DrumPositionResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=True,
            position=actual_position,
        )

    def _parse_position(self, value: str, *, operation: str) -> int:
        try:
            position = int(value.strip())
        except ValueError as error:
            raise HardwareFailureError(
                f"Drum controller returned an invalid position: {value!r}",
                device_type=self.device_type,
                operation=operation,
            ) from error
        if position < 0:
            raise HardwareFailureError(
                f"Drum controller returned a negative position: {value!r}",
                device_type=self.device_type,
                operation=operation,
            )
        return position
