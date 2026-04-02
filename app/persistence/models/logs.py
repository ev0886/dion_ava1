from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.persistence.base import Base, CreatedAtMixin, PrimaryKeyMixin


class EventLog(PrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "event_logs"

    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    operation_id: Mapped[int | None] = mapped_column(ForeignKey("operations.id"), nullable=True, index=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("operation_sessions.id"), nullable=True, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    slot_id: Mapped[int | None] = mapped_column(ForeignKey("slots.id"), nullable=True, index=True)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("items.id"), nullable=True, index=True)
    qty: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    result: Mapped[str | None] = mapped_column(String(100), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)


class AuditLog(PrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "audit_logs"

    entity_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    reason_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    before_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
