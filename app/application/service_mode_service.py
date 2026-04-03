from __future__ import annotations

from dataclasses import dataclass

from app.application.auth_service import AuthService
from app.config import HardwareProvider
from app.application.dto.service_mode import (
    DiagnosticCommandResultDTO,
    DiagnosticHardwareEntryDTO,
    DiagnosticSnapshotDTO,
    ServiceModeSessionDTO,
)
from app.application.time import utc_now
from app.domain.enums import RoleCode, SessionStatus, SessionType
from app.hardware import HardwareFacade
from app.hardware.dto import (
    DrumPositionResult,
    HardwareHealthSnapshot,
    HardwareOperationResult,
    LockStatusResult,
    RfidReadResult,
    UnlockResult,
    UnlockTimeResult,
)
from app.hardware.exceptions import HardwareError
from app.persistence.models import AuditLog, EventLog, OperationSession
from app.persistence.repositories.logs import AuditLogRepository, EventLogRepository
from app.persistence.repositories.operations import OperationSessionRepository


@dataclass(slots=True)
class ServiceModeService:
    auth_service: AuthService
    session_repository: OperationSessionRepository
    event_log_repository: EventLogRepository
    audit_log_repository: AuditLogRepository
    hardware_facade: HardwareFacade
    hardware_provider: HardwareProvider = HardwareProvider.MOCK

    def enter_service_mode(self, *, user_id: int, comment: str | None = None) -> ServiceModeSessionDTO:
        user = self._require_service_user(user_id)
        session = OperationSession(
            session_type=SessionType.SERVICE,
            status=SessionStatus.ACTIVE,
            started_by_user_id=user.user_id,
            started_at=utc_now(),
            finished_at=None,
            comment=comment,
            context_json={"entered_via": "service_mode_service"},
        )
        self.session_repository.add(session)
        self.session_repository.session.flush()
        self._record_event(
            event_type="service_mode_entered",
            session_id=session.id,
            user_id=user.user_id,
            result="active",
            comment=comment,
        )
        self._record_audit(
            entity_type="operation_session",
            entity_id=str(session.id),
            actor_user_id=user.user_id,
            action="service_mode_enter",
            comment=comment,
        )
        self.session_repository.session.commit()
        return self._to_session_dto(session, operator_role=user.role_code)

    def exit_service_mode(self, *, session_id: int, user_id: int, comment: str | None = None) -> ServiceModeSessionDTO:
        user = self._require_service_user(user_id)
        session = self.session_repository.get_by_id(session_id)
        if session is None:
            raise ValueError(f"Operation session not found: {session_id}")
        session.status = SessionStatus.COMPLETED
        session.finished_at = utc_now()
        session.comment = comment or session.comment
        self._record_event(
            event_type="service_mode_exited",
            session_id=session.id,
            user_id=user.user_id,
            result="completed",
            comment=comment,
        )
        self._record_audit(
            entity_type="operation_session",
            entity_id=str(session.id),
            actor_user_id=user.user_id,
            action="service_mode_exit",
            comment=comment,
        )
        self.session_repository.session.commit()
        return self._to_session_dto(session, operator_role=user.role_code)

    def get_hardware_snapshot(self, *, session_id: int | None = None) -> DiagnosticSnapshotDTO:
        captured_at = utc_now()
        snapshot = self.hardware_facade.hardware_healthcheck()
        return DiagnosticSnapshotDTO(
            session_id=session_id,
            captured_at=captured_at,
            provider_mode=self.hardware_provider.value,
            overall_ok=snapshot.all_ok,
            overall_status="ready" if snapshot.all_ok else "degraded",
            entries=self._snapshot_entries(snapshot),
        )

    def test_drum_positioning(self, *, session_id: int | None, position: int) -> DiagnosticCommandResultDTO:
        return self._execute_diagnostic(
            command_name="test_drum_positioning",
            session_id=session_id,
            action=lambda: self.hardware_facade.move_drum_to_position(position),
            success_payload=lambda result: {"position": result.position},
        )

    def test_lock_open(self, *, session_id: int | None, board_address: int, lock_number: int) -> DiagnosticCommandResultDTO:
        return self._execute_diagnostic(
            command_name="test_lock_open",
            session_id=session_id,
            action=lambda: self.hardware_facade.unlock_lock(board_address, lock_number),
            success_payload=lambda result: {
                "board_address": result.board_address,
                "lock_number": result.lock_number,
                "lock_state": result.lock_state.value,
            },
        )

    def get_lock_status(self, *, session_id: int | None, board_address: int, lock_number: int) -> DiagnosticCommandResultDTO:
        return self._execute_diagnostic(
            command_name="get_lock_status",
            session_id=session_id,
            action=lambda: self.hardware_facade.get_lock_status(board_address, lock_number),
            success_payload=lambda result: {
                "board_address": result.board_address,
                "lock_number": result.lock_number,
                "lock_state": result.lock_state.value,
            },
        )

    def get_unlock_time(self, *, session_id: int | None, board_address: int) -> DiagnosticCommandResultDTO:
        return self._execute_diagnostic(
            command_name="get_unlock_time",
            session_id=session_id,
            action=lambda: self.hardware_facade.get_unlock_time(board_address),
            success_payload=lambda result: {"board_address": result.board_address, "seconds": result.seconds},
        )

    def set_unlock_time(self, *, session_id: int | None, board_address: int, seconds: int) -> DiagnosticCommandResultDTO:
        return self._execute_diagnostic(
            command_name="set_unlock_time",
            session_id=session_id,
            action=lambda: self.hardware_facade.set_unlock_time(board_address, seconds),
            success_payload=lambda result: {"board_address": result.board_address, "seconds": result.seconds},
        )

    def read_rfid(self, *, session_id: int | None) -> DiagnosticCommandResultDTO:
        return self._execute_diagnostic(
            command_name="read_rfid",
            session_id=session_id,
            action=self.hardware_facade.read_rfid_card,
            success_payload=lambda result: {"uid": result.uid, "is_duplicate": result.is_duplicate},
        )

    def clear_rfid_buffer(self, *, session_id: int | None) -> DiagnosticCommandResultDTO:
        return self._execute_diagnostic(
            command_name="clear_rfid_buffer",
            session_id=session_id,
            action=self.hardware_facade.clear_rfid_buffer,
            success_payload=lambda result: {},
        )

    def _execute_diagnostic(
        self,
        *,
        command_name: str,
        session_id: int | None,
        action,
        success_payload,
    ) -> DiagnosticCommandResultDTO:
        try:
            result = action()
            dto = self._result_to_dto(command_name=command_name, result=result, payload=success_payload(result))
        except HardwareError as error:
            dto = DiagnosticCommandResultDTO(
                command_name=command_name,
                ok=False,
                device_type=error.device_type.value,
                status=error.normalized_status.value,
                message=str(error),
                payload={
                    "operation": error.operation,
                    "detail": dict(error.detail),
                },
            )
        self._record_event(
            event_type=command_name,
            session_id=session_id,
            user_id=None,
            result=dto.status,
            comment=dto.message,
            payload=dto.payload,
        )
        self.session_repository.session.commit()
        return dto

    def _require_service_user(self, user_id: int):
        user = self.auth_service.get_user_by_id(user_id)
        if user.role_code not in {RoleCode.ADMIN, RoleCode.OPERATOR}:
            from app.application.exceptions import AuthorizationError

            raise AuthorizationError(f"User role is not allowed for service mode: {user.role_code}")
        return user

    @staticmethod
    def _to_session_dto(session: OperationSession, *, operator_role: RoleCode | None) -> ServiceModeSessionDTO:
        return ServiceModeSessionDTO(
            session_id=session.id,
            session_type=session.session_type,
            status=session.status,
            started_by_user_id=session.started_by_user_id or 0,
            operator_role=operator_role,
            started_at=session.started_at,
            finished_at=session.finished_at,
            comment=session.comment,
            context=dict(session.context_json or {}),
        )

    def _snapshot_entries(self, snapshot: HardwareHealthSnapshot) -> tuple[DiagnosticHardwareEntryDTO, ...]:
        return tuple(
            DiagnosticHardwareEntryDTO(
                provider_mode=self.hardware_provider.value,
                device_type=entry.device_type.value,
                ok=entry.ok,
                is_available=entry.is_available,
                is_critical=self._is_critical_startup_dependency(entry.device_type.value),
                status=entry.status,
                summary=entry.message,
                detail=entry.detail,
            )
            for entry in (snapshot.drum, snapshot.lock, snapshot.rfid)
        )

    @staticmethod
    def _result_to_dto(command_name: str, result, payload: dict[str, object]) -> DiagnosticCommandResultDTO:
        return DiagnosticCommandResultDTO(
            command_name=command_name,
            ok=result.ok,
            device_type=result.device_type.value,
            status=result.status.value,
            message=result.message,
            payload=payload,
        )

    def _is_critical_startup_dependency(self, device_type: str) -> bool:
        if self.hardware_provider is not HardwareProvider.REAL:
            return False
        return device_type in {"drum_controller", "lock_controller"}

    def _record_event(
        self,
        *,
        event_type: str,
        session_id: int | None,
        user_id: int | None,
        result: str | None,
        comment: str | None,
        payload: dict[str, object] | None = None,
    ) -> None:
        error_results = {"failure", "timeout", "busy", "unavailable"}
        self.event_log_repository.add(
            EventLog(
                event_type=event_type,
                level="error" if result in error_results else "info",
                source="service_mode_service",
                operation_id=None,
                session_id=session_id,
                user_id=user_id,
                slot_id=None,
                item_id=None,
                qty=None,
                result=result,
                comment=comment,
                message=comment,
                payload_json=dict(payload or {}),
            )
        )

    def _record_audit(
        self,
        *,
        entity_type: str,
        entity_id: str,
        actor_user_id: int,
        action: str,
        comment: str | None,
    ) -> None:
        self.audit_log_repository.add(
            AuditLog(
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                actor_user_id=actor_user_id,
                reason_code=None,
                comment=comment,
                before_json=None,
                after_json=None,
            )
        )
