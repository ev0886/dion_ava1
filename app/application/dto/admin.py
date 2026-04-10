from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import DispenseRestrictionPolicy, RoleCode, UserStatus


@dataclass(frozen=True, slots=True)
class AdminUserRecordDTO:
    user_id: int
    user_code: str
    full_name: str
    status: UserStatus
    is_active: bool
    role_code: RoleCode | None
    rfid_uid: str | None
    dispense_restriction_policy: DispenseRestrictionPolicy
