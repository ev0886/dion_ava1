from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from app.persistence.models import AuditLog, EventLog
from app.persistence.repositories.base import Repository


class EventLogRepository(Repository):
    def add(self, event_log: EventLog) -> None:
        self.session.add(event_log)

    def list_recent(self, *, limit: int = 100) -> list[EventLog]:
        statement = select(EventLog).order_by(EventLog.id.desc()).limit(limit)
        return list(self.session.execute(statement).scalars())

    def list_events(
        self,
        *,
        limit: int,
        offset: int,
        event_type: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> list[EventLog]:
        statement = select(EventLog).order_by(EventLog.id.desc()).limit(limit).offset(offset)
        if event_type is not None:
            statement = statement.where(EventLog.event_type == event_type)
        if created_from is not None:
            statement = statement.where(EventLog.created_at >= created_from)
        if created_to is not None:
            statement = statement.where(EventLog.created_at <= created_to)
        return list(self.session.execute(statement).scalars())

    def count_events(
        self,
        *,
        event_type: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> int:
        statement = select(func.count()).select_from(EventLog)
        if event_type is not None:
            statement = statement.where(EventLog.event_type == event_type)
        if created_from is not None:
            statement = statement.where(EventLog.created_at >= created_from)
        if created_to is not None:
            statement = statement.where(EventLog.created_at <= created_to)
        return int(self.session.execute(statement).scalar_one())


class AuditLogRepository(Repository):
    def add(self, audit_log: AuditLog) -> None:
        self.session.add(audit_log)

    def list_recent(self, *, limit: int = 100) -> list[AuditLog]:
        statement = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
        return list(self.session.execute(statement).scalars())

    def list_audit_logs(
        self,
        *,
        limit: int,
        offset: int,
        entity_type: str | None = None,
        action: str | None = None,
        reason_code: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> list[AuditLog]:
        statement = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit).offset(offset)
        if entity_type is not None:
            statement = statement.where(AuditLog.entity_type == entity_type)
        if action is not None:
            statement = statement.where(AuditLog.action == action)
        if reason_code is not None:
            statement = statement.where(AuditLog.reason_code == reason_code)
        if created_from is not None:
            statement = statement.where(AuditLog.created_at >= created_from)
        if created_to is not None:
            statement = statement.where(AuditLog.created_at <= created_to)
        return list(self.session.execute(statement).scalars())

    def count_audit_logs(
        self,
        *,
        entity_type: str | None = None,
        action: str | None = None,
        reason_code: str | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> int:
        statement = select(func.count()).select_from(AuditLog)
        if entity_type is not None:
            statement = statement.where(AuditLog.entity_type == entity_type)
        if action is not None:
            statement = statement.where(AuditLog.action == action)
        if reason_code is not None:
            statement = statement.where(AuditLog.reason_code == reason_code)
        if created_from is not None:
            statement = statement.where(AuditLog.created_at >= created_from)
        if created_to is not None:
            statement = statement.where(AuditLog.created_at <= created_to)
        return int(self.session.execute(statement).scalar_one())
