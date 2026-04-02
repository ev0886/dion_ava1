from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class RfidBindingResultDTO:
    user_id: int
    actor_user_id: int
    card_uid: str | None
    previous_card_uid: str | None
    action: str
    active_card_count: int
    issued_at: datetime | None
    revoked_at: datetime | None
    comment: str | None
