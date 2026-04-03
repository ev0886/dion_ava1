from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.application.dto.recovery import RecoveryScanResult
from app.application.dto.startup import (
    DatabaseReadinessDTO,
    HardwareReadinessDTO,
    HardwareReadinessEntryDTO,
    RecoveryReadinessDTO,
    StartupReadinessDTO,
)
from app.application.exceptions import ApplicationError, RecoveryError
from app.domain.enums import HardwareEndpointType, StartupReadinessStatus
from app.config import HardwareProvider
from app.hardware import HardwareFacade
from app.hardware.dto import HardwareHealthSnapshot
from app.hardware.exceptions import HardwareError


class RecoveryStartupScanner(Protocol):
    def scan_recovery_targets(self) -> RecoveryScanResult: ...


@dataclass(slots=True)
class StartupOrchestrationService:
    db_session: Session
    hardware_facade: HardwareFacade
    recovery_service: RecoveryStartupScanner
    hardware_provider: HardwareProvider = HardwareProvider.MOCK

    def run_startup_checks(self) -> StartupReadinessDTO:
        database = self._check_database_readiness()
        if not database.ok:
            return StartupReadinessDTO(
                database=database,
                hardware=HardwareReadinessDTO(
                    provider_mode=self.hardware_provider.value,
                    ok=False,
                    degraded=False,
                    entries=(),
                    critical_failures=(),
                    message=None,
                ),
                recovery=RecoveryReadinessDTO(
                    ok=False,
                    recovery_candidates_found=False,
                    recovery_candidate_count=0,
                    recovery_case_count=0,
                    candidate_operation_ids=(),
                    message=None,
                ),
                readiness_status=StartupReadinessStatus.NOT_READY,
                message=database.message,
            )

        hardware = self._check_hardware_readiness()
        if not hardware.ok and not hardware.degraded:
            return StartupReadinessDTO(
                database=database,
                hardware=hardware,
                recovery=RecoveryReadinessDTO(
                    ok=False,
                    recovery_candidates_found=False,
                    recovery_candidate_count=0,
                    recovery_case_count=0,
                    candidate_operation_ids=(),
                    message=None,
                ),
                readiness_status=StartupReadinessStatus.NOT_READY,
                message=hardware.message,
            )

        recovery = self._check_recovery_readiness()
        if not recovery.ok:
            return StartupReadinessDTO(
                database=database,
                hardware=hardware,
                recovery=recovery,
                readiness_status=StartupReadinessStatus.NOT_READY,
                message=recovery.message,
            )

        readiness_status = self._derive_readiness_status(hardware=hardware, recovery=recovery)
        return StartupReadinessDTO(
            database=database,
            hardware=hardware,
            recovery=recovery,
            readiness_status=readiness_status,
            message=self._build_message(readiness_status, hardware=hardware, recovery=recovery),
        )

    def _check_database_readiness(self) -> DatabaseReadinessDTO:
        try:
            self.db_session.execute(text("SELECT 1"))
            bind = self.db_session.get_bind()
            alembic_version_table_present = inspect(bind).has_table("alembic_version")
        except SQLAlchemyError as error:
            return DatabaseReadinessDTO(
                ok=False,
                simple_query_ok=False,
                alembic_version_table_present=False,
                message=f"Database readiness check failed: {error}",
            )

        if not alembic_version_table_present:
            return DatabaseReadinessDTO(
                ok=False,
                simple_query_ok=True,
                alembic_version_table_present=False,
                message="Database is reachable but alembic_version table is missing.",
            )

        return DatabaseReadinessDTO(
            ok=True,
            simple_query_ok=True,
            alembic_version_table_present=True,
            message=None,
        )

    def _check_hardware_readiness(self) -> HardwareReadinessDTO:
        try:
            snapshot = self.hardware_facade.hardware_healthcheck()
        except HardwareError as error:
            return HardwareReadinessDTO(
                provider_mode=self.hardware_provider.value,
                ok=False,
                degraded=False,
                entries=(),
                critical_failures=(),
                message=f"Hardware readiness check failed: {error}",
            )

        entries = self._to_hardware_entries(snapshot)
        critical_failures = tuple(entry.device_type for entry in entries if entry.is_critical and not entry.ok)
        if critical_failures:
            return HardwareReadinessDTO(
                provider_mode=self.hardware_provider.value,
                ok=False,
                degraded=False,
                entries=entries,
                critical_failures=critical_failures,
                message="Critical hardware startup dependencies are unavailable.",
            )
        if snapshot.all_ok:
            return HardwareReadinessDTO(
                provider_mode=self.hardware_provider.value,
                ok=True,
                degraded=False,
                entries=entries,
                critical_failures=(),
                message=None,
            )
        # Hardware is treated as degradable at startup so misconfigured or offline
        # real endpoints remain visible to operators without taking down the process.
        return HardwareReadinessDTO(
            provider_mode=self.hardware_provider.value,
            ok=True,
            degraded=True,
            entries=entries,
            critical_failures=(),
            message="One or more hardware endpoints reported unavailable status.",
        )

    def _check_recovery_readiness(self) -> RecoveryReadinessDTO:
        try:
            recovery_scan = self.recovery_service.scan_recovery_targets()
        except (ApplicationError, RecoveryError) as error:
            return RecoveryReadinessDTO(
                ok=False,
                recovery_candidates_found=False,
                recovery_candidate_count=0,
                recovery_case_count=0,
                candidate_operation_ids=(),
                message=f"Recovery readiness check failed: {error}",
            )

        return RecoveryReadinessDTO(
            ok=True,
            recovery_candidates_found=bool(recovery_scan.candidate_operation_ids),
            recovery_candidate_count=len(recovery_scan.candidate_operation_ids),
            recovery_case_count=recovery_scan.open_case_count,
            candidate_operation_ids=recovery_scan.candidate_operation_ids,
            message=None,
        )

    @staticmethod
    def _derive_readiness_status(
        *,
        hardware: HardwareReadinessDTO,
        recovery: RecoveryReadinessDTO,
    ) -> StartupReadinessStatus:
        if hardware.degraded or recovery.recovery_candidates_found:
            return StartupReadinessStatus.DEGRADED
        return StartupReadinessStatus.READY

    def _to_hardware_entries(self, snapshot: HardwareHealthSnapshot) -> tuple[HardwareReadinessEntryDTO, ...]:
        return tuple(
            HardwareReadinessEntryDTO(
                device_type=entry.device_type.value,
                ok=entry.ok,
                is_available=entry.is_available,
                is_critical=self._is_critical_startup_dependency(entry.device_type),
                status=entry.status,
                message=entry.message,
                detail=entry.detail,
            )
            for entry in (snapshot.drum, snapshot.lock, snapshot.rfid)
        )

    @staticmethod
    def _build_message(
        readiness_status: StartupReadinessStatus,
        *,
        hardware: HardwareReadinessDTO,
        recovery: RecoveryReadinessDTO,
    ) -> str:
        if readiness_status is StartupReadinessStatus.READY:
            return "Startup checks passed."
        reasons: list[str] = []
        if hardware.critical_failures:
            reasons.append("critical hardware unavailable")
        if hardware.degraded:
            reasons.append("hardware degraded")
        if recovery.recovery_candidates_found:
            reasons.append("recovery candidates detected")
        return "Startup checks completed with degraded readiness: " + ", ".join(reasons) + "."

    def _is_critical_startup_dependency(self, device_type: HardwareEndpointType) -> bool:
        if self.hardware_provider is not HardwareProvider.REAL:
            return False
        return device_type in {
            HardwareEndpointType.DRUM_CONTROLLER,
            HardwareEndpointType.LOCK_CONTROLLER,
        }


StartupService = StartupOrchestrationService
