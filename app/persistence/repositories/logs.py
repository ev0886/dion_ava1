from __future__ import annotations

from sqlalchemy import select

from app.persistence.models import AuditLog, EventLog
from app.persistence.repositories.base import Repository


class EventLogRepository(Repository):
    def add(self, event_log: EventLog) -> None:
        self.session.add(event_log)

    def list_recent(self, *, limit: int = 100) -> list[EventLog]:
        statement = select(EventLog).order_by(EventLog.id.desc()).limit(limit)
        return list(self.session.execute(statement).scalars())

    def list_recent_filtered(
        self,
        *,
        event_type: str | None = None,
        level: str | None = None,
        limit: int = 100,
    ) -> list[EventLog]:
        statement = select(EventLog)
        if event_type is not None:
            statement = statement.where(EventLog.event_type == event_type)
        if level is not None:
            statement = statement.where(EventLog.level == level)
        statement = statement.order_by(EventLog.id.desc()).limit(limit)
        return list(self.session.execute(statement).scalars())


class AuditLogRepository(Repository):
    def add(self, audit_log: AuditLog) -> None:
        self.session.add(audit_log)

    def list_recent(self, *, limit: int = 100) -> list[AuditLog]:
        statement = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
        return list(self.session.execute(statement).scalars())

    def list_recent_filtered(
        self,
        *,
        entity_type: str | None = None,
        actor_user_id: int | None = None,
        limit: int = 100,
    ) -> list[AuditLog]:
        statement = select(AuditLog)
        if entity_type is not None:
            statement = statement.where(AuditLog.entity_type == entity_type)
        if actor_user_id is not None:
            statement = statement.where(AuditLog.actor_user_id == actor_user_id)
        statement = statement.order_by(AuditLog.id.desc()).limit(limit)
        return list(self.session.execute(statement).scalars())
