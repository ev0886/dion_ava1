from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.application.dto.seed import SeedWorkflowResultDTO
from app.domain.constants import DEFAULT_ROLE_NAMES
from app.domain.enums import BindingType, ItemStatus, RoleCode, SlotStatus, SlotType, UserStatus
from app.persistence.models import (
    AuditLog,
    Backup,
    EventLog,
    Export,
    InventoryBalance,
    InventoryTransaction,
    Item,
    ManualResolutionAction,
    Operation,
    OperationSession,
    OperationStateHistory,
    Permission,
    RecoveryAction,
    RecoveryCase,
    RecoveryCaseEntity,
    Role,
    Slot,
    SlotItemBinding,
    User,
    UserCredential,
    UserRfidCard,
)
from app.persistence.repositories.logs import AuditLogRepository, EventLogRepository

_DEMO_TIMESTAMP = datetime(2025, 1, 1, 9, 0, 0)
_DEMO_USER_SPECS = (
    ("demo-admin", "Demo Administrator", RoleCode.ADMIN),
    ("demo-operator", "Demo Operator", RoleCode.OPERATOR),
    ("demo-user", "Demo User", RoleCode.USER),
)
_DEMO_ITEM_SPECS = (
    ("demo-glove-nitrile", "Nitrile Gloves", "pairs", True, 4),
    ("demo-mask-ffp2", "FFP2 Mask", "pcs", True, 2),
    ("demo-battery-aa", "AA Battery", "pcs", False, 1),
)
_DEMO_SLOT_SPECS = (
    ("demo-slot-a01", SlotType.UNIVERSAL, 1, 1, 1, 20),
    ("demo-slot-a02", SlotType.DISPENSE, 2, 1, 2, 15),
    ("demo-slot-r01", SlotType.RETURN, 3, 1, 3, 25),
)
_DEMO_BINDING_SPECS = (
    ("demo-slot-a01", "demo-glove-nitrile", BindingType.PRIMARY),
    ("demo-slot-a01", "demo-glove-nitrile", BindingType.RETURN),
    ("demo-slot-a02", "demo-battery-aa", BindingType.PRIMARY),
    ("demo-slot-r01", "demo-mask-ffp2", BindingType.RETURN),
)
_DEMO_BALANCE_SPECS = (
    ("demo-slot-a01", "demo-glove-nitrile", 12),
    ("demo-slot-a02", "demo-battery-aa", 8),
    ("demo-slot-r01", "demo-mask-ffp2", 2),
)
_SEED_EVENT_SOURCE = "seed_service"
_SEED_AUDIT_ENTITY_TYPE = "seed_workflow"


@dataclass(slots=True)
class SeedService:
    session: Session
    event_log_repository: EventLogRepository
    audit_log_repository: AuditLogRepository

    def initialize_base_reference_data(self) -> SeedWorkflowResultDTO:
        recorder = _SeedRecorder("seed_base_data")
        try:
            for role_code in RoleCode:
                role = self._find_role(role_code)
                if role is None:
                    self.session.add(
                        Role(
                            code=role_code,
                            name=DEFAULT_ROLE_NAMES[role_code],
                            description=f"Base role for {role_code.value} workflows.",
                        )
                    )
                    recorder.created("role", role_code.value)
                else:
                    recorder.skipped("role", role_code.value)
            self.session.flush()
            self._record_seed_action(recorder)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return recorder.build()

    def create_demo_data_set(self) -> SeedWorkflowResultDTO:
        recorder = _SeedRecorder("seed_demo_data")
        try:
            self._ensure_base_roles(recorder)
            role_ids = self._role_ids()

            for user_code, full_name, role_code in _DEMO_USER_SPECS:
                user = self._find_user(user_code)
                if user is None:
                    self.session.add(
                        User(
                            role_id=role_ids[role_code],
                            user_code=user_code,
                            full_name=full_name,
                            status=UserStatus.ACTIVE,
                            is_active=True,
                        )
                    )
                    recorder.created("user", user_code)
                else:
                    recorder.skipped("user", user_code)

            for sku, name, unit, return_allowed, min_level in _DEMO_ITEM_SPECS:
                item = self._find_item(sku)
                if item is None:
                    self.session.add(
                        Item(
                            item_group_id=None,
                            sku=sku,
                            name=name,
                            description=f"Deterministic demo item {sku}.",
                            unit=unit,
                            return_allowed=return_allowed,
                            min_level=min_level,
                            status=ItemStatus.ACTIVE,
                        )
                    )
                    recorder.created("item", sku)
                else:
                    recorder.skipped("item", sku)

            for code, slot_type, drum_position, board_address, lock_number, capacity in _DEMO_SLOT_SPECS:
                slot = self._find_slot(code)
                if slot is None:
                    self.session.add(
                        Slot(
                            code=code,
                            slot_type=slot_type,
                            drum_position=drum_position,
                            board_address=board_address,
                            lock_number=lock_number,
                            capacity=capacity,
                            status=SlotStatus.ACTIVE,
                        )
                    )
                    recorder.created("slot", code)
                else:
                    recorder.skipped("slot", code)

            self.session.flush()
            slot_ids = self._slot_ids()
            item_ids = self._item_ids()

            for slot_code, item_sku, binding_type in _DEMO_BINDING_SPECS:
                binding = self.session.execute(
                    select(SlotItemBinding).where(
                        SlotItemBinding.slot_id == slot_ids[slot_code],
                        SlotItemBinding.item_id == item_ids[item_sku],
                        SlotItemBinding.binding_type == binding_type,
                    )
                ).scalar_one_or_none()
                binding_key = f"{slot_code}:{item_sku}:{binding_type.value}"
                if binding is None:
                    self.session.add(
                        SlotItemBinding(
                            slot_id=slot_ids[slot_code],
                            item_id=item_ids[item_sku],
                            binding_type=binding_type,
                            is_active=True,
                            valid_from=_DEMO_TIMESTAMP,
                            valid_to=None,
                        )
                    )
                    recorder.created("binding", binding_key)
                else:
                    recorder.skipped("binding", binding_key)

            for slot_code, item_sku, quantity in _DEMO_BALANCE_SPECS:
                balance = self.session.execute(
                    select(InventoryBalance).where(
                        InventoryBalance.slot_id == slot_ids[slot_code],
                        InventoryBalance.item_id == item_ids[item_sku],
                    )
                ).scalar_one_or_none()
                balance_key = f"{slot_code}:{item_sku}"
                if balance is None:
                    self.session.add(
                        InventoryBalance(
                            slot_id=slot_ids[slot_code],
                            item_id=item_ids[item_sku],
                            quantity=quantity,
                        )
                    )
                    recorder.created("inventory_balance", balance_key)
                else:
                    recorder.skipped("inventory_balance", balance_key)

            self.session.flush()
            self._record_seed_action(recorder)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return recorder.build()

    def reset_demo_data(self) -> SeedWorkflowResultDTO:
        recorder = _SeedRecorder("reset_demo_data")
        try:
            demo_users = {
                user.user_code: user
                for user in self.session.execute(select(User).where(User.user_code.in_(self._demo_user_codes()))).scalars()
            }
            demo_items = {
                item.sku: item
                for item in self.session.execute(select(Item).where(Item.sku.in_(self._demo_item_skus()))).scalars()
            }
            demo_slots = {
                slot.code: slot
                for slot in self.session.execute(select(Slot).where(Slot.code.in_(self._demo_slot_codes()))).scalars()
            }

            for user_code, _full_name, _role_code in _DEMO_USER_SPECS:
                self._record_presence(recorder, "user", user_code, user_code in demo_users)
            for sku, _name, _unit, _return_allowed, _min_level in _DEMO_ITEM_SPECS:
                self._record_presence(recorder, "item", sku, sku in demo_items)
            for code, _slot_type, _drum_position, _board_address, _lock_number, _capacity in _DEMO_SLOT_SPECS:
                self._record_presence(recorder, "slot", code, code in demo_slots)

            demo_user_ids = {user.id for user in demo_users.values()}
            demo_item_ids = {item.id for item in demo_items.values()}
            demo_slot_ids = {slot.id for slot in demo_slots.values()}

            session_ids = set()
            if demo_user_ids:
                session_ids.update(
                    self.session.execute(
                        select(OperationSession.id).where(OperationSession.started_by_user_id.in_(demo_user_ids))
                    ).scalars()
                )

            operation_ids = set()
            operation_filters = []
            if demo_user_ids:
                operation_filters.append(Operation.user_id.in_(demo_user_ids))
            if demo_item_ids:
                operation_filters.append(Operation.item_id.in_(demo_item_ids))
            if demo_slot_ids:
                operation_filters.append(Operation.slot_id.in_(demo_slot_ids))
            if session_ids:
                operation_filters.append(Operation.session_id.in_(session_ids))
            if operation_filters:
                operation_ids.update(
                    self.session.execute(select(Operation.id).where(or_(*operation_filters))).scalars()
                )
            if operation_ids:
                session_ids.update(
                    session_id
                    for session_id in self.session.execute(
                        select(Operation.session_id).where(Operation.id.in_(operation_ids))
                    ).scalars()
                    if session_id is not None
                )

            recovery_case_ids = set()
            related_entity_ids = {str(value) for value in (*demo_user_ids, *demo_item_ids, *demo_slot_ids, *session_ids, *operation_ids)}
            if related_entity_ids:
                recovery_case_ids.update(
                    self.session.execute(
                        select(RecoveryCaseEntity.recovery_case_id).where(RecoveryCaseEntity.entity_id.in_(related_entity_ids))
                    ).scalars()
                )
            if demo_user_ids:
                recovery_case_ids.update(
                    self.session.execute(
                        select(ManualResolutionAction.recovery_case_id).where(
                            ManualResolutionAction.actor_user_id.in_(demo_user_ids)
                        )
                    ).scalars()
                )

            self._delete_rows(UserCredential, UserCredential.user_id, demo_user_ids)
            self._delete_rows(UserRfidCard, UserRfidCard.user_id, demo_user_ids)
            if demo_user_ids or demo_item_ids:
                permission_filters = []
                if demo_user_ids:
                    permission_filters.append(Permission.user_id.in_(demo_user_ids))
                if demo_item_ids:
                    permission_filters.append(Permission.item_id.in_(demo_item_ids))
                if permission_filters:
                    self.session.execute(delete(Permission).where(or_(*permission_filters)))
            self._delete_rows(InventoryTransaction, InventoryTransaction.operation_id, operation_ids)
            self._delete_rows(InventoryTransaction, InventoryTransaction.session_id, session_ids)
            if demo_item_ids or demo_slot_ids:
                transaction_filters = []
                if demo_item_ids:
                    transaction_filters.append(InventoryTransaction.item_id.in_(demo_item_ids))
                if demo_slot_ids:
                    transaction_filters.append(InventoryTransaction.slot_id.in_(demo_slot_ids))
                if transaction_filters:
                    self.session.execute(delete(InventoryTransaction).where(or_(*transaction_filters)))
            self._delete_rows(OperationStateHistory, OperationStateHistory.operation_id, operation_ids)
            self._delete_rows(RecoveryAction, RecoveryAction.recovery_case_id, recovery_case_ids)
            self._delete_rows(ManualResolutionAction, ManualResolutionAction.recovery_case_id, recovery_case_ids)
            self._delete_rows(RecoveryCaseEntity, RecoveryCaseEntity.recovery_case_id, recovery_case_ids)
            self._delete_rows(RecoveryCase, RecoveryCase.id, recovery_case_ids)
            self._delete_rows(Operation, Operation.id, operation_ids)
            self._delete_rows(EventLog, EventLog.operation_id, operation_ids)
            self._delete_rows(EventLog, EventLog.session_id, session_ids)
            if demo_user_ids or demo_item_ids or demo_slot_ids:
                event_filters = [EventLog.source == _SEED_EVENT_SOURCE]
                if demo_user_ids:
                    event_filters.append(EventLog.user_id.in_(demo_user_ids))
                if demo_item_ids:
                    event_filters.append(EventLog.item_id.in_(demo_item_ids))
                if demo_slot_ids:
                    event_filters.append(EventLog.slot_id.in_(demo_slot_ids))
                self.session.execute(delete(EventLog).where(or_(*event_filters)))
            if demo_user_ids:
                self.session.execute(
                    delete(AuditLog).where(
                        or_(
                            AuditLog.actor_user_id.in_(demo_user_ids),
                            AuditLog.entity_type == _SEED_AUDIT_ENTITY_TYPE,
                        )
                    )
                )
                self._delete_rows(Export, Export.requested_by_user_id, demo_user_ids)
                self._delete_rows(Backup, Backup.requested_by_user_id, demo_user_ids)
            else:
                self.session.execute(delete(AuditLog).where(AuditLog.entity_type == _SEED_AUDIT_ENTITY_TYPE))
            self._delete_rows(OperationSession, OperationSession.id, session_ids)
            if demo_slot_ids:
                self.session.execute(delete(InventoryBalance).where(InventoryBalance.slot_id.in_(demo_slot_ids)))
                self.session.execute(delete(SlotItemBinding).where(SlotItemBinding.slot_id.in_(demo_slot_ids)))
                self.session.execute(delete(Slot).where(Slot.id.in_(demo_slot_ids)))
            if demo_item_ids:
                self.session.execute(delete(Item).where(Item.id.in_(demo_item_ids)))
            if demo_user_ids:
                self.session.execute(delete(User).where(User.id.in_(demo_user_ids)))

            self.session.flush()
            self._record_seed_action(recorder)
            self.session.commit()
        except Exception:
            self.session.rollback()
            raise
        return recorder.build()

    def _ensure_base_roles(self, recorder: "_SeedRecorder") -> None:
        for role_code in RoleCode:
            role = self._find_role(role_code)
            if role is None:
                self.session.add(
                    Role(
                        code=role_code,
                        name=DEFAULT_ROLE_NAMES[role_code],
                        description=f"Base role for {role_code.value} workflows.",
                    )
                )
                recorder.created("role", role_code.value)
            else:
                recorder.skipped("role", role_code.value)
        self.session.flush()

    def _record_seed_action(self, recorder: "_SeedRecorder") -> None:
        payload = {
            "workflow": recorder.workflow,
            "created": list(recorder.created_entries),
            "skipped": list(recorder.skipped_entries),
            "deleted": list(recorder.deleted_entries),
        }
        self.event_log_repository.add(
            EventLog(
                event_type=recorder.workflow,
                level="info",
                source=_SEED_EVENT_SOURCE,
                operation_id=None,
                session_id=None,
                user_id=None,
                slot_id=None,
                item_id=None,
                qty=None,
                result="completed",
                comment=f"{recorder.workflow} completed",
                message=f"{recorder.workflow} completed",
                payload_json=payload,
            )
        )
        self.audit_log_repository.add(
            AuditLog(
                entity_type=_SEED_AUDIT_ENTITY_TYPE,
                entity_id=recorder.workflow,
                action="completed",
                actor_user_id=None,
                reason_code="dev_seed",
                comment=f"{recorder.workflow} completed",
                before_json=None,
                after_json=payload,
            )
        )

    def _role_ids(self) -> dict[RoleCode, int]:
        rows = self.session.execute(select(Role)).scalars()
        return {role.code: role.id for role in rows}

    def _slot_ids(self) -> dict[str, int]:
        rows = self.session.execute(select(Slot).where(Slot.code.in_(self._demo_slot_codes()))).scalars()
        return {slot.code: slot.id for slot in rows}

    def _item_ids(self) -> dict[str, int]:
        rows = self.session.execute(select(Item).where(Item.sku.in_(self._demo_item_skus()))).scalars()
        return {item.sku: item.id for item in rows}

    def _find_role(self, role_code: RoleCode) -> Role | None:
        return self.session.execute(select(Role).where(Role.code == role_code)).scalar_one_or_none()

    def _find_user(self, user_code: str) -> User | None:
        return self.session.execute(select(User).where(User.user_code == user_code)).scalar_one_or_none()

    def _find_item(self, sku: str) -> Item | None:
        return self.session.execute(select(Item).where(Item.sku == sku)).scalar_one_or_none()

    def _find_slot(self, code: str) -> Slot | None:
        return self.session.execute(select(Slot).where(Slot.code == code)).scalar_one_or_none()

    @staticmethod
    def _record_presence(recorder: "_SeedRecorder", entity_type: str, key: str, exists: bool) -> None:
        if exists:
            recorder.deleted(entity_type, key)
        else:
            recorder.skipped(entity_type, key)

    def _delete_rows(self, model, column, ids: set[int]) -> None:
        if ids:
            self.session.execute(delete(model).where(column.in_(ids)))

    @staticmethod
    def _demo_user_codes() -> tuple[str, ...]:
        return tuple(user_code for user_code, _full_name, _role_code in _DEMO_USER_SPECS)

    @staticmethod
    def _demo_item_skus() -> tuple[str, ...]:
        return tuple(sku for sku, _name, _unit, _return_allowed, _min_level in _DEMO_ITEM_SPECS)

    @staticmethod
    def _demo_slot_codes() -> tuple[str, ...]:
        return tuple(code for code, _slot_type, _drum_position, _board_address, _lock_number, _capacity in _DEMO_SLOT_SPECS)


@dataclass(slots=True)
class _SeedRecorder:
    workflow: str
    created_entries: list[str] = field(default_factory=list)
    skipped_entries: list[str] = field(default_factory=list)
    deleted_entries: list[str] = field(default_factory=list)

    def created(self, entity_type: str, key: str) -> None:
        self.created_entries.append(f"{entity_type}:{key}")

    def skipped(self, entity_type: str, key: str) -> None:
        self.skipped_entries.append(f"{entity_type}:{key}")

    def deleted(self, entity_type: str, key: str) -> None:
        self.deleted_entries.append(f"{entity_type}:{key}")

    def build(self) -> SeedWorkflowResultDTO:
        return SeedWorkflowResultDTO(
            workflow=self.workflow,
            created_count=len(self.created_entries),
            skipped_count=len(self.skipped_entries),
            deleted_count=len(self.deleted_entries),
            created=tuple(self.created_entries),
            skipped=tuple(self.skipped_entries),
            deleted=tuple(self.deleted_entries),
        )
