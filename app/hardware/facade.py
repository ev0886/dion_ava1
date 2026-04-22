from __future__ import annotations

from app.domain.enums import HardwareEndpointType
from app.hardware.contracts import DrumControllerContract, LockControllerContract, RfidReaderContract
from app.hardware.dto import (
    DrumPositionResult,
    HardwareHealthEntry,
    HardwareHealthSnapshot,
    LockBoardStatusResult,
    LockStatusResult,
    RfidReadResult,
    UnlockResult,
    UnlockTimeResult,
)
from app.hardware.exceptions import HardwareError


class HardwareFacade:
    def __init__(
        self,
        drum_controller: DrumControllerContract,
        lock_controller: LockControllerContract,
        rfid_reader: RfidReaderContract,
    ) -> None:
        self._drum_controller = drum_controller
        self._lock_controller = lock_controller
        self._rfid_reader = rfid_reader

    def hardware_healthcheck(self) -> HardwareHealthSnapshot:
        return HardwareHealthSnapshot(
            drum=self._ping_entry(HardwareEndpointType.DRUM_CONTROLLER),
            lock=self._ping_entry(HardwareEndpointType.LOCK_CONTROLLER),
            rfid=self._ping_entry(HardwareEndpointType.RFID_READER),
        )

    def get_drum_position(self) -> DrumPositionResult:
        return self._drum_controller.get_position()

    def move_drum_to_position(self, position: int) -> DrumPositionResult:
        return self._drum_controller.move_to_position(position)

    def get_board_lock_status(self, board_address: int) -> LockBoardStatusResult:
        return self._lock_controller.get_board_status(board_address)

    def any_open(self, board_address: int) -> bool:
        return self.get_board_lock_status(board_address).any_open()

    def is_lock_open(self, board_address: int, lock_number: int) -> bool:
        return self.get_board_lock_status(board_address).is_lock_open(lock_number)

    def is_lock_closed(self, board_address: int, lock_number: int) -> bool:
        return self.get_board_lock_status(board_address).is_lock_closed(lock_number)

    def get_lock_status(self, board_address: int, lock_number: int) -> LockStatusResult:
        return self._lock_controller.get_lock_status(board_address, lock_number)

    def unlock_lock(self, board_address: int, lock_number: int) -> UnlockResult:
        return self._lock_controller.unlock_lock(board_address, lock_number)

    def get_unlock_time(self, board_address: int) -> UnlockTimeResult:
        return self._lock_controller.get_unlock_time(board_address)

    def set_unlock_time(self, board_address: int, seconds: int) -> UnlockTimeResult:
        return self._lock_controller.set_unlock_time(board_address, seconds)

    def read_rfid_card(self) -> RfidReadResult:
        return self._rfid_reader.read_card()

    def clear_rfid_buffer(self):
        return self._rfid_reader.clear_buffer()

    def _ping_entry(self, device_type: HardwareEndpointType) -> HardwareHealthEntry:
        try:
            if device_type is HardwareEndpointType.DRUM_CONTROLLER:
                result = self._drum_controller.ping()
            elif device_type is HardwareEndpointType.LOCK_CONTROLLER:
                result = self._lock_controller.ping()
            else:
                result = self._rfid_reader.ping()
            return HardwareHealthEntry(
                device_type=device_type,
                is_available=result.ok,
                status=result.status,
                message=result.message,
            )
        except HardwareError as error:
            return HardwareHealthEntry(
                device_type=device_type,
                is_available=False,
                status=self._status_from_error(error),
                message=str(error),
            )

    @staticmethod
    def _status_from_error(error: HardwareError):
        from app.hardware.dto import HardwareOperationStatus
        from app.hardware.exceptions import (
            HardwareBusyError,
            HardwareFailureError,
            HardwareTimeoutError,
            HardwareUnavailableError,
        )

        if isinstance(error, HardwareBusyError):
            return HardwareOperationStatus.BUSY
        if isinstance(error, HardwareTimeoutError):
            return HardwareOperationStatus.TIMEOUT
        if isinstance(error, HardwareUnavailableError):
            return HardwareOperationStatus.FAILURE
        if isinstance(error, HardwareFailureError):
            return HardwareOperationStatus.FAILURE
        return HardwareOperationStatus.FAILURE
