from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.application.admin_service import AdminNomenclatureService, AdminOperationService, AdminUserService
from app.application.dto.admin import AdminRecentOperationDTO
from app.application.exceptions import ValidationError
from app.domain.enums import (
    DispenseRestrictionPolicy,
    InventoryTransactionType,
    ItemStatus,
    OperationState,
    OperationType,
    RoleCode,
    SlotStatus,
    SlotType,
    UserStatus,
)
from app.persistence.base import Base
from app.persistence.models import InventoryTransaction, Item, Operation, Role, Slot, User, UserRfidCard
from app.persistence.repositories.inventory import InventoryRepository
from app.persistence.repositories.nomenclature import NomenclatureRepository
from app.persistence.repositories.operations import OperationRepository
from app.persistence.repositories.users import UserRepository


@pytest.fixture
def session_factory(tmp_path: Path) -> Iterator[sessionmaker[Session]]:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'admin_service.sqlite3').resolve()}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


def test_import_users_csv_adds_row_context_to_duplicate_rfid_conflict(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_import_duplicate_rfid_domain(session)
        service = AdminUserService(UserRepository(session))

        csv_payload = "\n".join(
            (
                "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
                "operator-1,Operator One,operator,00 0f-e2 76 7c 00 45,once_per_day",
            )
        )

        with pytest.raises(ValidationError) as exc_info:
            service.import_users_csv(csv_payload)

        assert str(exc_info.value) == (
            "CSV row 2: RFID UID '000FE2767C0045' is already assigned to user_code "
            "'user-1' (User One)"
        )


def test_import_users_csv_rejects_invalid_role_code_with_allowed_values(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_import_duplicate_rfid_domain(session)
        service = AdminUserService(UserRepository(session))

        csv_payload = "\n".join(
            (
                "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
                "user-2,User Two,manager,,once_per_day",
            )
        )

        with pytest.raises(ValidationError) as exc_info:
            service.import_users_csv(csv_payload)

        assert str(exc_info.value) == (
            "CSV row 2: invalid role_code 'manager'. "
            "Allowed role_code values: admin, operator, user"
        )


def test_import_users_csv_rejects_duplicate_user_code_in_same_payload(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_import_duplicate_rfid_domain(session)
        service = AdminUserService(UserRepository(session))

        csv_payload = "\n".join(
            (
                "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
                "user-2,User Two,user,,once_per_day",
                "user-2,User Two Again,user,,unlimited",
            )
        )

        with pytest.raises(ValidationError) as exc_info:
            service.import_users_csv(csv_payload)

        assert str(exc_info.value) == "CSV row 3: duplicate user_code user-2 in import file"


def test_import_users_csv_rejects_header_mismatch_with_expected_and_received_header(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_import_duplicate_rfid_domain(session)
        service = AdminUserService(UserRepository(session))

        csv_payload = "\n".join(
            (
                "user_code,full_name,rfid_uid,role_code,dispense_restriction_policy,unexpected_column",
                "user-2,User Two,,user,once_per_day,extra",
            )
        )

        with pytest.raises(ValidationError) as exc_info:
            service.import_users_csv(csv_payload)

        assert str(exc_info.value) == (
            "CSV header mismatch. Expected: "
            "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy. "
            "Got: user_code,full_name,rfid_uid,role_code,dispense_restriction_policy,unexpected_column"
        )


@pytest.mark.parametrize(
    ("row_text", "expected_detail"),
    (
        (
            ",User Two,user,,once_per_day",
            "CSV row 2: user_code must not be empty",
        ),
        (
            "user-2,   ,user,,once_per_day",
            "CSV row 2: full_name must not be empty",
        ),
        (
            "user-2,User Two,  ,,once_per_day",
            "CSV row 2: role_code must not be empty",
        ),
        (
            "user-2,User Two,user,,   ",
            "CSV row 2: dispense_restriction_policy must not be empty",
        ),
    ),
)
def test_import_users_csv_rejects_empty_required_fields_with_row_context(
    session_factory: sessionmaker[Session],
    row_text: str,
    expected_detail: str,
) -> None:
    with session_factory() as session:
        _seed_import_duplicate_rfid_domain(session)
        service = AdminUserService(UserRepository(session))

        csv_payload = "\n".join(
            (
                "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
                row_text,
            )
        )

        with pytest.raises(ValidationError) as exc_info:
            service.import_users_csv(csv_payload)

        assert str(exc_info.value) == expected_detail


def test_export_users_csv_returns_import_compatible_columns_and_current_values(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_import_duplicate_rfid_domain(session)
        service = AdminUserService(UserRepository(session))

        exported_csv = service.export_users_csv()

        assert exported_csv == "\n".join(
            (
                "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
                "user-1,User One,user,000FE2767C0045,unlimited",
                "operator-1,Operator One,operator,,once_per_day",
                "",
            )
        )


def test_create_nomenclature_reactivates_existing_inactive_duplicate(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        service = AdminNomenclatureService(NomenclatureRepository(session))

        created = service.create_nomenclature(name="  Test   Item  ")
        deactivated = service.deactivate_nomenclature(nomenclature_id=created.record.id)
        reactivated = service.create_nomenclature(name="Test Item")

        assert created.reactivated_existing is False
        assert deactivated.is_active is False
        assert reactivated.reactivated_existing is True
        assert reactivated.record.id == created.record.id
        assert reactivated.record.name == "Test Item"
        assert reactivated.record.is_active is True


def test_create_nomenclature_rejects_duplicate_active_normalized_name(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        service = AdminNomenclatureService(NomenclatureRepository(session))
        service.create_nomenclature(name="Test Item")

        with pytest.raises(ValidationError) as exc_info:
            service.create_nomenclature(name="  test   item ")

        assert str(exc_info.value) == "Nomenclature name already exists"


def test_update_nomenclature_rejects_conflict_with_existing_inactive_duplicate(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        service = AdminNomenclatureService(NomenclatureRepository(session))
        first = service.create_nomenclature(name="Alpha")
        second = service.create_nomenclature(name="Beta")
        service.deactivate_nomenclature(nomenclature_id=first.record.id)

        with pytest.raises(ValidationError) as exc_info:
            service.update_nomenclature(nomenclature_id=second.record.id, name=" alpha ")

        assert str(exc_info.value) == "Inactive nomenclature entry with this name already exists"


def test_create_nomenclature_creates_real_active_item(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        repository = NomenclatureRepository(session)
        service = AdminNomenclatureService(repository)

        created = service.create_nomenclature(name="  Очки   защитные  ")
        item = session.execute(
            select(Item).where(Item.sku == repository.sync_item_sku(created.record.id))
        ).scalar_one()
        persisted_status = session.execute(
            text("SELECT status FROM items WHERE id = :item_id"),
            {"item_id": item.id},
        ).scalar_one()
        resolution = InventoryRepository(session).resolve_authoritative_replenish_item(
            normalized_name="очки защитные",
            slot_ids=(),
        )

        assert created.record.name == "Очки защитные"
        assert item.name == "Очки защитные"
        assert item.status is ItemStatus.ACTIVE
        assert persisted_status == _persisted_item_status(session, ItemStatus.ACTIVE)
        assert item.unit == "pcs"
        assert item.return_allowed is True
        assert resolution.item is not None
        assert resolution.item.id == item.id
        assert resolution.matched_candidate_count == 1
        assert resolution.resolution_source == "single_name_match"


def test_update_nomenclature_renames_paired_item(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        repository = NomenclatureRepository(session)
        service = AdminNomenclatureService(repository)

        created = service.create_nomenclature(name="Очки защитные")
        updated = service.update_nomenclature(
            nomenclature_id=created.record.id,
            name="Очки закрытые",
        )
        item = session.execute(
            select(Item).where(Item.sku == repository.sync_item_sku(created.record.id))
        ).scalar_one()

        assert updated.name == "Очки закрытые"
        assert item.name == "Очки закрытые"
        assert item.status is ItemStatus.ACTIVE


def test_activate_nomenclature_restores_missing_or_inactive_item(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        repository = NomenclatureRepository(session)
        service = AdminNomenclatureService(repository)

        created = service.create_nomenclature(name="Перчатки защитные")
        item = session.execute(
            select(Item).where(Item.sku == repository.sync_item_sku(created.record.id))
        ).scalar_one()
        item.status = ItemStatus.INACTIVE
        service.deactivate_nomenclature(nomenclature_id=created.record.id)
        session.commit()

        reactivated = service.activate_nomenclature(nomenclature_id=created.record.id)
        refreshed_item = session.execute(
            select(Item).where(Item.sku == repository.sync_item_sku(created.record.id))
        ).scalar_one()

        assert reactivated.is_active is True
        assert refreshed_item.name == "Перчатки защитные"
        assert refreshed_item.status is ItemStatus.ACTIVE


def test_update_user_can_deactivate_user_and_preserve_record(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_import_duplicate_rfid_domain(session)
        service = AdminUserService(UserRepository(session))

        updated = service.update_user(
            user_id=1,
            rfid_uid="000FE2767C0045",
            is_active=False,
            dispense_restriction_policy=DispenseRestrictionPolicy.UNLIMITED,
        )

        persisted = session.get(User, 1)

        assert updated.user_id == 1
        assert updated.is_active is False
        assert updated.status is UserStatus.INACTIVE
        assert persisted is not None
        assert persisted.is_active is False
        assert persisted.status is UserStatus.INACTIVE


def test_create_user_uses_same_admin_rules_and_normalizes_rfid(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_import_duplicate_rfid_domain(session)
        session.add(Role(code=RoleCode.ADMIN, name="Admin"))
        session.commit()
        service = AdminUserService(UserRepository(session))

        created = service.create_user(
            user_code="  admin-1  ",
            full_name="  Admin One  ",
            role_code=RoleCode.ADMIN,
            rfid_uid="aa bb-11 22",
            dispense_restriction_policy=DispenseRestrictionPolicy.UNLIMITED,
            is_active=False,
        )

        persisted = session.get(User, created.user_id)

        assert created.user_code == "admin-1"
        assert created.full_name == "Admin One"
        assert created.role_code is RoleCode.ADMIN
        assert created.rfid_uid == "AABB1122"
        assert created.is_active is False
        assert created.status is UserStatus.INACTIVE
        assert persisted is not None
        assert persisted.is_active is False
        assert persisted.status is UserStatus.INACTIVE


def test_list_recent_operations_for_admin_returns_newest_first_with_joined_fields(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_import_duplicate_rfid_domain(session)
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

        session.add_all(
            (
                Operation(
                    session_id=None,
                    operation_type=OperationType.REFILL_ITEM,
                    operation_state=OperationState.COMPLETED,
                    user_id=2,
                    item_id=item.id,
                    slot_id=slot.id,
                    qty_requested=4,
                    qty_confirmed=4,
                    result=None,
                    error_code=None,
                    error_message=None,
                    hardware_context_json={},
                    business_context_json={},
                    started_at=datetime(2026, 4, 13, 11, 30, 0),
                    finished_at=datetime(2026, 4, 13, 11, 31, 0),
                ),
                Operation(
                    session_id=None,
                    operation_type=OperationType.DISPENSE,
                    operation_state=OperationState.FAILED,
                    user_id=1,
                    item_id=item.id,
                    slot_id=slot.id,
                    qty_requested=1,
                    qty_confirmed=None,
                    result=None,
                    error_code=None,
                    error_message=None,
                    hardware_context_json={},
                    business_context_json={},
                    started_at=datetime(2026, 4, 13, 10, 0, 0),
                    finished_at=datetime(2026, 4, 13, 10, 1, 0),
                ),
            )
        )
        session.commit()

        rows = OperationRepository(session).list_recent_for_admin(limit=20)

        assert len(rows) == 2
        assert rows[0] == AdminRecentOperationDTO(
            operation_id=rows[0].operation_id,
            started_at=datetime(2026, 4, 13, 11, 30, 0),
            operation_type=OperationType.REFILL_ITEM,
            quantity_delta=None,
            operation_state=OperationState.COMPLETED,
            user_code="operator-1",
            user_full_name="Operator One",
            item_name="Item One",
            quantity=4,
            slot_code="slot-1",
            cell_number=25,
        )
        assert rows[1] == AdminRecentOperationDTO(
            operation_id=rows[1].operation_id,
            started_at=datetime(2026, 4, 13, 10, 0, 0),
            operation_type=OperationType.DISPENSE,
            quantity_delta=None,
            operation_state=OperationState.FAILED,
            user_code="user-1",
            user_full_name="User One",
            item_name="Item One",
            quantity=1,
            slot_code="slot-1",
            cell_number=25,
        )


def test_list_problem_operations_for_admin_returns_failed_and_recovery_required_newest_first(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_import_duplicate_rfid_domain(session)
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

        session.add_all(
            (
                Operation(
                    session_id=None,
                    operation_type=OperationType.DISPENSE,
                    operation_state=OperationState.COMPLETED,
                    user_id=1,
                    item_id=item.id,
                    slot_id=slot.id,
                    qty_requested=1,
                    qty_confirmed=1,
                    result=None,
                    error_code=None,
                    error_message=None,
                    hardware_context_json={},
                    business_context_json={},
                    started_at=datetime(2026, 4, 13, 9, 0, 0),
                    finished_at=datetime(2026, 4, 13, 9, 1, 0),
                ),
                Operation(
                    session_id=None,
                    operation_type=OperationType.DISPENSE,
                    operation_state=OperationState.FAILED,
                    user_id=1,
                    item_id=item.id,
                    slot_id=slot.id,
                    qty_requested=2,
                    qty_confirmed=None,
                    result=None,
                    error_code=None,
                    error_message=None,
                    hardware_context_json={},
                    business_context_json={},
                    started_at=datetime(2026, 4, 13, 10, 0, 0),
                    finished_at=datetime(2026, 4, 13, 10, 1, 0),
                ),
                Operation(
                    session_id=None,
                    operation_type=OperationType.RETURN,
                    operation_state=OperationState.RECOVERY_REQUIRED,
                    user_id=2,
                    item_id=item.id,
                    slot_id=slot.id,
                    qty_requested=3,
                    qty_confirmed=None,
                    result=None,
                    error_code=None,
                    error_message=None,
                    hardware_context_json={},
                    business_context_json={},
                    started_at=datetime(2026, 4, 13, 11, 0, 0),
                    finished_at=datetime(2026, 4, 13, 11, 1, 0),
                ),
            )
        )
        session.commit()

        rows = OperationRepository(session).list_problem_for_admin(limit=20)

        assert rows == [
            AdminRecentOperationDTO(
                operation_id=rows[0].operation_id,
                started_at=datetime(2026, 4, 13, 11, 0, 0),
                operation_type=OperationType.RETURN,
                quantity_delta=None,
                operation_state=OperationState.RECOVERY_REQUIRED,
                user_code="operator-1",
                user_full_name="Operator One",
                item_name="Item One",
                quantity=3,
                slot_code="slot-1",
                cell_number=25,
            ),
            AdminRecentOperationDTO(
                operation_id=rows[1].operation_id,
                started_at=datetime(2026, 4, 13, 10, 0, 0),
                operation_type=OperationType.DISPENSE,
                quantity_delta=None,
                operation_state=OperationState.FAILED,
                user_code="user-1",
                user_full_name="User One",
                item_name="Item One",
                quantity=2,
                slot_code="slot-1",
                cell_number=25,
            ),
        ]


def test_list_recent_operations_for_admin_includes_inventory_adjustment_quantity_delta(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_import_duplicate_rfid_domain(session)
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

        operation = Operation(
            session_id=None,
            operation_type=OperationType.INVENTORY_ADJUSTMENT,
            operation_state=OperationState.COMPLETED,
            user_id=2,
            item_id=item.id,
            slot_id=slot.id,
            qty_requested=3,
            qty_confirmed=3,
            result=None,
            error_code=None,
            error_message=None,
            hardware_context_json={},
            business_context_json={},
            started_at=datetime(2026, 4, 13, 12, 0, 0),
            finished_at=datetime(2026, 4, 13, 12, 1, 0),
        )
        session.add(operation)
        session.flush()
        session.add(
            InventoryTransaction(
                slot_id=slot.id,
                item_id=item.id,
                operation_id=operation.id,
                session_id=None,
                transaction_type=InventoryTransactionType.INVENTORY_ADJUSTMENT,
                quantity_delta=3,
                quantity_before=2,
                quantity_after=5,
                comment=None,
                created_at=datetime(2026, 4, 13, 12, 0, 30),
            )
        )
        session.commit()

        rows = OperationRepository(session).list_recent_for_admin(limit=20)

        assert rows == [
            AdminRecentOperationDTO(
                operation_id=operation.id,
                started_at=datetime(2026, 4, 13, 12, 0, 0),
                operation_type=OperationType.INVENTORY_ADJUSTMENT,
                quantity_delta=3,
                operation_state=OperationState.COMPLETED,
                user_code="operator-1",
                user_full_name="Operator One",
                item_name="Item One",
                quantity=3,
                slot_code="slot-1",
                cell_number=25,
            )
        ]


def test_export_operations_csv_filters_inclusive_date_range_and_emits_expected_columns(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_import_duplicate_rfid_domain(session)
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

        session.add_all(
            (
                Operation(
                    session_id=None,
                    operation_type=OperationType.DISPENSE,
                    operation_state=OperationState.COMPLETED,
                    user_id=1,
                    item_id=item.id,
                    slot_id=slot.id,
                    qty_requested=1,
                    qty_confirmed=1,
                    result="ok",
                    error_code=None,
                    error_message=None,
                    hardware_context_json={},
                    business_context_json={},
                    started_at=datetime(2026, 4, 13, 8, 0, 0),
                    finished_at=datetime(2026, 4, 13, 8, 5, 0),
                ),
                Operation(
                    session_id=None,
                    operation_type=OperationType.RETURN,
                    operation_state=OperationState.FAILED,
                    user_id=2,
                    item_id=item.id,
                    slot_id=slot.id,
                    qty_requested=2,
                    qty_confirmed=None,
                    result="hardware_error",
                    error_code="lock_timeout",
                    error_message="Door lock timeout",
                    hardware_context_json={},
                    business_context_json={},
                    started_at=datetime(2026, 4, 14, 9, 0, 0),
                    finished_at=datetime(2026, 4, 14, 9, 10, 0),
                ),
                Operation(
                    session_id=None,
                    operation_type=OperationType.INVENTORY_ADJUSTMENT,
                    operation_state=OperationState.COMPLETED,
                    user_id=2,
                    item_id=item.id,
                    slot_id=slot.id,
                    qty_requested=3,
                    qty_confirmed=3,
                    result="ok",
                    error_code=None,
                    error_message=None,
                    hardware_context_json={},
                    business_context_json={},
                    started_at=datetime(2026, 4, 14, 10, 0, 0),
                    finished_at=datetime(2026, 4, 14, 10, 5, 0),
                ),
                Operation(
                    session_id=None,
                    operation_type=OperationType.INVENTORY_ADJUSTMENT,
                    operation_state=OperationState.COMPLETED,
                    user_id=2,
                    item_id=item.id,
                    slot_id=slot.id,
                    qty_requested=2,
                    qty_confirmed=2,
                    result="ok",
                    error_code=None,
                    error_message=None,
                    hardware_context_json={},
                    business_context_json={},
                    started_at=datetime(2026, 4, 14, 11, 0, 0),
                    finished_at=datetime(2026, 4, 14, 11, 5, 0),
                ),
                Operation(
                    session_id=None,
                    operation_type=OperationType.REFILL_ITEM,
                    operation_state=OperationState.COMPLETED,
                    user_id=2,
                    item_id=item.id,
                    slot_id=slot.id,
                    qty_requested=4,
                    qty_confirmed=4,
                    result="ok",
                    error_code=None,
                    error_message=None,
                    hardware_context_json={},
                    business_context_json={},
                    started_at=datetime(2026, 4, 15, 7, 0, 0),
                    finished_at=datetime(2026, 4, 15, 7, 20, 0),
                ),
            )
        )
        session.flush()
        session.add_all(
            (
                InventoryTransaction(
                    slot_id=slot.id,
                    item_id=item.id,
                    operation_id=3,
                    session_id=None,
                    transaction_type=InventoryTransactionType.INVENTORY_ADJUSTMENT,
                    quantity_delta=3,
                    quantity_before=2,
                    quantity_after=5,
                    comment=None,
                    created_at=datetime(2026, 4, 14, 10, 0, 30),
                ),
                InventoryTransaction(
                    slot_id=slot.id,
                    item_id=item.id,
                    operation_id=4,
                    session_id=None,
                    transaction_type=InventoryTransactionType.INVENTORY_ADJUSTMENT,
                    quantity_delta=-2,
                    quantity_before=5,
                    quantity_after=3,
                    comment=None,
                    created_at=datetime(2026, 4, 14, 11, 0, 30),
                ),
            )
        )
        session.commit()

        exported_csv = AdminOperationService(OperationRepository(session)).export_operations_csv(
            date_from=date(2026, 4, 14),
            date_to=date(2026, 4, 14),
        )

        assert exported_csv == "\n".join(
            (
                "operation_id,started_at,finished_at,operation_type,operation_state,user_code,user_full_name,item_name,quantity,slot_code,result,error_code,error_message",
                f"2,2026-04-14T09:00:00,2026-04-14T09:10:00,Возврат,failed,operator-1,Operator One,Item One,2,slot-1,hardware_error,lock_timeout,Door lock timeout",
                f"3,2026-04-14T10:00:00,2026-04-14T10:05:00,Пополнение,completed,operator-1,Operator One,Item One,3,slot-1,ok,,",
                f"4,2026-04-14T11:00:00,2026-04-14T11:05:00,Изъятие,completed,operator-1,Operator One,Item One,2,slot-1,ok,,",
                "",
            )
        )


def test_export_operations_csv_rejects_reversed_date_range(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        _seed_import_duplicate_rfid_domain(session)
        service = AdminOperationService(OperationRepository(session))

        with pytest.raises(ValidationError) as exc_info:
            service.export_operations_csv(
                date_from=date(2026, 4, 15),
                date_to=date(2026, 4, 14),
            )

        assert str(exc_info.value) == "date_from must be less than or equal to date_to"


def _seed_import_duplicate_rfid_domain(session: Session) -> None:
    user_role = Role(code=RoleCode.USER, name="User")
    operator_role = Role(code=RoleCode.OPERATOR, name="Operator")
    session.add_all((user_role, operator_role))
    session.flush()

    assigned_user = User(
        role_id=user_role.id,
        user_code="user-1",
        full_name="User One",
        status=UserStatus.ACTIVE,
        dispense_restriction_policy=DispenseRestrictionPolicy.UNLIMITED,
        is_active=True,
    )
    operator_user = User(
        role_id=operator_role.id,
        user_code="operator-1",
        full_name="Operator One",
        status=UserStatus.ACTIVE,
        dispense_restriction_policy=DispenseRestrictionPolicy.ONCE_PER_DAY,
        is_active=True,
    )
    session.add_all((assigned_user, operator_user))
    session.flush()

    session.add(
        UserRfidCard(
            user_id=assigned_user.id,
            card_uid="000FE2767C0045",
            is_active=True,
            issued_at=assigned_user.created_at,
            revoked_at=None,
        )
    )
    session.commit()


def _persisted_item_status(session: Session, status: ItemStatus) -> str:
    bind = session.get_bind()
    assert bind is not None
    processor = Item.__table__.c.status.type.bind_processor(bind.dialect)
    assert processor is not None
    persisted = processor(status)
    assert persisted is not None
    return persisted
