from __future__ import annotations

from dataclasses import dataclass

from app.application.dto.operations import DispenseRequest, RefillRequest, ReturnRequest
from app.application.dto.rules import RuleEvaluationDTO, RuleResultDTO
from app.application.exceptions import ValidationError
from app.domain.enums import BindingType, ItemStatus, OperationType, RoleCode, SessionStatus, SessionType, SlotStatus, UserStatus
from app.persistence.models import Item, OperationSession, Slot, User
from app.persistence.repositories.inventory import InventoryRepository
from app.persistence.repositories.operations import OperationSessionRepository
from app.persistence.repositories.users import UserRepository


@dataclass(slots=True)
class RuleEvaluationService:
    user_repository: UserRepository
    inventory_repository: InventoryRepository
    session_repository: OperationSessionRepository

    def evaluate_dispense(self, request: DispenseRequest) -> RuleEvaluationDTO:
        self._validate_positive_quantity(request.quantity)

        rules: list[RuleResultDTO] = []
        user = self.user_repository.get_by_id(request.user_id)
        item = self.inventory_repository.get_item(request.item_id)
        slot = self.inventory_repository.get_slot(request.slot_id)

        self._append_user_rules(rules, user=user, user_id=request.user_id, reason_prefix="user")
        self._append_item_rules(rules, item=item, item_id=request.item_id)
        self._append_slot_rules(rules, slot=slot, slot_id=request.slot_id)
        self._append_slot_binding_rule(
            rules,
            slot=slot,
            item=item,
            allowed_binding_types=(BindingType.PRIMARY, BindingType.RETURN),
            missing_code="slot_item_binding_missing",
            missing_message="No active slot binding exists for the requested item",
        )
        self._append_permission_rule(
            rules,
            user=user,
            item=item,
            action="dispense",
            missing_code="dispense_permission_missing",
            missing_message="No dispense permission is configured for the user and item",
        )
        self._append_inventory_rule(rules, slot=slot, item=item, requested_quantity=request.quantity)
        return self._build_result(
            operation_type=OperationType.DISPENSE,
            rules=rules,
            user_id=request.user_id,
            item_id=request.item_id,
            slot_id=request.slot_id,
            session_id=request.session_id,
        )

    def evaluate_return(self, request: ReturnRequest) -> RuleEvaluationDTO:
        self._validate_positive_quantity(request.quantity)

        rules: list[RuleResultDTO] = []
        user = self.user_repository.get_by_id(request.user_id)
        item = self.inventory_repository.get_item(request.item_id)
        requested_slot = self.inventory_repository.get_slot(request.slot_id) if request.slot_id is not None else None

        self._append_user_rules(rules, user=user, user_id=request.user_id, reason_prefix="user")
        self._append_item_rules(rules, item=item, item_id=request.item_id)
        self._append_return_allowed_rule(rules, item=item)

        resolved_slot_id = request.slot_id
        if request.slot_id is not None:
            self._append_slot_rules(rules, slot=requested_slot, slot_id=request.slot_id)
            self._append_slot_binding_rule(
                rules,
                slot=requested_slot,
                item=item,
                allowed_binding_types=(BindingType.RETURN, BindingType.PRIMARY),
                missing_code="return_slot_binding_missing",
                missing_message="Requested slot is not bound for returns of this item",
            )
        else:
            binding = self.inventory_repository.find_preferred_binding_for_item(request.item_id) if item is not None else None
            if binding is None:
                rules.append(
                    RuleResultDTO(
                        code="return_slot_binding_missing",
                        passed=False,
                        message="No active return slot binding exists for the requested item",
                    )
                )
                resolved_slot = None
            else:
                resolved_slot_id = binding.slot_id
                rules.append(
                    RuleResultDTO(
                        code="return_slot_binding_found",
                        passed=True,
                        message="Active return slot binding was resolved",
                        context={"binding_slot_id": binding.slot_id, "binding_type": binding.binding_type.value},
                    )
                )
                resolved_slot = self.inventory_repository.get_slot(binding.slot_id)
                self._append_slot_rules(rules, slot=resolved_slot, slot_id=binding.slot_id)

        self._append_permission_rule(
            rules,
            user=user,
            item=item,
            action="return",
            missing_code="return_permission_missing",
            missing_message="No return permission is configured for the user and item",
        )
        return self._build_result(
            operation_type=OperationType.RETURN,
            rules=rules,
            user_id=request.user_id,
            item_id=request.item_id,
            slot_id=request.slot_id,
            session_id=request.session_id,
            resolved_slot_id=resolved_slot_id,
        )

    def evaluate_refill(self, request: RefillRequest) -> RuleEvaluationDTO:
        if request.quantity < 0:
            raise ValidationError("quantity must be non-negative")

        rules: list[RuleResultDTO] = []
        operator = self.user_repository.get_by_id(request.operator_user_id)
        item = self.inventory_repository.get_item(request.item_id)
        slot = self.inventory_repository.get_slot(request.slot_id)
        session = self.session_repository.get_by_id(request.session_id) if request.session_id is not None else None

        self._append_user_rules(rules, user=operator, user_id=request.operator_user_id, reason_prefix="operator")
        self._append_operator_role_rule(rules, operator=operator)
        self._append_item_rules(rules, item=item, item_id=request.item_id)
        self._append_slot_rules(rules, slot=slot, slot_id=request.slot_id)
        self._append_slot_binding_rule(
            rules,
            slot=slot,
            item=item,
            allowed_binding_types=(BindingType.PRIMARY, BindingType.RETURN),
            missing_code="slot_item_binding_missing",
            missing_message="No active slot binding exists for the requested item",
        )
        self._append_refill_session_rule(rules, session=session, session_id=request.session_id)
        return self._build_result(
            operation_type=OperationType.REFILL_ITEM,
            rules=rules,
            operator_user_id=request.operator_user_id,
            item_id=request.item_id,
            slot_id=request.slot_id,
            session_id=request.session_id,
        )

    def _append_user_rules(
        self,
        rules: list[RuleResultDTO],
        *,
        user: User | None,
        user_id: int,
        reason_prefix: str,
    ) -> None:
        if user is None:
            rules.append(
                RuleResultDTO(
                    code=f"{reason_prefix}_not_found",
                    passed=False,
                    message=f"{reason_prefix.capitalize()} was not found",
                    context={f"{reason_prefix}_id": user_id},
                )
            )
            return
        if not user.is_active:
            rules.append(
                RuleResultDTO(
                    code=f"{reason_prefix}_inactive",
                    passed=False,
                    message=f"{reason_prefix.capitalize()} is inactive",
                    context={f"{reason_prefix}_id": user.id},
                )
            )
            return
        if user.status is UserStatus.BLOCKED:
            rules.append(
                RuleResultDTO(
                    code=f"{reason_prefix}_blocked",
                    passed=False,
                    message=f"{reason_prefix.capitalize()} is blocked",
                    context={f"{reason_prefix}_id": user.id},
                )
            )
            return
        if user.status is not UserStatus.ACTIVE:
            rules.append(
                RuleResultDTO(
                    code=f"{reason_prefix}_status_invalid",
                    passed=False,
                    message=f"{reason_prefix.capitalize()} status does not allow this action",
                    context={f"{reason_prefix}_id": user.id, "status": user.status.value},
                )
            )
            return
        rules.append(
            RuleResultDTO(
                code=f"{reason_prefix}_active",
                passed=True,
                message=f"{reason_prefix.capitalize()} is active and allowed for evaluation",
                context={f"{reason_prefix}_id": user.id},
            )
        )

    def _append_item_rules(self, rules: list[RuleResultDTO], *, item: Item | None, item_id: int) -> None:
        if item is None:
            rules.append(
                RuleResultDTO(
                    code="item_not_found",
                    passed=False,
                    message="Item was not found",
                    context={"item_id": item_id},
                )
            )
            return
        if item.status is not ItemStatus.ACTIVE:
            rules.append(
                RuleResultDTO(
                    code="item_inactive",
                    passed=False,
                    message="Item is not active",
                    context={"item_id": item.id, "status": item.status.value},
                )
            )
            return
        rules.append(
            RuleResultDTO(
                code="item_active",
                passed=True,
                message="Item is active",
                context={"item_id": item.id},
            )
        )

    def _append_slot_rules(self, rules: list[RuleResultDTO], *, slot: Slot | None, slot_id: int) -> None:
        if slot is None:
            rules.append(
                RuleResultDTO(
                    code="slot_not_found",
                    passed=False,
                    message="Slot was not found",
                    context={"slot_id": slot_id},
                )
            )
            return
        if slot.status is not SlotStatus.ACTIVE:
            rules.append(
                RuleResultDTO(
                    code="slot_inactive",
                    passed=False,
                    message="Slot is not active",
                    context={"slot_id": slot.id, "status": slot.status.value},
                )
            )
            return
        rules.append(
            RuleResultDTO(
                code="slot_active",
                passed=True,
                message="Slot is active",
                context={"slot_id": slot.id},
            )
        )

    def _append_slot_binding_rule(
        self,
        rules: list[RuleResultDTO],
        *,
        slot: Slot | None,
        item: Item | None,
        allowed_binding_types: tuple[BindingType, ...],
        missing_code: str,
        missing_message: str,
    ) -> None:
        if slot is None or item is None:
            return
        binding = self.inventory_repository.get_slot_item_binding(
            slot.id,
            item.id,
            allowed_binding_types=allowed_binding_types,
        )
        if binding is None:
            rules.append(
                RuleResultDTO(
                    code=missing_code,
                    passed=False,
                    message=missing_message,
                    context={"slot_id": slot.id, "item_id": item.id},
                )
            )
            return
        rules.append(
            RuleResultDTO(
                code="slot_item_binding_valid",
                passed=True,
                message="Slot and item binding is active",
                context={
                    "slot_id": slot.id,
                    "item_id": item.id,
                    "binding_type": binding.binding_type.value,
                },
            )
        )

    def _append_permission_rule(
        self,
        rules: list[RuleResultDTO],
        *,
        user: User | None,
        item: Item | None,
        action: str,
        missing_code: str,
        missing_message: str,
    ) -> None:
        if user is None or item is None:
            return
        permission = self.inventory_repository.find_permission_for_action(
            user_id=user.id,
            item_id=item.id,
            item_group_id=item.item_group_id,
            action=action,
        )
        if permission is None:
            rules.append(
                RuleResultDTO(
                    code=missing_code,
                    passed=False,
                    message=missing_message,
                    context={"user_id": user.id, "item_id": item.id},
                )
            )
            return
        rules.append(
            RuleResultDTO(
                code=f"{action}_permission_granted",
                passed=True,
                message=f"{action.capitalize()} permission is configured",
                context={"permission_id": permission.id, "user_id": user.id, "item_id": item.id},
            )
        )

    def _append_inventory_rule(
        self,
        rules: list[RuleResultDTO],
        *,
        slot: Slot | None,
        item: Item | None,
        requested_quantity: int,
    ) -> None:
        if slot is None or item is None:
            return
        balance = self.inventory_repository.get_balance(slot.id, item.id)
        available_quantity = 0 if balance is None else balance.quantity
        if balance is None or balance.quantity < requested_quantity:
            rules.append(
                RuleResultDTO(
                    code="insufficient_inventory",
                    passed=False,
                    message="Inventory quantity is insufficient for the requested dispense",
                    context={
                        "slot_id": slot.id,
                        "item_id": item.id,
                        "requested_quantity": requested_quantity,
                        "available_quantity": available_quantity,
                    },
                )
            )
            return
        rules.append(
            RuleResultDTO(
                code="inventory_available",
                passed=True,
                message="Inventory quantity is sufficient",
                context={
                    "slot_id": slot.id,
                    "item_id": item.id,
                    "requested_quantity": requested_quantity,
                    "available_quantity": balance.quantity,
                },
            )
        )

    def _append_return_allowed_rule(self, rules: list[RuleResultDTO], *, item: Item | None) -> None:
        if item is None:
            return
        if not item.return_allowed:
            rules.append(
                RuleResultDTO(
                    code="return_not_allowed",
                    passed=False,
                    message="Item is not allowed to be returned",
                    context={"item_id": item.id},
                )
            )
            return
        rules.append(
            RuleResultDTO(
                code="return_allowed",
                passed=True,
                message="Item is configured as returnable",
                context={"item_id": item.id},
            )
        )

    def _append_operator_role_rule(self, rules: list[RuleResultDTO], *, operator: User | None) -> None:
        if operator is None:
            return
        role_code = self.user_repository.get_role_code(operator)
        if role_code not in {RoleCode.ADMIN, RoleCode.OPERATOR}:
            rules.append(
                RuleResultDTO(
                    code="operator_role_not_allowed",
                    passed=False,
                    message="Operator role is not allowed for refill",
                    context={"operator_user_id": operator.id, "role_code": role_code.value if role_code else None},
                )
            )
            return
        rules.append(
            RuleResultDTO(
                code="operator_role_allowed",
                passed=True,
                message="Operator role is allowed for refill",
                context={"operator_user_id": operator.id, "role_code": role_code.value if role_code else None},
            )
        )

    def _append_refill_session_rule(
        self,
        rules: list[RuleResultDTO],
        *,
        session: OperationSession | None,
        session_id: int | None,
    ) -> None:
        if session_id is None:
            rules.append(
                RuleResultDTO(
                    code="refill_session_optional",
                    passed=True,
                    message="No existing session was provided; refill execution may create one",
                )
            )
            return
        if session is None:
            rules.append(
                RuleResultDTO(
                    code="refill_session_not_found",
                    passed=False,
                    message="Refill session was not found",
                    context={"session_id": session_id},
                )
            )
            return
        if session.session_type not in {SessionType.REFILL, SessionType.SERVICE}:
            rules.append(
                RuleResultDTO(
                    code="refill_session_type_invalid",
                    passed=False,
                    message="Session type is not valid for refill evaluation",
                    context={"session_id": session.id, "session_type": session.session_type.value},
                )
            )
            return
        if session.status not in {SessionStatus.CREATED, SessionStatus.ACTIVE}:
            rules.append(
                RuleResultDTO(
                    code="refill_session_status_invalid",
                    passed=False,
                    message="Session status does not allow refill",
                    context={"session_id": session.id, "status": session.status.value},
                )
            )
            return
        rules.append(
            RuleResultDTO(
                code="refill_session_valid",
                passed=True,
                message="Session is valid for refill evaluation",
                context={
                    "session_id": session.id,
                    "session_type": session.session_type.value,
                    "status": session.status.value,
                },
            )
        )

    @staticmethod
    def _validate_positive_quantity(quantity: int) -> None:
        if quantity <= 0:
            raise ValidationError("quantity must be positive")

    @staticmethod
    def _build_result(
        *,
        operation_type: OperationType,
        rules: list[RuleResultDTO],
        user_id: int | None = None,
        operator_user_id: int | None = None,
        item_id: int | None = None,
        slot_id: int | None = None,
        session_id: int | None = None,
        resolved_slot_id: int | None = None,
    ) -> RuleEvaluationDTO:
        failed_codes = tuple(rule.code for rule in rules if not rule.passed)
        allowed = not failed_codes
        summary_message = (
            f"{operation_type.value} allowed"
            if allowed
            else f"{operation_type.value} denied: {', '.join(failed_codes)}"
        )
        return RuleEvaluationDTO(
            allowed=allowed,
            operation_type=operation_type,
            user_id=user_id,
            operator_user_id=operator_user_id,
            item_id=item_id,
            slot_id=slot_id,
            session_id=session_id,
            resolved_slot_id=resolved_slot_id,
            reason_codes=failed_codes,
            summary_message=summary_message,
            rules=tuple(rules),
        )
