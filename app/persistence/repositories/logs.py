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

    def list_recent_since(self, *, limit: int, created_since: datetime) -> list[EventLog]:
        statement = (
            select(EventLog)
            .where(EventLog.created_at >= created_since)
            .order_by(EventLog.created_at.desc(), EventLog.id.desc())
            .limit(limit)
        )
        return list(self.session.execute(statement).scalars())


class AuditLogRepository(Repository):
    def add(self, audit_log: AuditLog) -> None:
        self.session.add(audit_log)

    def list_recent(self, *, limit: int = 100) -> list[AuditLog]:
        statement = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
        return list(self.session.execute(statement).scalars())

    def list_recent_since(self, *, limit: int, created_since: datetime) -> list[AuditLog]:
        statement = (
            select(AuditLog)
            .where(AuditLog.created_at >= created_since)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
        )
        return list(self.session.execute(statement).scalars())
