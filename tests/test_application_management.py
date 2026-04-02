from __future__ import annotations

from pathlib import Path

import pytest

from app.application.composition import create_bootstrapped_application_container
from app.application.exceptions import ConflictError, InvalidStateTransitionError
from app.config import AppSettings
from app.domain.enums import BindingType, ItemStatus, RoleCode, SlotStatus, SlotType, UserStatus
from app.persistence.models import AuditLog, InventoryBalance, Item, ItemGroup, Permission, Role, Slot, SlotItemBinding, User, UserRfidCard


def test_user_create_happy_path(tmp_path: Path) -> None:
    container = _container(tmp_path, "user_create.sqlite3")
    try:
        role_id = _seed_roles(container)["user"]

        result = container.services.users.create_user(
            user_code="user-100",
            full_name="User One Hundred",
            role_id=role_id,
            actor_user_id=None,
            comment="create user",
        )

        assert result.user_code == "user-100"
        assert result.full_name == "User One Hundred"
        assert result.role_id == role_id
        assert result.status is UserStatus.ACTIVE
        assert result.is_active is True
    finally:
        container.close()


def test_duplicate_user_code_rejection(tmp_path: Path) -> None:
    container = _container(tmp_path, "user_duplicate.sqlite3")
    try:
        role_id = _seed_roles(container)["user"]
        container.services.users.create_user(user_code="dup-user", full_name="Original", role_id=role_id)

        with pytest.raises(ConflictError, match="user_code already exists"):
            container.services.users.create_user(user_code="dup-user", full_name="Duplicate", role_id=role_id)
    finally:
        container.close()


def test_user_update_deactivate_activate_behavior(tmp_path: Path) -> None:
    container = _container(tmp_path, "user_update.sqlite3")
    try:
        role_ids = _seed_roles(container)
        user_id = _seed_user(container, role_ids["user"], user_code="user-200")

        updated = container.services.users.update_user(
            user_id=user_id,
            full_name="Updated User",
            role_id=role_ids["operator"],
        )
        inactive = container.services.users.set_user_active(user_id=user_id, is_active=False)
        active = container.services.users.set_user_active(user_id=user_id, is_active=True)

        assert updated.full_name == "Updated User"
        assert updated.role_code is RoleCode.OPERATOR
        assert inactive.status is UserStatus.INACTIVE
        assert inactive.is_active is False
        assert active.status is UserStatus.ACTIVE
        assert active.is_active is True

        with pytest.raises(InvalidStateTransitionError, match="already active"):
            container.services.users.set_user_active(user_id=user_id, is_active=True)
    finally:
        container.close()


def test_item_create_happy_path(tmp_path: Path) -> None:
    container = _container(tmp_path, "item_create.sqlite3")
    try:
        item_group_id = _seed_item_group(container)

        result = container.services.items.create_item(
            sku="sku-100",
            name="Item Hundred",
            unit="pcs",
            item_group_id=item_group_id,
            min_level=2,
            return_allowed=True,
        )

        assert result.sku == "sku-100"
        assert result.item_group_id == item_group_id
        assert result.status is ItemStatus.ACTIVE
        assert result.inventory_summary.total_quantity == 0
    finally:
        container.close()


def test_duplicate_sku_rejection(tmp_path: Path) -> None:
    container = _container(tmp_path, "item_duplicate.sqlite3")
    try:
        container.services.items.create_item(sku="dup-sku", name="First", unit="pcs")

        with pytest.raises(ConflictError, match="sku already exists"):
            container.services.items.create_item(sku="dup-sku", name="Second", unit="pcs")
    finally:
        container.close()


def test_item_update_deactivate_activate_behavior(tmp_path: Path) -> None:
    container = _container(tmp_path, "item_update.sqlite3")
    try:
        item_group_id = _seed_item_group(container)
        item_id = _seed_item(container, sku="sku-200")

        updated = container.services.items.update_item(
            item_id=item_id,
            name="Updated Item",
            item_group_id=item_group_id,
            min_level=3,
        )
        inactive = container.services.items.set_item_active(item_id=item_id, is_active=False)
        active = container.services.items.set_item_active(item_id=item_id, is_active=True)

        assert updated.name == "Updated Item"
        assert updated.item_group_id == item_group_id
        assert updated.min_level == 3
        assert inactive.status is ItemStatus.INACTIVE
        assert active.status is ItemStatus.ACTIVE

        with pytest.raises(InvalidStateTransitionError, match="already active"):
            container.services.items.set_item_active(item_id=item_id, is_active=True)
    finally:
        container.close()


def test_permission_assign_happy_path_item(tmp_path: Path) -> None:
    container = _container(tmp_path, "permission_item.sqlite3")
    try:
        role_ids = _seed_roles(container)
        user_id = _seed_user(container, role_ids["user"], user_code="perm-user-item")
        item_id = _seed_item(container, sku="perm-item")

        result = container.services.permissions.assign_permission(
            user_id=user_id,
            item_id=item_id,
            can_dispense=True,
        )

        assert result.user_id == user_id
        assert result.item_id == item_id
        assert result.target_type == "item"
        assert result.is_active is True
    finally:
        container.close()


def test_permission_assign_happy_path_item_group(tmp_path: Path) -> None:
    container = _container(tmp_path, "permission_group.sqlite3")
    try:
        role_ids = _seed_roles(container)
        user_id = _seed_user(container, role_ids["user"], user_code="perm-user-group")
        item_group_id = _seed_item_group(container)

        result = container.services.permissions.assign_permission(
            user_id=user_id,
            item_group_id=item_group_id,
            can_return=True,
        )

        assert result.user_id == user_id
        assert result.item_group_id == item_group_id
        assert result.target_type == "item_group"
        assert result.is_active is True
    finally:
        container.close()


def test_duplicate_permission_rejection(tmp_path: Path) -> None:
    container = _container(tmp_path, "permission_duplicate.sqlite3")
    try:
        role_ids = _seed_roles(container)
        user_id = _seed_user(container, role_ids["user"], user_code="perm-dup-user")
        item_id = _seed_item(container, sku="perm-dup-item")
        container.services.permissions.assign_permission(user_id=user_id, item_id=item_id, can_dispense=True)

        with pytest.raises(ConflictError, match="Active equivalent permission already exists"):
            container.services.permissions.assign_permission(user_id=user_id, item_id=item_id, can_dispense=True)
    finally:
        container.close()


def test_permission_revoke_path(tmp_path: Path) -> None:
    container = _container(tmp_path, "permission_revoke.sqlite3")
    try:
        role_ids = _seed_roles(container)
        user_id = _seed_user(container, role_ids["user"], user_code="perm-revoke-user")
        item_id = _seed_item(container, sku="perm-revoke-item")
        assigned = container.services.permissions.assign_permission(user_id=user_id, item_id=item_id, can_dispense=True)

        revoked = container.services.permissions.revoke_permission(permission_id=assigned.permission_id)

        assert revoked.permission_id == assigned.permission_id
        assert revoked.is_active is False
        assert revoked.valid_to is not None
    finally:
        container.close()


def test_audit_log_creation_for_representative_mutations(tmp_path: Path) -> None:
    container = _container(tmp_path, "audit.sqlite3")
    try:
        role_ids = _seed_roles(container)
        user = container.services.users.create_user(
            user_code="audit-user",
            full_name="Audit User",
            role_id=role_ids["user"],
            actor_user_id=None,
            comment="created",
        )
        item = container.services.items.create_item(
            sku="audit-item",
            name="Audit Item",
            unit="pcs",
            actor_user_id=None,
            comment="created",
        )
        container.services.permissions.assign_permission(
            user_id=user.user_id,
            item_id=item.item_id,
            can_dispense=True,
            actor_user_id=None,
            comment="assigned",
        )

        with container.session_factory() as session:
            audit_logs = session.query(AuditLog).order_by(AuditLog.id.asc()).all()

        assert len(audit_logs) == 3
        assert [entry.entity_type for entry in audit_logs] == ["user", "item", "permission"]
        assert audit_logs[0].action == "create"
        assert audit_logs[1].action == "create"
        assert audit_logs[2].action == "assign"
    finally:
        container.close()


def _container(tmp_path: Path, sqlite_filename: str):
    return create_bootstrapped_application_container(
        AppSettings(
            data_dir=tmp_path,
            sqlite_filename=sqlite_filename,
            alembic_config_path=Path("alembic.ini"),
        )
    )


def _seed_roles(container) -> dict[str, int]:
    with container.session_factory() as session:
        admin = Role(code=RoleCode.ADMIN, name="Admin")
        operator = Role(code=RoleCode.OPERATOR, name="Operator")
        user = Role(code=RoleCode.USER, name="User")
        session.add_all((admin, operator, user))
        session.commit()
        return {"admin": admin.id, "operator": operator.id, "user": user.id}


def _seed_user(container, role_id: int, *, user_code: str) -> int:
    with container.session_factory() as session:
        user = User(
            role_id=role_id,
            user_code=user_code,
            full_name=f"{user_code} name",
            status=UserStatus.ACTIVE,
            is_active=True,
        )
        session.add(user)
        session.commit()
        return user.id


def _seed_item_group(container) -> int:
    with container.session_factory() as session:
        group = ItemGroup(code="group-1", name="Group One", description=None, is_active=True)
        session.add(group)
        session.commit()
        return group.id


def _seed_item(container, *, sku: str) -> int:
    with container.session_factory() as session:
        item = Item(
            item_group_id=None,
            sku=sku,
            name=f"{sku} name",
            description=None,
            unit="pcs",
            return_allowed=True,
            min_level=0,
            status=ItemStatus.ACTIVE,
        )
        session.add(item)
        session.commit()
        return item.id
