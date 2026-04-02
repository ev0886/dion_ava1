from __future__ import annotations

from app.persistence.models import AuditLog
from app.persistence.repositories.logs import AuditLogRepository


def record_audit(
    repository: AuditLogRepository,
    *,
    entity_type: str,
    entity_id: str,
    action: str,
    actor_user_id: int | None,
    comment: str | None,
    before: dict[str, object] | None,
    after: dict[str, object] | None,
) -> None:
    repository.add(
        AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_user_id=actor_user_id,
            reason_code=None,
            comment=comment,
            before_json=before,
            after_json=after,
        )
    )
