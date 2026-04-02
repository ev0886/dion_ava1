from __future__ import annotations

from datetime import datetime

from app.application.dto.operations import CreateOperationSessionCommand, OperationSessionDTO
from app.application.exceptions import NotFoundError
from app.domain.enums import SessionStatus
from app.persistence.models import OperationSession
from app.persistence.repositories.operations import OperationSessionRepository


class OperationSessionService:
    def __init__(self, session_repository: OperationSessionRepository) -> None:
        self.session_repository = session_repository

    def create_session(self, command: CreateOperationSessionCommand) -> OperationSessionDTO:
        session = OperationSession(
            session_type=command.session_type,
            status=SessionStatus.CREATED,
            started_by_user_id=command.started_by_user_id,
            started_at=datetime.utcnow(),
            finished_at=None,
            comment=command.comment,
            context_json=dict(command.context),
        )
        self.session_repository.session.add(session)
        return self._to_dto(session)

    def get_session(self, session_id: int) -> OperationSessionDTO:
        session = self.session_repository.get_by_id(session_id)
        if session is None:
            raise NotFoundError(f"Operation session not found: {session_id}")
        return self._to_dto(session)

    @staticmethod
    def _to_dto(session: OperationSession) -> OperationSessionDTO:
        return OperationSessionDTO(
            session_id=session.id,
            session_type=session.session_type,
            status=session.status,
            started_by_user_id=session.started_by_user_id,
            started_at=session.started_at,
            finished_at=session.finished_at,
            comment=session.comment,
            context=dict(session.context_json or {}),
        )
