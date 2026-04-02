from __future__ import annotations

from pathlib import Path

import pytest

from app.application.composition import create_bootstrapped_application_container
from app.application.exceptions import ConflictError, ValidationError
from app.config import AppSettings
from app.domain.enums import BindingType, InventoryTransactionType, ItemStatus, RoleCode, SlotStatus, SlotType, UserStatus
from app.persistence.models import AuditLog, InventoryBalance, InventoryTransaction, Item, Role, Slot, SlotItemBinding, User


def test_slot_create_happy_path(tmp_path: Path) -> None:
    container = _container(tmp_path, "slot_create.sqlite3")
    try:
        _seed_role_and_user(container)
        result = container.services.slots.create_slot(
            code="slot-a1",
            slot_type=SlotType.UNIVERSAL,
            drum_position=0,
            board_address=1,
            lock_number=2,
            capacity=12,
            status=SlotStatus.ACTIVE,
            actor_user_id=1,
            comment="create slot",
        )

        assert result.slot.code == "slot-a1"
        assert result.slot.slot_type is SlotType.UNIVERSAL
        assert result.slot.status is SlotStatus.ACTIVE
        assert result.active_bindings == ()
        assert result.inventory_balances == ()
    finally:
        container.close()


def test_duplicate_slot_code_rejection(tmp_path: Path) -> None:
    container = _container(tmp_path, "slot_duplicate.sqlite3")
    try:
        _seed_slot(container, code="slot-a1")

        with pytest.raises(ConflictError):
            container.services.slots.create_slot(
                code="slot-a1",
                slot_type=SlotType.DISPENSE,
                drum_position=1,
                board_address=1,
                lock_number=3,
                capacity=5,
                status=SlotStatus.ACTIVE,
            )
    finally:
        container.close()


def test_slot_update_activate_and_deactivate(tmp_path: Path) -> None:
    container = _container(tmp_path, "slot_update.sqlite3")
    try:
        slot = _seed_slot(container, code="slot-a1", status=SlotStatus.ACTIVE)

        updated = container.services.slots.update_slot(
            slot_id=slot.id,
            code="slot-b2",
            drum_position=5,
            board_address=2,
            lock_number=4,
            capacity=20,
            status=SlotStatus.OUT_OF_SERVICE,
        )
        deactivated = container.services.slots.deactivate_slot(slot_id=slot.id)
        activated = container.services.slots.activate_slot(slot_id=slot.id)

        assert updated.slot.code == "slot-b2"
        assert updated.slot.drum_position == 5
        assert updated.slot.status is SlotStatus.OUT_OF_SERVICE
        assert deactivated.slot.status is SlotStatus.DISABLED
        assert activated.slot.status is SlotStatus.ACTIVE
    finally:
        container.close()


def test_slot_binding_create_happy_path(tmp_path: Path) -> None:
    container = _container(tmp_path, "binding_create.sqlite3")
    try:
        slot = _seed_slot(container)
        item = _seed_item(container)

        binding = container.services.slots.create_binding(
            slot_id=slot.id,
            item_id=item.id,
            binding_type=BindingType.PRIMARY,
        )

        assert binding.binding_id is not None
        assert binding.slot_id == slot.id
        assert binding.item_id == item.id
        assert binding.binding_type is BindingType.PRIMARY
        assert binding.is_active is True
    finally:
        container.close()


def test_duplicate_binding_rejection(tmp_path: Path) -> None:
    container = _container(tmp_path, "binding_duplicate.sqlite3")
    try:
        slot = _seed_slot(container)
        item = _seed_item(container)
        _seed_binding(container, slot_id=slot.id, item_id=item.id, binding_type=BindingType.RETURN)

        with pytest.raises(ConflictError):
            container.services.slots.create_binding(
                slot_id=slot.id,
                item_id=item.id,
                binding_type=BindingType.RETURN,
            )
    finally:
        container.close()


def test_slot_binding_deactivate_path(tmp_path: Path) -> None:
    container = _container(tmp_path, "binding_deactivate.sqlite3")
    try:
        slot = _seed_slot(container)
        item = _seed_item(container)
        binding = _seed_binding(container, slot_id=slot.id, item_id=item.id, binding_type=BindingType.PRIMARY)

        result = container.services.slots.deactivate_binding(binding_id=binding.id)

        assert result.is_active is False
        assert result.valid_to is not None
    finally:
        container.close()


def test_inventory_balance_list_and_read_shape(tmp_path: Path) -> None:
    container = _container(tmp_path, "balance_list.sqlite3")
    try:
        slot = _seed_slot(container)
        item = _seed_item(container)
        _seed_binding(container, slot_id=slot.id, item_id=item.id, binding_type=BindingType.PRIMARY)
        _seed_balance(container, slot_id=slot.id, item_id=item.id, quantity=7)

        balances = container.services.inventory.list_balances(slot_id=slot.id)
        slot_detail = container.services.slots.get_slot_details(slot.id)

        assert len(balances) == 1
        assert balances[0].quantity == 7
        assert slot_detail.inventory_balances[0].item_id == item.id
        assert slot_detail.active_bindings[0].binding_type is BindingType.PRIMARY
    finally:
        container.close()


def test_manual_inventory_delta_adjustment_happy_path(tmp_path: Path) -> None:
    container = _container(tmp_path, "adjust_delta.sqlite3")
    try:
        slot = _seed_slot(container)
        item = _seed_item(container)
        _seed_balance(container, slot_id=slot.id, item_id=item.id, quantity=5)

        result = container.services.inventory_admin.adjust_inventory(
            slot_id=slot.id,
            item_id=item.id,
            quantity_delta=3,
            comment="manual delta",
        )

        assert result.quantity_before == 5
        assert result.quantity_after == 8
        assert result.transaction_type is InventoryTransactionType.INVENTORY_ADJUSTMENT
        assert result.balance.quantity == 8

        transactions = container.repositories.inventory.list_transactions()
        assert transactions[-1].quantity_after == 8
    finally:
        container.close()


def test_manual_inventory_set_happy_path(tmp_path: Path) -> None:
    container = _container(tmp_path, "adjust_set.sqlite3")
    try:
        slot = _seed_slot(container)
        item = _seed_item(container)
        _seed_balance(container, slot_id=slot.id, item_id=item.id, quantity=9)

        result = container.services.inventory_admin.set_inventory(
            slot_id=slot.id,
            item_id=item.id,
            quantity=4,
            comment="manual set",
        )

        assert result.quantity_delta == -5
        assert result.quantity_after == 4
        assert result.balance.quantity == 4
    finally:
        container.close()


def test_negative_and_invalid_inventory_adjustment_rejection(tmp_path: Path) -> None:
    container = _container(tmp_path, "adjust_invalid.sqlite3")
    try:
        slot = _seed_slot(container)
        item = _seed_item(container)
        _seed_balance(container, slot_id=slot.id, item_id=item.id, quantity=2)

        with pytest.raises(ValidationError):
            container.services.inventory_admin.adjust_inventory(
                slot_id=slot.id,
                item_id=item.id,
                quantity_delta=-3,
            )

        with pytest.raises(ValidationError):
            container.services.inventory_admin.set_inventory(
                slot_id=slot.id,
                item_id=item.id,
                quantity=-1,
            )
    finally:
        container.close()


def test_audit_log_creation_for_representative_mutations(tmp_path: Path) -> None:
    container = _container(tmp_path, "audit_logs.sqlite3")
    try:
        _seed_role_and_user(container)
        slot_result = container.services.slots.create_slot(
            code="slot-a1",
            slot_type=SlotType.UNIVERSAL,
            drum_position=0,
            board_address=1,
            lock_number=1,
            capacity=10,
            status=SlotStatus.ACTIVE,
            actor_user_id=1,
            reason_code="admin_create",
            comment="create",
        )
        item = _seed_item(container)
        binding = container.services.slots.create_binding(
            slot_id=slot_result.slot.slot_id,
            item_id=item.id,
            binding_type=BindingType.PRIMARY,
            actor_user_id=1,
            comment="bind",
        )
        container.services.inventory_admin.adjust_inventory(
            slot_id=slot_result.slot.slot_id,
            item_id=item.id,
            quantity_delta=2,
            actor_user_id=1,
            comment="adjust",
        )

        logs = container.repositories.audit_logs.list_recent(limit=10)

        assert [log.action for log in logs[:3]] == ["manual_adjust_delta", "create", "create"]
        assert logs[0].entity_type == "inventory_balance"
        assert logs[1].entity_type == "slot_item_binding"
        assert logs[2].entity_type == "slot"
        assert binding.binding_id is not None
    finally:
        container.close()


def _container(tmp_path: Path, sqlite_filename: str):
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename=sqlite_filename,
        alembic_config_path=Path("alembic.ini"),
    )
    return create_bootstrapped_application_container(settings)


def _seed_role_and_user(container):
    role = Role(code=RoleCode.ADMIN, name="Admin")
    container.session.add(role)
    container.session.flush()
    user = User(
        role_id=role.id,
        user_code="admin-1",
        full_name="Admin User",
        status=UserStatus.ACTIVE,
        is_active=True,
    )
    container.session.add(user)
    container.session.commit()
    return user


def _seed_item(container):
    item = Item(
        item_group_id=None,
        sku=f"item-{container.session.query(Item).count() + 1}",
        name="Item",
        description=None,
        unit="pcs",
        return_allowed=True,
        min_level=0,
        status=ItemStatus.ACTIVE,
    )
    container.session.add(item)
    container.session.commit()
    return item


def _seed_slot(container, code: str = "slot-1", status: SlotStatus = SlotStatus.ACTIVE):
    slot = Slot(
        code=code,
        slot_type=SlotType.UNIVERSAL,
        drum_position=1,
        board_address=1,
        lock_number=1,
        capacity=10,
        status=status,
    )
    container.session.add(slot)
    container.session.commit()
    return slot


def _seed_binding(container, *, slot_id: int, item_id: int, binding_type: BindingType):
    binding = SlotItemBinding(
        slot_id=slot_id,
        item_id=item_id,
        binding_type=binding_type,
        is_active=True,
        valid_from=None,
        valid_to=None,
    )
    container.session.add(binding)
    container.session.commit()
    return binding


def _seed_balance(container, *, slot_id: int, item_id: int, quantity: int):
    balance = InventoryBalance(slot_id=slot_id, item_id=item_id, quantity=quantity)
    container.session.add(balance)
    container.session.commit()
    return balance
