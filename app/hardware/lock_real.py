from __future__ import annotations

from app.domain.enums import HardwareEndpointType
from app.hardware.dto import (
    HardwareOperationResult,
    HardwareOperationStatus,
    LockBoardStatusResult,
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
    _BOARD_LOCK_COUNT = 24
    _BOARD_STATUS_DATA_LENGTH = 3

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

    def get_board_status(self, board_address: int) -> LockBoardStatusResult:
        configured_board_address = self._ensure_configured_board_address(board_address, operation="get_board_status")
        response = self._read_board_status(operation="get_board_status")
        lock_states, raw_hook_mask = self._decode_board_lock_states(response, operation="get_board_status")
        return LockBoardStatusResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=True,
            board_address=configured_board_address,
            lock_states=lock_states,
            raw_hook_mask=raw_hook_mask,
        )

    def get_lock_status(self, board_address: int, lock_number: int) -> LockStatusResult:
        board_status = self.get_board_status(board_address)
        lock_state = self._lock_state_from_board_status(board_status, lock_number)
        return LockStatusResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=True,
            board_address=board_address,
            lock_number=lock_number,
            lock_state=lock_state,
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

    def _read_board_status(self, *, operation: str) -> Cu24Packet:
        configured_board_address = self._configured_board_address
        response = self._send_cu24_request(
            build_packet(
                address=configured_board_address,
                lock_number=0,
                command=CU24_CMD_GET_STATUS,
            ),
            operation=operation,
        )
        self._assert_successful_response(
            response,
            expected_command=CU24_CMD_GET_STATUS,
            expected_address=configured_board_address,
            expected_lock_number=0,
            operation=operation,
        )
        return response

    def _decode_board_lock_states(self, response: Cu24Packet, *, operation: str) -> tuple[tuple[LockState, ...], int]:
        if len(response.data) != self._BOARD_STATUS_DATA_LENGTH:
            raise HardwareFailureError(
                (
                    "Lock controller returned unexpected board-status payload length: "
                    f"{len(response.data)} bytes."
                ),
                device_type=self.device_type,
                operation=operation,
            )
        # The verified live payload FF 7F 00 for 15 closed cells maps cleanly to a little-endian
        # 24-bit mask where bit N describes physical lock N+1 and 1 means closed/hooked.
        raw_hook_mask = int.from_bytes(response.data, byteorder="little", signed=False)
        lock_states = tuple(
            LockState.LOCKED if raw_hook_mask & (1 << bit_index) else LockState.OPEN
            for bit_index in range(self._BOARD_LOCK_COUNT)
        )
        return lock_states, raw_hook_mask

    def _lock_state_from_board_status(self, board_status: LockBoardStatusResult, lock_number: int) -> LockState:
        if not 1 <= lock_number <= self._BOARD_LOCK_COUNT:
            raise ValueError(f"lock_number must be between 1 and {self._BOARD_LOCK_COUNT}")
        return board_status.lock_states[lock_number - 1]

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
