from __future__ import annotations

from dataclasses import dataclass

from app.application.audit import record_audit
from app.application.dto.management import (
    ItemDetailDTO,
    ItemInventorySummaryDTO,
    ItemListResultDTO,
    ItemSlotBindingDTO,
    ItemSummaryDTO,
)
from app.application.exceptions import ConflictError, InvalidStateTransitionError, NotFoundError, ValidationError
from app.domain.enums import ItemStatus
from app.persistence.models import InventoryBalance, Item, ItemGroup, SlotItemBinding
from app.persistence.repositories.inventory import InventoryRepository
from app.persistence.repositories.logs import AuditLogRepository


@dataclass(slots=True)
class ItemManagementService:
    inventory_repository: InventoryRepository
    audit_log_repository: AuditLogRepository

    def create_item(
        self,
        *,
        sku: str,
        name: str,
        unit: str,
        item_group_id: int | None = None,
        description: str | None = None,
        return_allowed: bool = False,
        min_level: int = 0,
        actor_user_id: int | None = None,
        comment: str | None = None,
    ) -> ItemDetailDTO:
        normalized_sku = self._require_text(sku, "sku")
        normalized_name = self._require_text(name, "name")
        normalized_unit = self._require_text(unit, "unit")
        if min_level < 0:
            raise ValidationError("min_level cannot be negative")
        group = self._require_item_group(item_group_id) if item_group_id is not None else None
        if self.inventory_repository.get_item_by_sku(normalized_sku) is not None:
            raise ConflictError(f"sku already exists: {normalized_sku}")

        item = Item(
            item_group_id=group.id if group is not None else None,
            sku=normalized_sku,
            name=normalized_name,
            description=description.strip() if description else None,
            unit=normalized_unit,
            return_allowed=return_allowed,
            min_level=min_level,
            status=ItemStatus.ACTIVE,
        )
        self.inventory_repository.add_item(item)
        self.inventory_repository.session.flush()
        record_audit(
            self.audit_log_repository,
            entity_type="item",
            entity_id=str(item.id),
            action="create",
            actor_user_id=actor_user_id,
            comment=comment,
            before=None,
            after=self._snapshot_item(item, group),
        )
        self.inventory_repository.session.commit()
        return self.get_item_details(item.id)

    def update_item(
        self,
        *,
        item_id: int,
        sku: str | None = None,
        name: str | None = None,
        unit: str | None = None,
        item_group_id: int | None = None,
        description: str | None = None,
        return_allowed: bool | None = None,
        min_level: int | None = None,
        actor_user_id: int | None = None,
        comment: str | None = None,
    ) -> ItemDetailDTO:
        item = self._require_item(item_id)
        before = self._snapshot_item(item, self._load_group(item.item_group_id))
        changed = False

        if sku is not None:
            normalized_sku = self._require_text(sku, "sku")
            existing = self.inventory_repository.get_item_by_sku(normalized_sku)
            if existing is not None and existing.id != item.id:
                raise ConflictError(f"sku already exists: {normalized_sku}")
            item.sku = normalized_sku
            changed = True
        if name is not None:
            item.name = self._require_text(name, "name")
            changed = True
        if unit is not None:
            item.unit = self._require_text(unit, "unit")
            changed = True
        if item_group_id is not None:
            item.item_group_id = self._require_item_group(item_group_id).id
            changed = True
        if description is not None:
            item.description = description.strip() or None
            changed = True
        if return_allowed is not None:
            item.return_allowed = return_allowed
            changed = True
        if min_level is not None:
            if min_level < 0:
                raise ValidationError("min_level cannot be negative")
            item.min_level = min_level
            changed = True

        if changed:
            self.inventory_repository.session.flush()
            record_audit(
                self.audit_log_repository,
                entity_type="item",
                entity_id=str(item.id),
                action="update",
                actor_user_id=actor_user_id,
                comment=comment,
                before=before,
                after=self._snapshot_item(item, self._load_group(item.item_group_id)),
            )
            self.inventory_repository.session.commit()
        return self.get_item_details(item.id)

    def set_item_active(
        self,
        *,
        item_id: int,
        is_active: bool,
        actor_user_id: int | None = None,
        comment: str | None = None,
    ) -> ItemDetailDTO:
        item = self._require_item(item_id)
        if item.status is ItemStatus.ARCHIVED:
            raise InvalidStateTransitionError("Archived item cannot be changed through this workflow")
        before = self._snapshot_item(item, self._load_group(item.item_group_id))
        if is_active:
            if item.status is ItemStatus.ACTIVE:
                raise InvalidStateTransitionError(f"Item is already active: {item_id}")
            item.status = ItemStatus.ACTIVE
            action = "activate"
        else:
            if item.status is ItemStatus.INACTIVE:
                raise InvalidStateTransitionError(f"Item is already inactive: {item_id}")
            item.status = ItemStatus.INACTIVE
            action = "deactivate"
        self.inventory_repository.session.flush()
        record_audit(
            self.audit_log_repository,
            entity_type="item",
            entity_id=str(item.id),
            action=action,
            actor_user_id=actor_user_id,
            comment=comment,
            before=before,
            after=self._snapshot_item(item, self._load_group(item.item_group_id)),
        )
        self.inventory_repository.session.commit()
        return self.get_item_details(item.id)

    def get_item_details(self, item_id: int) -> ItemDetailDTO:
        item = self._require_item(item_id)
        group = self._load_group(item.item_group_id)
        summary = self._to_summary_dto(item, group)
        bindings = tuple(self._to_binding_dto(binding) for binding in self.inventory_repository.list_active_bindings_for_item(item.id))
        balances = self.inventory_repository.list_balances_for_item(item.id)
        return ItemDetailDTO(
            item_id=summary.item_id,
            item_group_id=summary.item_group_id,
            item_group_code=summary.item_group_code,
            item_group_name=summary.item_group_name,
            sku=summary.sku,
            name=summary.name,
            description=summary.description,
            unit=summary.unit,
            return_allowed=summary.return_allowed,
            min_level=summary.min_level,
            status=summary.status,
            active_slot_bindings=bindings,
            inventory_summary=self._to_inventory_summary(balances),
        )

    def list_items(
        self,
        *,
        item_group_id: int | None = None,
        status: ItemStatus | None = None,
        search: str | None = None,
    ) -> ItemListResultDTO:
        if item_group_id is not None:
            self._require_item_group(item_group_id)
        items = self.inventory_repository.list_items(item_group_id=item_group_id, status=status, search=search)
        return ItemListResultDTO(
            items=tuple(self._to_summary_dto(item, self._load_group(item.item_group_id)) for item in items)
        )

    @staticmethod
    def _require_text(value: str, field_name: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValidationError(f"{field_name} is required")
        return normalized

    def _require_item(self, item_id: int) -> Item:
        if item_id <= 0:
            raise ValidationError("item_id must be positive")
        item = self.inventory_repository.get_item(item_id)
        if item is None:
            raise NotFoundError(f"Item not found: {item_id}")
        return item

    def _require_item_group(self, item_group_id: int) -> ItemGroup:
        if item_group_id <= 0:
            raise ValidationError("item_group_id must be positive")
        group = self.inventory_repository.get_item_group(item_group_id)
        if group is None:
            raise NotFoundError(f"Item group not found: {item_group_id}")
        return group

    def _load_group(self, item_group_id: int | None) -> ItemGroup | None:
        if item_group_id is None:
            return None
        return self.inventory_repository.get_item_group(item_group_id)

    def _to_summary_dto(self, item: Item, group: ItemGroup | None) -> ItemSummaryDTO:
        return ItemSummaryDTO(
            item_id=item.id,
            item_group_id=item.item_group_id,
            item_group_code=group.code if group is not None else None,
            item_group_name=group.name if group is not None else None,
            sku=item.sku,
            name=item.name,
            description=item.description,
            unit=item.unit,
            return_allowed=item.return_allowed,
            min_level=item.min_level,
            status=item.status,
        )

    def _snapshot_item(self, item: Item, group: ItemGroup | None) -> dict[str, object]:
        return {
            "sku": item.sku,
            "name": item.name,
            "item_group_id": item.item_group_id,
            "item_group_code": group.code if group is not None else None,
            "unit": item.unit,
            "return_allowed": item.return_allowed,
            "min_level": item.min_level,
            "status": item.status.value,
        }

    def _to_binding_dto(self, binding: SlotItemBinding) -> ItemSlotBindingDTO:
        slot = self.inventory_repository.get_slot(binding.slot_id)
        return ItemSlotBindingDTO(
            slot_id=binding.slot_id,
            slot_code=slot.code if slot is not None else f"slot-{binding.slot_id}",
            binding_type=binding.binding_type,
            is_active=binding.is_active,
            valid_from=binding.valid_from,
            valid_to=binding.valid_to,
        )

    @staticmethod
    def _to_inventory_summary(balances: list[InventoryBalance]) -> ItemInventorySummaryDTO:
        total_quantity = sum(balance.quantity for balance in balances)
        slot_quantities = tuple({"slot_id": balance.slot_id, "quantity": balance.quantity} for balance in balances)
        return ItemInventorySummaryDTO(total_quantity=total_quantity, slot_quantities=slot_quantities)
