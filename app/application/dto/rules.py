from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.enums import OperationType


@dataclass(frozen=True, slots=True)
class RuleResultDTO:
    code: str
    passed: bool
    message: str
    context: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RuleEvaluationDTO:
    allowed: bool
    operation_type: OperationType
    user_id: int | None = None
    operator_user_id: int | None = None
    item_id: int | None = None
    slot_id: int | None = None
    session_id: int | None = None
    resolved_slot_id: int | None = None
    reason_codes: tuple[str, ...] = ()
    summary_message: str = ""
    rules: tuple[RuleResultDTO, ...] = ()
