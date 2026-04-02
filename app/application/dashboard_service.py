from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import ClassVar

from app.application.dto.dashboard import (
    DashboardSummaryDTO,
    LowStockEntryDTO,
    LowStockOverviewDTO,
    RecentActivityEntryDTO,
    RecentActivityOverviewDTO,
    RecentOperationEntryDTO,
    RecentOperationsOverviewDTO,
    RecoveryOverviewDTO,
    RecoveryOverviewEntryDTO,
)
from app.application.exceptions import ValidationError
from app.application.time import utc_now
from app.persistence.models import AuditLog, EventLog
from app.persistence.repositories.inventory import InventoryDashboardRecord, InventoryRepository
from app.persistence.repositories.logs import AuditLogRepository, EventLogRepository
from app.persistence.repositories.operations import OperationDashboardRecord, OperationRepository
from app.persistence.repositories.recovery import RecoveryRepository
from app.persistence.repositories.users import UserRepository


@dataclass(slots=True)
class DashboardService:
    user_repository: UserRepository
    inventory_repository: InventoryRepository
    operation_repository: OperationRepository
    recovery_repository: RecoveryRepository
    event_log_repository: EventLogRepository
    audit_log_repository: AuditLogRepository

    _DEFAULT_LIMIT: ClassVar[int] = 10
    _MAX_LIMIT: ClassVar[int] = 50
    _DEFAULT_WINDOW_DAYS: ClassVar[int] = 7
    _MAX_WINDOW_DAYS: ClassVar[int] = 30

    def get_summary(self, *, recent_window_days: int = _DEFAULT_WINDOW_DAYS) -> DashboardSummaryDTO:
        window_days = self._normalize_recent_window_days(recent_window_days)
        window_start = utc_now() - timedelta(days=window_days)
        user_counts = self.user_repository.get_dashboard_counts()
        inventory_counts = self.inventory_repository.get_dashboard_counts()
        low_stock_counts = self.inventory_repository.get_low_stock_counts()
        return DashboardSummaryDTO(
            generated_at=utc_now(),
            recent_window_days=window_days,
            total_users=user_counts["total_users"],
            active_users=user_counts["active_users"],
            blocked_users=user_counts["blocked_users"],
            total_items=inventory_counts["total_items"],
            active_items=inventory_counts["active_items"],
            total_slots=inventory_counts["total_slots"],
            active_slots=inventory_counts["active_slots"],
            low_stock_item_count=low_stock_counts["low_stock_item_count"],
            low_stock_slot_count=low_stock_counts["low_stock_slot_count"],
            open_recovery_case_count=self.recovery_repository.count_open_cases(),
            unfinished_operation_count=self.operation_repository.count_unfinished(),
            recent_problem_operation_count=self.operation_repository.count_recent_problem_operations(window_start),
        )

    def get_low_stock_overview(
        self,
        *,
        limit: int = _DEFAULT_LIMIT,
        low_stock_only: bool = True,
    ) -> LowStockOverviewDTO:
        normalized_limit = self._normalize_limit(limit)
        records, total_count = self.inventory_repository.list_low_stock_records(
            limit=normalized_limit,
            low_stock_only=low_stock_only,
        )
        return LowStockOverviewDTO(
            generated_at=utc_now(),
            limit=normalized_limit,
            low_stock_only=low_stock_only,
            total_count=total_count,
            entries=tuple(self._to_low_stock_entry(record) for record in records),
        )

    def get_recovery_overview(self, *, limit: int = _DEFAULT_LIMIT) -> RecoveryOverviewDTO:
        normalized_limit = self._normalize_limit(limit)
        cases = self.recovery_repository.list_recent_open_cases(limit=normalized_limit)
        return RecoveryOverviewDTO(
            generated_at=utc_now(),
            limit=normalized_limit,
            total_open_count=self.recovery_repository.count_open_cases(),
            entries=tuple(
                RecoveryOverviewEntryDTO(
                    recovery_case_id=case.id,
                    classification=case.classification,
                    status=case.status,
                    summary=case.summary,
                    operation_id=self._context_int(case.context_json, "operation_id"),
                    created_at=case.created_at,
                    resolved_at=case.resolved_at,
                )
                for case in cases
            ),
        )

    def get_recent_operations(
        self,
        *,
        limit: int = _DEFAULT_LIMIT,
        recent_window_days: int = _DEFAULT_WINDOW_DAYS,
    ) -> RecentOperationsOverviewDTO:
        normalized_limit = self._normalize_limit(limit)
        window_days = self._normalize_recent_window_days(recent_window_days)
        window_start = utc_now() - timedelta(days=window_days)
        records, total_count = self.operation_repository.list_recent_dashboard_operations(
            limit=normalized_limit,
            window_start=window_start,
        )
        return RecentOperationsOverviewDTO(
            generated_at=utc_now(),
            limit=normalized_limit,
            recent_window_days=window_days,
            total_count=total_count,
            entries=tuple(self._to_recent_operation_entry(record) for record in records),
        )

    def get_recent_activity(
        self,
        *,
        limit: int = _DEFAULT_LIMIT,
        recent_window_days: int = _DEFAULT_WINDOW_DAYS,
    ) -> RecentActivityOverviewDTO:
        normalized_limit = self._normalize_limit(limit)
        window_days = self._normalize_recent_window_days(recent_window_days)
        window_start = utc_now() - timedelta(days=window_days)
        event_logs = self.event_log_repository.list_recent_since(limit=normalized_limit, created_since=window_start)
        audit_logs = self.audit_log_repository.list_recent_since(limit=normalized_limit, created_since=window_start)
        merged = [
            *(self._to_event_activity(log) for log in event_logs),
            *(self._to_audit_activity(log) for log in audit_logs),
        ]
        merged.sort(key=lambda entry: (entry.created_at, entry.activity_kind, entry.summary), reverse=True)
        entries = tuple(merged[:normalized_limit])
        return RecentActivityOverviewDTO(
            generated_at=utc_now(),
            limit=normalized_limit,
            recent_window_days=window_days,
            total_count=len(entries),
            entries=entries,
        )

    def _normalize_limit(self, limit: int) -> int:
        if limit <= 0:
            raise ValidationError("limit must be positive")
        return min(limit, self._MAX_LIMIT)

    def _normalize_recent_window_days(self, recent_window_days: int) -> int:
        if recent_window_days <= 0:
            raise ValidationError("recent_window_days must be positive")
        return min(recent_window_days, self._MAX_WINDOW_DAYS)

    @staticmethod
    def _to_low_stock_entry(record: InventoryDashboardRecord) -> LowStockEntryDTO:
        return LowStockEntryDTO(
            slot_id=record.slot_id,
            slot_code=record.slot_code,
            slot_status=record.slot_status,
            item_id=record.item_id,
            item_sku=record.item_sku,
            item_name=record.item_name,
            item_status=record.item_status,
            quantity=record.quantity,
            min_level=record.min_level,
            shortage=max(record.min_level - record.quantity, 0),
        )

    @staticmethod
    def _to_recent_operation_entry(record: OperationDashboardRecord) -> RecentOperationEntryDTO:
        return RecentOperationEntryDTO(
            operation_id=record.operation_id,
            operation_type=record.operation_type,
            operation_state=record.operation_state,
            user_id=record.user_id,
            item_id=record.item_id,
            slot_id=record.slot_id,
            qty_requested=record.qty_requested,
            qty_confirmed=record.qty_confirmed,
            result=record.result,
            error_code=record.error_code,
            started_at=record.started_at,
            finished_at=record.finished_at,
        )

    @staticmethod
    def _to_event_activity(log: EventLog) -> RecentActivityEntryDTO:
        summary = log.message or log.comment or log.event_type
        return RecentActivityEntryDTO(
            activity_kind="event",
            created_at=log.created_at,
            summary=summary,
            source=f"{log.source}:{log.event_type}",
            operation_id=log.operation_id,
            user_id=log.user_id,
            item_id=log.item_id,
            slot_id=log.slot_id,
        )

    @staticmethod
    def _to_audit_activity(log: AuditLog) -> RecentActivityEntryDTO:
        summary = log.comment or f"{log.action} {log.entity_type}:{log.entity_id}"
        return RecentActivityEntryDTO(
            activity_kind="audit",
            created_at=log.created_at,
            summary=summary,
            source=f"{log.entity_type}:{log.action}",
            operation_id=None,
            user_id=log.actor_user_id,
            item_id=int(log.entity_id) if log.entity_type == "item" and log.entity_id.isdigit() else None,
            slot_id=int(log.entity_id) if log.entity_type == "slot" and log.entity_id.isdigit() else None,
        )

    @staticmethod
    def _context_int(context: dict[str, object] | None, key: str) -> int | None:
        value = (context or {}).get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
        return None
