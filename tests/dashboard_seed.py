from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from app.application.time import utc_now
from app.domain.enums import (
    BindingType,
    ItemStatus,
    OperationState,
    OperationType,
    RecoveryClassification,
    RecoveryStatus,
    RoleCode,
    SlotStatus,
    SlotType,
    UserStatus,
)
from app.persistence.models import (
    AuditLog,
    EventLog,
    InventoryBalance,
    Item,
    Operation,
    RecoveryCase,
    Role,
    Slot,
    SlotItemBinding,
    User,
)


def seed_dashboard_data(session: Session) -> None:
    now = utc_now()
    admin_role = Role(code=RoleCode.ADMIN, name="Admin")
    operator_role = Role(code=RoleCode.OPERATOR, name="Operator")
    user_role = Role(code=RoleCode.USER, name="User")
    session.add_all((admin_role, operator_role, user_role))
    session.flush()

    session.add_all(
        (
            User(
                role_id=admin_role.id,
                user_code="admin-1",
                full_name="Admin One",
                status=UserStatus.ACTIVE,
                is_active=True,
            ),
            User(
                role_id=operator_role.id,
                user_code="operator-1",
                full_name="Operator One",
                status=UserStatus.BLOCKED,
                is_active=False,
            ),
            User(
                role_id=user_role.id,
                user_code="user-1",
                full_name="User One",
                status=UserStatus.INACTIVE,
                is_active=False,
            ),
        )
    )

    low_item = Item(
        item_group_id=None,
        sku="item-low",
        name="Low Item",
        description=None,
        unit="pcs",
        return_allowed=True,
        min_level=3,
        status=ItemStatus.ACTIVE,
    )
    inactive_item = Item(
        item_group_id=None,
        sku="item-inactive",
        name="Inactive Item",
        description=None,
        unit="pcs",
        return_allowed=False,
        min_level=1,
        status=ItemStatus.INACTIVE,
    )
    active_slot = Slot(
        code="slot-a",
        slot_type=SlotType.UNIVERSAL,
        drum_position=1,
        board_address=1,
        lock_number=1,
        capacity=10,
        status=SlotStatus.ACTIVE,
    )
    disabled_slot = Slot(
        code="slot-b",
        slot_type=SlotType.UNIVERSAL,
        drum_position=2,
        board_address=1,
        lock_number=2,
        capacity=10,
        status=SlotStatus.DISABLED,
    )
    session.add_all((low_item, inactive_item, active_slot, disabled_slot))
    session.flush()

    session.add_all(
        (
            SlotItemBinding(
                slot_id=active_slot.id,
                item_id=low_item.id,
                binding_type=BindingType.PRIMARY,
                is_active=True,
                valid_from=None,
                valid_to=None,
            ),
            SlotItemBinding(
                slot_id=disabled_slot.id,
                item_id=inactive_item.id,
                binding_type=BindingType.PRIMARY,
                is_active=True,
                valid_from=None,
                valid_to=None,
            ),
            InventoryBalance(slot_id=active_slot.id, item_id=low_item.id, quantity=2),
            InventoryBalance(slot_id=disabled_slot.id, item_id=inactive_item.id, quantity=5),
        )
    )
    session.flush()

    completed_operation = Operation(
        session_id=None,
        operation_type=OperationType.DISPENSE,
        operation_state=OperationState.COMPLETED,
        user_id=1,
        item_id=low_item.id,
        slot_id=active_slot.id,
        qty_requested=1,
        qty_confirmed=1,
        result="ok",
        error_code=None,
        error_message=None,
        hardware_context_json={},
        business_context_json={},
        started_at=now - timedelta(hours=4),
        finished_at=now - timedelta(hours=4) + timedelta(minutes=2),
    )
    failed_operation = Operation(
        session_id=None,
        operation_type=OperationType.RETURN,
        operation_state=OperationState.FAILED,
        user_id=1,
        item_id=low_item.id,
        slot_id=active_slot.id,
        qty_requested=1,
        qty_confirmed=0,
        result="failed",
        error_code="jam",
        error_message="Door jam",
        hardware_context_json={},
        business_context_json={},
        started_at=now - timedelta(hours=3),
        finished_at=now - timedelta(hours=3) + timedelta(minutes=5),
    )
    recovery_operation = Operation(
        session_id=None,
        operation_type=OperationType.DISPENSE,
        operation_state=OperationState.RECOVERY_REQUIRED,
        user_id=1,
        item_id=low_item.id,
        slot_id=active_slot.id,
        qty_requested=1,
        qty_confirmed=None,
        result=None,
        error_code=None,
        error_message=None,
        hardware_context_json={},
        business_context_json={},
        started_at=now - timedelta(hours=2),
        finished_at=now - timedelta(hours=2) + timedelta(minutes=1),
    )
    unfinished_operation = Operation(
        session_id=None,
        operation_type=OperationType.REFILL_ITEM,
        operation_state=OperationState.USER_ACTION_PENDING,
        user_id=1,
        item_id=low_item.id,
        slot_id=active_slot.id,
        qty_requested=4,
        qty_confirmed=None,
        result=None,
        error_code=None,
        error_message=None,
        hardware_context_json={},
        business_context_json={},
        started_at=now - timedelta(hours=1),
        finished_at=None,
    )
    session.add_all((completed_operation, failed_operation, recovery_operation, unfinished_operation))
    session.flush()

    session.add(
        RecoveryCase(
            classification=RecoveryClassification.MANUAL_REVIEW_REQUIRED,
            status=RecoveryStatus.OPEN,
            resolved_at=None,
            summary="Recovery required for dispense mismatch",
            context_json={"operation_id": recovery_operation.id},
            created_at=now - timedelta(minutes=45),
        )
    )

    session.add_all(
        (
            EventLog(
                event_type="operation_failed",
                level="error",
                source="operations",
                operation_id=failed_operation.id,
                session_id=None,
                user_id=1,
                slot_id=active_slot.id,
                item_id=low_item.id,
                qty=None,
                result="failed",
                comment="Door jam recorded",
                message="Operation failed during unlock",
                payload_json={},
                created_at=now - timedelta(minutes=30),
            ),
            AuditLog(
                entity_type="recovery_case",
                entity_id="1",
                action="review_requested",
                actor_user_id=1,
                reason_code=None,
                comment="Recovery case queued for review",
                before_json=None,
                after_json=None,
                created_at=now - timedelta(minutes=20),
            ),
        )
    )
    session.commit()
