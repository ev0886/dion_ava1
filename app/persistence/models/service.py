from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.domain.enums import BackupStatus, ExportStatus, HardwareEndpointStatus, HardwareEndpointType
from app.persistence.base import Base, CreatedAtMixin, PrimaryKeyMixin, UpdatedAtMixin
from app.persistence.types import enum_column


class SystemSetting(PrimaryKeyMixin, UpdatedAtMixin, Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    value_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class HardwareEndpoint(PrimaryKeyMixin, Base):
    __tablename__ = "hardware_endpoints"

    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    endpoint_type: Mapped[HardwareEndpointType] = enum_column(HardwareEndpointType, index=True)
    connection_string: Mapped[str] = mapped_column(String(255), nullable=False)
    driver_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[HardwareEndpointStatus] = enum_column(HardwareEndpointStatus, index=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")
    settings_json: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)


class Export(PrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "exports"

    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    export_type: Mapped[str] = mapped_column(String(100), nullable=False)
    destination_type: Mapped[str] = mapped_column(String(100), nullable=False)
    destination_path: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[ExportStatus] = enum_column(ExportStatus, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class Backup(PrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "backups"

    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    backup_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_path: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[BackupStatus] = enum_column(BackupStatus, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
