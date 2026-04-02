from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import OperationState, OperationType, SessionStatus, SessionType
from app.persistence.base import Base, CreatedAtMixin, PrimaryKeyMixin
from app.persistence.types import enum_column


class OperationSession(PrimaryKeyMixin, Base):
    __tablename__ = "operation_sessions"

    session_type: Mapped[SessionType] = enum_column(SessionType, index=True)
    status: Mapped[SessionStatus] = enum_column(SessionStatus, index=True)
    started_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)


class Operation(PrimaryKeyMixin, Base):
    __tablename__ = "operations"

    session_id: Mapped[int | None] = mapped_column(ForeignKey("operation_sessions.id"), nullable=True, index=True)
    operation_type: Mapped[OperationType] = enum_column(OperationType, index=True)
    operation_state: Mapped[OperationState] = enum_column(OperationState, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"), nullable=True, index=True)
    slot_id: Mapped[int | None] = mapped_column(ForeignKey("slots.id"), nullable=True, index=True)
    qty_requested: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    qty_confirmed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    hardware_context_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    business_context_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)


class OperationStateHistory(PrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "operation_state_history"

    operation_id: Mapped[int] = mapped_column(ForeignKey("operations.id"), nullable=False, index=True)
    state: Mapped[OperationState] = enum_column(OperationState, index=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
