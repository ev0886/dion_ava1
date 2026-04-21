from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import BindingType, ItemStatus, SlotStatus, SlotType
from app.persistence.base import Base, PrimaryKeyMixin, UpdatedAtMixin
from app.persistence.types import enum_column


class ItemGroup(PrimaryKeyMixin, Base):
    __tablename__ = "item_groups"

    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")


class NomenclatureEntry(PrimaryKeyMixin, Base):
    __tablename__ = "nomenclature_entries"
    __table_args__ = (UniqueConstraint("normalized_name", name="uq_nomenclature_entries_normalized_name"),)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")


class Item(PrimaryKeyMixin, Base):
    __tablename__ = "items"

    item_group_id: Mapped[int | None] = mapped_column(ForeignKey("item_groups.id"), nullable=True, index=True)
    sku: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    return_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    min_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[ItemStatus] = enum_column(ItemStatus, index=True)


class Slot(PrimaryKeyMixin, Base):
    __tablename__ = "slots"

    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    slot_type: Mapped[SlotType] = enum_column(SlotType, index=True)
    drum_position: Mapped[int] = mapped_column(Integer, nullable=False)
    board_address: Mapped[int] = mapped_column(Integer, nullable=False)
    lock_number: Mapped[int] = mapped_column(Integer, nullable=False)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[SlotStatus] = enum_column(SlotStatus, index=True)


class SlotItemBinding(PrimaryKeyMixin, Base):
    __tablename__ = "slot_item_bindings"
    __table_args__ = (
        UniqueConstraint("slot_id", "item_id", "binding_type", name="uq_slot_item_bindings_slot_item_binding"),
    )

    slot_id: Mapped[int] = mapped_column(ForeignKey("slots.id"), nullable=False, index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False, index=True)
    binding_type: Mapped[BindingType] = enum_column(BindingType, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)


class Permission(PrimaryKeyMixin, Base):
    __tablename__ = "permissions"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"), nullable=True, index=True)
    item_group_id: Mapped[int | None] = mapped_column(ForeignKey("item_groups.id"), nullable=True, index=True)
    can_dispense: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    can_return: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class InventoryBalance(PrimaryKeyMixin, UpdatedAtMixin, Base):
    __tablename__ = "inventory_balances"
    __table_args__ = (UniqueConstraint("slot_id", "item_id", name="uq_inventory_balances_slot_item"),)

    slot_id: Mapped[int] = mapped_column(ForeignKey("slots.id"), nullable=False, index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
