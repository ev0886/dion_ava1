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
from app.hardware.exceptions import HardwareFailureError, HardwareTimeoutError, HardwareUnavailableError
from app.hardware.real_adapter_base import RealHardwareAdapterBase
from app.hardware.transport_config import HardwareEndpointTransportConfig
from app.hardware.transports import SerialRequestResponseTransport, TcpRequestResponseTransport


class RealLockAdapter(RealHardwareAdapterBase):
    _PING_TEMPLATE = "PING {board}\n"
    _GET_STATUS_TEMPLATE = "GET_LOCK_STATUS {board} {lock}\n"
    _UNLOCK_TEMPLATE = "UNLOCK {board} {lock}\n"
    _GET_UNLOCK_TIME_TEMPLATE = "GET_UNLOCK_TIME {board}\n"
    _SET_UNLOCK_TIME_TEMPLATE = "SET_UNLOCK_TIME {board} {seconds}\n"
    _PONG_RESPONSE = "PONG"
    _STATUS_PREFIX = "STATUS:"
    _UNLOCKED_RESPONSE = "UNLOCKED"
    _ALREADY_OPEN_RESPONSE = "ALREADY_OPEN"
    _UNAVAILABLE_RESPONSE = "UNAVAILABLE"
    _UNLOCK_TIME_PREFIX = "UNLOCK_TIME:"
    _SET_UNLOCK_TIME_PREFIX = "SET_UNLOCK_TIME:"

    def __init__(
        self,
        *,
        config: HardwareEndpointTransportConfig | None,
        transport: SerialRequestResponseTransport | TcpRequestResponseTransport | None,
        config_error: str | None = None,
    ) -> None:
        super().__init__(
            device_type=HardwareEndpointType.LOCK_CONTROLLER,
            config=config,
            transport=transport,
            config_error=config_error,
        )

    def ping(self) -> HardwareOperationResult:
        response = self._send_request(self._PING_TEMPLATE.format(board=0).encode("ascii"), operation="ping")
        if response != self._PONG_RESPONSE:
            raise HardwareFailureError(
                f"Lock controller returned unsupported ping response: {response!r}",
                device_type=self.device_type,
                operation="ping",
            )
        return HardwareOperationResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=True,
        )

    def get_lock_status(self, board_address: int, lock_number: int) -> LockStatusResult:
        response = self._send_request(
            self._GET_STATUS_TEMPLATE.format(board=board_address, lock=lock_number).encode("ascii"),
            operation="get_lock_status",
        )
        if not response.startswith(self._STATUS_PREFIX):
            raise HardwareFailureError(
                f"Lock controller returned unsupported status response: {response!r}",
                device_type=self.device_type,
                operation="get_lock_status",
            )
        lock_state = self._parse_lock_state(response.removeprefix(self._STATUS_PREFIX), operation="get_lock_status")
        return LockStatusResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=lock_state is not LockState.UNAVAILABLE,
            board_address=board_address,
            lock_number=lock_number,
            lock_state=lock_state,
            message="Lock is unavailable" if lock_state is LockState.UNAVAILABLE else None,
        )

    def unlock_lock(self, board_address: int, lock_number: int) -> UnlockResult:
        response = self._send_request(
            self._UNLOCK_TEMPLATE.format(board=board_address, lock=lock_number).encode("ascii"),
            operation="unlock_lock",
        )
        if response == self._UNLOCKED_RESPONSE:
            return UnlockResult(
                device_type=self.device_type,
                status=HardwareOperationStatus.SUCCESS,
                ok=True,
                board_address=board_address,
                lock_number=lock_number,
                lock_state=LockState.OPEN,
            )
        if response == self._ALREADY_OPEN_RESPONSE:
            return UnlockResult(
                device_type=self.device_type,
                status=HardwareOperationStatus.ALREADY_OPEN,
                ok=True,
                board_address=board_address,
                lock_number=lock_number,
                lock_state=LockState.OPEN,
                message="Lock is already open",
            )
        if response == self._UNAVAILABLE_RESPONSE:
            raise HardwareUnavailableError(
                "Lock is unavailable",
                device_type=self.device_type,
                operation="unlock_lock",
            )
        raise HardwareFailureError(
            f"Lock controller returned unsupported unlock response: {response!r}",
            device_type=self.device_type,
            operation="unlock_lock",
        )

    def get_unlock_time(self, board_address: int) -> UnlockTimeResult:
        response = self._send_request(
            self._GET_UNLOCK_TIME_TEMPLATE.format(board=board_address).encode("ascii"),
            operation="get_unlock_time",
        )
        if not response.startswith(self._UNLOCK_TIME_PREFIX):
            raise HardwareFailureError(
                f"Lock controller returned unsupported unlock time response: {response!r}",
                device_type=self.device_type,
                operation="get_unlock_time",
            )
        seconds = self._parse_seconds(response.removeprefix(self._UNLOCK_TIME_PREFIX), operation="get_unlock_time")
        return UnlockTimeResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=True,
            board_address=board_address,
            seconds=seconds,
        )

    def set_unlock_time(self, board_address: int, seconds: int) -> UnlockTimeResult:
        if seconds <= 0:
            raise ValueError("seconds must be positive")
        response = self._send_request(
            self._SET_UNLOCK_TIME_TEMPLATE.format(board=board_address, seconds=seconds).encode("ascii"),
            operation="set_unlock_time",
        )
        if not response.startswith(self._SET_UNLOCK_TIME_PREFIX):
            raise HardwareFailureError(
                f"Lock controller returned unsupported set unlock time response: {response!r}",
                device_type=self.device_type,
                operation="set_unlock_time",
            )
        applied_seconds = self._parse_seconds(
            response.removeprefix(self._SET_UNLOCK_TIME_PREFIX),
            operation="set_unlock_time",
        )
        return UnlockTimeResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=True,
            board_address=board_address,
            seconds=applied_seconds,
        )

    def _send_request(self, payload: bytes, *, operation: str) -> str:
        self._raise_if_unavailable(operation=operation)
        assert self._transport is not None
        timeout_ms = self._config.endpoint.timeouts.read_timeout_ms if self._config is not None else None
        try:
            raw_response = self._transport.request(payload, timeout_ms=timeout_ms)
        except TimeoutError as error:
            raise HardwareTimeoutError(
                f"Lock controller transport request timed out: {error}",
                device_type=self.device_type,
                operation=operation,
            ) from error
        except NotImplementedError as error:
            raise HardwareUnavailableError(
                f"Lock controller transport I/O is not implemented yet: {error}",
                device_type=self.device_type,
                operation=operation,
            ) from error
        except OSError as error:
            raise HardwareUnavailableError(
                f"Lock controller transport request failed: {error}",
                device_type=self.device_type,
                operation=operation,
            ) from error
        try:
            return raw_response.decode("ascii").strip()
        except (AttributeError, TypeError, UnicodeDecodeError) as error:
            raise HardwareFailureError(
                "Lock controller returned a malformed response.",
                device_type=self.device_type,
                operation=operation,
            ) from error

    def _parse_lock_state(self, state: str, *, operation: str) -> LockState:
        normalized = state.strip().upper()
        if normalized == "LOCKED":
            return LockState.LOCKED
        if normalized == "OPEN":
            return LockState.OPEN
        if normalized == "UNAVAILABLE":
            return LockState.UNAVAILABLE
        raise HardwareFailureError(
            f"Lock controller returned unsupported lock state: {state!r}",
            device_type=self.device_type,
            operation=operation,
        )

    def _parse_seconds(self, value: str, *, operation: str) -> int:
        try:
            seconds = int(value.strip())
        except ValueError as error:
            raise HardwareFailureError(
                f"Lock controller returned an invalid unlock time: {value!r}",
                device_type=self.device_type,
                operation=operation,
            ) from error
        if seconds <= 0:
            raise HardwareFailureError(
                f"Lock controller returned a non-positive unlock time: {value!r}",
                device_type=self.device_type,
                operation=operation,
            )
        return seconds
