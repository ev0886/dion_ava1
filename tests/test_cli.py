from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
from app.application.dto.inventory import InventoryAdjustmentResultDTO, InventoryBalanceDTO, SlotDTO, SlotDetailDTO
from app.cli import main
from app.domain.enums import InventoryTransactionType, SlotStatus, SlotType, StartupReadinessStatus
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


def test_create_slot_command_dispatches_to_slot_service(monkeypatch) -> None:
    slot_detail = SlotDetailDTO(
        slot=SlotDTO(
            slot_id=1,
            code="slot-a1",
            slot_type=SlotType.UNIVERSAL,
            drum_position=0,
            board_address=1,
            lock_number=1,
            capacity=10,
            status=SlotStatus.ACTIVE,
        ),
        active_bindings=(),
        inventory_balances=(),
    )
    fake_slots = _FakeSlotService(slot_detail=slot_detail)

    monkeypatch.setattr(
        "app.cli.create_bootstrapped_application_container",
        lambda _settings: _FakeCommandContainer(slots=fake_slots),
    )

    exit_code, stdout, stderr = _run_cli(
        [
            "create-slot",
            "--code",
            "slot-a1",
            "--slot-type",
            "universal",
            "--drum-position",
            "0",
            "--board-address",
            "1",
            "--lock-number",
            "1",
        ]
    )

    assert exit_code == 0
    assert '"code": "slot-a1"' in stdout
    assert stderr == ""
    assert fake_slots.calls[0]["code"] == "slot-a1"


def test_adjust_and_list_inventory_commands_dispatch(monkeypatch) -> None:
    adjustment = InventoryAdjustmentResultDTO(
        slot_id=1,
        item_id=2,
        transaction_type=InventoryTransactionType.INVENTORY_ADJUSTMENT,
        quantity_delta=3,
        quantity_before=4,
        quantity_after=7,
        comment="manual",
        created_at=datetime(2026, 4, 2, 0, 0, 0),
        balance=InventoryBalanceDTO(slot_id=1, item_id=2, quantity=7, updated_at=None),
    )
    balances = (InventoryBalanceDTO(slot_id=1, item_id=2, quantity=7, updated_at=None),)
    fake_inventory = _FakeInventoryService(balances=balances)
    fake_inventory_admin = _FakeInventoryAdminService(adjustment=adjustment)

    monkeypatch.setattr(
        "app.cli.create_bootstrapped_application_container",
        lambda _settings: _FakeCommandContainer(inventory=fake_inventory, inventory_admin=fake_inventory_admin),
    )

    adjust_exit_code, adjust_stdout, adjust_stderr = _run_cli(
        [
            "adjust-inventory",
            "--slot-id",
            "1",
            "--item-id",
            "2",
            "--quantity-delta",
            "3",
        ]
    )
    list_exit_code, list_stdout, list_stderr = _run_cli(["list-inventory-balances", "--slot-id", "1"])

    assert adjust_exit_code == 0
    assert '"quantity_after": 7' in adjust_stdout
    assert adjust_stderr == ""
    assert fake_inventory_admin.calls[0]["quantity_delta"] == 3

    assert list_exit_code == 0
    assert '"quantity": 7' in list_stdout
    assert list_stderr == ""
    assert fake_inventory.calls[0]["slot_id"] == 1


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
class _FakeSlotService:
    slot_detail: SlotDetailDTO
    calls: list[dict[str, object]] | None = None

    def __post_init__(self) -> None:
        self.calls = []

    def create_slot(self, **kwargs):
        assert self.calls is not None
        self.calls.append(kwargs)
        return self.slot_detail


@dataclass(slots=True)
class _FakeInventoryService:
    balances: tuple[InventoryBalanceDTO, ...]
    calls: list[dict[str, object]] | None = None

    def __post_init__(self) -> None:
        self.calls = []

    def list_balances(self, *, slot_id=None, item_id=None):
        assert self.calls is not None
        self.calls.append({"slot_id": slot_id, "item_id": item_id})
        return self.balances


@dataclass(slots=True)
class _FakeInventoryAdminService:
    adjustment: InventoryAdjustmentResultDTO
    calls: list[dict[str, object]] | None = None

    def __post_init__(self) -> None:
        self.calls = []

    def adjust_inventory(self, **kwargs):
        assert self.calls is not None
        self.calls.append(kwargs)
        return self.adjustment


@dataclass(slots=True)
class _FakeCommandContainer:
    slots: _FakeSlotService | None = None
    inventory: _FakeInventoryService | None = None
    inventory_admin: _FakeInventoryAdminService | None = None
    services: SimpleNamespace | None = None

    def __post_init__(self) -> None:
        self.services = SimpleNamespace(
            slots=self.slots or _FakeSlotService(
                slot_detail=SlotDetailDTO(
                    slot=SlotDTO(
                        slot_id=1,
                        code="slot-1",
                        slot_type=SlotType.UNIVERSAL,
                        drum_position=0,
                        board_address=1,
                        lock_number=1,
                        capacity=10,
                        status=SlotStatus.ACTIVE,
                    ),
                    active_bindings=(),
                    inventory_balances=(),
                )
            ),
            inventory=self.inventory or _FakeInventoryService(balances=()),
            inventory_admin=self.inventory_admin
            or _FakeInventoryAdminService(
                adjustment=InventoryAdjustmentResultDTO(
                    slot_id=1,
                    item_id=1,
                    transaction_type=InventoryTransactionType.INVENTORY_ADJUSTMENT,
                    quantity_delta=1,
                    quantity_before=0,
                    quantity_after=1,
                    comment=None,
                    created_at=datetime(2026, 4, 2, 0, 0, 0),
                    balance=InventoryBalanceDTO(slot_id=1, item_id=1, quantity=1, updated_at=None),
                )
            ),
        )

    def close(self) -> None:
        return None


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    stdout_buffer = StringIO()
    stderr_buffer = StringIO()
    with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
        exit_code = main(argv)
    return exit_code, stdout_buffer.getvalue(), stderr_buffer.getvalue()
