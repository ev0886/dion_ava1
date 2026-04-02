from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import case, distinct, func, select

from app.domain.enums import BindingType, ItemStatus, SlotStatus
from app.persistence.models import InventoryBalance, InventoryTransaction, Item, Slot, SlotItemBinding
from app.persistence.repositories.base import Repository


@dataclass(frozen=True, slots=True)
class InventoryDashboardRecord:
    slot_id: int
    slot_code: str
    slot_status: SlotStatus
    item_id: int
    item_sku: str
    item_name: str
    item_status: ItemStatus
    quantity: int
    min_level: int


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

    def get_dashboard_counts(self) -> dict[str, int]:
        total_items = self.session.execute(select(func.count(Item.id))).scalar_one()
        active_items = self.session.execute(
            select(func.count(Item.id)).where(Item.status == ItemStatus.ACTIVE)
        ).scalar_one()
        total_slots = self.session.execute(select(func.count(Slot.id))).scalar_one()
        active_slots = self.session.execute(
            select(func.count(Slot.id)).where(Slot.status == SlotStatus.ACTIVE)
        ).scalar_one()
        return {
            "total_items": int(total_items),
            "active_items": int(active_items),
            "total_slots": int(total_slots),
            "active_slots": int(active_slots),
        }

    def get_low_stock_counts(self) -> dict[str, int]:
        low_stock_pairs = self._monitored_inventory_statement(low_stock_only=True).subquery()
        statement = select(
            func.count(distinct(low_stock_pairs.c.item_id)),
            func.count(distinct(low_stock_pairs.c.slot_id)),
        )
        item_count, slot_count = self.session.execute(statement).one()
        return {
            "low_stock_item_count": int(item_count or 0),
            "low_stock_slot_count": int(slot_count or 0),
        }

    def list_low_stock_records(
        self,
        *,
        limit: int,
        low_stock_only: bool,
    ) -> tuple[list[InventoryDashboardRecord], int]:
        statement = self._monitored_inventory_statement(low_stock_only=low_stock_only)
        total_count = int(self.session.execute(select(func.count()).select_from(statement.subquery())).scalar_one())
        rows = self.session.execute(statement.limit(limit)).all()
        records = [
            InventoryDashboardRecord(
                slot_id=row.slot_id,
                slot_code=row.slot_code,
                slot_status=row.slot_status,
                item_id=row.item_id,
                item_sku=row.item_sku,
                item_name=row.item_name,
                item_status=row.item_status,
                quantity=int(row.quantity),
                min_level=int(row.min_level),
            )
            for row in rows
        ]
        return (records, total_count)

    def _monitored_inventory_statement(self, *, low_stock_only: bool):
        active_bindings = (
            select(
                SlotItemBinding.slot_id.label("slot_id"),
                SlotItemBinding.item_id.label("item_id"),
            )
            .where(SlotItemBinding.is_active.is_(True))
            .distinct()
            .subquery()
        )
        quantity = func.coalesce(InventoryBalance.quantity, 0)
        shortage = Item.min_level - quantity
        statement = (
            select(
                active_bindings.c.slot_id,
                active_bindings.c.item_id,
                Slot.code.label("slot_code"),
                Slot.status.label("slot_status"),
                Item.sku.label("item_sku"),
                Item.name.label("item_name"),
                Item.status.label("item_status"),
                quantity.label("quantity"),
                Item.min_level.label("min_level"),
            )
            .join(Slot, Slot.id == active_bindings.c.slot_id)
            .join(Item, Item.id == active_bindings.c.item_id)
            .outerjoin(
                InventoryBalance,
                (InventoryBalance.slot_id == active_bindings.c.slot_id)
                & (InventoryBalance.item_id == active_bindings.c.item_id),
            )
            .where(
                Slot.status == SlotStatus.ACTIVE,
                Item.status == ItemStatus.ACTIVE,
            )
            .order_by(shortage.desc(), Slot.id.asc(), Item.id.asc())
        )
        if low_stock_only:
            statement = statement.where(quantity <= Item.min_level)
        return statement
