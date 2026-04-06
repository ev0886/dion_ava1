from __future__ import annotations

from dataclasses import dataclass

from app.application.dto.recovery import (
    ManualResolutionPreparationDTO,
    ManualResolutionRequestDTO,
    ManualResolutionResultDTO,
    RecoveryActionDTO,
    RecoveryCaseEntityDTO,
)
from app.application.exceptions import NotFoundError, RecoveryError
from app.application.time import utc_now
from app.domain.enums import RecoveryActionStatus, RecoveryStatus
from app.persistence.models import ManualResolutionAction, RecoveryAction
from app.persistence.repositories.recovery import RecoveryRepository


@dataclass(slots=True)
class ManualResolutionPreparationService:
    recovery_repository: RecoveryRepository

    def prepare_case(self, recovery_case_id: int) -> ManualResolutionPreparationDTO:
        recovery_case = self.recovery_repository.get_by_id(recovery_case_id)
        if recovery_case is None:
            raise RecoveryError(f"Recovery case not found: {recovery_case_id}")

        entities = tuple(
            RecoveryCaseEntityDTO(
                entity_type=entity.entity_type,
                entity_id=entity.entity_id,
                role=entity.role,
                decision_outcome=entity.decision_outcome,
            )
            for entity in self.recovery_repository.list_entities_for_case(recovery_case_id)
        )
        actions = tuple(
            RecoveryActionDTO(
                action_type=action.action_type,
                status=action.status.value,
                comment=action.comment,
                context=dict(action.context_json or {}),
                created_at=action.created_at,
            )
            for action in self.recovery_repository.list_actions_for_case(recovery_case_id)
        )
        return ManualResolutionPreparationDTO(
            recovery_case_id=recovery_case.id,
            classification=recovery_case.classification,
            status=recovery_case.status,
            summary=recovery_case.summary,
            impacted_entities=entities,
            recovery_actions=actions,
            recommended_next_action_categories=self._recommend_categories(dict(recovery_case.context_json or {})),
            context=dict(recovery_case.context_json or {}),
        )

    def apply_case(self, recovery_case_id: int, request: ManualResolutionRequestDTO) -> ManualResolutionResultDTO:
        recovery_case = self.recovery_repository.get_by_id(recovery_case_id)
        if recovery_case is None:
            raise NotFoundError(f"Recovery case not found: {recovery_case_id}")
        if recovery_case.status is not RecoveryStatus.OPEN or recovery_case.resolved_at is not None:
            raise RecoveryError(
                f"Recovery case {recovery_case_id} cannot be manually resolved from status {recovery_case.status.value}"
            )

        resolved_at = utc_now()
        resolution_context = {
            "operator_user_id": request.operator_user_id,
            "decision": request.decision,
        }
        if request.comment is not None:
            resolution_context["comment"] = request.comment

        self.recovery_repository.add_action(
            RecoveryAction(
                recovery_case_id=recovery_case.id,
                action_type="manual_resolution",
                status=RecoveryActionStatus.APPLIED,
                applied_at=resolved_at,
                comment=request.comment,
                context_json=resolution_context,
            )
        )
        self.recovery_repository.add_manual_resolution_action(
            ManualResolutionAction(
                recovery_case_id=recovery_case.id,
                actor_user_id=request.operator_user_id,
                action_type=request.decision,
                comment=request.comment,
                context_json=resolution_context,
            )
        )

        context = dict(recovery_case.context_json or {})
        context["manual_resolution"] = resolution_context
        recovery_case.context_json = context
        recovery_case.status = RecoveryStatus.RESOLVED
        recovery_case.resolved_at = resolved_at
        self.recovery_repository.session.commit()

        return ManualResolutionResultDTO(
            recovery_case_id=recovery_case.id,
            classification=recovery_case.classification,
            status=recovery_case.status,
            summary=recovery_case.summary,
            context=dict(recovery_case.context_json or {}),
            created_at=recovery_case.created_at,
            resolved_at=recovery_case.resolved_at,
            operator_user_id=request.operator_user_id,
            decision=request.decision,
            comment=request.comment,
        )

    @staticmethod
    def _recommend_categories(context: dict[str, object]) -> tuple[str, ...]:
        outcome = context.get("reconciliation_outcome")
        if outcome == "inventory_write_likely_missing":
            return (
                "review_operation_history",
                "verify_inventory_records",
                "confirm_physical_state",
            )
        if outcome == "no_action_needed":
            return (
                "review_operation_history",
                "decide_case_closure",
            )
        return (
            "review_operation_history",
            "verify_inventory_records",
            "confirm_physical_state",
            "decide_case_closure",
        )
