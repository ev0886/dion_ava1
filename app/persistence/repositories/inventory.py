from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, case, func, select

from app.domain.enums import BindingType, ItemStatus, SlotStatus, SlotType
from app.persistence.models import InventoryBalance, InventoryTransaction, Item, Slot, SlotItemBinding
from app.persistence.repositories.base import Repository


@dataclass(frozen=True, slots=True)
class AvailableDispenseOptionRecord:
    slot_id: int
    item_id: int
    quantity: int
    updated_at: datetime | None
    slot_code: str
    drum_position: int
    board_address: int
    lock_number: int
    item_sku: str
    item_name: str
    item_unit: str


@dataclass(frozen=True, slots=True)
class FilledBalanceSummaryRecord:
    item_name: str
    quantity: int


@dataclass(frozen=True, slots=True)
class OperatorBoardSlotRecord:
    slot_id: int
    drum_position: int
    lock_number: int
    filled: bool
    item_name: str | None


@dataclass(frozen=True, slots=True)
class ReplenishItemResolution:
    item: Item | None
    matched_candidate_count: int
    resolution_source: str


class InventoryRepository(Repository):
    @staticmethod
    def _normalize_name(value: str) -> str:
        return " ".join(value.split()).casefold()

    def get_balance(self, slot_id: int, item_id: int) -> InventoryBalance | None:
        statement = select(InventoryBalance).where(
            InventoryBalance.slot_id == slot_id,
            InventoryBalance.item_id == item_id,
        )
        return self.session.execute(statement).scalar_one_or_none()

    def add_balance(self, balance: InventoryBalance) -> None:
        self.session.add(balance)

    def add_transaction(self, transaction: InventoryTransaction) -> None:
        self.session.add(transaction)

    def get_slot(self, slot_id: int) -> Slot | None:
        return self.session.get(Slot, slot_id)

    def list_active_slots_by_ids(self, slot_ids: tuple[int, ...]) -> tuple[Slot, ...]:
        if not slot_ids:
            return ()
        statement = (
            select(Slot)
            .where(
                Slot.id.in_(slot_ids),
                Slot.status == SlotStatus.ACTIVE,
            )
            .order_by(Slot.drum_position.asc(), Slot.lock_number.asc(), Slot.id.asc())
        )
        return tuple(self.session.execute(statement).scalars())

    def list_operator_board_slots(self) -> tuple[OperatorBoardSlotRecord, ...]:
        positive_balance_items = (
            select(
                InventoryBalance.slot_id.label("slot_id"),
                func.min(Item.name).label("item_name"),
            )
            .join(Item, Item.id == InventoryBalance.item_id)
            .where(InventoryBalance.quantity > 0)
            .group_by(InventoryBalance.slot_id)
            .subquery()
        )
        statement = (
            select(
                Slot.id,
                Slot.drum_position,
                Slot.lock_number,
                positive_balance_items.c.slot_id.is_not(None),
                positive_balance_items.c.item_name,
            )
            .outerjoin(positive_balance_items, positive_balance_items.c.slot_id == Slot.id)
            .where(
                Slot.status == SlotStatus.ACTIVE,
                Slot.lock_number >= 1,
                Slot.lock_number <= 15,
                Slot.drum_position >= 0,
                Slot.drum_position < 32,
            )
            .order_by(Slot.drum_position.asc(), Slot.lock_number.asc(), Slot.id.asc())
        )
        rows = self.session.execute(statement).all()
        return tuple(
            OperatorBoardSlotRecord(
                slot_id=row[0],
                drum_position=row[1],
                lock_number=row[2],
                filled=bool(row[3]),
                item_name=row[4],
            )
            for row in rows
        )

    def list_balances_for_slot_ids(self, slot_ids: tuple[int, ...]) -> tuple[InventoryBalance, ...]:
        if not slot_ids:
            return ()
        statement = (
            select(InventoryBalance)
            .where(InventoryBalance.slot_id.in_(slot_ids))
            .order_by(InventoryBalance.slot_id.asc(), InventoryBalance.item_id.asc(), InventoryBalance.id.asc())
        )
        return tuple(self.session.execute(statement).scalars())

    def list_positive_balances_for_slot_ids(self, slot_ids: tuple[int, ...]) -> tuple[InventoryBalance, ...]:
        if not slot_ids:
            return ()
        statement = (
            select(InventoryBalance)
            .where(
                InventoryBalance.slot_id.in_(slot_ids),
                InventoryBalance.quantity > 0,
            )
            .order_by(InventoryBalance.slot_id.asc(), InventoryBalance.item_id.asc(), InventoryBalance.id.asc())
        )
        return tuple(self.session.execute(statement).scalars())

    def list_active_items_by_normalized_name(self, normalized_name: str) -> tuple[Item, ...]:
        statement = (
            select(Item)
            .where(Item.status == ItemStatus.ACTIVE)
            .order_by(Item.id.asc())
        )
        return tuple(
            item
            for item in self.session.execute(statement).scalars()
            if self._normalize_name(item.name) == normalized_name
        )

    def resolve_authoritative_replenish_item(
        self,
        *,
        normalized_name: str,
        slot_ids: tuple[int, ...],
    ) -> ReplenishItemResolution:
        candidates = self.list_active_items_by_normalized_name(normalized_name)
        if not candidates:
            return ReplenishItemResolution(
                item=None,
                matched_candidate_count=0,
                resolution_source="no_name_match",
            )
        if len(candidates) == 1:
            return ReplenishItemResolution(
                item=candidates[0],
                matched_candidate_count=1,
                resolution_source="single_name_match",
            )

        candidate_ids = tuple(item.id for item in candidates)
        active_binding_rows = self.session.execute(
            select(
                SlotItemBinding.slot_id,
                SlotItemBinding.item_id,
            ).where(
                SlotItemBinding.item_id.in_(candidate_ids),
                SlotItemBinding.is_active.is_(True),
            )
        ).all()
        positive_inventory_item_ids = {
            item_id
            for (item_id,) in self.session.execute(
                select(InventoryBalance.item_id)
                .where(
                    InventoryBalance.item_id.in_(candidate_ids),
                    InventoryBalance.quantity > 0,
                )
                .group_by(InventoryBalance.item_id)
            ).all()
        }

        selected_slot_binding_item_ids = {
            item_id
            for slot_id, item_id in active_binding_rows
            if slot_id in slot_ids
        }
        if len(selected_slot_binding_item_ids) == 1:
            resolved_item_id = next(iter(selected_slot_binding_item_ids))
            return ReplenishItemResolution(
                item=next(item for item in candidates if item.id == resolved_item_id),
                matched_candidate_count=len(candidates),
                resolution_source="selected_slot_active_binding",
            )

        active_binding_item_ids = {item_id for _, item_id in active_binding_rows}
        active_binding_with_positive_inventory_item_ids = active_binding_item_ids & positive_inventory_item_ids
        if len(active_binding_with_positive_inventory_item_ids) == 1:
            resolved_item_id = next(iter(active_binding_with_positive_inventory_item_ids))
            return ReplenishItemResolution(
                item=next(item for item in candidates if item.id == resolved_item_id),
                matched_candidate_count=len(candidates),
                resolution_source="machine_active_binding_with_positive_inventory",
            )

        if len(active_binding_item_ids) == 1:
            resolved_item_id = next(iter(active_binding_item_ids))
            return ReplenishItemResolution(
                item=next(item for item in candidates if item.id == resolved_item_id),
                matched_candidate_count=len(candidates),
                resolution_source="machine_active_binding",
            )

        return ReplenishItemResolution(
            item=None,
            matched_candidate_count=len(candidates),
            resolution_source="ambiguous_name_match",
        )

    def get_binding(self, *, slot_id: int, item_id: int, binding_type: BindingType) -> SlotItemBinding | None:
        statement = select(SlotItemBinding).where(
            SlotItemBinding.slot_id == slot_id,
            SlotItemBinding.item_id == item_id,
            SlotItemBinding.binding_type == binding_type,
        )
        return self.session.execute(statement).scalar_one_or_none()

    def add_binding(self, binding: SlotItemBinding) -> None:
        self.session.add(binding)

    def has_active_dispense_path(self, slot_id: int, item_id: int) -> bool:
        from app.persistence.models import Item

        statement = (
            select(SlotItemBinding.id)
            .join(
                Slot,
                Slot.id == SlotItemBinding.slot_id,
            )
            .join(
                Item,
                Item.id == SlotItemBinding.item_id,
            )
            .where(
                SlotItemBinding.slot_id == slot_id,
                SlotItemBinding.item_id == item_id,
                SlotItemBinding.is_active.is_(True),
                Slot.status == SlotStatus.ACTIVE,
                Slot.slot_type.in_((SlotType.UNIVERSAL, SlotType.DISPENSE)),
                Item.status == ItemStatus.ACTIVE,
            )
            .limit(1)
        )
        return self.session.execute(statement).scalar_one_or_none() is not None

    def list_available_dispense_options(self) -> tuple[AvailableDispenseOptionRecord, ...]:
        from app.persistence.models import Item

        statement = (
            select(
                InventoryBalance.slot_id,
                InventoryBalance.item_id,
                InventoryBalance.quantity,
                InventoryBalance.updated_at,
                Slot.code,
                Slot.drum_position,
                Slot.board_address,
                Slot.lock_number,
                Item.sku,
                Item.name,
                Item.unit,
            )
            .distinct()
            .join(Slot, Slot.id == InventoryBalance.slot_id)
            .join(Item, Item.id == InventoryBalance.item_id)
            .join(
                SlotItemBinding,
                and_(
                    SlotItemBinding.slot_id == InventoryBalance.slot_id,
                    SlotItemBinding.item_id == InventoryBalance.item_id,
                    SlotItemBinding.is_active.is_(True),
                ),
            )
            .where(
                InventoryBalance.quantity > 0,
                Slot.status == SlotStatus.ACTIVE,
                Slot.slot_type.in_((SlotType.UNIVERSAL, SlotType.DISPENSE)),
                Item.status == ItemStatus.ACTIVE,
            )
            .order_by(
                Item.name.asc(),
                Slot.drum_position.asc(),
                Slot.lock_number.asc(),
                InventoryBalance.slot_id.asc(),
                InventoryBalance.item_id.asc(),
            )
        )
        rows = self.session.execute(statement).all()
        return tuple(
            AvailableDispenseOptionRecord(
                slot_id=row[0],
                item_id=row[1],
                quantity=row[2],
                updated_at=row[3],
                slot_code=row[4],
                drum_position=row[5],
                board_address=row[6],
                lock_number=row[7],
                item_sku=row[8],
                item_name=row[9],
                item_unit=row[10],
            )
            for row in rows
        )

    def list_filled_balance_summaries(self) -> tuple[FilledBalanceSummaryRecord, ...]:
        from app.persistence.models import Item

        statement = (
            select(
                Item.name,
                func.sum(InventoryBalance.quantity),
            )
            .join(Item, Item.id == InventoryBalance.item_id)
            .where(InventoryBalance.quantity > 0)
            .group_by(Item.name)
            .order_by(Item.name.asc())
        )
        rows = self.session.execute(statement).all()
        return tuple(
            FilledBalanceSummaryRecord(
                item_name=item_name,
                quantity=int(quantity),
            )
            for item_name, quantity in rows
        )

    def resolve_available_dispense_option(self, item_id: int) -> AvailableDispenseOptionRecord | None:
        for option in self.list_available_dispense_options():
            if option.item_id == item_id:
                return option
        return None

    def find_preferred_binding_for_item(self, item_id: int) -> SlotItemBinding | None:
        statement = (
            select(SlotItemBinding)
            .where(
                SlotItemBinding.item_id == item_id,
                SlotItemBinding.is_active.is_(True),
                SlotItemBinding.binding_type.in_((BindingType.RETURN, BindingType.PRIMARY)),
            )
            .order_by(
                case(
                    (SlotItemBinding.binding_type == BindingType.RETURN, 0),
                    else_=1,
                ),
                SlotItemBinding.id.asc(),
            )
        )
        return self.session.execute(statement).scalars().first()

    def list_transactions(self, operation_id: int | None = None) -> list[InventoryTransaction]:
        statement = select(InventoryTransaction).order_by(InventoryTransaction.id.asc())
        if operation_id is not None:
            statement = statement.where(InventoryTransaction.operation_id == operation_id)
        return list(self.session.execute(statement).scalars())
