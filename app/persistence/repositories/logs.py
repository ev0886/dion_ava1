from __future__ import annotations

from sqlalchemy import or_, select

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
        limit: int = 100,
        levels: tuple[str, ...] = (),
        event_types: tuple[str, ...] = (),
        results: tuple[str, ...] = (),
    ) -> list[EventLog]:
        statement = select(EventLog)
        predicates = []
        if levels:
            predicates.append(EventLog.level.in_(levels))
        if event_types:
            predicates.append(EventLog.event_type.in_(event_types))
        if results:
            predicates.append(EventLog.result.in_(results))
        if predicates:
            statement = statement.where(or_(*predicates))
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
        limit: int = 100,
        actions: tuple[str, ...] = (),
        reason_codes: tuple[str, ...] = (),
    ) -> list[AuditLog]:
        statement = select(AuditLog)
        predicates = []
        if actions:
            predicates.append(AuditLog.action.in_(actions))
        if reason_codes:
            predicates.append(AuditLog.reason_code.in_(reason_codes))
        if predicates:
            statement = statement.where(or_(*predicates))
        statement = statement.order_by(AuditLog.id.desc()).limit(limit)
        return list(self.session.execute(statement).scalars())
