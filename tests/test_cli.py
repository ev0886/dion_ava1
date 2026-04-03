from __future__ import annotations

from dataclasses import dataclass
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from contextlib import redirect_stderr, redirect_stdout

from app.application.dto.startup import (
    DatabaseReadinessDTO,
    HardwareReadinessDTO,
    RecoveryReadinessDTO,
    StartupReadinessDTO,
)
from app.application.dto.rules import RuleEvaluationDTO, RuleResultDTO
from app.cli import main
from app.domain.enums import OperationType, StartupReadinessStatus
from app.hardware.dto import HardwareOperationStatus


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
                hardware=HardwareReadinessDTO(ok=False, degraded=False, entries=(), message=None),
                recovery=RecoveryReadinessDTO(
                    ok=False,
                    recovery_candidates_found=False,
                    recovery_candidate_count=0,
                    recovery_case_count=0,
                    candidate_operation_ids=(),
                    message=None,
                ),
                readiness_status=StartupReadinessStatus.NOT_READY,
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


def test_check_dispense_rules_command_renders_rule_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.cli.create_bootstrapped_application_container",
        lambda _settings: _FakeRulesContainer("dispense"),
    )

    exit_code, stdout, stderr = _run_cli(
        ["check-dispense-rules", "--user-id", "1", "--item-id", "2", "--slot-id", "3", "--quantity", "1"]
    )

    assert exit_code == 0
    assert '"operation_type": "dispense"' in stdout
    assert '"allowed": true' in stdout
    assert stderr == ""


def test_check_return_rules_command_renders_reason_codes(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.cli.create_bootstrapped_application_container",
        lambda _settings: _FakeRulesContainer("return"),
    )

    exit_code, stdout, stderr = _run_cli(["check-return-rules", "--user-id", "1", "--item-id", "2", "--quantity", "1"])

    assert exit_code == 0
    assert '"operation_type": "return"' in stdout
    assert '"reason_codes": [' in stdout
    assert '"return_not_allowed"' in stdout
    assert stderr == ""


def test_check_refill_rules_command_renders_rule_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.cli.create_bootstrapped_application_container",
        lambda _settings: _FakeRulesContainer("refill_item"),
    )

    exit_code, stdout, stderr = _run_cli(
        [
            "check-refill-rules",
            "--operator-user-id",
            "7",
            "--item-id",
            "2",
            "--slot-id",
            "3",
            "--quantity",
            "5",
            "--mode",
            "add",
        ]
    )

    assert exit_code == 0
    assert '"operation_type": "refill_item"' in stdout
    assert '"summary_message": "refill_item allowed"' in stdout
    assert stderr == ""


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
class _FakeRulesService:
    operation_type: OperationType

    def evaluate_dispense(self, _request) -> RuleEvaluationDTO:
        return self._result()

    def evaluate_return(self, _request) -> RuleEvaluationDTO:
        return self._result(allowed=False, failed_code="return_not_allowed")

    def evaluate_refill(self, _request) -> RuleEvaluationDTO:
        return self._result()

    def _result(self, *, allowed: bool = True, failed_code: str | None = None) -> RuleEvaluationDTO:
        return RuleEvaluationDTO(
            allowed=allowed,
            operation_type=self.operation_type,
            user_id=1,
            operator_user_id=7 if self.operation_type is OperationType.REFILL_ITEM else None,
            item_id=2,
            slot_id=3,
            session_id=None,
            resolved_slot_id=3,
            reason_codes=() if failed_code is None else (failed_code,),
            summary_message=(
                f"{self.operation_type.value} allowed"
                if failed_code is None
                else f"{self.operation_type.value} denied: {failed_code}"
            ),
            rules=(
                RuleResultDTO(
                    code="sample_rule" if failed_code is None else failed_code,
                    passed=failed_code is None,
                    message="sample",
                    context={},
                ),
            ),
        )


@dataclass(slots=True)
class _FakeRulesContainer:
    operation_type_value: str
    services: SimpleNamespace | None = None

    def __post_init__(self) -> None:
        self.services = SimpleNamespace(rules=_FakeRulesService(OperationType(self.operation_type_value)))

    def close(self) -> None:
        return None


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exit_code = main(argv)
    return exit_code, stdout_buffer.getvalue(), stderr_buffer.getvalue()
