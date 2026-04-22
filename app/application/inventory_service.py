from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select

from app.application.dto.inventory import (
    AvailableDispenseOptionDTO,
    AvailableDispenseOptionsResult,
    InventoryBalanceDTO,
    InventoryLookupResult,
    KioskDispenseOptionDTO,
    KioskDispenseOptionsResult,
    OperatorBoardCellDTO,
    OperatorBoardStateResult,
    OperatorInventoryActionResult,
    SlotBindingDTO,
)
from app.application.exceptions import NotFoundError, ValidationError
from app.application.open_door_guard import OpenDoorGuard
from app.application.time import utc_now
from app.domain.enums import BindingType, InventoryTransactionType, OperationState, OperationType
from app.hardware.exceptions import HardwareError
from app.persistence.models import (
    EventLog,
    InventoryBalance,
    InventoryTransaction,
    Operation,
    OperationStateHistory,
    SlotItemBinding,
)
from app.persistence.repositories.logs import EventLogRepository
from app.persistence.repositories.nomenclature import NomenclatureRepository
from app.persistence.repositories.operations import OperationRepository
from app.persistence.repositories.inventory import InventoryRepository


class InventoryService:
    _OPERATOR_ACCESS_SECTOR_BY_QUARTER = {
        1: 7,
        2: 15,
        3: 23,
        4: 31,
    }

    def __init__(
        self,
        inventory_repository: InventoryRepository,
        nomenclature_repository: NomenclatureRepository,
        operation_repository: OperationRepository,
        event_log_repository: EventLogRepository,
        open_door_guard: OpenDoorGuard | None = None,
    ) -> None:
        self.inventory_repository = inventory_repository
        self.nomenclature_repository = nomenclature_repository
        self.operation_repository = operation_repository
        self.event_log_repository = event_log_repository
        self._open_door_guard = open_door_guard

    def get_balance(self, slot_id: int, item_id: int) -> InventoryBalanceDTO | None:
        self._validate_slot_item_ids(slot_id, item_id)
        balance = self.inventory_repository.get_balance(slot_id, item_id)
        if balance is None:
            return None
        return self._to_balance_dto(balance)

    def lookup_inventory(self, slot_id: int, item_id: int) -> InventoryLookupResult:
        self._validate_slot_item_ids(slot_id, item_id)
        balance = self.inventory_repository.get_balance(slot_id, item_id)
        bindings = self.list_bindings(slot_id=slot_id, item_id=item_id)
        return InventoryLookupResult(
            slot_id=slot_id,
            item_id=item_id,
            balance=self._to_balance_dto(balance) if balance is not None else None,
            bindings=bindings,
        )

    def list_available_dispense_options(self) -> AvailableDispenseOptionsResult:
        return AvailableDispenseOptionsResult(
            options=tuple(
                AvailableDispenseOptionDTO(
                    slot_id=option.slot_id,
                    item_id=option.item_id,
                    quantity=option.quantity,
                    updated_at=option.updated_at,
                    slot_code=option.slot_code,
                    drum_position=option.drum_position,
                    board_address=option.board_address,
                    lock_number=option.lock_number,
                    item_sku=option.item_sku,
                    item_name=option.item_name,
                    item_unit=option.item_unit,
                )
                for option in self.inventory_repository.list_available_dispense_options()
            )
        )

    def list_kiosk_dispense_options(self) -> KioskDispenseOptionsResult:
        aggregated: dict[int, KioskDispenseOptionDTO] = {}
        for option in self.inventory_repository.list_available_dispense_options():
            current = aggregated.get(option.item_id)
            if current is None:
                aggregated[option.item_id] = KioskDispenseOptionDTO(
                    item_id=option.item_id,
                    item_name=option.item_name,
                    item_unit=option.item_unit,
                    total_quantity=option.quantity,
                )
                continue
            aggregated[option.item_id] = KioskDispenseOptionDTO(
                item_id=current.item_id,
                item_name=current.item_name,
                item_unit=current.item_unit,
                total_quantity=current.total_quantity + option.quantity,
        )
        return KioskDispenseOptionsResult(options=tuple(aggregated.values()))

    def get_operator_board_state(self) -> OperatorBoardStateResult:
        records = self.inventory_repository.list_operator_board_slots()
        return OperatorBoardStateResult(
            cells=tuple(
                OperatorBoardCellDTO(
                    slot_id=record.slot_id,
                    cell_number=self._cell_number(record.drum_position, record.lock_number),
                    sector_number=record.drum_position + 1,
                    quarter_number=(record.drum_position // 8) + 1,
                    drum_position=record.drum_position,
                    lock_number=record.lock_number,
                    filled=record.filled,
                )
                for record in records
            )
        )

    def operator_replenish_slots(
        self,
        *,
        operator_user_id: int,
        nomenclature_id: int,
        slot_ids: tuple[int, ...],
        hardware_facade=None,
    ) -> OperatorInventoryActionResult:
        self._ensure_all_cells_closed(hardware_facade, "Operator replenish blocked: one or more cells are open")
        normalized_slot_ids = self._normalize_slot_ids(slot_ids)
        if operator_user_id <= 0:
            raise ValidationError("operator_user_id must be positive")
        if nomenclature_id <= 0:
            raise ValidationError("nomenclature_id must be positive")

        nomenclature = self.nomenclature_repository.get_by_id(nomenclature_id)
        if nomenclature is None or not nomenclature.is_active:
            raise NotFoundError(f"Nomenclature entry not found: {nomenclature_id}")

        item_resolution = self.inventory_repository.resolve_authoritative_replenish_item(
            normalized_name=nomenclature.normalized_name,
            slot_ids=normalized_slot_ids,
        )
        item = item_resolution.item
        if item is None and item_resolution.matched_candidate_count == 0:
            raise ValidationError(
                f"Active inventory item not found for nomenclature '{nomenclature.name}'"
            )
        if item is None:
            raise ValidationError(
                f"Ambiguous inventory item mapping for nomenclature '{nomenclature.name}'"
            )

        slots, balances_by_slot = self._load_slots_and_balances(normalized_slot_ids)
        invalid_slots = [
            self._cell_number(slot.drum_position, slot.lock_number)
            for slot in slots
            if self._slot_total_quantity(balances_by_slot.get(slot.id, ())) > 0
        ]
        if invalid_slots:
            raise ValidationError(
                "Replenishment rejected: selected slots are already filled: "
                + ", ".join(str(cell_number) for cell_number in invalid_slots)
            )

        operation_ids: list[int] = []
        cell_numbers: list[int] = []
        timestamp = utc_now()

        try:
            for slot in slots:
                cell_number = self._cell_number(slot.drum_position, slot.lock_number)
                operation = Operation(
                    session_id=None,
                    operation_type=OperationType.INVENTORY_ADJUSTMENT,
                    operation_state=OperationState.COMPLETED,
                    user_id=operator_user_id,
                    item_id=item.id,
                    slot_id=slot.id,
                    qty_requested=1,
                    qty_confirmed=1,
                    result="completed",
                    error_code=None,
                    error_message=None,
                    hardware_context_json=None,
                    business_context_json={
                        "source": "operator_touch",
                        "action": "replenish",
                        "nomenclature_id": nomenclature.id,
                    },
                    started_at=timestamp,
                    finished_at=timestamp,
                )
                self.operation_repository.add(operation)
                self.operation_repository.session.flush()
                self.operation_repository.add_state_history(
                    OperationStateHistory(
                        operation_id=operation.id,
                        state=OperationState.COMPLETED,
                        comment="Operator replenish completed",
                        context_json={
                            "source": "operator_touch",
                            "action": "replenish",
                            "cell_number": cell_number,
                            "nomenclature_id": nomenclature.id,
                        },
                    )
                )

                balance = self.inventory_repository.get_balance(slot.id, item.id)
                quantity_before = balance.quantity if balance is not None else 0
                if balance is None:
                    balance = InventoryBalance(slot_id=slot.id, item_id=item.id, quantity=0)
                    self.inventory_repository.add_balance(balance)
                    self.inventory_repository.session.flush()
                balance.quantity = 1

                binding = self.inventory_repository.get_binding(
                    slot_id=slot.id,
                    item_id=item.id,
                    binding_type=BindingType.PRIMARY,
                )
                if binding is None:
                    self.inventory_repository.add_binding(
                        SlotItemBinding(
                            slot_id=slot.id,
                            item_id=item.id,
                            binding_type=BindingType.PRIMARY,
                            is_active=True,
                            valid_from=timestamp,
                            valid_to=None,
                        )
                    )
                else:
                    binding.is_active = True
                    if binding.valid_from is None:
                        binding.valid_from = timestamp
                    binding.valid_to = None

                self.inventory_repository.add_transaction(
                    InventoryTransaction(
                        slot_id=slot.id,
                        item_id=item.id,
                        operation_id=operation.id,
                        session_id=None,
                        transaction_type=InventoryTransactionType.INVENTORY_ADJUSTMENT,
                        quantity_delta=1 - quantity_before,
                        quantity_before=quantity_before,
                        quantity_after=1,
                        comment="Operator replenish inventory committed",
                        created_at=timestamp,
                    )
                )
                self.event_log_repository.add(
                    EventLog(
                        event_type="operator_inventory_replenish",
                        level="info",
                        source="operator_touch",
                        operation_id=operation.id,
                        session_id=None,
                        user_id=operator_user_id,
                        slot_id=slot.id,
                        item_id=item.id,
                        qty=1,
                        result="success",
                        comment="Operator replenish completed",
                        message=f"Cell {cell_number} replenished with {item.name}",
                        payload_json={
                            "cell_number": cell_number,
                            "nomenclature_id": nomenclature.id,
                            "item_id": item.id,
                        },
                    )
                )
                operation_ids.append(operation.id)
                cell_numbers.append(cell_number)

            self.inventory_repository.session.commit()
        except Exception:
            self.inventory_repository.session.rollback()
            raise

        return OperatorInventoryActionResult(
            action="replenish",
            operator_user_id=operator_user_id,
            item_id=item.id,
            item_name=item.name,
            nomenclature_id=nomenclature.id,
            slot_ids=tuple(slot.id for slot in slots),
            cell_numbers=tuple(sorted(cell_numbers)),
            operation_ids=tuple(operation_ids),
        )

    def operator_remove_slots(
        self,
        *,
        operator_user_id: int,
        slot_ids: tuple[int, ...],
        hardware_facade=None,
    ) -> OperatorInventoryActionResult:
        self._ensure_all_cells_closed(hardware_facade, "Operator removal blocked: one or more cells are open")
        normalized_slot_ids = self._normalize_slot_ids(slot_ids)
        if operator_user_id <= 0:
            raise ValidationError("operator_user_id must be positive")

        slots, balances_by_slot = self._load_slots_and_balances(normalized_slot_ids)
        invalid_slots = [
            self._cell_number(slot.drum_position, slot.lock_number)
            for slot in slots
            if self._slot_total_quantity(balances_by_slot.get(slot.id, ())) <= 0
        ]
        if invalid_slots:
            raise ValidationError(
                "Removal rejected: selected slots are already empty: "
                + ", ".join(str(cell_number) for cell_number in invalid_slots)
            )

        operation_ids: list[int] = []
        cell_numbers: list[int] = []
        timestamp = utc_now()

        try:
            for slot in slots:
                cell_number = self._cell_number(slot.drum_position, slot.lock_number)
                positive_balances = tuple(
                    balance for balance in balances_by_slot.get(slot.id, ()) if balance.quantity > 0
                )
                for balance in positive_balances:
                    quantity_before = balance.quantity
                    operation = Operation(
                        session_id=None,
                        operation_type=OperationType.INVENTORY_ADJUSTMENT,
                        operation_state=OperationState.COMPLETED,
                        user_id=operator_user_id,
                        item_id=balance.item_id,
                        slot_id=slot.id,
                        qty_requested=quantity_before,
                        qty_confirmed=quantity_before,
                        result="completed",
                        error_code=None,
                        error_message=None,
                        hardware_context_json=None,
                        business_context_json={
                            "source": "operator_touch",
                            "action": "remove",
                            "cleared_slot": True,
                        },
                        started_at=timestamp,
                        finished_at=timestamp,
                    )
                    self.operation_repository.add(operation)
                    self.operation_repository.session.flush()
                    self.operation_repository.add_state_history(
                        OperationStateHistory(
                            operation_id=operation.id,
                            state=OperationState.COMPLETED,
                            comment="Operator removal completed",
                            context_json={
                                "source": "operator_touch",
                                "action": "remove",
                                "cell_number": cell_number,
                            },
                        )
                    )

                    balance.quantity = 0
                    self.inventory_repository.add_transaction(
                        InventoryTransaction(
                            slot_id=slot.id,
                            item_id=balance.item_id,
                            operation_id=operation.id,
                            session_id=None,
                            transaction_type=InventoryTransactionType.INVENTORY_ADJUSTMENT,
                            quantity_delta=-quantity_before,
                            quantity_before=quantity_before,
                            quantity_after=0,
                            comment="Operator removal inventory committed",
                            created_at=timestamp,
                        )
                    )
                    self.event_log_repository.add(
                        EventLog(
                            event_type="operator_inventory_remove",
                            level="info",
                            source="operator_touch",
                            operation_id=operation.id,
                            session_id=None,
                            user_id=operator_user_id,
                            slot_id=slot.id,
                            item_id=balance.item_id,
                            qty=quantity_before,
                            result="success",
                            comment="Operator removal completed",
                            message=f"Cell {cell_number} cleared",
                            payload_json={
                                "cell_number": cell_number,
                                "item_id": balance.item_id,
                            },
                        )
                    )
                    operation_ids.append(operation.id)

                cell_numbers.append(cell_number)

            self.inventory_repository.session.commit()
        except Exception:
            self.inventory_repository.session.rollback()
            raise

        return OperatorInventoryActionResult(
            action="remove",
            operator_user_id=operator_user_id,
            item_id=None,
            item_name=None,
            nomenclature_id=None,
            slot_ids=tuple(slot.id for slot in slots),
            cell_numbers=tuple(sorted(cell_numbers)),
            operation_ids=tuple(operation_ids),
        )

    def operator_prepare_replenish_slots(
        self,
        *,
        operator_user_id: int,
        slot_ids: tuple[int, ...],
        hardware_facade=None,
    ) -> OperatorBoardStateResult:
        self._prepare_operator_quarter_access(
            operator_user_id=operator_user_id,
            slot_ids=slot_ids,
            hardware_facade=hardware_facade,
            error_message="Operator replenish blocked: one or more cells are open",
        )
        return self.get_operator_board_state()

    def operator_prepare_remove_slots(
        self,
        *,
        operator_user_id: int,
        slot_ids: tuple[int, ...],
        hardware_facade=None,
    ) -> OperatorBoardStateResult:
        self._prepare_operator_quarter_access(
            operator_user_id=operator_user_id,
            slot_ids=slot_ids,
            hardware_facade=hardware_facade,
            error_message="Operator removal blocked: one or more cells are open",
        )
        return self.get_operator_board_state()

    def resolve_dispense_slot_for_item(self, item_id: int) -> int:
        if item_id <= 0:
            raise ValidationError("item_id must be positive")
        option = self.inventory_repository.resolve_available_dispense_option(item_id)
        if option is None:
            raise NotFoundError(f"No available dispense slot found for item: {item_id}")
        return option.slot_id

    def list_bindings(self, slot_id: int | None = None, item_id: int | None = None) -> tuple[SlotBindingDTO, ...]:
        statement = select(SlotItemBinding)
        if slot_id is not None:
            statement = statement.where(SlotItemBinding.slot_id == slot_id)
        if item_id is not None:
            statement = statement.where(SlotItemBinding.item_id == item_id)
        bindings = self.inventory_repository.session.execute(statement).scalars()
        return tuple(self._to_binding_dto(binding) for binding in bindings)

    @staticmethod
    def _validate_slot_item_ids(slot_id: int, item_id: int) -> None:
        if slot_id <= 0:
            raise ValidationError("slot_id must be positive")
        if item_id <= 0:
            raise ValidationError("item_id must be positive")

    @staticmethod
    def _to_balance_dto(balance: InventoryBalance) -> InventoryBalanceDTO:
        return InventoryBalanceDTO(
            slot_id=balance.slot_id,
            item_id=balance.item_id,
            quantity=balance.quantity,
            updated_at=balance.updated_at,
        )

    @staticmethod
    def _to_binding_dto(binding: SlotItemBinding) -> SlotBindingDTO:
        return SlotBindingDTO(
            slot_id=binding.slot_id,
            item_id=binding.item_id,
            binding_type=binding.binding_type,
            is_active=binding.is_active,
            valid_from=binding.valid_from,
            valid_to=binding.valid_to,
        )

    @staticmethod
    def _normalize_slot_ids(slot_ids: tuple[int, ...]) -> tuple[int, ...]:
        normalized: list[int] = []
        for slot_id in slot_ids:
            if slot_id <= 0:
                raise ValidationError("slot_ids must contain only positive integers")
            if slot_id not in normalized:
                normalized.append(slot_id)
        if not normalized:
            raise ValidationError("slot_ids must not be empty")
        return tuple(normalized)

    def _load_slots_and_balances(
        self,
        slot_ids: tuple[int, ...],
    ):
        slots = self.inventory_repository.list_active_slots_by_ids(slot_ids)
        slots_by_id = {slot.id: slot for slot in slots}
        missing_slot_ids = [slot_id for slot_id in slot_ids if slot_id not in slots_by_id]
        if missing_slot_ids:
            raise ValidationError(
                "Selected slots are not available: " + ", ".join(str(slot_id) for slot_id in missing_slot_ids)
            )

        balances_by_slot: dict[int, tuple[InventoryBalance, ...]] = {}
        grouped_balances: dict[int, list[InventoryBalance]] = defaultdict(list)
        for balance in self.inventory_repository.list_balances_for_slot_ids(slot_ids):
            grouped_balances[balance.slot_id].append(balance)
        for slot_id in slot_ids:
            balances_by_slot[slot_id] = tuple(grouped_balances.get(slot_id, ()))

        ordered_slots = tuple(slots_by_id[slot_id] for slot_id in slot_ids)
        return ordered_slots, balances_by_slot

    @staticmethod
    def _slot_total_quantity(balances: tuple[InventoryBalance, ...]) -> int:
        return sum(balance.quantity for balance in balances)

    @staticmethod
    def _cell_number(drum_position: int, lock_number: int) -> int:
        return (drum_position * 15) + lock_number

    @classmethod
    def _quarter_number(cls, drum_position: int) -> int:
        quarter_number = (drum_position // 8) + 1
        if quarter_number not in cls._OPERATOR_ACCESS_SECTOR_BY_QUARTER:
            raise ValidationError(f"Unsupported operator quarter for drum position: {drum_position}")
        return quarter_number

    def _position_operator_quarter_access(self, slots, hardware_facade) -> None:
        if hardware_facade is None:
            return
        quarter_numbers = {self._quarter_number(slot.drum_position) for slot in slots}
        if len(quarter_numbers) != 1:
            raise ValidationError("Selected slots must belong to exactly one quarter")
        quarter_number = next(iter(quarter_numbers))
        target_sector = self._OPERATOR_ACCESS_SECTOR_BY_QUARTER[quarter_number]
        try:
            hardware_facade.move_drum_to_position(target_sector)
        except HardwareError:
            self.inventory_repository.session.rollback()
            raise

    def _prepare_operator_quarter_access(
        self,
        *,
        operator_user_id: int,
        slot_ids: tuple[int, ...],
        hardware_facade,
        error_message: str,
    ) -> None:
        self._ensure_all_cells_closed(hardware_facade, error_message)
        normalized_slot_ids = self._normalize_slot_ids(slot_ids)
        if operator_user_id <= 0:
            raise ValidationError("operator_user_id must be positive")
        slots, _balances_by_slot = self._load_slots_and_balances(normalized_slot_ids)
        self._position_operator_quarter_access(slots, hardware_facade)

    def _ensure_all_cells_closed(self, hardware_facade, error_message: str) -> None:
        if self._open_door_guard is None or hardware_facade is None:
            return
        self._open_door_guard.ensure_all_closed(hardware_facade, error_message=error_message)
