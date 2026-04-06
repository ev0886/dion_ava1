from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.time import utc_now
from app.domain.enums import BindingType, ItemStatus, OperationState, OperationType, RoleCode, SlotStatus, SlotType, UserStatus
from app.persistence.models import InventoryBalance, Item, Operation, OperationStateHistory, Role, Slot, SlotItemBinding, User, UserRfidCard


class DemoSeedError(Exception):
    """Raised when demo data cannot be seeded."""


@dataclass(frozen=True, slots=True)
class DemoSeedResult:
    role_ids: dict[str, int]
    user_ids: dict[str, int]
    item_id: int
    slot_id: int
    binding_id: int
    inventory_balance_id: int
    inventory_quantity: int
    user_rfid_card_id: int
    user_rfid_card_uid: str
    recovery_operation_id: int | None
    recovery_history_id: int | None


def seed_demo_data(session: Session, *, with_recovery: bool = False) -> DemoSeedResult:
    non_empty_tables = _find_non_empty_core_tables(session)
    if non_empty_tables:
        names = ", ".join(non_empty_tables)
        raise DemoSeedError(f"demo seed requires an empty domain database; found existing rows in: {names}")

    role_ids = _seed_roles(session)
    user_ids = _seed_users(session, role_ids=role_ids)
    item = Item(
        item_group_id=None,
        sku="item-1",
        name="Item One",
        description=None,
        unit="pcs",
        return_allowed=True,
        min_level=0,
        status=ItemStatus.ACTIVE,
    )
    slot = Slot(
        code="slot-1",
        slot_type=SlotType.UNIVERSAL,
        drum_position=1,
        board_address=1,
        lock_number=1,
        capacity=10,
        status=SlotStatus.ACTIVE,
    )
    session.add_all((item, slot))
    session.flush()

    binding = SlotItemBinding(
        slot_id=slot.id,
        item_id=item.id,
        binding_type=BindingType.RETURN,
        is_active=True,
        valid_from=None,
        valid_to=None,
    )
    balance = InventoryBalance(
        slot_id=slot.id,
        item_id=item.id,
        quantity=5,
    )
    rfid_card = UserRfidCard(
        user_id=user_ids["user-1"],
        card_uid="DEMO-USER-1",
        is_active=True,
        issued_at=utc_now(),
        revoked_at=None,
    )
    session.add_all((binding, balance, rfid_card))
    session.flush()

    recovery_operation_id: int | None = None
    recovery_history_id: int | None = None
    if with_recovery:
        operation = Operation(
            session_id=None,
            operation_type=OperationType.DISPENSE,
            operation_state=OperationState.USER_ACTION_PENDING,
            user_id=user_ids["user-1"],
            item_id=item.id,
            slot_id=slot.id,
            qty_requested=1,
            qty_confirmed=None,
            result=None,
            error_code=None,
            error_message=None,
            hardware_context_json={},
            business_context_json={},
            started_at=utc_now(),
            finished_at=None,
        )
        session.add(operation)
        session.flush()
        history = OperationStateHistory(
            operation_id=operation.id,
            state=OperationState.USER_ACTION_PENDING,
            comment="seeded recovery candidate",
            context_json={},
        )
        session.add(history)
        session.flush()
        recovery_operation_id = operation.id
        recovery_history_id = history.id

    session.commit()
    return DemoSeedResult(
        role_ids=role_ids,
        user_ids=user_ids,
        item_id=item.id,
        slot_id=slot.id,
        binding_id=binding.id,
        inventory_balance_id=balance.id,
        inventory_quantity=balance.quantity,
        user_rfid_card_id=rfid_card.id,
        user_rfid_card_uid=rfid_card.card_uid,
        recovery_operation_id=recovery_operation_id,
        recovery_history_id=recovery_history_id,
    )


def _seed_roles(session: Session) -> dict[str, int]:
    roles = (
        Role(code=RoleCode.ADMIN, name="Admin"),
        Role(code=RoleCode.OPERATOR, name="Operator"),
        Role(code=RoleCode.USER, name="User"),
    )
    session.add_all(roles)
    session.flush()
    return {role.code.value: role.id for role in roles}


def _seed_users(session: Session, *, role_ids: dict[str, int]) -> dict[str, int]:
    users = (
        User(
            role_id=role_ids[RoleCode.ADMIN.value],
            user_code="admin-1",
            full_name="Admin One",
            status=UserStatus.ACTIVE,
            is_active=True,
        ),
        User(
            role_id=role_ids[RoleCode.OPERATOR.value],
            user_code="operator-1",
            full_name="Operator One",
            status=UserStatus.ACTIVE,
            is_active=True,
        ),
        User(
            role_id=role_ids[RoleCode.USER.value],
            user_code="user-1",
            full_name="User One",
            status=UserStatus.ACTIVE,
            is_active=True,
        ),
    )
    session.add_all(users)
    session.flush()
    return {user.user_code: user.id for user in users}


def _find_non_empty_core_tables(session: Session) -> list[str]:
    checks: tuple[tuple[str, type], ...] = (
        ("roles", Role),
        ("users", User),
        ("items", Item),
        ("slots", Slot),
        ("slot_item_bindings", SlotItemBinding),
        ("inventory_balances", InventoryBalance),
        ("operations", Operation),
        ("operation_state_history", OperationStateHistory),
        ("user_rfid_cards", UserRfidCard),
    )
    non_empty: list[str] = []
    for table_name, model in checks:
        row_id = session.execute(select(model.id).limit(1)).scalar_one_or_none()
        if row_id is not None:
            non_empty.append(table_name)
    return non_empty
