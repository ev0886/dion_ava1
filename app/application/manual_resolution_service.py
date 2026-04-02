from __future__ import annotations

from dataclasses import dataclass

from app.application.dto.recovery import (
    ManualResolutionPreparationDTO,
    RecoveryActionDTO,
    RecoveryCaseEntityDTO,
)
from app.application.exceptions import RecoveryError
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
