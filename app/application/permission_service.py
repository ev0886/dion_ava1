from __future__ import annotations

from dataclasses import dataclass

from app.application.audit import record_audit
from app.application.dto.management import PermissionDetailDTO, PermissionListResultDTO
from app.application.exceptions import ConflictError, NotFoundError, ValidationError
from app.application.time import utc_now
from app.persistence.models import Item, ItemGroup, Permission
from app.persistence.repositories.inventory import InventoryRepository
from app.persistence.repositories.logs import AuditLogRepository
from app.persistence.repositories.users import UserRepository


@dataclass(slots=True)
class PermissionService:
    user_repository: UserRepository
    inventory_repository: InventoryRepository
    audit_log_repository: AuditLogRepository

    def assign_permission(
        self,
        *,
        user_id: int,
        item_id: int | None = None,
        item_group_id: int | None = None,
        can_dispense: bool = False,
        can_return: bool = False,
        comment: str | None = None,
        actor_user_id: int | None = None,
    ) -> PermissionDetailDTO:
        self._require_user(user_id)
        target = self._resolve_target(item_id=item_id, item_group_id=item_group_id)
        if not can_dispense and not can_return:
            raise ValidationError("At least one permission flag must be enabled")
        duplicate = self.inventory_repository.find_active_equivalent_permission(
            user_id=user_id,
            item_id=item_id,
            item_group_id=item_group_id,
            can_dispense=can_dispense,
            can_return=can_return,
        )
        if duplicate is not None:
            raise ConflictError("Active equivalent permission already exists")

        permission = Permission(
            user_id=user_id,
            item_id=item_id,
            item_group_id=item_group_id,
            can_dispense=can_dispense,
            can_return=can_return,
            valid_from=utc_now(),
            valid_to=None,
            comment=comment,
        )
        self.inventory_repository.add_permission(permission)
        self.inventory_repository.session.flush()
        record_audit(
            self.audit_log_repository,
            entity_type="permission",
            entity_id=str(permission.id),
            action="assign",
            actor_user_id=actor_user_id,
            comment=comment,
            before=None,
            after=self._snapshot_permission(permission, *target),
        )
        self.inventory_repository.session.commit()
        return self._to_permission_detail(permission)

    def revoke_permission(
        self,
        *,
        permission_id: int,
        actor_user_id: int | None = None,
        comment: str | None = None,
    ) -> PermissionDetailDTO:
        permission = self._require_permission(permission_id)
        before = self._snapshot_permission(permission, *self._load_permission_target(permission))
        now = utc_now()
        if permission.valid_to is not None and permission.valid_to <= now:
            raise ConflictError(f"Permission is already revoked: {permission_id}")
        permission.valid_to = now
        self.inventory_repository.session.flush()
        record_audit(
            self.audit_log_repository,
            entity_type="permission",
            entity_id=str(permission.id),
            action="revoke",
            actor_user_id=actor_user_id,
            comment=comment,
            before=before,
            after=self._snapshot_permission(permission, *self._load_permission_target(permission)),
        )
        self.inventory_repository.session.commit()
        return self._to_permission_detail(permission)

    def list_permissions_for_user(self, user_id: int) -> PermissionListResultDTO:
        self._require_user(user_id)
        permissions = self.inventory_repository.list_permissions_for_user(user_id)
        return PermissionListResultDTO(
            user_id=user_id,
            permissions=tuple(self._to_permission_detail(permission) for permission in permissions),
        )

    def _require_user(self, user_id: int) -> None:
        if user_id <= 0:
            raise ValidationError("user_id must be positive")
        if self.user_repository.get_by_id(user_id) is None:
            raise NotFoundError(f"User not found: {user_id}")

    def _require_permission(self, permission_id: int) -> Permission:
        if permission_id <= 0:
            raise ValidationError("permission_id must be positive")
        permission = self.inventory_repository.get_permission(permission_id)
        if permission is None:
            raise NotFoundError(f"Permission not found: {permission_id}")
        return permission

    def _resolve_target(self, *, item_id: int | None, item_group_id: int | None) -> tuple[str, Item | ItemGroup]:
        if item_id is None and item_group_id is None:
            raise ValidationError("permission must target either item or item_group")
        if item_id is not None and item_group_id is not None:
            raise ValidationError("permission cannot target both item and item_group")
        if item_id is not None:
            if item_id <= 0:
                raise ValidationError("item_id must be positive")
            item = self.inventory_repository.get_item(item_id)
            if item is None:
                raise NotFoundError(f"Item not found: {item_id}")
            return ("item", item)
        if item_group_id is None or item_group_id <= 0:
            raise ValidationError("item_group_id must be positive")
        group = self.inventory_repository.get_item_group(item_group_id)
        if group is None:
            raise NotFoundError(f"Item group not found: {item_group_id}")
        return ("item_group", group)

    def _load_permission_target(self, permission: Permission) -> tuple[str, Item | ItemGroup]:
        return self._resolve_target(item_id=permission.item_id, item_group_id=permission.item_group_id)

    def _to_permission_detail(self, permission: Permission) -> PermissionDetailDTO:
        target_type, target = self._load_permission_target(permission)
        now = utc_now()
        is_active = permission.valid_to is None or permission.valid_to > now
        return PermissionDetailDTO(
            permission_id=permission.id,
            user_id=permission.user_id,
            item_id=permission.item_id,
            item_group_id=permission.item_group_id,
            target_type=target_type,
            target_code=target.sku if isinstance(target, Item) else target.code,
            target_name=target.name,
            can_dispense=permission.can_dispense,
            can_return=permission.can_return,
            valid_from=permission.valid_from,
            valid_to=permission.valid_to,
            is_active=is_active,
            comment=permission.comment,
        )

    def _snapshot_permission(self, permission: Permission, target_type: str, target: Item | ItemGroup) -> dict[str, object]:
        return {
            "user_id": permission.user_id,
            "item_id": permission.item_id,
            "item_group_id": permission.item_group_id,
            "target_type": target_type,
            "target_code": target.sku if isinstance(target, Item) else target.code,
            "can_dispense": permission.can_dispense,
            "can_return": permission.can_return,
            "valid_to": permission.valid_to.isoformat() if permission.valid_to is not None else None,
        }
