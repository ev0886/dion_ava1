from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from app.application.exceptions import ValidationError
from app.domain.enums import SlotStatus
from app.hardware import HardwareFacade, LockBoardStatusResult
from app.hardware.dto import LockState
from app.persistence.models import Slot


@dataclass(frozen=True, slots=True)
class TargetDoorStatus:
    board_address: int
    lock_number: int
    lock_state: LockState
    is_open: bool
    is_closed: bool


class OpenDoorGuard:
    def __init__(self, session) -> None:
        self._session = session

    def list_controlled_board_addresses(self) -> tuple[int, ...]:
        return tuple(board_address for board_address, _ in self.list_controlled_lock_numbers_by_board())

    def list_controlled_lock_numbers_by_board(self) -> tuple[tuple[int, tuple[int, ...]], ...]:
        statement = (
            select(Slot.board_address, Slot.lock_number)
            .where(Slot.status == SlotStatus.ACTIVE)
            .order_by(Slot.board_address.asc(), Slot.lock_number.asc(), Slot.id.asc())
        )
        grouped: dict[int, list[int]] = {}
        for board_address, lock_number in self._session.execute(statement).all():
            lock_numbers = grouped.setdefault(int(board_address), [])
            normalized_lock_number = int(lock_number)
            if normalized_lock_number not in lock_numbers:
                lock_numbers.append(normalized_lock_number)
        return tuple(
            (board_address, tuple(lock_numbers))
            for board_address, lock_numbers in grouped.items()
        )

    def any_controlled_cell_open(self, hardware_facade: HardwareFacade) -> bool:
        for board_address, lock_numbers in self.list_controlled_lock_numbers_by_board():
            board_status = hardware_facade.get_board_lock_status(board_address)
            if any(board_status.is_lock_open(lock_number) for lock_number in lock_numbers):
                return True
        return False

    def ensure_all_closed(self, hardware_facade: HardwareFacade, *, error_message: str) -> None:
        if self.any_controlled_cell_open(hardware_facade):
            raise ValidationError(error_message)

    def get_target_door_status(
        self,
        hardware_facade: HardwareFacade,
        *,
        board_address: int,
        lock_number: int,
    ) -> TargetDoorStatus:
        board_status = hardware_facade.get_board_lock_status(board_address)
        if board_status.is_lock_open(lock_number):
            lock_state = LockState.OPEN
        elif board_status.is_lock_closed(lock_number):
            lock_state = LockState.LOCKED
        else:
            lock_state = board_status.lock_states[lock_number - 1]
        return TargetDoorStatus(
            board_address=board_address,
            lock_number=lock_number,
            lock_state=lock_state,
            is_open=board_status.is_lock_open(lock_number),
            is_closed=board_status.is_lock_closed(lock_number),
        )

    def _read_board_statuses(self, hardware_facade: HardwareFacade) -> tuple[LockBoardStatusResult, ...]:
        board_addresses = self.list_controlled_board_addresses()
        return tuple(hardware_facade.get_board_lock_status(board_address) for board_address in board_addresses)
