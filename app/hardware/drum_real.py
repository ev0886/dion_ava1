from __future__ import annotations

from app.domain.enums import HardwareEndpointType
from app.hardware.drum_uart import (
    DRUM_ANS1_ACCEPTED,
    DRUM_ANS1_BUSY,
    DRUM_ANS1_RESULT,
    DRUM_ANS1_UNKNOWN,
    DRUM_ANS2_ERR,
    DRUM_ANS2_OK,
    DRUM_CONF_OK,
    DRUM_GETPOS,
    DRUM_SETPOS,
    DrumPacket,
    build_long_packet,
    build_short_packet,
    parse_packet,
    validate_position,
)
from app.hardware.dto import DrumPositionResult, HardwareOperationResult, HardwareOperationStatus
from app.hardware.exceptions import HardwareBusyError, HardwareFailureError, HardwareTimeoutError, HardwareUnavailableError
from app.hardware.real_adapter_base import RealHardwareAdapterBase
from app.hardware.transport_config import DrumHardwareEndpointTransportConfig
from app.hardware.transports import SerialRequestResponseTransport


class RealDrumAdapter(RealHardwareAdapterBase):
    def __init__(
        self,
        *,
        config: DrumHardwareEndpointTransportConfig | None,
        transport: SerialRequestResponseTransport | None,
        config_error: str | None = None,
    ) -> None:
        super().__init__(
            device_type=HardwareEndpointType.DRUM_CONTROLLER,
            config=config,
            transport=transport,
            config_error=config_error,
        )

    def ping(self) -> HardwareOperationResult:
        self._probe_position(operation="ping")
        return self._success_result()

    def get_position(self) -> DrumPositionResult:
        position = self._probe_position(operation="get_position")
        return DrumPositionResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=True,
            position=position,
        )

    def move_to_position(self, position: int) -> DrumPositionResult:
        validated_position = validate_position(position)
        first_response, second_response = self._move_setpos_sequence(validated_position)
        if first_response.command == DRUM_ANS1_BUSY:
            raise HardwareBusyError(
                "Drum controller is busy",
                device_type=self.device_type,
                operation="move_to_position",
            )
        if first_response.command == DRUM_ANS1_UNKNOWN:
            raise HardwareFailureError(
                "Drum controller rejected SETPOS as unknown.",
                device_type=self.device_type,
                operation="move_to_position",
            )
        if first_response.command != DRUM_ANS1_ACCEPTED:
            raise HardwareFailureError(
                f"Drum controller returned unsupported SETPOS acknowledgement: {first_response.command:#04x}",
                device_type=self.device_type,
                operation="move_to_position",
            )
        if second_response.command == DRUM_ANS2_ERR:
            raise HardwareFailureError(
                "Drum controller reported SETPOS failure.",
                device_type=self.device_type,
                operation="move_to_position",
            )
        if second_response.command != DRUM_ANS2_OK:
            raise HardwareFailureError(
                f"Drum controller returned unsupported SETPOS completion: {second_response.command:#04x}",
                device_type=self.device_type,
                operation="move_to_position",
            )
        return DrumPositionResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=True,
            position=validated_position,
        )

    def _probe_position(self, *, operation: str) -> int:
        response = parse_packet(
            self._send_binary_request(build_long_packet(DRUM_GETPOS, 0), operation=operation)
        )
        if response.command == DRUM_ANS1_BUSY:
            raise HardwareBusyError(
                "Drum controller is busy",
                device_type=self.device_type,
                operation=operation,
            )
        if response.command != DRUM_ANS1_RESULT or response.argument is None:
            raise HardwareFailureError(
                f"Drum controller returned unsupported GETPOS response: {response.command:#04x}",
                device_type=self.device_type,
                operation=operation,
            )
        position = validate_position(response.argument)
        self._send_confirmation(operation=operation)
        return position

    def _send_confirmation(self, *, operation: str) -> None:
        self._raise_if_unavailable(operation=operation)
        assert self._transport is not None
        transport_send = getattr(self._transport, "send", None)
        if callable(transport_send):
            try:
                transport_send(build_short_packet(DRUM_CONF_OK))
                return
            except TimeoutError:
                return
            except OSError as error:
                raise HardwareFailureError(
                    f"Drum controller confirmation failed: {error}",
                    device_type=self.device_type,
                    operation=operation,
                ) from error
        try:
            self._transport.request(build_short_packet(DRUM_CONF_OK), timeout_ms=50)
        except TimeoutError:
            return

    def _move_setpos_sequence(self, position: int) -> tuple[DrumPacket, DrumPacket]:
        payloads = [
            build_long_packet(DRUM_SETPOS, position),
            build_short_packet(DRUM_CONF_OK),
        ]
        self._raise_if_unavailable(operation="move_to_position")
        assert self._transport is not None
        request_sequence = getattr(self._transport, "request_sequence", None)
        if callable(request_sequence):
            timeout_ms = self._config.endpoint.timeouts.read_timeout_ms if self._config is not None else None
            try:
                raw_first_response, raw_second_response = request_sequence(payloads, timeout_ms=timeout_ms)
            except TimeoutError as error:
                raise HardwareTimeoutError(
                    f"{self._device_label.capitalize()} transport request timed out: {error}",
                    device_type=self.device_type,
                    operation="move_to_position",
                ) from error
            except NotImplementedError:
                raw_first_response = self._send_binary_request(payloads[0], operation="move_to_position")
                raw_second_response = self._send_binary_request(payloads[1], operation="move_to_position")
            except OSError as error:
                raise HardwareUnavailableError(
                    f"{self._device_label.capitalize()} transport request failed: {error}",
                    device_type=self.device_type,
                    operation="move_to_position",
                ) from error
        else:
            raw_first_response = self._send_binary_request(payloads[0], operation="move_to_position")
            raw_second_response = self._send_binary_request(payloads[1], operation="move_to_position")
        return parse_packet(raw_first_response), parse_packet(raw_second_response)
