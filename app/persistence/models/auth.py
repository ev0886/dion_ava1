from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import RoleCode, UserStatus
from app.persistence.base import Base, CreatedAtMixin, PrimaryKeyMixin, UpdatedAtMixin
from app.persistence.types import enum_column


class Role(PrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "roles"

    code: Mapped[RoleCode] = enum_column(RoleCode, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class User(PrimaryKeyMixin, CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "users"

    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False, index=True)
    user_code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[UserStatus] = enum_column(UserStatus, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")


class UserCredential(PrimaryKeyMixin, UpdatedAtMixin, Base):
    __tablename__ = "user_credentials"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, unique=True, index=True)
    pin_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    pin_salt: Mapped[str] = mapped_column(String(255), nullable=False)
    pin_algorithm: Mapped[str] = mapped_column(String(50), nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)


class UserRfidCard(PrimaryKeyMixin, Base):
    __tablename__ = "user_rfid_cards"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    card_uid: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
