from __future__ import annotations

from collections import deque

from app.domain.constants import DEFAULT_RFID_UID_FORMAT
from app.domain.enums import HardwareEndpointType
from app.hardware.dto import HardwareOperationResult, HardwareOperationStatus, MockHardwareMode, RfidReadResult
from app.hardware.exceptions import HardwareBusyError, HardwareFailureError, HardwareTimeoutError


class MockRfidAdapter:
    device_type = HardwareEndpointType.RFID_READER

    def __init__(
        self,
        *,
        ping_mode: MockHardwareMode = MockHardwareMode.SUCCESS,
        read_mode: MockHardwareMode = MockHardwareMode.SUCCESS,
        emit_duplicates: bool = False,
    ) -> None:
        self._ping_mode = ping_mode
        self._read_mode = read_mode
        self._emit_duplicates = emit_duplicates
        self._queued_reads: deque[str] = deque()
        self._last_uid: str | None = None

    def set_ping_mode(self, mode: MockHardwareMode) -> None:
        self._ping_mode = mode

    def set_read_mode(self, mode: MockHardwareMode) -> None:
        self._read_mode = mode

    def queue_card(self, uid: str) -> None:
        normalized_uid = self._normalize_uid(uid)
        self._queued_reads.append(normalized_uid)

    def ping(self) -> HardwareOperationResult:
        self._raise_for_mode(self._ping_mode, operation="ping")
        return HardwareOperationResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=True,
        )

    def read_card(self) -> RfidReadResult:
        self._raise_for_mode(self._read_mode, operation="read_card")
        while self._queued_reads:
            uid = self._queued_reads.popleft()
            is_duplicate = uid == self._last_uid
            if is_duplicate and not self._emit_duplicates:
                continue
            self._last_uid = uid
            return RfidReadResult(
                device_type=self.device_type,
                status=HardwareOperationStatus.NO_CARD if uid is None else (
                    HardwareOperationStatus.SUCCESS if not is_duplicate else HardwareOperationStatus.SUCCESS
                ),
                ok=True,
                uid=uid,
                is_duplicate=is_duplicate,
            )
        return RfidReadResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.NO_CARD,
            ok=True,
            uid=None,
            is_duplicate=False,
            message=f"No RFID card present ({DEFAULT_RFID_UID_FORMAT})",
        )

    def clear_buffer(self) -> HardwareOperationResult:
        self._queued_reads.clear()
        return HardwareOperationResult(
            device_type=self.device_type,
            status=HardwareOperationStatus.SUCCESS,
            ok=True,
        )

    @staticmethod
    def _normalize_uid(uid: str) -> str:
        cleaned = "".join(character for character in uid if character.isalnum()).upper()
        if not cleaned:
            raise ValueError("uid must contain at least one hexadecimal character")
        return cleaned

    def _raise_for_mode(self, mode: MockHardwareMode, *, operation: str) -> None:
        if mode is MockHardwareMode.SUCCESS:
            return
        if mode is MockHardwareMode.BUSY:
            raise HardwareBusyError("RFID reader is busy", device_type=self.device_type, operation=operation)
        if mode is MockHardwareMode.TIMEOUT:
            raise HardwareTimeoutError("RFID reader timed out", device_type=self.device_type, operation=operation)
        raise HardwareFailureError("RFID reader failed", device_type=self.device_type, operation=operation)
