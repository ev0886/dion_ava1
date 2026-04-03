from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from app.domain.enums import RecoveryClassification, RecoveryStatus
from app.persistence.models import RecoveryAction, RecoveryCase, RecoveryCaseEntity
from app.persistence.repositories.base import Repository


class RecoveryRepository(Repository):
    def add_case(self, recovery_case: RecoveryCase) -> None:
        self.session.add(recovery_case)

    def get_by_id(self, recovery_case_id: int) -> RecoveryCase | None:
        return self.session.get(RecoveryCase, recovery_case_id)

    def list_open_cases(self) -> list[RecoveryCase]:
        statement = select(RecoveryCase).where(RecoveryCase.resolved_at.is_(None))
        return list(self.session.execute(statement).scalars())

    def list_cases(
        self,
        *,
        limit: int,
        offset: int,
        status: RecoveryStatus | None = None,
        classification: RecoveryClassification | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> list[RecoveryCase]:
        statement = select(RecoveryCase).order_by(RecoveryCase.id.asc()).limit(limit).offset(offset)
        if status is not None:
            statement = statement.where(RecoveryCase.status == status)
        if classification is not None:
            statement = statement.where(RecoveryCase.classification == classification)
        if created_from is not None:
            statement = statement.where(RecoveryCase.created_at >= created_from)
        if created_to is not None:
            statement = statement.where(RecoveryCase.created_at <= created_to)
        return list(self.session.execute(statement).scalars())

    def count_cases(
        self,
        *,
        status: RecoveryStatus | None = None,
        classification: RecoveryClassification | None = None,
        created_from: datetime | None = None,
        created_to: datetime | None = None,
    ) -> int:
        statement = select(func.count()).select_from(RecoveryCase)
        if status is not None:
            statement = statement.where(RecoveryCase.status == status)
        if classification is not None:
            statement = statement.where(RecoveryCase.classification == classification)
        if created_from is not None:
            statement = statement.where(RecoveryCase.created_at >= created_from)
        if created_to is not None:
            statement = statement.where(RecoveryCase.created_at <= created_to)
        return int(self.session.execute(statement).scalar_one())

    def find_open_case_by_operation_id(self, operation_id: int) -> RecoveryCase | None:
        statement = (
            select(RecoveryCase)
            .join(RecoveryCaseEntity, RecoveryCaseEntity.recovery_case_id == RecoveryCase.id)
            .where(
                RecoveryCase.resolved_at.is_(None),
                RecoveryCaseEntity.entity_type == "operation",
                RecoveryCaseEntity.entity_id == str(operation_id),
            )
            .order_by(RecoveryCase.id.asc())
        )
        return self.session.execute(statement).scalars().first()

    def add_case_entity(self, recovery_case_entity: RecoveryCaseEntity) -> None:
        self.session.add(recovery_case_entity)

    def get_case_entity(
        self,
        recovery_case_id: int,
        *,
        entity_type: str,
        entity_id: str,
        role: str,
    ) -> RecoveryCaseEntity | None:
        statement = select(RecoveryCaseEntity).where(
            RecoveryCaseEntity.recovery_case_id == recovery_case_id,
            RecoveryCaseEntity.entity_type == entity_type,
            RecoveryCaseEntity.entity_id == entity_id,
            RecoveryCaseEntity.role == role,
        )
        return self.session.execute(statement).scalar_one_or_none()

    def list_entities_for_case(self, recovery_case_id: int) -> list[RecoveryCaseEntity]:
        statement = (
            select(RecoveryCaseEntity)
            .where(RecoveryCaseEntity.recovery_case_id == recovery_case_id)
            .order_by(RecoveryCaseEntity.id.asc())
        )
        return list(self.session.execute(statement).scalars())

    def list_actions_for_case(self, recovery_case_id: int) -> list[RecoveryAction]:
        statement = (
            select(RecoveryAction)
            .where(RecoveryAction.recovery_case_id == recovery_case_id)
            .order_by(RecoveryAction.id.asc())
        )
        return list(self.session.execute(statement).scalars())
