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


class AuditLogRepository(Repository):
    def add(self, audit_log: AuditLog) -> None:
        self.session.add(audit_log)

    def list_recent(self, *, limit: int = 100) -> list[AuditLog]:
        statement = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
        return list(self.session.execute(statement).scalars())
