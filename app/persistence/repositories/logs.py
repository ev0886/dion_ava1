from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import select

from app.persistence.models import AuditLog, EventLog
from app.persistence.repositories.base import Repository


class EventLogRepository(Repository):
    def add(self, event_log: EventLog) -> None:
        self.session.add(event_log)

    def list_recent(self, *, limit: int = 100) -> list[EventLog]:
        statement = select(EventLog).order_by(EventLog.id.desc()).limit(limit)
        return list(self.session.execute(statement).scalars())

    def list_data_exchange_events(self, *, date_from: date, date_to: date) -> list[EventLog]:
        range_start = datetime.combine(date_from, time.min)
        range_end = datetime.combine(date_to + timedelta(days=1), time.min)
        statement = (
            select(EventLog)
            .where(EventLog.source == "admin_touch_usb")
            .where(EventLog.created_at >= range_start)
            .where(EventLog.created_at < range_end)
            .order_by(EventLog.created_at.asc(), EventLog.id.asc())
        )
        return list(self.session.execute(statement).scalars())


class AuditLogRepository(Repository):
    def add(self, audit_log: AuditLog) -> None:
        self.session.add(audit_log)

    def list_recent(self, *, limit: int = 100) -> list[AuditLog]:
        statement = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
        return list(self.session.execute(statement).scalars())
