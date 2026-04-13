from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, case, select

from app.domain.enums import BindingType, ItemStatus, SlotStatus, SlotType
from app.persistence.models import InventoryBalance, InventoryTransaction, Slot, SlotItemBinding
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


class InventoryRepository(Repository):
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
