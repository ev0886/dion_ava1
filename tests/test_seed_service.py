from __future__ import annotations

from pathlib import Path

from sqlalchemy import select

from app.application.composition import create_bootstrapped_application_container
from app.application.dto.operations import DispenseRequest
from app.config import AppSettings
from app.domain.enums import BindingType, RoleCode, StartupReadinessStatus
from app.persistence.models import AuditLog, EventLog, InventoryBalance, Item, Operation, Role, Slot, SlotItemBinding, User


def test_base_seed_happy_path(tmp_path: Path) -> None:
    container = create_bootstrapped_application_container(_settings(tmp_path, "seed_base.sqlite3"))
    try:
        result = container.services.seed.initialize_base_reference_data()

        roles = container.session.execute(select(Role).order_by(Role.id.asc())).scalars().all()

        assert result.workflow == "seed_base_data"
        assert result.created_count == 3
        assert result.skipped_count == 0
        assert [role.code for role in roles] == [RoleCode.ADMIN, RoleCode.OPERATOR, RoleCode.USER]
    finally:
        container.close()


def test_base_seed_is_idempotent(tmp_path: Path) -> None:
    container = create_bootstrapped_application_container(_settings(tmp_path, "seed_base_idempotent.sqlite3"))
    try:
        first = container.services.seed.initialize_base_reference_data()
        second = container.services.seed.initialize_base_reference_data()
        role_count = container.session.execute(select(Role)).scalars().all()

        assert first.created_count == 3
        assert second.created_count == 0
        assert second.skipped_count == 3
        assert len(role_count) == 3
    finally:
        container.close()


def test_demo_seed_happy_path(tmp_path: Path) -> None:
    container = create_bootstrapped_application_container(_settings(tmp_path, "seed_demo.sqlite3"))
    try:
        result = container.services.seed.create_demo_data_set()

        users = container.session.execute(select(User).where(User.user_code.like("demo-%")).order_by(User.user_code.asc())).scalars().all()
        items = container.session.execute(select(Item).where(Item.sku.like("demo-%")).order_by(Item.sku.asc())).scalars().all()
        slots = container.session.execute(select(Slot).where(Slot.code.like("demo-%")).order_by(Slot.code.asc())).scalars().all()
        bindings = container.session.execute(select(SlotItemBinding).order_by(SlotItemBinding.id.asc())).scalars().all()
        balances = container.session.execute(select(InventoryBalance).order_by(InventoryBalance.id.asc())).scalars().all()

        assert result.workflow == "seed_demo_data"
        assert result.created_count == 19
        assert [user.user_code for user in users] == ["demo-admin", "demo-operator", "demo-user"]
        assert [item.sku for item in items] == ["demo-battery-aa", "demo-glove-nitrile", "demo-mask-ffp2"]
        assert [slot.code for slot in slots] == ["demo-slot-a01", "demo-slot-a02", "demo-slot-r01"]
        assert len(bindings) == 4
        assert [balance.quantity for balance in balances] == [12, 8, 2]
    finally:
        container.close()


def test_demo_seed_has_deterministic_shape_across_runs(tmp_path: Path) -> None:
    container = create_bootstrapped_application_container(_settings(tmp_path, "seed_demo_shape.sqlite3"))
    try:
        first = container.services.seed.create_demo_data_set()
        first_snapshot = _demo_snapshot(container)

        second = container.services.seed.create_demo_data_set()
        second_snapshot = _demo_snapshot(container)

        assert first.created_count == 19
        assert second.created_count == 0
        assert second.skipped_count == 19
        assert first_snapshot == second_snapshot
        assert second_snapshot["bindings"] == (
            ("demo-slot-a01", "demo-glove-nitrile", BindingType.PRIMARY.value),
            ("demo-slot-a01", "demo-glove-nitrile", BindingType.RETURN.value),
            ("demo-slot-a02", "demo-battery-aa", BindingType.PRIMARY.value),
            ("demo-slot-r01", "demo-mask-ffp2", BindingType.RETURN.value),
        )
    finally:
        container.close()


def test_reset_demo_data_removes_demo_rows_and_related_operations(tmp_path: Path) -> None:
    container = create_bootstrapped_application_container(_settings(tmp_path, "seed_reset.sqlite3"))
    try:
        container.services.seed.create_demo_data_set()
        ids = _demo_ids(container)
        operation = container.services.dispense.execute(
            DispenseRequest(
                user_id=ids["demo-user"],
                item_id=ids["demo-glove-nitrile"],
                slot_id=ids["demo-slot-a01"],
                quantity=1,
                session_id=None,
            ),
            container.hardware.facade,
        )

        result = container.services.seed.reset_demo_data()

        remaining_demo_users = container.session.execute(select(User).where(User.user_code.like("demo-%"))).scalars().all()
        remaining_demo_items = container.session.execute(select(Item).where(Item.sku.like("demo-%"))).scalars().all()
        remaining_demo_slots = container.session.execute(select(Slot).where(Slot.code.like("demo-%"))).scalars().all()
        remaining_operations = container.session.execute(select(Operation).where(Operation.id == operation.operation_id)).scalars().all()
        seed_events = container.session.execute(select(EventLog).where(EventLog.source == "seed_service")).scalars().all()
        seed_audits = container.session.execute(select(AuditLog).where(AuditLog.entity_type == "seed_workflow")).scalars().all()

        assert result.workflow == "reset_demo_data"
        assert result.deleted_count == 9
        assert remaining_demo_users == []
        assert remaining_demo_items == []
        assert remaining_demo_slots == []
        assert remaining_operations == []
        assert len(seed_events) == 1
        assert seed_events[0].event_type == "reset_demo_data"
        assert len(seed_audits) == 1
        assert seed_audits[0].entity_id == "reset_demo_data"
    finally:
        container.close()


def test_startup_remains_ready_after_demo_seed(tmp_path: Path) -> None:
    container = create_bootstrapped_application_container(_settings(tmp_path, "seed_startup.sqlite3"))
    try:
        container.services.seed.create_demo_data_set()

        result = container.services.startup.run_startup_checks()

        assert result.database.ok is True
        assert result.recovery.ok is True
        assert result.readiness_status is StartupReadinessStatus.READY
    finally:
        container.close()


def _settings(tmp_path: Path, sqlite_filename: str) -> AppSettings:
    return AppSettings(
        data_dir=tmp_path,
        sqlite_filename=sqlite_filename,
        alembic_config_path=Path("alembic.ini"),
    )


def _demo_snapshot(container) -> dict[str, tuple[tuple[object, ...], ...]]:
    role_names = {
        role.id: role.code.value
        for role in container.session.execute(select(Role)).scalars().all()
    }
    slot_codes = {
        slot.id: slot.code
        for slot in container.session.execute(select(Slot)).scalars().all()
    }
    item_skus = {
        item.id: item.sku
        for item in container.session.execute(select(Item)).scalars().all()
    }
    users = tuple(
        (user.user_code, user.full_name, role_names[user.role_id])
        for user in container.session.execute(select(User).where(User.user_code.like("demo-%")).order_by(User.user_code.asc())).scalars()
    )
    items = tuple(
        (item.sku, item.name, item.unit, item.return_allowed, item.min_level)
        for item in container.session.execute(select(Item).where(Item.sku.like("demo-%")).order_by(Item.sku.asc())).scalars()
    )
    slots = tuple(
        (slot.code, slot.slot_type.value, slot.drum_position, slot.board_address, slot.lock_number, slot.capacity)
        for slot in container.session.execute(select(Slot).where(Slot.code.like("demo-%")).order_by(Slot.code.asc())).scalars()
    )
    bindings = tuple(
        (slot_codes[binding.slot_id], item_skus[binding.item_id], binding.binding_type.value)
        for binding in container.session.execute(select(SlotItemBinding).order_by(SlotItemBinding.id.asc())).scalars()
    )
    balances = tuple(
        (slot_codes[balance.slot_id], item_skus[balance.item_id], balance.quantity)
        for balance in container.session.execute(select(InventoryBalance).order_by(InventoryBalance.id.asc())).scalars()
    )
    return {
        "users": users,
        "items": items,
        "slots": slots,
        "bindings": bindings,
        "balances": balances,
    }


def _demo_ids(container) -> dict[str, int]:
    users = {
        user.user_code: user.id
        for user in container.session.execute(select(User).where(User.user_code.like("demo-%"))).scalars()
    }
    items = {
        item.sku: item.id
        for item in container.session.execute(select(Item).where(Item.sku.like("demo-%"))).scalars()
    }
    slots = {
        slot.code: slot.id
        for slot in container.session.execute(select(Slot).where(Slot.code.like("demo-%"))).scalars()
    }
    return {**users, **items, **slots}
