from __future__ import annotations

from pathlib import Path

from app.application.composition import create_bootstrapped_application_container
from app.config import AppSettings

from tests.dashboard_seed import seed_dashboard_data


def test_dashboard_summary_happy_path(tmp_path: Path) -> None:
    container = _container(tmp_path, "dashboard_summary.sqlite3")
    try:
        seed_dashboard_data(container.session)

        result = container.services.dashboard.get_summary()

        assert result.total_users == 3
        assert result.active_users == 1
        assert result.blocked_users == 1
        assert result.total_items == 2
        assert result.active_items == 1
        assert result.total_slots == 2
        assert result.active_slots == 1
        assert result.low_stock_item_count == 1
        assert result.low_stock_slot_count == 1
        assert result.open_recovery_case_count == 1
        assert result.unfinished_operation_count == 1
        assert result.recent_problem_operation_count == 2
    finally:
        container.close()


def test_low_stock_overview_shape(tmp_path: Path) -> None:
    container = _container(tmp_path, "dashboard_low_stock.sqlite3")
    try:
        seed_dashboard_data(container.session)

        result = container.services.dashboard.get_low_stock_overview(limit=5)

        assert result.total_count == 1
        assert len(result.entries) == 1
        assert result.entries[0].slot_code == "slot-a"
        assert result.entries[0].item_sku == "item-low"
        assert result.entries[0].shortage == 1
    finally:
        container.close()


def test_recovery_overview_shape(tmp_path: Path) -> None:
    container = _container(tmp_path, "dashboard_recovery.sqlite3")
    try:
        seed_dashboard_data(container.session)

        result = container.services.dashboard.get_recovery_overview(limit=5)

        assert result.total_open_count == 1
        assert len(result.entries) == 1
        assert result.entries[0].operation_id == 3
        assert result.entries[0].summary == "Recovery required for dispense mismatch"
    finally:
        container.close()


def test_recent_operations_overview_shape(tmp_path: Path) -> None:
    container = _container(tmp_path, "dashboard_operations.sqlite3")
    try:
        seed_dashboard_data(container.session)

        result = container.services.dashboard.get_recent_operations(limit=3, recent_window_days=7)

        assert result.total_count == 4
        assert len(result.entries) == 3
        assert result.entries[0].operation_state.value == "user_action_pending"
        assert result.entries[1].operation_state.value == "recovery_required"
        assert result.entries[2].error_code == "jam"
    finally:
        container.close()


def test_recent_activity_overview_shape(tmp_path: Path) -> None:
    container = _container(tmp_path, "dashboard_activity.sqlite3")
    try:
        seed_dashboard_data(container.session)

        result = container.services.dashboard.get_recent_activity(limit=5, recent_window_days=7)

        assert result.total_count == 2
        assert len(result.entries) == 2
        assert result.entries[0].activity_kind == "audit"
        assert result.entries[1].activity_kind == "event"
        assert result.entries[1].source == "operations:operation_failed"
    finally:
        container.close()


def _container(tmp_path: Path, sqlite_filename: str):
    return create_bootstrapped_application_container(
        AppSettings(
            data_dir=tmp_path,
            sqlite_filename=sqlite_filename,
            alembic_config_path=Path("alembic.ini"),
        )
    )
