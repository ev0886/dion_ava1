from __future__ import annotations

import json
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
from app.api import create_app
from app.cli import main
from app.config import AppSettings
from app.domain.enums import BindingType, ItemStatus, OperationState, OperationType, RoleCode, SlotStatus, SlotType, StartupReadinessStatus, UserStatus
from app.hardware.dto import HardwareOperationStatus
from app.persistence.models import InventoryBalance, Item, Operation, Role, Slot, SlotItemBinding, User


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


def test_operations_list_prints_paginated_json_shape(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "cli_operations.sqlite3"))
    _seed_cli_operation_listing(app)

    exit_code, stdout, stderr = _run_cli(
        [
            "--data-dir",
            str(tmp_path),
            "--sqlite-filename",
            "cli_operations.sqlite3",
            "--alembic-config-path",
            "alembic.ini",
            "operations-list",
            "--state",
            "completed",
            "--limit",
            "1",
            "--offset",
            "1",
        ]
    )

    assert exit_code == 0
    assert "ERROR:" not in stderr
    payload = json.loads(stdout)
    assert payload["limit"] == 1
    assert payload["offset"] == 1
    assert payload["total"] == 2
    assert [item["operation_id"] for item in payload["items"]] == [2]


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


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exit_code = main(argv)
    return exit_code, stdout_buffer.getvalue(), stderr_buffer.getvalue()


def _settings(tmp_path: Path, sqlite_filename: str) -> AppSettings:
    return AppSettings(
        data_dir=tmp_path,
        sqlite_filename=sqlite_filename,
        alembic_config_path=Path("alembic.ini"),
    )


def _seed_cli_operation_listing(app) -> None:
    with app.state.session_factory() as session:
        role = Role(code=RoleCode.USER, name="User")
        session.add(role)
        session.flush()

        user = User(
            role_id=role.id,
            user_code="user-1",
            full_name="User One",
            status=UserStatus.ACTIVE,
            is_active=True,
        )
        item = Item(
            item_group_id=None,
            sku="item-1",
            name="Item One",
            description=None,
            unit="pcs",
            return_allowed=True,
            min_level=0,
            status=ItemStatus.ACTIVE,
        )
        slot = Slot(
            code="slot-1",
            slot_type=SlotType.UNIVERSAL,
            drum_position=3,
            board_address=1,
            lock_number=1,
            capacity=10,
            status=SlotStatus.ACTIVE,
        )
        session.add_all((user, item, slot))
        session.flush()
        session.add(
            SlotItemBinding(
                slot_id=slot.id,
                item_id=item.id,
                binding_type=BindingType.RETURN,
                is_active=True,
                valid_from=None,
                valid_to=None,
            )
        )
        session.add(InventoryBalance(slot_id=slot.id, item_id=item.id, quantity=5))
        session.add_all(
            (
                Operation(
                    session_id=None,
                    operation_type=OperationType.DISPENSE,
                    operation_state=OperationState.COMPLETED,
                    user_id=1,
                    item_id=1,
                    slot_id=1,
                    qty_requested=1,
                    qty_confirmed=1,
                    result="ok",
                    error_code=None,
                    error_message=None,
                    hardware_context_json={},
                    business_context_json={},
                    started_at=None,
                    finished_at=None,
                ),
                Operation(
                    session_id=None,
                    operation_type=OperationType.RETURN,
                    operation_state=OperationState.COMPLETED,
                    user_id=1,
                    item_id=1,
                    slot_id=1,
                    qty_requested=1,
                    qty_confirmed=1,
                    result="ok",
                    error_code=None,
                    error_message=None,
                    hardware_context_json={},
                    business_context_json={},
                    started_at=None,
                    finished_at=None,
                ),
                Operation(
                    session_id=None,
                    operation_type=OperationType.REFILL_ITEM,
                    operation_state=OperationState.FAILED,
                    user_id=1,
                    item_id=1,
                    slot_id=1,
                    qty_requested=5,
                    qty_confirmed=None,
                    result="error",
                    error_code="hardware_error",
                    error_message="motor jam",
                    hardware_context_json={},
                    business_context_json={},
                    started_at=None,
                    finished_at=None,
                ),
            )
        )
        session.commit()
