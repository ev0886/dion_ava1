from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from contextlib import redirect_stderr, redirect_stdout

from app.application.dto.rfid import RfidBindingResultDTO
from app.application.dto.import_export import (
    ExportPreparationResultDTO as DataExportPreparationResultDTO,
    ImportPreparationResultDTO,
    ImportExportArtifactPlanDTO,
    NormalizedRowFieldDTO,
)
from app.application.dto.service_mode import ExportPreparationResultDTO, ServiceModeSessionDTO
from app.application.dto.startup import (
    DatabaseReadinessDTO,
    HardwareReadinessDTO,
    RecoveryReadinessDTO,
    StartupReadinessDTO,
)
from app.cli import main
from app.domain.enums import ExportStatus, RoleCode, SessionStatus, SessionType, StartupReadinessStatus


def test_startup_check_returns_success_for_healthy_temp_environment(tmp_path: Path) -> None:
    exit_code, stdout, stderr = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "--sqlite-filename",
            "cli_healthy.sqlite3",
            "--alembic-config-path",
            "alembic.ini",
            "startup-check",
        ]
    )

    assert exit_code == 0
    assert '"readiness_status": "ready"' in stdout
    assert "ERROR:" not in stderr


def test_startup_check_returns_non_zero_when_startup_is_not_ready(monkeypatch) -> None:
    def _fake_container(_settings):
        return _FakeContainer(
            startup_result=StartupReadinessDTO(
                database=DatabaseReadinessDTO(
                    ok=False,
                    simple_query_ok=False,
                    alembic_version_table_present=False,
                    message="db failed",
                ),
                hardware=HardwareReadinessDTO(
                    ok=False,
                    degraded=False,
                    device_count=0,
                    available_device_count=0,
                    unavailable_device_count=0,
                    entries=(),
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
                status_reasons=("database_unavailable",),
                message="db failed",
            )
        )

    monkeypatch.setattr("app.cli.create_bootstrapped_application_container", _fake_container)

    exit_code, stdout, stderr = _run_cli(["startup-check"])

    assert exit_code == 1
    assert '"readiness_status": "not_ready"' in stdout
    assert stderr == ""


def test_hardware_health_prints_three_mock_device_statuses(tmp_path: Path) -> None:
    exit_code, stdout, _stderr = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "--sqlite-filename",
            "cli_hardware.sqlite3",
            "--alembic-config-path",
            "alembic.ini",
            "hardware-health",
        ]
    )

    assert exit_code == 0
    assert '"drum"' in stdout
    assert '"lock"' in stdout
    assert '"rfid"' in stdout


def test_recovery_scan_runs_and_prints_deterministic_summary(tmp_path: Path) -> None:
    exit_code, stdout, _stderr = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "--sqlite-filename",
            "cli_recovery.sqlite3",
            "--alembic-config-path",
            "alembic.ini",
            "recovery-scan",
        ]
    )

    assert exit_code == 0
    assert '"candidate_operation_ids": []' in stdout
    assert '"open_case_count": 0' in stdout
    assert '"unfinished_operation_ids": []' in stdout


def test_service_mode_open_and_close_dispatch_to_container(monkeypatch) -> None:
    fake_session = ServiceModeSessionDTO(
        session_id=7,
        session_type=SessionType.SERVICE,
        status=SessionStatus.ACTIVE,
        started_by_user_id=2,
        operator_role=RoleCode.OPERATOR,
        started_at=None,
        finished_at=None,
        comment="maintenance",
        context={"entered_via": "service_mode_service"},
    )
    closed_session = ServiceModeSessionDTO(
        session_id=7,
        session_type=SessionType.SERVICE,
        status=SessionStatus.COMPLETED,
        started_by_user_id=2,
        operator_role=RoleCode.OPERATOR,
        started_at=None,
        finished_at=None,
        comment="done",
        context={"entered_via": "service_mode_service", "finished_by_user_id": 2},
    )

    class _FakeServiceModeService:
        def enter_service_mode(self, *, user_id: int, comment: str | None = None) -> ServiceModeSessionDTO:
            assert user_id == 2
            assert comment == "maintenance"
            return fake_session

        def exit_service_mode(self, *, session_id: int, user_id: int, comment: str | None = None) -> ServiceModeSessionDTO:
            assert session_id == 7
            assert user_id == 2
            assert comment == "done"
            return closed_session

    def _fake_container(_settings):
        return _FakeDispatchContainer(services=SimpleNamespace(service_mode=_FakeServiceModeService()))

    monkeypatch.setattr("app.cli.create_bootstrapped_application_container", _fake_container)

    open_exit_code, open_stdout, open_stderr = _run_cli(["service-mode-open", "--user-id", "2", "--comment", "maintenance"])
    close_exit_code, close_stdout, close_stderr = _run_cli(
        ["service-mode-close", "--session-id", "7", "--user-id", "2", "--comment", "done"]
    )

    assert open_exit_code == 0
    assert '"session_id": 7' in open_stdout
    assert '"status": "active"' in open_stdout
    assert open_stderr == ""
    assert close_exit_code == 0
    assert '"status": "completed"' in close_stdout
    assert close_stderr == ""


def test_export_plan_dispatch_to_container(monkeypatch) -> None:
    class _FakeServiceModeService:
        def get_hardware_snapshot(self, *, session_id: int | None = None):
            assert session_id is None
            return {"snapshot": "ok"}

    class _FakeExportService:
        def build_diagnostic_dump_manifest(self, *, session_id: int | None, snapshot):
            assert session_id is None
            assert snapshot == {"snapshot": "ok"}
            return {"manifest": True}

        def prepare_export(
            self,
            *,
            requested_by_user_id: int,
            destination_type: str,
            destination_path: str,
            diagnostic_manifest,
            comment: str | None = None,
        ) -> ExportPreparationResultDTO:
            assert requested_by_user_id == 1
            assert destination_type == "filesystem"
            assert destination_path == "var/exports"
            assert diagnostic_manifest == {"manifest": True}
            assert comment == "bundle"
            return ExportPreparationResultDTO(
                export_id=11,
                requested_by_user_id=1,
                destination_type="filesystem",
                destination_path="var/exports",
                export_type="service_diagnostics_bundle",
                status=ExportStatus.PENDING,
                artifact_count=1,
                manifest_included=True,
                artifact_plan=(),
                manifest=None,
                comment="bundle",
            )

    def _fake_container(_settings):
        return _FakeDispatchContainer(
            services=SimpleNamespace(service_mode=_FakeServiceModeService(), exports=_FakeExportService())
        )

    monkeypatch.setattr("app.cli.create_bootstrapped_application_container", _fake_container)

    exit_code, stdout, stderr = _run_cli(
        ["export-plan", "--requested-by-user-id", "1", "--destination-path", "var/exports", "--comment", "bundle"]
    )

    assert exit_code == 0
    assert '"export_id": 11' in stdout
    assert '"artifact_count": 1' in stdout
    assert '"manifest_included": true' in stdout
    assert stderr == ""


def test_rfid_and_import_export_cli_dispatch(monkeypatch) -> None:
    class _FakeRfidService:
        def bind_card(self, *, actor_user_id: int, user_id: int, card_uid: str, comment: str | None = None) -> RfidBindingResultDTO:
            assert actor_user_id == 1
            assert user_id == 3
            assert card_uid == "aa-bb"
            assert comment == "bind"
            return RfidBindingResultDTO(
                user_id=3,
                actor_user_id=1,
                card_uid="AABB",
                previous_card_uid=None,
                action="bind",
                active_card_count=1,
                issued_at=None,
                revoked_at=None,
                comment="bind",
            )

        def unbind_card(self, *, actor_user_id: int, user_id: int, comment: str | None = None) -> RfidBindingResultDTO:
            assert actor_user_id == 1
            assert user_id == 3
            assert comment == "remove"
            return RfidBindingResultDTO(
                user_id=3,
                actor_user_id=1,
                card_uid=None,
                previous_card_uid="AABB",
                action="unbind",
                active_card_count=0,
                issued_at=None,
                revoked_at=None,
                comment="remove",
            )

    class _FakeImportExportService:
        def prepare_import(self, request) -> ImportPreparationResultDTO:
            assert request.entity_type == "users"
            return ImportPreparationResultDTO(
                entity_type="users",
                source_type="filesystem",
                source_path=request.source_path,
                format_type="csv",
                row_schema=(NormalizedRowFieldDTO("user_code", "user_code", "string", True),),
                required_fields=("user_code",),
                artifact_plan=(ImportExportArtifactPlanDTO("users_import.csv", "source_placeholder", {}),),
                validation_messages=("Parsing is not implemented in this MVP step.",),
            )

        def prepare_export(self, request) -> DataExportPreparationResultDTO:
            assert request.entity_type == "items"
            assert request.include_inactive is True
            return DataExportPreparationResultDTO(
                entity_type="items",
                destination_type="filesystem",
                destination_path=request.destination_path,
                format_type="xlsx",
                row_schema=(NormalizedRowFieldDTO("sku", "sku", "string", True),),
                artifact_plan=(ImportExportArtifactPlanDTO("items_export.xlsx", "data_placeholder", {}),),
                validation_messages=("File generation is not implemented in this MVP step.",),
                include_inactive=True,
            )

    def _fake_container(_settings):
        return _FakeDispatchContainer(
            services=SimpleNamespace(rfid=_FakeRfidService(), import_export=_FakeImportExportService())
        )

    monkeypatch.setattr("app.cli.create_bootstrapped_application_container", _fake_container)

    bind_exit_code, bind_stdout, bind_stderr = _run_cli(
        ["rfid-bind", "--actor-user-id", "1", "--user-id", "3", "--card-uid", "aa-bb", "--comment", "bind"]
    )
    import_exit_code, import_stdout, import_stderr = _run_cli(
        [
            "import-plan",
            "--requested-by-user-id",
            "1",
            "--entity-type",
            "users",
            "--source-path",
            "var/imports/users.csv",
        ]
    )
    export_exit_code, export_stdout, export_stderr = _run_cli(
        [
            "data-export-plan",
            "--requested-by-user-id",
            "1",
            "--entity-type",
            "items",
            "--destination-path",
            "var/exports/items.xlsx",
            "--format-type",
            "xlsx",
            "--include-inactive",
        ]
    )
    unbind_exit_code, unbind_stdout, unbind_stderr = _run_cli(
        ["rfid-unbind", "--actor-user-id", "1", "--user-id", "3", "--comment", "remove"]
    )

    assert bind_exit_code == 0
    assert '"card_uid": "AABB"' in bind_stdout
    assert bind_stderr == ""
    assert import_exit_code == 0
    assert '"entity_type": "users"' in import_stdout
    assert import_stderr == ""
    assert export_exit_code == 0
    assert '"include_inactive": true' in export_stdout
    assert export_stderr == ""
    assert unbind_exit_code == 0
    assert '"action": "unbind"' in unbind_stdout
    assert unbind_stderr == ""


@dataclass(slots=True)
class _FakeStartupService:
    result: StartupReadinessDTO

    def run_startup_checks(self) -> StartupReadinessDTO:
        return self.result


@dataclass(slots=True)
class _FakeContainer:
    startup_result: StartupReadinessDTO
    services: SimpleNamespace | None = None

    def __post_init__(self) -> None:
        self.services = SimpleNamespace(startup=_FakeStartupService(self.startup_result))

    def close(self) -> None:
        return None


@dataclass(slots=True)
class _FakeDispatchContainer:
    services: SimpleNamespace

    def close(self) -> None:
        return None


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exit_code = main(argv)
    return exit_code, stdout_buffer.getvalue(), stderr_buffer.getvalue()
