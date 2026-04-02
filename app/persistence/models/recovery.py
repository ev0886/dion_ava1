from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import RecoveryActionStatus, RecoveryClassification, RecoveryStatus
from app.persistence.base import Base, CreatedAtMixin, PrimaryKeyMixin
from app.persistence.types import enum_column


class RecoveryCase(PrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "recovery_cases"

    classification: Mapped[RecoveryClassification] = enum_column(RecoveryClassification, index=True)
    status: Mapped[RecoveryStatus] = enum_column(RecoveryStatus, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    context_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)


class RecoveryCaseEntity(PrimaryKeyMixin, Base):
    __tablename__ = "recovery_case_entities"

    recovery_case_id: Mapped[int] = mapped_column(ForeignKey("recovery_cases.id"), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(100), nullable=False)
    decision_outcome: Mapped[str | None] = mapped_column(String(100), nullable=True)


class RecoveryAction(PrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "recovery_actions"

    recovery_case_id: Mapped[int] = mapped_column(ForeignKey("recovery_cases.id"), nullable=False, index=True)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[RecoveryActionStatus] = enum_column(RecoveryActionStatus, index=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)


class ManualResolutionAction(PrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "manual_resolution_actions"

    recovery_case_id: Mapped[int] = mapped_column(ForeignKey("recovery_cases.id"), nullable=False, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
