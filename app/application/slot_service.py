from __future__ import annotations

from dataclasses import dataclass

from app.application.dto.inventory import (
    SlotBindingDTO,
    SlotDTO,
    SlotDetailDTO,
)
from app.application.exceptions import ConflictError, NotFoundError, ValidationError
from app.application.time import utc_now
from app.domain.enums import BindingType, SlotStatus, SlotType
from app.persistence.models import AuditLog, InventoryBalance, Slot, SlotItemBinding
from app.persistence.repositories.inventory import InventoryRepository
from app.persistence.repositories.logs import AuditLogRepository


@dataclass(slots=True)
class SlotService:
    inventory_repository: InventoryRepository
    audit_log_repository: AuditLogRepository

    def create_slot(
        self,
        *,
        code: str,
        slot_type: SlotType | str,
        drum_position: int,
        board_address: int,
        lock_number: int,
        capacity: int | None,
        status: SlotStatus | str,
        actor_user_id: int | None = None,
        reason_code: str | None = None,
        comment: str | None = None,
    ) -> SlotDetailDTO:
        normalized_code = self._validate_code(code)
        normalized_slot_type = self._coerce_slot_type(slot_type)
        normalized_status = self._coerce_slot_status(status)
        normalized_drum_position = self._validate_drum_position(drum_position)
        normalized_board_address = self._validate_positive_int(board_address, field_name="board_address")
        normalized_lock_number = self._validate_positive_int(lock_number, field_name="lock_number")
        normalized_capacity = self._validate_capacity(capacity)

        if self.inventory_repository.get_slot_by_code(normalized_code) is not None:
            raise ConflictError(f"Slot code already exists: {normalized_code}")

        slot = Slot(
            code=normalized_code,
            slot_type=normalized_slot_type,
            drum_position=normalized_drum_position,
            board_address=normalized_board_address,
            lock_number=normalized_lock_number,
            capacity=normalized_capacity,
            status=normalized_status,
        )
        self.inventory_repository.add_slot(slot)
        self.inventory_repository.session.flush()
        self._record_audit(
            entity_type="slot",
            entity_id=str(slot.id),
            action="create",
            actor_user_id=actor_user_id,
            reason_code=reason_code,
            comment=comment,
            before_json=None,
            after_json=self._slot_payload(slot),
        )
        self.inventory_repository.session.commit()
        return self.get_slot_details(slot.id)

    def update_slot(
        self,
        *,
        slot_id: int,
        code: str | None = None,
        slot_type: SlotType | str | None = None,
        drum_position: int | None = None,
        board_address: int | None = None,
        lock_number: int | None = None,
        capacity: int | None = None,
        status: SlotStatus | str | None = None,
        actor_user_id: int | None = None,
        reason_code: str | None = None,
        comment: str | None = None,
    ) -> SlotDetailDTO:
        slot = self._require_slot(slot_id)
        before = self._slot_payload(slot)

        if code is not None:
            normalized_code = self._validate_code(code)
            existing = self.inventory_repository.get_slot_by_code(normalized_code)
            if existing is not None and existing.id != slot.id:
                raise ConflictError(f"Slot code already exists: {normalized_code}")
            slot.code = normalized_code
        if slot_type is not None:
            slot.slot_type = self._coerce_slot_type(slot_type)
        if drum_position is not None:
            slot.drum_position = self._validate_drum_position(drum_position)
        if board_address is not None:
            slot.board_address = self._validate_positive_int(board_address, field_name="board_address")
        if lock_number is not None:
            slot.lock_number = self._validate_positive_int(lock_number, field_name="lock_number")
        if capacity is not None:
            slot.capacity = self._validate_capacity(capacity)
        if status is not None:
            slot.status = self._coerce_slot_status(status)

        self.inventory_repository.session.flush()
        self._record_audit(
            entity_type="slot",
            entity_id=str(slot.id),
            action="update",
            actor_user_id=actor_user_id,
            reason_code=reason_code,
            comment=comment,
            before_json=before,
            after_json=self._slot_payload(slot),
        )
        self.inventory_repository.session.commit()
        return self.get_slot_details(slot.id)

    def activate_slot(
        self,
        *,
        slot_id: int,
        actor_user_id: int | None = None,
        reason_code: str | None = None,
        comment: str | None = None,
    ) -> SlotDetailDTO:
        return self._set_slot_status(
            slot_id=slot_id,
            status=SlotStatus.ACTIVE,
            action="activate",
            actor_user_id=actor_user_id,
            reason_code=reason_code,
            comment=comment,
        )

    def deactivate_slot(
        self,
        *,
        slot_id: int,
        actor_user_id: int | None = None,
        reason_code: str | None = None,
        comment: str | None = None,
    ) -> SlotDetailDTO:
        return self._set_slot_status(
            slot_id=slot_id,
            status=SlotStatus.DISABLED,
            action="deactivate",
            actor_user_id=actor_user_id,
            reason_code=reason_code,
            comment=comment,
        )

    def get_slot_details(self, slot_id: int) -> SlotDetailDTO:
        slot = self._require_slot(slot_id)
        active_bindings = self.inventory_repository.list_bindings(slot_id=slot.id, is_active=True)
        bound_item_ids = {binding.item_id for binding in active_bindings}
        balances = tuple(
            self._to_balance_dto(balance)
            for balance in self.inventory_repository.list_balances(slot_id=slot.id)
            if balance.item_id in bound_item_ids
        )
        return SlotDetailDTO(
            slot=self._to_slot_dto(slot),
            active_bindings=tuple(self._to_binding_dto(binding) for binding in active_bindings),
            inventory_balances=balances,
        )

    def list_slots(self) -> tuple[SlotDTO, ...]:
        return tuple(self._to_slot_dto(slot) for slot in self.inventory_repository.list_slots())

    def create_binding(
        self,
        *,
        slot_id: int,
        item_id: int,
        binding_type: BindingType | str,
        actor_user_id: int | None = None,
        reason_code: str | None = None,
        comment: str | None = None,
    ) -> SlotBindingDTO:
        normalized_slot_id = self._validate_positive_int(slot_id, field_name="slot_id")
        normalized_item_id = self._validate_positive_int(item_id, field_name="item_id")
        normalized_binding_type = self._coerce_binding_type(binding_type)

        self._require_slot(normalized_slot_id)
        self._require_item(normalized_item_id)

        existing = self.inventory_repository.find_binding(
            slot_id=normalized_slot_id,
            item_id=normalized_item_id,
            binding_type=normalized_binding_type,
        )
        if existing is not None:
            if existing.is_active:
                raise ConflictError("Active binding already exists for slot, item, and binding_type")
            raise ConflictError("Binding already exists and is inactive")

        binding = SlotItemBinding(
            slot_id=normalized_slot_id,
            item_id=normalized_item_id,
            binding_type=normalized_binding_type,
            is_active=True,
            valid_from=utc_now(),
            valid_to=None,
        )
        self.inventory_repository.add_binding(binding)
        self.inventory_repository.session.flush()
        self._record_audit(
            entity_type="slot_item_binding",
            entity_id=str(binding.id),
            action="create",
            actor_user_id=actor_user_id,
            reason_code=reason_code,
            comment=comment,
            before_json=None,
            after_json=self._binding_payload(binding),
        )
        self.inventory_repository.session.commit()
        return self._to_binding_dto(binding)

    def deactivate_binding(
        self,
        *,
        binding_id: int,
        actor_user_id: int | None = None,
        reason_code: str | None = None,
        comment: str | None = None,
    ) -> SlotBindingDTO:
        binding = self._require_binding(binding_id)
        if not binding.is_active:
            raise ConflictError(f"Binding is already inactive: {binding_id}")

        before = self._binding_payload(binding)
        binding.is_active = False
        binding.valid_to = binding.valid_to or utc_now()
        self.inventory_repository.session.flush()
        self._record_audit(
            entity_type="slot_item_binding",
            entity_id=str(binding.id),
            action="deactivate",
            actor_user_id=actor_user_id,
            reason_code=reason_code,
            comment=comment,
            before_json=before,
            after_json=self._binding_payload(binding),
        )
        self.inventory_repository.session.commit()
        return self._to_binding_dto(binding)

    def list_bindings_for_slot(self, slot_id: int) -> tuple[SlotBindingDTO, ...]:
        self._require_slot(slot_id)
        return tuple(
            self._to_binding_dto(binding)
            for binding in self.inventory_repository.list_bindings(slot_id=slot_id)
        )

    def list_bindings_for_item(self, item_id: int) -> tuple[SlotBindingDTO, ...]:
        self._require_item(item_id)
        return tuple(
            self._to_binding_dto(binding)
            for binding in self.inventory_repository.list_bindings(item_id=item_id)
        )

    def _set_slot_status(
        self,
        *,
        slot_id: int,
        status: SlotStatus,
        action: str,
        actor_user_id: int | None,
        reason_code: str | None,
        comment: str | None,
    ) -> SlotDetailDTO:
        slot = self._require_slot(slot_id)
        before = self._slot_payload(slot)
        slot.status = status
        self.inventory_repository.session.flush()
        self._record_audit(
            entity_type="slot",
            entity_id=str(slot.id),
            action=action,
            actor_user_id=actor_user_id,
            reason_code=reason_code,
            comment=comment,
            before_json=before,
            after_json=self._slot_payload(slot),
        )
        self.inventory_repository.session.commit()
        return self.get_slot_details(slot.id)

    def _require_slot(self, slot_id: int) -> Slot:
        normalized_slot_id = self._validate_positive_int(slot_id, field_name="slot_id")
        slot = self.inventory_repository.get_slot(normalized_slot_id)
        if slot is None:
            raise NotFoundError(f"Slot not found: {normalized_slot_id}")
        return slot

    def _require_item(self, item_id: int):
        normalized_item_id = self._validate_positive_int(item_id, field_name="item_id")
        item = self.inventory_repository.get_item(normalized_item_id)
        if item is None:
            raise NotFoundError(f"Item not found: {normalized_item_id}")
        return item

    def _require_binding(self, binding_id: int) -> SlotItemBinding:
        normalized_binding_id = self._validate_positive_int(binding_id, field_name="binding_id")
        binding = self.inventory_repository.get_binding(normalized_binding_id)
        if binding is None:
            raise NotFoundError(f"Binding not found: {normalized_binding_id}")
        return binding

    def _record_audit(
        self,
        *,
        entity_type: str,
        entity_id: str,
        action: str,
        actor_user_id: int | None,
        reason_code: str | None,
        comment: str | None,
        before_json: dict[str, object] | None,
        after_json: dict[str, object] | None,
    ) -> None:
        self.audit_log_repository.add(
            AuditLog(
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                actor_user_id=actor_user_id,
                reason_code=reason_code,
                comment=comment,
                before_json=before_json,
                after_json=after_json,
            )
        )

    @staticmethod
    def _validate_code(code: str) -> str:
        normalized = code.strip()
        if not normalized:
            raise ValidationError("code is required")
        return normalized

    @staticmethod
    def _validate_drum_position(drum_position: int) -> int:
        if drum_position < 0:
            raise ValidationError("drum_position must be non-negative")
        return drum_position

    @staticmethod
    def _validate_positive_int(value: int, *, field_name: str) -> int:
        if value <= 0:
            raise ValidationError(f"{field_name} must be positive")
        return value

    @staticmethod
    def _validate_capacity(capacity: int | None) -> int | None:
        if capacity is not None and capacity < 0:
            raise ValidationError("capacity cannot be negative")
        return capacity

    @staticmethod
    def _coerce_slot_type(slot_type: SlotType | str) -> SlotType:
        try:
            return slot_type if isinstance(slot_type, SlotType) else SlotType(slot_type)
        except ValueError as error:
            raise ValidationError(f"Invalid slot_type: {slot_type}") from error

    @staticmethod
    def _coerce_slot_status(status: SlotStatus | str) -> SlotStatus:
        try:
            return status if isinstance(status, SlotStatus) else SlotStatus(status)
        except ValueError as error:
            raise ValidationError(f"Invalid slot_status: {status}") from error

    @staticmethod
    def _coerce_binding_type(binding_type: BindingType | str) -> BindingType:
        try:
            return binding_type if isinstance(binding_type, BindingType) else BindingType(binding_type)
        except ValueError as error:
            raise ValidationError(f"Invalid binding_type: {binding_type}") from error

    @staticmethod
    def _to_slot_dto(slot: Slot) -> SlotDTO:
        return SlotDTO(
            slot_id=slot.id,
            code=slot.code,
            slot_type=slot.slot_type,
            drum_position=slot.drum_position,
            board_address=slot.board_address,
            lock_number=slot.lock_number,
            capacity=slot.capacity,
            status=slot.status,
        )

    @staticmethod
    def _to_binding_dto(binding: SlotItemBinding) -> SlotBindingDTO:
        return SlotBindingDTO(
            binding_id=binding.id,
            slot_id=binding.slot_id,
            item_id=binding.item_id,
            binding_type=binding.binding_type,
            is_active=binding.is_active,
            valid_from=binding.valid_from,
            valid_to=binding.valid_to,
        )

    @staticmethod
    def _to_balance_dto(balance: InventoryBalance):
        from app.application.dto.inventory import InventoryBalanceDTO

        return InventoryBalanceDTO(
            slot_id=balance.slot_id,
            item_id=balance.item_id,
            quantity=balance.quantity,
            updated_at=balance.updated_at,
        )

    @classmethod
    def _slot_payload(cls, slot: Slot) -> dict[str, object]:
        return {
            "id": slot.id,
            "code": slot.code,
            "slot_type": slot.slot_type.value,
            "drum_position": slot.drum_position,
            "board_address": slot.board_address,
            "lock_number": slot.lock_number,
            "capacity": slot.capacity,
            "status": slot.status.value,
        }

    @classmethod
    def _binding_payload(cls, binding: SlotItemBinding) -> dict[str, object]:
        return {
            "id": binding.id,
            "slot_id": binding.slot_id,
            "item_id": binding.item_id,
            "binding_type": binding.binding_type.value,
            "is_active": binding.is_active,
            "valid_from": binding.valid_from.isoformat() if binding.valid_from is not None else None,
            "valid_to": binding.valid_to.isoformat() if binding.valid_to is not None else None,
        }
