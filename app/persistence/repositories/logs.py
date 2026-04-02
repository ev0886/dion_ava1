from __future__ import annotations

from datetime import datetime

from sqlalchemy import select

from app.persistence.models import AuditLog, EventLog
from app.persistence.repositories.base import Repository


class EventLogRepository(Repository):
    def add(self, event_log: EventLog) -> None:
        self.session.add(event_log)

    def list_recent(self, *, limit: int = 100) -> list[EventLog]:
        statement = select(EventLog).order_by(EventLog.id.desc()).limit(limit)
        return list(self.session.execute(statement).scalars())

    def list_for_report(
        self,
        *,
        limit: int | None = None,
        event_type: str | None = None,
        level: str | None = None,
        slot_id: int | None = None,
        item_id: int | None = None,
        user_id: int | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> list[EventLog]:
        statement = select(EventLog).order_by(EventLog.id.asc())
        if event_type is not None:
            statement = statement.where(EventLog.event_type == event_type)
        if level is not None:
            statement = statement.where(EventLog.level == level)
        if slot_id is not None:
            statement = statement.where(EventLog.slot_id == slot_id)
        if item_id is not None:
            statement = statement.where(EventLog.item_id == item_id)
        if user_id is not None:
            statement = statement.where(EventLog.user_id == user_id)
        if created_from is not None:
            statement = statement.where(EventLog.created_at >= created_from)
        if created_to is not None:
            statement = statement.where(EventLog.created_at <= created_to)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.execute(statement).scalars())


class AuditLogRepository(Repository):
    def add(self, audit_log: AuditLog) -> None:
        self.session.add(audit_log)

    def list_recent(self, *, limit: int = 100) -> list[AuditLog]:
        statement = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
        return list(self.session.execute(statement).scalars())

    def list_for_report(
        self,
        *,
        limit: int | None = None,
        entity_type: str | None = None,
        actor_user_id: int | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> list[AuditLog]:
        statement = select(AuditLog).order_by(AuditLog.id.asc())
        if entity_type is not None:
            statement = statement.where(AuditLog.entity_type == entity_type)
        if actor_user_id is not None:
            statement = statement.where(AuditLog.actor_user_id == actor_user_id)
        if created_from is not None:
            statement = statement.where(AuditLog.created_at >= created_from)
        if created_to is not None:
            statement = statement.where(AuditLog.created_at <= created_to)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.execute(statement).scalars())
