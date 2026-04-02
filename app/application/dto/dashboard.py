from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.enums import ItemStatus, OperationState, OperationType, RecoveryClassification, RecoveryStatus, SlotStatus


@dataclass(frozen=True, slots=True)
class DashboardSummaryDTO:
    generated_at: datetime
    recent_window_days: int
    total_users: int
    active_users: int
    blocked_users: int
    total_items: int
    active_items: int
    total_slots: int
    active_slots: int
    low_stock_item_count: int
    low_stock_slot_count: int
    open_recovery_case_count: int
    unfinished_operation_count: int
    recent_problem_operation_count: int


@dataclass(frozen=True, slots=True)
class LowStockEntryDTO:
    slot_id: int
    slot_code: str
    slot_status: SlotStatus
    item_id: int
    item_sku: str
    item_name: str
    item_status: ItemStatus
    quantity: int
    min_level: int
    shortage: int


@dataclass(frozen=True, slots=True)
class LowStockOverviewDTO:
    generated_at: datetime
    limit: int
    low_stock_only: bool
    total_count: int
    entries: tuple[LowStockEntryDTO, ...]


@dataclass(frozen=True, slots=True)
class RecoveryOverviewEntryDTO:
    recovery_case_id: int
    classification: RecoveryClassification
    status: RecoveryStatus
    summary: str
    operation_id: int | None
    created_at: datetime | None
    resolved_at: datetime | None


@dataclass(frozen=True, slots=True)
class RecoveryOverviewDTO:
    generated_at: datetime
    limit: int
    total_open_count: int
    entries: tuple[RecoveryOverviewEntryDTO, ...]


@dataclass(frozen=True, slots=True)
class RecentOperationEntryDTO:
    operation_id: int
    operation_type: OperationType
    operation_state: OperationState
    user_id: int | None
    item_id: int | None
    slot_id: int | None
    qty_requested: int
    qty_confirmed: int | None
    result: str | None
    error_code: str | None
    started_at: datetime | None
    finished_at: datetime | None


@dataclass(frozen=True, slots=True)
class RecentOperationsOverviewDTO:
    generated_at: datetime
    limit: int
    recent_window_days: int
    total_count: int
    entries: tuple[RecentOperationEntryDTO, ...]


@dataclass(frozen=True, slots=True)
class RecentActivityEntryDTO:
    activity_kind: str
    created_at: datetime
    summary: str
    source: str
    operation_id: int | None
    user_id: int | None
    item_id: int | None
    slot_id: int | None


@dataclass(frozen=True, slots=True)
class RecentActivityOverviewDTO:
    generated_at: datetime
    limit: int
    recent_window_days: int
    total_count: int
    entries: tuple[RecentActivityEntryDTO, ...]
