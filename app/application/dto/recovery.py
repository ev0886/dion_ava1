from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from app.domain.enums import RecoveryClassification, RecoveryStatus

ReconciliationOutcome = Literal[
    "no_action_needed",
    "inventory_write_likely_missing",
    "manual_review_required",
    "operation_likely_failed_before_inventory_mutation",
]

ManualResolutionActionCategory = Literal[
    "review_operation_history",
    "verify_inventory_records",
    "confirm_physical_state",
    "decide_case_closure",
]


@dataclass(frozen=True, slots=True)
class RecoveryCaseDTO:
    recovery_case_id: int | None
    classification: RecoveryClassification
    status: RecoveryStatus
    summary: str
    context: dict[str, object]
    created_at: datetime | None
    resolved_at: datetime | None


@dataclass(frozen=True, slots=True)
class RecoveryCaseQueryFilters:
    status: RecoveryStatus | None = None
    classification: RecoveryClassification | None = None
    limit: int = 100


@dataclass(frozen=True, slots=True)
class RecoveryScanResult:
    open_case_count: int
    open_cases: tuple[RecoveryCaseDTO, ...]
    unfinished_operation_ids: tuple[int, ...]
    candidate_operation_ids: tuple[int, ...] = ()
    candidates: tuple["RecoveryCandidateDTO", ...] = ()


@dataclass(frozen=True, slots=True)
class RecoveryContextDTO:
    recovery_case_id: int
    summary: str
    context: dict[str, object]


@dataclass(frozen=True, slots=True)
class RecoveryCandidateDTO:
    operation_id: int
    detected_state: str
    classification: RecoveryClassification
    reconciliation_outcome: ReconciliationOutcome
    recovery_case_id: int
    reused_existing_case: bool


@dataclass(frozen=True, slots=True)
class ReconciliationResultDTO:
    operation_id: int
    operation_state: str
    inventory_transaction_count: int
    inventory_transaction_ids: tuple[int, ...]
    outcome: ReconciliationOutcome
    reason: str


@dataclass(frozen=True, slots=True)
class RecoveryCaseEntityDTO:
    entity_type: str
    entity_id: str
    role: str
    decision_outcome: str | None


@dataclass(frozen=True, slots=True)
class RecoveryActionDTO:
    action_type: str
    status: str
    comment: str | None
    context: dict[str, object]
    created_at: datetime | None


@dataclass(frozen=True, slots=True)
class RecoveryCaseDetailDTO:
    recovery_case_id: int
    classification: RecoveryClassification
    status: RecoveryStatus
    summary: str
    context: dict[str, object]
    created_at: datetime | None
    resolved_at: datetime | None
    impacted_entities: tuple[RecoveryCaseEntityDTO, ...]
    recovery_actions: tuple[RecoveryActionDTO, ...]


@dataclass(frozen=True, slots=True)
class ManualResolutionPreparationDTO:
    recovery_case_id: int
    classification: RecoveryClassification
    status: RecoveryStatus
    summary: str
    impacted_entities: tuple[RecoveryCaseEntityDTO, ...]
    recovery_actions: tuple[RecoveryActionDTO, ...]
    recommended_next_action_categories: tuple[ManualResolutionActionCategory, ...]
    context: dict[str, object]
