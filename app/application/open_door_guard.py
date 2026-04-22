from __future__ import annotations

from dataclasses import dataclass

from app.application.exceptions import NotFoundError, ValidationError
from app.hardware import HardwareFacade, LockState
from app.hardware.exceptions import HardwareError
from app.persistence.repositories.inventory import InventoryRepository, SlotHardwareRefRecord


@dataclass(frozen=True, slots=True)
class OpenDoorCellDTO:
    slot_id: int
    cell_number: int
    drum_position: int
    board_address: int
    lock_number: int
    lock_state: LockState


@dataclass(frozen=True, slots=True)
class OpenDoorGuardStatusDTO:
    any_cell_open: bool
    open_cell: OpenDoorCellDTO | None


@dataclass(frozen=True, slots=True)
class SlotDoorStatusDTO:
    slot_id: int
    cell_number: int
    drum_position: int
    board_address: int
    lock_number: int
    lock_state: LockState
    is_open: bool
    any_cell_open: bool
    open_cell: OpenDoorCellDTO | None


@dataclass(slots=True)
class OpenDoorGuard:
    inventory_repository: InventoryRepository
    hardware_facade: HardwareFacade

    def assert_all_closed(self, *, action_description: str) -> None:
        status = self.get_status()
        if not status.any_cell_open or status.open_cell is None:
            return
        raise ValidationError(f"{action_description} blocked: cell {status.open_cell.cell_number} is open")

    def assert_all_closed_for_drum_movement(self) -> None:
        self.assert_all_closed(action_description="Drum movement")

    def get_status(self) -> OpenDoorGuardStatusDTO:
        open_cell = self._find_first_open_cell()
        return OpenDoorGuardStatusDTO(any_cell_open=open_cell is not None, open_cell=open_cell)

    def get_slot_status(self, slot_id: int) -> SlotDoorStatusDTO:
        slot = self.inventory_repository.get_slot(slot_id)
        if slot is None:
            raise NotFoundError(f"Slot not found: {slot_id}")

        lock_status = self._read_lock_status(
            board_address=slot.board_address,
            lock_number=slot.lock_number,
            context=f"slot {self._cell_number(slot.drum_position, slot.lock_number)}",
        )
        global_status = self.get_status()
        return SlotDoorStatusDTO(
            slot_id=slot.id,
            cell_number=self._cell_number(slot.drum_position, slot.lock_number),
            drum_position=slot.drum_position,
            board_address=slot.board_address,
            lock_number=slot.lock_number,
            lock_state=lock_status.lock_state,
            is_open=lock_status.lock_state is LockState.OPEN,
            any_cell_open=global_status.any_cell_open,
            open_cell=global_status.open_cell,
        )

    def _find_first_open_cell(self) -> OpenDoorCellDTO | None:
        for slot in self.inventory_repository.list_active_slot_hardware_refs():
            lock_status = self._read_lock_status(
                board_address=slot.board_address,
                lock_number=slot.lock_number,
                context=f"cell {self._cell_number(slot.drum_position, slot.lock_number)}",
            )
            if lock_status.lock_state is LockState.OPEN:
                return OpenDoorCellDTO(
                    slot_id=slot.slot_id,
                    cell_number=self._cell_number(slot.drum_position, slot.lock_number),
                    drum_position=slot.drum_position,
                    board_address=slot.board_address,
                    lock_number=slot.lock_number,
                    lock_state=lock_status.lock_state,
                )
        return None

    def _read_lock_status(self, *, board_address: int, lock_number: int, context: str):
        try:
            return self.hardware_facade.get_lock_status(board_address, lock_number)
        except HardwareError as error:
            raise ValidationError(f"Open-door guard blocked: unable to read lock state for {context}: {error}") from error

    @staticmethod
    def _cell_number(drum_position: int, lock_number: int) -> int:
        return (drum_position * 15) + lock_number
