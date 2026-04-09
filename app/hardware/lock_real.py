from __future__ import annotations

from app.domain.enums import HardwareEndpointType
from app.hardware.dto import (
    HardwareOperationResult,
    HardwareOperationStatus,
    LockState,
    LockStatusResult,
    UnlockResult,
    UnlockTimeResult,
)
from app.hardware.exceptions import HardwareFailureError, HardwareProtocolNotImplementedError, HardwareUnavailableError
from app.hardware.lock_cu24 import (
    CU24_ACK_SUCCESS,
    CU24_CMD_GET_STATUS,
    CU24_CMD_QUERY_VERSION,
    CU24_CMD_UNLOCK,
    Cu24Packet,
    build_packet,
    parse_packet,
    protocol_lock_number,
)
from app.hardware.real_adapter_base import RealHardwareAdapterBase
from app.hardware.transport_config import LockHardwareEndpointTransportConfig
from app.hardware.transports import SerialRequestResponseTransport


class RealLockAdapter(RealHardwareAdapterBase):
    def __init__(
        self,
        *,
        config: LockHardwareEndpointTransportConfig | None,
        transport: SerialRequestResponseTransport | None,
        config_error: str | None = None,
    ) -> None:
        super().__init__(
            device_type=HardwareEndpointType.LOCK_CONTROLLER,
            config=config,
            transport=transport,
            config_error=config_error,
        )

    def ping(self) -> HardwareOperationResult:
        self._query_version(operation="ping")
        return self._success_result()

    def get_lock_status(self, board_address: int, lock_number: int) -> LockStatusResult:
        self._ensure_configured_board_address(board_address, operation="get_lock_status")
        self._probe_status(lock_number=lock_number, operation="get_lock_status")
        raise HardwareProtocolNotImplementedError(
            "CU24 get_lock_status probe is wired, but lock-state decoding is not implemented yet.",
            device_type=self.device_type,
            operation="get_lock_status",
        )

    def unlock_lock(self, board_address: int, lock_number: int) -> UnlockResult:
        configured_board_address = self._ensure_configured_board_address(board_address, operation="unlock_lock")
        protocol_number = protocol_lock_number(lock_number)
        response = self._send_cu24_request(
            build_packet(
                address=configured_board_address,
                lock_number=protocol_number,
                command=CU24_CMD_UNLOCK,
            ),
            operation="unlock_lock",
        )
        self._assert_successful_response(
            response,
            expected_command=CU24_CMD_UNLOCK,
            expected_address=configured_board_address,
            expected_lock_number=protocol_number,
            operation="unlock_lock",
        )
        return UnlockResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=True,
            board_address=board_address,
            lock_number=lock_number,
            lock_state=LockState.OPEN,
        )

    def get_unlock_time(self, board_address: int) -> UnlockTimeResult:
        self._ensure_configured_board_address(board_address, operation="get_unlock_time")
        raise HardwareProtocolNotImplementedError(
            "CU24 unlock-time reads are not implemented for the real adapter yet.",
            device_type=self.device_type,
            operation="get_unlock_time",
        )

    def set_unlock_time(self, board_address: int, seconds: int) -> UnlockTimeResult:
        if seconds <= 0:
            raise ValueError("seconds must be positive")
        self._ensure_configured_board_address(board_address, operation="set_unlock_time")
        raise HardwareProtocolNotImplementedError(
            "CU24 unlock-time writes are not implemented for the real adapter yet.",
            device_type=self.device_type,
            operation="set_unlock_time",
        )

    def _query_version(self, *, operation: str) -> None:
        configured_board_address = self._configured_board_address
        response = self._send_cu24_request(
            build_packet(
                address=configured_board_address,
                lock_number=0,
                command=CU24_CMD_QUERY_VERSION,
            ),
            operation=operation,
        )
        self._assert_successful_response(
            response,
            expected_command=CU24_CMD_QUERY_VERSION,
            expected_address=configured_board_address,
            expected_lock_number=0,
            operation=operation,
        )

    def _probe_status(self, *, lock_number: int, operation: str) -> Cu24Packet:
        configured_board_address = self._configured_board_address
        protocol_number = protocol_lock_number(lock_number)
        response = self._send_cu24_request(
            build_packet(
                address=configured_board_address,
                lock_number=protocol_number,
                command=CU24_CMD_GET_STATUS,
            ),
            operation=operation,
        )
        self._assert_successful_response(
            response,
            expected_command=CU24_CMD_GET_STATUS,
            expected_address=configured_board_address,
            expected_lock_number=protocol_number,
            operation=operation,
        )
        return response

    def _send_cu24_request(self, payload: bytes, *, operation: str) -> Cu24Packet:
        try:
            return parse_packet(self._send_binary_request(payload, operation=operation))
        except ValueError as error:
            raise HardwareFailureError(
                f"Lock controller returned a malformed response: {error}",
                device_type=self.device_type,
                operation=operation,
            ) from error

    @property
    def _configured_board_address(self) -> int:
        if self._config_error:
            raise HardwareUnavailableError(
                self._config_error,
                device_type=self.device_type,
                operation="config",
            )
        if self._config is None:
            raise HardwareUnavailableError(
                "Lock controller real transport config is missing.",
                device_type=self.device_type,
                operation="config",
            )
        return self._config.protocol.board_address

    def _ensure_configured_board_address(self, board_address: int, *, operation: str) -> int:
        configured_board_address = self._configured_board_address
        if board_address != configured_board_address:
            raise HardwareFailureError(
                f"Lock controller is configured for board address {configured_board_address}, got {board_address}.",
                device_type=self.device_type,
                operation=operation,
            )
        return configured_board_address

    def _assert_successful_response(
        self,
        response: Cu24Packet,
        *,
        expected_command: int,
        expected_address: int,
        expected_lock_number: int,
        operation: str,
    ) -> None:
        if response.command != expected_command:
            raise HardwareFailureError(
                f"Lock controller returned unexpected command in response: {response.command:#04x}",
                device_type=self.device_type,
                operation=operation,
            )
        if response.address != expected_address:
            raise HardwareFailureError(
                f"Lock controller returned unexpected board address in response: {response.address:#04x}",
                device_type=self.device_type,
                operation=operation,
            )
        if response.lock_number != expected_lock_number:
            raise HardwareFailureError(
                f"Lock controller returned unexpected lock number in response: {response.lock_number:#04x}",
                device_type=self.device_type,
                operation=operation,
            )
        if response.ask != CU24_ACK_SUCCESS:
            raise HardwareFailureError(
                f"Lock controller returned unsupported acknowledgement code: {response.ask:#04x}",
                device_type=self.device_type,
                operation=operation,
            )
