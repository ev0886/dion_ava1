from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class AuditLogQueryFilters:
    entity_type: str | None = None
    actor_user_id: int | None = None
    limit: int = 100


@dataclass(frozen=True, slots=True)
class AuditLogEntryDTO:
    audit_log_id: int
    entity_type: str
    entity_id: str
    action: str
    actor_user_id: int | None
    reason_code: str | None
    comment: str | None
    before: dict[str, object]
    after: dict[str, object]
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class EventLogQueryFilters:
    event_type: str | None = None
    level: str | None = None
    limit: int = 100


@dataclass(frozen=True, slots=True)
class EventLogEntryDTO:
    event_log_id: int
    event_type: str
    level: str
    source: str
    operation_id: int | None
    session_id: int | None
    user_id: int | None
    slot_id: int | None
    item_id: int | None
    qty: float | None
    result: str | None
    comment: str | None
    message: str | None
    payload: dict[str, object]
    created_at: datetime | None
