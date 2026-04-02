from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.application.dto.recovery import RecoveryCaseDTO, RecoveryScanResult
from app.application.startup_service import StartupOrchestrationService
from app.bootstrap import run_database_migrations
from app.config import AppSettings
from app.domain.enums import (
    HardwareEndpointType,
    RecoveryClassification,
    RecoveryStatus,
    StartupReadinessStatus,
)
from app.hardware import (
    HardwareFacade,
    HardwareFailureError,
    HardwareOperationResult,
    LockState,
    MockDrumAdapter,
    MockLockAdapter,
    MockRfidAdapter,
)


def test_db_readiness_success(tmp_path: Path) -> None:
    session = _migrated_session(tmp_path, "startup_ready.sqlite3")
    try:
        service = StartupOrchestrationService(
            db_session=session,
            hardware_facade=_healthy_hardware(),
            recovery_service=_FakeRecoveryService(_recovery_scan_result()),
        )

        result = service.run_startup_checks()

        assert result.database.ok is True
        assert result.database.simple_query_ok is True
        assert result.database.alembic_version_table_present is True
        assert result.readiness_status is StartupReadinessStatus.READY
    finally:
        session.close()


def test_hardware_degraded_readiness_when_one_mock_device_is_unavailable(tmp_path: Path) -> None:
    session = _migrated_session(tmp_path, "startup_degraded_hardware.sqlite3")
    try:
        service = StartupOrchestrationService(
            db_session=session,
            hardware_facade=HardwareFacade(
                drum_controller=MockDrumAdapter(),
                lock_controller=_FailingPingLockAdapter(),
                rfid_reader=MockRfidAdapter(),
            ),
            recovery_service=_FakeRecoveryService(_recovery_scan_result()),
        )

        result = service.run_startup_checks()

        assert result.database.ok is True
        assert result.hardware.ok is True
        assert result.hardware.degraded is True
        assert result.readiness_status is StartupReadinessStatus.DEGRADED
    finally:
        session.close()


def test_recovery_scan_producing_candidates_results_in_degraded_readiness(tmp_path: Path) -> None:
    session = _migrated_session(tmp_path, "startup_degraded_recovery.sqlite3")
    try:
        service = StartupOrchestrationService(
            db_session=session,
            hardware_facade=_healthy_hardware(),
            recovery_service=_FakeRecoveryService(
                _recovery_scan_result(
                    candidate_operation_ids=(1001,),
                    open_case_ids=(501,),
                )
            ),
        )

        result = service.run_startup_checks()

        assert result.recovery.ok is True
        assert result.recovery.recovery_candidates_found is True
        assert result.recovery.recovery_candidate_count == 1
        assert result.readiness_status is StartupReadinessStatus.DEGRADED
    finally:
        session.close()


def test_not_ready_when_db_check_fails(tmp_path: Path) -> None:
    session = _plain_session_without_alembic(tmp_path, "startup_db_fail.sqlite3")
    try:
        service = StartupOrchestrationService(
            db_session=session,
            hardware_facade=_healthy_hardware(),
            recovery_service=_FakeRecoveryService(_recovery_scan_result()),
        )

        result = service.run_startup_checks()

        assert result.database.ok is False
        assert result.database.simple_query_ok is True
        assert result.database.alembic_version_table_present is False
        assert result.readiness_status is StartupReadinessStatus.NOT_READY
    finally:
        session.close()


@dataclass(slots=True)
class _FakeRecoveryService:
    result: RecoveryScanResult

    def scan_recovery_targets(self) -> RecoveryScanResult:
        return self.result


class _FailingPingLockAdapter(MockLockAdapter):
    def ping(self) -> HardwareOperationResult:
        raise HardwareFailureError(
            "lock controller unavailable",
            device_type=HardwareEndpointType.LOCK_CONTROLLER,
            operation="ping",
        )


def _healthy_hardware() -> HardwareFacade:
    return HardwareFacade(
        drum_controller=MockDrumAdapter(),
        lock_controller=MockLockAdapter(lock_states={(1, 1): LockState.LOCKED}),
        rfid_reader=MockRfidAdapter(),
    )


def _recovery_scan_result(
    *,
    candidate_operation_ids: tuple[int, ...] = (),
    open_case_ids: tuple[int, ...] = (),
) -> RecoveryScanResult:
    return RecoveryScanResult(
        open_case_count=len(open_case_ids),
        open_cases=tuple(
            RecoveryCaseDTO(
                recovery_case_id=case_id,
                classification=RecoveryClassification.MANUAL_REVIEW_REQUIRED,
                status=RecoveryStatus.OPEN,
                summary=f"Recovery case {case_id}",
                context={},
                created_at=None,
                resolved_at=None,
            )
            for case_id in open_case_ids
        ),
        unfinished_operation_ids=candidate_operation_ids,
        candidate_operation_ids=candidate_operation_ids,
        candidates=(),
    )


def _migrated_session(tmp_path: Path, sqlite_filename: str) -> Session:
    settings = AppSettings(
        data_dir=tmp_path,
        sqlite_filename=sqlite_filename,
        alembic_config_path=Path("alembic.ini"),
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    run_database_migrations(settings)
    engine = create_engine(settings.database_url, future=True, connect_args={"check_same_thread": False})
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def _plain_session_without_alembic(tmp_path: Path, sqlite_filename: str) -> Session:
    sqlite_path = (tmp_path / sqlite_filename).resolve()
    engine = create_engine(f"sqlite:///{sqlite_path}", future=True, connect_args={"check_same_thread": False})
    with engine.begin() as connection:
        connection.execute(text("SELECT 1"))
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
