from __future__ import annotations

from app.domain.enums import HardwareEndpointType
from app.hardware.dto import (
    HardwareOperationResult,
    HardwareOperationStatus,
    LockBoardStatusResult,
    LockState,
    LockStatusResult,
    MockHardwareMode,
    UnlockResult,
    UnlockTimeResult,
)
from app.hardware.exceptions import (
    HardwareBusyError,
    HardwareFailureError,
    HardwareTimeoutError,
    HardwareUnavailableError,
)

LockKey = tuple[int, int]


class MockLockAdapter:
    device_type = HardwareEndpointType.LOCK_CONTROLLER

    def __init__(
        self,
        *,
        ping_mode: MockHardwareMode = MockHardwareMode.SUCCESS,
        operation_mode: MockHardwareMode = MockHardwareMode.SUCCESS,
        lock_states: dict[LockKey, LockState] | None = None,
        unlock_times: dict[int, int] | None = None,
    ) -> None:
        self._ping_mode = ping_mode
        self._operation_mode = operation_mode
        self._lock_states: dict[LockKey, LockState] = dict(lock_states or {})
        self._unlock_times: dict[int, int] = dict(unlock_times or {})

    def set_ping_mode(self, mode: MockHardwareMode) -> None:
        self._ping_mode = mode

    def set_operation_mode(self, mode: MockHardwareMode) -> None:
        self._operation_mode = mode

    def set_lock_state(self, board_address: int, lock_number: int, state: LockState) -> None:
        self._lock_states[(board_address, lock_number)] = state

    def ping(self) -> HardwareOperationResult:
        self._raise_for_mode(self._ping_mode, operation="ping")
        return HardwareOperationResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=True,
        )

    def get_board_status(self, board_address: int) -> LockBoardStatusResult:
        lock_states = tuple(self._lock_state(board_address, lock_number) for lock_number in range(1, 25))
        raw_hook_mask = sum(1 << index for index, state in enumerate(lock_states) if state is LockState.LOCKED)
        return LockBoardStatusResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=all(state is not LockState.UNAVAILABLE for state in lock_states),
            board_address=board_address,
            lock_states=lock_states,
            raw_hook_mask=raw_hook_mask,
            message="One or more locks are unavailable" if any(state is LockState.UNAVAILABLE for state in lock_states) else None,
        )

    def get_lock_status(self, board_address: int, lock_number: int) -> LockStatusResult:
        board_status = self.get_board_status(board_address)
        if lock_number < 1 or lock_number > len(board_status.lock_states):
            raise ValueError(f"lock_number must be between 1 and {len(board_status.lock_states)}")
        lock_state = board_status.lock_states[lock_number - 1]
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
        self._raise_for_mode(self._operation_mode, operation="unlock_lock")
        lock_state = self._lock_state(board_address, lock_number)
        if lock_state is LockState.UNAVAILABLE:
            raise HardwareUnavailableError(
                "Lock is unavailable",
                device_type=self.device_type,
                operation="unlock_lock",
            )
        if lock_state is LockState.OPEN:
            return UnlockResult(
                device_type=self.device_type,
                status=HardwareOperationStatus.ALREADY_OPEN,
                ok=True,
                board_address=board_address,
                lock_number=lock_number,
                lock_state=LockState.OPEN,
                message="Lock is already open",
            )
        self._lock_states[(board_address, lock_number)] = LockState.OPEN
        return UnlockResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=True,
            board_address=board_address,
            lock_number=lock_number,
            lock_state=LockState.OPEN,
        )

    def get_unlock_time(self, board_address: int) -> UnlockTimeResult:
        seconds = self._unlock_times.get(board_address, 5)
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
        self._raise_for_mode(self._operation_mode, operation="set_unlock_time")
        self._unlock_times[board_address] = seconds
        return UnlockTimeResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=True,
            board_address=board_address,
            seconds=seconds,
        )

    def _lock_state(self, board_address: int, lock_number: int) -> LockState:
        return self._lock_states.get((board_address, lock_number), LockState.LOCKED)

    def _raise_for_mode(self, mode: MockHardwareMode, *, operation: str) -> None:
        if mode is MockHardwareMode.SUCCESS:
            return
        if mode is MockHardwareMode.BUSY:
            raise HardwareBusyError("Lock controller is busy", device_type=self.device_type, operation=operation)
        if mode is MockHardwareMode.TIMEOUT:
            raise HardwareTimeoutError("Lock controller timed out", device_type=self.device_type, operation=operation)
        raise HardwareFailureError("Lock controller failed", device_type=self.device_type, operation=operation)
