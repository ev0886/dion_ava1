from __future__ import annotations

from app.domain.enums import HardwareEndpointType
from app.hardware.contracts import DrumControllerContract, LockControllerContract, RfidReaderContract
from app.hardware.dto import (
    DrumPositionResult,
    HardwareEndpointDescriptor,
    HardwareHealthEntry,
    HardwareHealthSnapshot,
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
        adapter = self._adapter_for(device_type)
        descriptor = self._describe_adapter(adapter)
        try:
            result = adapter.ping()
            return HardwareHealthEntry(
                device_type=device_type,
                is_available=result.ok,
                status=result.status,
                normalized_status="ok" if result.ok else "failure",
                endpoint_kind=descriptor.endpoint_kind,
                configured_transport_mode=descriptor.configured_transport_mode,
                active_transport_mode=descriptor.active_transport_mode,
                detail=result.message or "responsive",
                message=result.message,
            )
        except HardwareError as error:
            return HardwareHealthEntry(
                device_type=device_type,
                is_available=False,
                status=self._status_from_error(error),
                normalized_status=self._normalized_status_from_error(error),
                endpoint_kind=descriptor.endpoint_kind,
                configured_transport_mode=descriptor.configured_transport_mode,
                active_transport_mode=descriptor.active_transport_mode,
                detail=self._detail_from_message(str(error)),
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

    @staticmethod
    def _normalized_status_from_error(error: HardwareError) -> str:
        from app.hardware.exceptions import (
            HardwareBusyError,
            HardwareFailureError,
            HardwareTimeoutError,
            HardwareUnavailableError,
        )

        if isinstance(error, HardwareBusyError):
            return "busy"
        if isinstance(error, HardwareTimeoutError):
            return "timeout"
        if isinstance(error, HardwareUnavailableError):
            return "unavailable"
        if isinstance(error, HardwareFailureError):
            return "failure"
        return "failure"

    @staticmethod
    def _detail_from_message(message: str) -> str:
        compact = " ".join(part for part in message.strip().split())
        return compact[:120] if len(compact) > 120 else compact

    def _adapter_for(self, device_type: HardwareEndpointType):
        if device_type is HardwareEndpointType.DRUM_CONTROLLER:
            return self._drum_controller
        if device_type is HardwareEndpointType.LOCK_CONTROLLER:
            return self._lock_controller
        return self._rfid_reader

    @staticmethod
    def _describe_adapter(adapter) -> HardwareEndpointDescriptor:
        describe_endpoint = getattr(adapter, "describe_endpoint", None)
        if callable(describe_endpoint):
            descriptor = describe_endpoint()
            if isinstance(descriptor, HardwareEndpointDescriptor):
                return descriptor
        return HardwareEndpointDescriptor(
            endpoint_kind="unknown",
            configured_transport_mode=None,
            active_transport_mode="unknown",
        )
