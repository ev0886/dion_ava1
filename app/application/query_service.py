from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.application.dto.logs import (
    AuditLogEntryDTO,
    AuditLogQueryFilters,
    EventLogEntryDTO,
    EventLogQueryFilters,
)
from app.application.dto.operations import (
    OperationDTO,
    OperationDetailDTO,
    OperationInventoryTransactionDTO,
    OperationQueryFilters,
    OperationStateHistoryEntryDTO,
)
from app.application.exceptions import NotFoundError
from app.persistence.models import AuditLog, EventLog, InventoryTransaction, Operation, OperationStateHistory
from app.persistence.repositories.inventory import InventoryRepository
from app.persistence.repositories.logs import AuditLogRepository, EventLogRepository
from app.persistence.repositories.operations import OperationRepository
from app.persistence.repositories.recovery import RecoveryRepository


@dataclass(slots=True)
class OperationQueryService:
    operation_repository: OperationRepository
    inventory_repository: InventoryRepository
    recovery_repository: RecoveryRepository

    def list_operations(self, filters: OperationQueryFilters) -> tuple[OperationDTO, ...]:
        operations = self.operation_repository.list_filtered(
            operation_type=filters.operation_type,
            operation_state=filters.operation_state,
            user_id=filters.user_id,
            item_id=filters.item_id,
            slot_id=filters.slot_id,
            session_id=filters.session_id,
            limit=filters.limit,
        )
        return tuple(self._to_operation_dto(operation) for operation in operations)

    def get_operation(self, operation_id: int) -> OperationDetailDTO:
        operation = self.operation_repository.get_by_id(operation_id)
        if operation is None:
            raise NotFoundError(f"Operation not found: {operation_id}")
        return OperationDetailDTO(
            operation=self._to_operation_dto(operation),
            state_history=self.get_operation_history(operation_id),
            inventory_transactions=tuple(
                self._to_inventory_transaction_dto(transaction)
                for transaction in self.inventory_repository.list_transactions(operation_id=operation_id)
            ),
            recovery_case_id=self.recovery_repository.find_case_id_by_operation_id(operation_id),
        )

    def get_operation_history(self, operation_id: int) -> tuple[OperationStateHistoryEntryDTO, ...]:
        operation = self.operation_repository.get_by_id(operation_id)
        if operation is None:
            raise NotFoundError(f"Operation not found: {operation_id}")
        return tuple(
            self._to_state_history_dto(entry)
            for entry in self.operation_repository.list_state_history(operation_id)
        )

    @staticmethod
    def _to_operation_dto(operation: Operation) -> OperationDTO:
        return OperationDTO(
            operation_id=operation.id,
            session_id=operation.session_id,
            operation_type=operation.operation_type,
            operation_state=operation.operation_state,
            user_id=operation.user_id,
            item_id=operation.item_id,
            slot_id=operation.slot_id,
            qty_requested=operation.qty_requested,
            qty_confirmed=operation.qty_confirmed,
            result=operation.result,
            error_code=operation.error_code,
            error_message=operation.error_message,
            hardware_context=dict(operation.hardware_context_json or {}),
            business_context=dict(operation.business_context_json or {}),
            started_at=operation.started_at,
            finished_at=operation.finished_at,
        )

    @staticmethod
    def _to_state_history_dto(entry: OperationStateHistory) -> OperationStateHistoryEntryDTO:
        return OperationStateHistoryEntryDTO(
            history_entry_id=entry.id,
            operation_id=entry.operation_id,
            state=entry.state,
            comment=entry.comment,
            context=dict(entry.context_json or {}),
            created_at=entry.created_at,
        )

    @staticmethod
    def _to_inventory_transaction_dto(transaction: InventoryTransaction) -> OperationInventoryTransactionDTO:
        return OperationInventoryTransactionDTO(
            transaction_id=transaction.id,
            operation_id=transaction.operation_id,
            session_id=transaction.session_id,
            slot_id=transaction.slot_id,
            item_id=transaction.item_id,
            transaction_type=transaction.transaction_type.value,
            quantity_delta=transaction.quantity_delta,
            quantity_before=transaction.quantity_before,
            quantity_after=transaction.quantity_after,
            comment=transaction.comment,
            created_at=transaction.created_at,
        )


@dataclass(slots=True)
class LogQueryService:
    audit_log_repository: AuditLogRepository
    event_log_repository: EventLogRepository

    def list_audit_logs(self, filters: AuditLogQueryFilters) -> tuple[AuditLogEntryDTO, ...]:
        return tuple(
            self._to_audit_log_dto(entry)
            for entry in self.audit_log_repository.list_recent_filtered(
                entity_type=filters.entity_type,
                actor_user_id=filters.actor_user_id,
                limit=filters.limit,
            )
        )

    def list_event_logs(self, filters: EventLogQueryFilters) -> tuple[EventLogEntryDTO, ...]:
        return tuple(
            self._to_event_log_dto(entry)
            for entry in self.event_log_repository.list_recent_filtered(
                event_type=filters.event_type,
                level=filters.level,
                limit=filters.limit,
            )
        )

    @staticmethod
    def _to_audit_log_dto(entry: AuditLog) -> AuditLogEntryDTO:
        return AuditLogEntryDTO(
            audit_log_id=entry.id,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            action=entry.action,
            actor_user_id=entry.actor_user_id,
            reason_code=entry.reason_code,
            comment=entry.comment,
            before=dict(entry.before_json or {}),
            after=dict(entry.after_json or {}),
            created_at=entry.created_at,
        )

    @staticmethod
    def _to_event_log_dto(entry: EventLog) -> EventLogEntryDTO:
        qty = float(entry.qty) if isinstance(entry.qty, Decimal) else entry.qty
        return EventLogEntryDTO(
            event_log_id=entry.id,
            event_type=entry.event_type,
            level=entry.level,
            source=entry.source,
            operation_id=entry.operation_id,
            session_id=entry.session_id,
            user_id=entry.user_id,
            slot_id=entry.slot_id,
            item_id=entry.item_id,
            qty=qty,
            result=entry.result,
            comment=entry.comment,
            message=entry.message,
            payload=dict(entry.payload_json or {}),
            created_at=entry.created_at,
        )
