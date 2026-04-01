from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import InventoryTransactionType
from app.persistence.base import Base, PrimaryKeyMixin
from app.persistence.types import enum_column


class InventoryTransaction(PrimaryKeyMixin, Base):
    __tablename__ = "inventory_transactions"

    slot_id: Mapped[int] = mapped_column(ForeignKey("slots.id"), nullable=False, index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False, index=True)
    operation_id: Mapped[int | None] = mapped_column(ForeignKey("operations.id"), nullable=True, index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("operation_sessions.id"), nullable=True, index=True)
    transaction_type: Mapped[InventoryTransactionType] = enum_column(InventoryTransactionType, index=True)
    quantity_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_before: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_after: Mapped[int] = mapped_column(Integer, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
