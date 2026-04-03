from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from app.application.dto.operations import OperationDTO
from app.application.dto.query import (
    AuditLogListFilters,
    AuditLogListItemDTO,
    EventLogListFilters,
    EventLogListItemDTO,
    ItemListFilters,
    ItemListItemDTO,
    OperationListFilters,
    PaginatedResult,
    Pagination,
    RecoveryCaseListFilters,
    SlotListFilters,
    SlotListItemDTO,
    UserListFilters,
    UserListItemDTO,
)
from app.application.dto.recovery import RecoveryCaseDTO
from app.application.exceptions import ValidationError
from app.application.recovery_service import RecoveryService
from app.domain.enums import RoleCode
from app.persistence.models import AuditLog, EventLog, Operation, Role, User
from app.persistence.repositories.catalog import CatalogRepository
from app.persistence.repositories.logs import AuditLogRepository, EventLogRepository
from app.persistence.repositories.operations import OperationRepository
from app.persistence.repositories.recovery import RecoveryRepository
from app.persistence.repositories.users import UserRepository


class QueryService:
    def __init__(
        self,
        *,
        users: UserRepository,
        catalog: CatalogRepository,
        operations: OperationRepository,
        recovery: RecoveryRepository,
        event_logs: EventLogRepository,
        audit_logs: AuditLogRepository,
    ) -> None:
        self.users = users
        self.catalog = catalog
        self.operations = operations
        self.recovery = recovery
        self.event_logs = event_logs
        self.audit_logs = audit_logs

    def list_users(self, *, pagination: Pagination, filters: UserListFilters) -> PaginatedResult[UserListItemDTO]:
        pagination = self._validate_pagination(pagination)
        items = tuple(
            self._to_user_list_item(user)
            for user in self.users.list_users(
                limit=pagination.limit,
                offset=pagination.offset,
                status=filters.status,
                created_from=filters.created_from,
                created_to=filters.created_to,
            )
        )
        total = self.users.count_users(
            status=filters.status,
            created_from=filters.created_from,
            created_to=filters.created_to,
        )
        return PaginatedResult(items=items, total=total, limit=pagination.limit, offset=pagination.offset)

    def list_items(self, *, pagination: Pagination, filters: ItemListFilters) -> PaginatedResult[ItemListItemDTO]:
        pagination = self._validate_pagination(pagination)
        items = tuple(
            ItemListItemDTO(
                item_id=item.id,
                item_group_id=item.item_group_id,
                sku=item.sku,
                name=item.name,
                unit=item.unit,
                return_allowed=item.return_allowed,
                min_level=item.min_level,
                status=item.status,
            )
            for item in self.catalog.list_items(limit=pagination.limit, offset=pagination.offset, status=filters.status)
        )
        total = self.catalog.count_items(status=filters.status)
        return PaginatedResult(items=items, total=total, limit=pagination.limit, offset=pagination.offset)

    def list_slots(self, *, pagination: Pagination, filters: SlotListFilters) -> PaginatedResult[SlotListItemDTO]:
        pagination = self._validate_pagination(pagination)
        items = tuple(
            SlotListItemDTO(
                slot_id=slot.id,
                code=slot.code,
                slot_type=slot.slot_type,
                drum_position=slot.drum_position,
                board_address=slot.board_address,
                lock_number=slot.lock_number,
                capacity=slot.capacity,
                status=slot.status,
            )
            for slot in self.catalog.list_slots(
                limit=pagination.limit,
                offset=pagination.offset,
                status=filters.status,
                slot_type=filters.slot_type,
            )
        )
        total = self.catalog.count_slots(status=filters.status, slot_type=filters.slot_type)
        return PaginatedResult(items=items, total=total, limit=pagination.limit, offset=pagination.offset)

    def list_operations(
        self,
        *,
        pagination: Pagination,
        filters: OperationListFilters,
    ) -> PaginatedResult[OperationDTO]:
        pagination = self._validate_pagination(pagination)
        items = tuple(
            self._to_operation_dto(operation)
            for operation in self.operations.list_operations(
                limit=pagination.limit,
                offset=pagination.offset,
                operation_state=filters.operation_state,
                operation_type=filters.operation_type,
                user_id=filters.user_id,
                item_id=filters.item_id,
                slot_id=filters.slot_id,
                session_id=filters.session_id,
            )
        )
        total = self.operations.count_operations(
            operation_state=filters.operation_state,
            operation_type=filters.operation_type,
            user_id=filters.user_id,
            item_id=filters.item_id,
            slot_id=filters.slot_id,
            session_id=filters.session_id,
        )
        return PaginatedResult(items=items, total=total, limit=pagination.limit, offset=pagination.offset)

    def list_recovery_cases(
        self,
        *,
        pagination: Pagination,
        filters: RecoveryCaseListFilters,
    ) -> PaginatedResult[RecoveryCaseDTO]:
        pagination = self._validate_pagination(pagination)
        items = tuple(
            RecoveryService._to_dto(case)
            for case in self.recovery.list_cases(
                limit=pagination.limit,
                offset=pagination.offset,
                status=filters.status,
                classification=filters.classification,
                created_from=filters.created_from,
                created_to=filters.created_to,
            )
        )
        total = self.recovery.count_cases(
            status=filters.status,
            classification=filters.classification,
            created_from=filters.created_from,
            created_to=filters.created_to,
        )
        return PaginatedResult(items=items, total=total, limit=pagination.limit, offset=pagination.offset)

    def list_event_logs(
        self,
        *,
        pagination: Pagination,
        filters: EventLogListFilters,
    ) -> PaginatedResult[EventLogListItemDTO]:
        pagination = self._validate_pagination(pagination)
        items = tuple(
            self._to_event_log_item(event_log)
            for event_log in self.event_logs.list_events(
                limit=pagination.limit,
                offset=pagination.offset,
                event_type=filters.event_type,
                created_from=filters.created_from,
                created_to=filters.created_to,
            )
        )
        total = self.event_logs.count_events(
            event_type=filters.event_type,
            created_from=filters.created_from,
            created_to=filters.created_to,
        )
        return PaginatedResult(items=items, total=total, limit=pagination.limit, offset=pagination.offset)

    def list_audit_logs(
        self,
        *,
        pagination: Pagination,
        filters: AuditLogListFilters,
    ) -> PaginatedResult[AuditLogListItemDTO]:
        pagination = self._validate_pagination(pagination)
        items = tuple(
            self._to_audit_log_item(audit_log)
            for audit_log in self.audit_logs.list_audit_logs(
                limit=pagination.limit,
                offset=pagination.offset,
                entity_type=filters.entity_type,
                action=filters.action,
                reason_code=filters.reason_code,
                created_from=filters.created_from,
                created_to=filters.created_to,
            )
        )
        total = self.audit_logs.count_audit_logs(
            entity_type=filters.entity_type,
            action=filters.action,
            reason_code=filters.reason_code,
            created_from=filters.created_from,
            created_to=filters.created_to,
        )
        return PaginatedResult(items=items, total=total, limit=pagination.limit, offset=pagination.offset)

    def _validate_pagination(self, pagination: Pagination) -> Pagination:
        if pagination.limit <= 0:
            raise ValidationError("limit must be positive")
        if pagination.limit > 100:
            raise ValidationError("limit must be less than or equal to 100")
        if pagination.offset < 0:
            raise ValidationError("offset must be greater than or equal to 0")
        return replace(pagination)

    def _to_user_list_item(self, user: User) -> UserListItemDTO:
        role = self.users.session.get(Role, user.role_id)
        role_code = role.code if role is not None else None
        if role_code is not None and not isinstance(role_code, RoleCode):
            role_code = RoleCode(role_code)
        return UserListItemDTO(
            user_id=user.id,
            user_code=user.user_code,
            full_name=user.full_name,
            status=user.status,
            is_active=user.is_active,
            role_code=role_code,
            created_at=user.created_at,
            updated_at=user.updated_at,
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
    def _to_event_log_item(event_log: EventLog) -> EventLogListItemDTO:
        qty = event_log.qty
        return EventLogListItemDTO(
            event_log_id=event_log.id,
            event_type=event_log.event_type,
            level=event_log.level,
            source=event_log.source,
            operation_id=event_log.operation_id,
            session_id=event_log.session_id,
            user_id=event_log.user_id,
            slot_id=event_log.slot_id,
            item_id=event_log.item_id,
            qty=float(qty) if isinstance(qty, Decimal) else qty,
            result=event_log.result,
            comment=event_log.comment,
            message=event_log.message,
            payload=dict(event_log.payload_json or {}),
            created_at=event_log.created_at,
        )

    @staticmethod
    def _to_audit_log_item(audit_log: AuditLog) -> AuditLogListItemDTO:
        return AuditLogListItemDTO(
            audit_log_id=audit_log.id,
            entity_type=audit_log.entity_type,
            entity_id=audit_log.entity_id,
            action=audit_log.action,
            actor_user_id=audit_log.actor_user_id,
            reason_code=audit_log.reason_code,
            comment=audit_log.comment,
            before=dict(audit_log.before_json or {}),
            after=dict(audit_log.after_json or {}),
            created_at=audit_log.created_at,
        )
