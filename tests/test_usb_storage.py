from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.api import create_app
from app.application.admin_service import AdminOperationService, AdminUserService
from app.application.dto.usb_storage import UsbStorageStatusDTO
from app.application.exceptions import ValidationError
from app.application.local_usb_export_service import LocalUsbExportService
from app.application.usb_storage_service import UsbStorageDiscoveryService
from app.config import AppSettings
from app.domain.enums import DispenseRestrictionPolicy, ItemStatus, OperationState, OperationType, RoleCode, SlotStatus, SlotType, UserStatus
from app.persistence.base import Base
from app.persistence.models import InventoryBalance, Item, Operation, Role, Slot, User, UserRfidCard
from app.persistence.repositories.operations import OperationRepository
from app.persistence.repositories.users import UserRepository


def test_usb_storage_service_returns_not_available_when_no_candidate_mount_is_present(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    media_root.mkdir()
    other_mount = tmp_path / "system-root"
    other_mount.mkdir()
    mounts_file = tmp_path / "mounts.txt"
    mounts_file.write_text(f"/dev/mmcblk0p2 {other_mount} ext4 rw 0 0\n", encoding="utf-8")

    service = UsbStorageDiscoveryService(
        mounts_file=mounts_file,
        candidate_roots=(media_root,),
    )

    assert service.get_status_payload() == {
        "usb_available": False,
        "mount_path": None,
        "readable": False,
        "writable": False,
    }


def test_usb_storage_service_returns_available_status_for_usb_like_mount(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    usb_mount = media_root / "operator" / "USB_DISK"
    usb_mount.mkdir(parents=True)
    mounts_file = tmp_path / "mounts.txt"
    mounts_file.write_text(f"/dev/sda1 {usb_mount} vfat rw 0 0\n", encoding="utf-8")

    service = UsbStorageDiscoveryService(
        mounts_file=mounts_file,
        candidate_roots=(media_root,),
    )

    assert service.get_status_payload() == {
        "usb_available": True,
        "mount_path": str(usb_mount),
        "readable": True,
        "writable": True,
        "device_name": "sda1",
    }


def test_local_usb_status_endpoint_returns_expected_payload(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        UsbStorageDiscoveryService,
        "get_status_payload",
        lambda self: {
            "usb_available": True,
            "mount_path": "/media/pi/USB1",
            "readable": True,
            "writable": False,
            "device_name": "sda1",
        },
    )
    app = create_app(_settings(tmp_path, "api_local_usb_status.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/local/usb/status")

    assert response.status_code == 200
    assert response.json() == {
        "usb_available": True,
        "mount_path": "/media/pi/USB1",
        "readable": True,
        "writable": False,
        "device_name": "sda1",
    }


def test_local_usb_operations_export_service_blocks_when_usb_is_missing(tmp_path: Path) -> None:
    admin_service, session = _build_admin_operations_service(tmp_path, "usb_export_service_no_usb.sqlite3")
    service = LocalUsbExportService(
        usb_storage=_StubUsbStorage(
            UsbStorageStatusDTO(
                usb_available=False,
                mount_path=None,
                readable=False,
                writable=False,
            )
        ),
        admin_operations=admin_service,
        admin_users=AdminUserService(UserRepository(session)),
    )

    try:
        with pytest.raises(ValidationError) as exc_info:
            service.export_operations_csv(date_from=date(2026, 4, 14), date_to=date(2026, 4, 14))
    finally:
        session.close()

    assert str(exc_info.value) == "USB-\u043d\u043e\u0441\u0438\u0442\u0435\u043b\u044c \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d"


def test_local_usb_operations_export_service_writes_csv_file_to_usb_mount(tmp_path: Path, monkeypatch) -> None:
    admin_service, session = _build_admin_operations_service(tmp_path, "usb_export_service_write.sqlite3")
    usb_mount = tmp_path / "media" / "operator" / "USB_DISK"
    usb_mount.mkdir(parents=True)
    service = LocalUsbExportService(
        usb_storage=_StubUsbStorage(
            UsbStorageStatusDTO(
                usb_available=True,
                mount_path=str(usb_mount),
                readable=True,
                writable=True,
                device_name="sda1",
            )
        ),
        admin_operations=admin_service,
        admin_users=AdminUserService(UserRepository(session)),
    )
    monkeypatch.setattr(
        LocalUsbExportService,
        "_timestamp_now",
        staticmethod(lambda: datetime(2026, 4, 14, 12, 34, 56)),
    )

    try:
        result = service.export_operations_csv(date_from=date(2026, 4, 14), date_to=date(2026, 4, 14))
    finally:
        session.close()

    exported_path = Path(result.file_path)
    assert result.success is True
    assert result.file_name == "operations_14-04-2026_14-04-2026_12-34-56.csv"
    assert result.mount_path == str(usb_mount)
    assert exported_path == usb_mount / "operations_14-04-2026_14-04-2026_12-34-56.csv"
    assert exported_path.read_text(encoding="utf-8-sig") == "\n".join(
        (
            "operation_id,started_at,finished_at,operation_type,operation_state,user_code,user_full_name,item_name,quantity,slot_code,result,error_code,error_message",
            "1,2026-04-14T09:00:00,2026-04-14T09:10:00,Выдача,completed,user-1,User One,Item One,1,slot-1,ok,,",
            "",
        )
    )


def test_local_usb_operations_export_endpoint_returns_success_payload_and_writes_file(
    tmp_path: Path, monkeypatch
) -> None:
    usb_mount = tmp_path / "media" / "operator" / "USB_DISK"
    usb_mount.mkdir(parents=True)
    monkeypatch.setattr(
        UsbStorageDiscoveryService,
        "get_status",
        lambda self: UsbStorageStatusDTO(
            usb_available=True,
            mount_path=str(usb_mount),
            readable=True,
            writable=True,
            device_name="sda1",
        ),
    )
    monkeypatch.setattr(
        LocalUsbExportService,
        "_timestamp_now",
        staticmethod(lambda: datetime(2026, 4, 14, 12, 34, 56)),
    )
    app = create_app(_settings(tmp_path, "api_local_usb_operations_export.sqlite3"))
    _seed_operations_export_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/local/usb/export/operations",
            json={"date_from": "2026-04-14", "date_to": "2026-04-14"},
        )

    exported_path = usb_mount / "operations_14-04-2026_14-04-2026_12-34-56.csv"
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "file_path": str(exported_path),
        "file_name": "operations_14-04-2026_14-04-2026_12-34-56.csv",
        "mount_path": str(usb_mount),
    }
    assert exported_path.read_text(encoding="utf-8-sig") == "\n".join(
        (
            "operation_id,started_at,finished_at,operation_type,operation_state,user_code,user_full_name,item_name,quantity,slot_code,result,error_code,error_message",
            "1,2026-04-14T09:00:00,2026-04-14T09:10:00,Выдача,completed,user-1,User One,Item One,1,slot-1,ok,,",
            "",
        )
    )


def test_local_usb_operations_export_endpoint_blocks_when_usb_is_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        UsbStorageDiscoveryService,
        "get_status",
        lambda self: UsbStorageStatusDTO(
            usb_available=False,
            mount_path=None,
            readable=False,
            writable=False,
        ),
    )
    app = create_app(_settings(tmp_path, "api_local_usb_operations_export_no_usb.sqlite3"))
    _seed_operations_export_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/local/usb/export/operations",
            json={"date_from": "2026-04-14", "date_to": "2026-04-14"},
        )

    assert response.status_code == 400
    assert response.json() == {
        "error": "validation_error",
        "detail": "USB-\u043d\u043e\u0441\u0438\u0442\u0435\u043b\u044c \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d",
    }


def test_local_usb_users_export_service_blocks_when_usb_is_missing(tmp_path: Path) -> None:
    admin_service, session = _build_admin_users_service(tmp_path, "usb_users_export_service_no_usb.sqlite3")
    service = LocalUsbExportService(
        usb_storage=_StubUsbStorage(
            UsbStorageStatusDTO(
                usb_available=False,
                mount_path=None,
                readable=False,
                writable=False,
            )
        ),
        admin_operations=AdminOperationService(OperationRepository(session)),
        admin_users=admin_service,
    )

    try:
        with pytest.raises(ValidationError) as exc_info:
            service.export_users_csv()
    finally:
        session.close()

    assert str(exc_info.value) == (
        "USB-\u043d\u043e\u0441\u0438\u0442\u0435\u043b\u044c \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d"
    )


def test_local_usb_users_export_service_writes_csv_file_to_usb_mount(tmp_path: Path, monkeypatch) -> None:
    admin_service, session = _build_admin_users_service(tmp_path, "usb_users_export_service_write.sqlite3")
    usb_mount = tmp_path / "media" / "operator" / "USB_DISK"
    usb_mount.mkdir(parents=True)
    monkeypatch.setattr(
        LocalUsbExportService,
        "_timestamp_now",
        staticmethod(lambda: datetime(2026, 4, 15, 12, 34, 56)),
    )
    service = LocalUsbExportService(
        usb_storage=_StubUsbStorage(
            UsbStorageStatusDTO(
                usb_available=True,
                mount_path=str(usb_mount),
                readable=True,
                writable=True,
                device_name="sda1",
            )
        ),
        admin_operations=AdminOperationService(OperationRepository(session)),
        admin_users=admin_service,
    )

    try:
        result = service.export_users_csv()
    finally:
        session.close()

    exported_path = Path(result.file_path)
    assert result.success is True
    assert result.file_name == "users_export_15-04-2026_12-34-56.csv"
    assert result.mount_path == str(usb_mount)
    assert exported_path == usb_mount / "users_export_15-04-2026_12-34-56.csv"
    assert exported_path.read_text(encoding="utf-8-sig") == "\n".join(
        (
            "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
            "user-1,User One,user,000FE2767C0045,unlimited",
            "operator-1,Operator One,operator,,once_per_day",
            "",
        )
    )


def test_local_usb_users_export_endpoint_returns_success_payload_and_writes_file(
    tmp_path: Path, monkeypatch
) -> None:
    usb_mount = tmp_path / "media" / "operator" / "USB_DISK"
    usb_mount.mkdir(parents=True)
    monkeypatch.setattr(
        LocalUsbExportService,
        "_timestamp_now",
        staticmethod(lambda: datetime(2026, 4, 15, 12, 34, 56)),
    )
    monkeypatch.setattr(
        UsbStorageDiscoveryService,
        "get_status",
        lambda self: UsbStorageStatusDTO(
            usb_available=True,
            mount_path=str(usb_mount),
            readable=True,
            writable=True,
            device_name="sda1",
        ),
    )
    app = create_app(_settings(tmp_path, "api_local_usb_users_export.sqlite3"))
    _seed_users_export_domain(app)

    with TestClient(app) as client:
        response = client.post("/local/usb/export/users", json={})

    exported_path = usb_mount / "users_export_15-04-2026_12-34-56.csv"
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "file_path": str(exported_path),
        "file_name": "users_export_15-04-2026_12-34-56.csv",
        "mount_path": str(usb_mount),
    }
    assert exported_path.read_text(encoding="utf-8-sig") == "\n".join(
        (
            "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
            "user-1,User One,user,000FE2767C0045,unlimited",
            "operator-1,Operator One,operator,,once_per_day",
            "",
        )
    )


def test_local_usb_balances_export_service_writes_csv_file_to_usb_mount(tmp_path: Path, monkeypatch) -> None:
    admin_service, session = _build_admin_users_service(tmp_path, "usb_balances_export_service_write.sqlite3")
    _seed_balances_export_domain_for_session(session)
    usb_mount = tmp_path / "media" / "operator" / "USB_DISK"
    usb_mount.mkdir(parents=True)
    monkeypatch.setattr(
        LocalUsbExportService,
        "_timestamp_now",
        staticmethod(lambda: datetime(2026, 4, 16, 8, 9, 10)),
    )
    service = LocalUsbExportService(
        usb_storage=_StubUsbStorage(
            UsbStorageStatusDTO(
                usb_available=True,
                mount_path=str(usb_mount),
                readable=True,
                writable=True,
                device_name="sda1",
            )
        ),
        admin_operations=AdminOperationService(OperationRepository(session)),
        admin_users=admin_service,
    )

    try:
        result = service.export_balances_csv()
    finally:
        session.close()

    exported_path = Path(result.file_path)
    assert result.success is True
    assert result.file_name == "balances_export_16-04-2026_08-09-10.csv"
    assert result.mount_path == str(usb_mount)
    assert exported_path == usb_mount / "balances_export_16-04-2026_08-09-10.csv"
    assert exported_path.read_text(encoding="utf-8-sig") == "\n".join(
        (
            "Номенклатура,Количество",
            "Item One,5",
            "Item Two,2",
            "",
        )
    )


def test_local_usb_balances_export_endpoint_returns_success_payload_and_writes_file(
    tmp_path: Path, monkeypatch
) -> None:
    usb_mount = tmp_path / "media" / "operator" / "USB_DISK"
    usb_mount.mkdir(parents=True)
    monkeypatch.setattr(
        LocalUsbExportService,
        "_timestamp_now",
        staticmethod(lambda: datetime(2026, 4, 16, 8, 9, 10)),
    )
    monkeypatch.setattr(
        UsbStorageDiscoveryService,
        "get_status",
        lambda self: UsbStorageStatusDTO(
            usb_available=True,
            mount_path=str(usb_mount),
            readable=True,
            writable=True,
            device_name="sda1",
        ),
    )
    app = create_app(_settings(tmp_path, "api_local_usb_balances_export.sqlite3"))
    _seed_users_export_domain(app)
    with app.state.session_factory() as session:
        _seed_balances_export_domain_for_session(session)

    with TestClient(app) as client:
        response = client.post("/local/usb/export/balances", json={})

    exported_path = usb_mount / "balances_export_16-04-2026_08-09-10.csv"
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "file_path": str(exported_path),
        "file_name": "balances_export_16-04-2026_08-09-10.csv",
        "mount_path": str(usb_mount),
    }
    assert exported_path.read_text(encoding="utf-8-sig") == "\n".join(
        (
            "Номенклатура,Количество",
            "Item One,5",
            "Item Two,2",
            "",
        )
    )


def test_local_usb_users_import_service_blocks_when_usb_is_missing(tmp_path: Path) -> None:
    admin_service, session = _build_admin_users_service(tmp_path, "usb_users_import_service_no_usb.sqlite3")
    service = LocalUsbExportService(
        usb_storage=_StubUsbStorage(
            UsbStorageStatusDTO(
                usb_available=False,
                mount_path=None,
                readable=False,
                writable=False,
            )
        ),
        admin_operations=AdminOperationService(OperationRepository(session)),
        admin_users=admin_service,
    )

    try:
        with pytest.raises(ValidationError) as exc_info:
            service.import_users_csv()
    finally:
        session.close()

    assert str(exc_info.value) == "USB-носитель не найден"


def test_local_usb_users_import_service_blocks_when_users_csv_is_missing(tmp_path: Path) -> None:
    admin_service, session = _build_admin_users_service(tmp_path, "usb_users_import_service_missing_file.sqlite3")
    usb_mount = tmp_path / "media" / "operator" / "USB_DISK"
    usb_mount.mkdir(parents=True)
    service = LocalUsbExportService(
        usb_storage=_StubUsbStorage(
            UsbStorageStatusDTO(
                usb_available=True,
                mount_path=str(usb_mount),
                readable=True,
                writable=True,
                device_name="sda1",
            )
        ),
        admin_operations=AdminOperationService(OperationRepository(session)),
        admin_users=admin_service,
    )

    try:
        with pytest.raises(ValidationError) as exc_info:
            service.import_users_csv()
    finally:
        session.close()

    assert str(exc_info.value) == "Файл users_import.csv не найден"


def test_local_usb_users_import_service_reads_fixed_users_csv_and_returns_summary(tmp_path: Path) -> None:
    admin_service, session = _build_admin_users_service(tmp_path, "usb_users_import_service_success.sqlite3")
    usb_mount = tmp_path / "media" / "operator" / "USB_DISK"
    usb_mount.mkdir(parents=True)
    import_file = usb_mount / "users_import.csv"
    import_file.write_text(
        "\n".join(
            (
                "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
                "user-1,Updated User,user,11 22 aa bb,once_per_day",
                "user-2,User Two,user,,unlimited",
            )
        ),
        encoding="utf-8-sig",
    )
    service = LocalUsbExportService(
        usb_storage=_StubUsbStorage(
            UsbStorageStatusDTO(
                usb_available=True,
                mount_path=str(usb_mount),
                readable=True,
                writable=True,
                device_name="sda1",
            )
        ),
        admin_operations=AdminOperationService(OperationRepository(session)),
        admin_users=admin_service,
    )

    try:
        result = service.import_users_csv()
        users = admin_service.list_users()
    finally:
        session.close()

    assert result.success is True
    assert result.file_name == "users_import.csv"
    assert result.file_path == str(import_file)
    assert result.mount_path == str(usb_mount)
    assert result.created_count == 1
    assert result.updated_count == 0
    assert result.total_rows == 2
    assert [user.user_code for user in users] == ["user-1", "operator-1", "user-2"]
    imported_users = {user.user_code: user for user in users}
    assert imported_users["user-1"].full_name == "User One"
    assert imported_users["user-1"].rfid_uid == "000FE2767C0045"
    assert imported_users["user-1"].dispense_restriction_policy is DispenseRestrictionPolicy.UNLIMITED
    assert imported_users["user-2"].full_name == "User Two"
    assert imported_users["user-2"].dispense_restriction_policy is DispenseRestrictionPolicy.UNLIMITED


def test_local_usb_users_import_endpoint_returns_expected_payload(tmp_path: Path, monkeypatch) -> None:
    usb_mount = tmp_path / "media" / "operator" / "USB_DISK"
    usb_mount.mkdir(parents=True)
    import_file = usb_mount / "users_import.csv"
    import_file.write_text(
        "\n".join(
            (
                "user_code,full_name,role_code,rfid_uid,dispense_restriction_policy",
                "user-1,Updated User,user,11 22 aa bb,once_per_day",
                "user-2,User Two,user,,unlimited",
            )
        ),
        encoding="utf-8-sig",
    )
    monkeypatch.setattr(
        UsbStorageDiscoveryService,
        "get_status",
        lambda self: UsbStorageStatusDTO(
            usb_available=True,
            mount_path=str(usb_mount),
            readable=True,
            writable=True,
            device_name="sda1",
        ),
    )
    app = create_app(_settings(tmp_path, "api_local_usb_users_import.sqlite3"))
    _seed_users_export_domain(app)

    with TestClient(app) as client:
        response = client.post("/local/usb/import/users", json={})
        list_response = client.get("/admin/users")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "file_path": str(import_file),
        "file_name": "users_import.csv",
        "mount_path": str(usb_mount),
        "created_count": 1,
        "updated_count": 0,
        "total_rows": 2,
    }
    assert list_response.status_code == 200
    assert list_response.json()["users"] == [
        {
            "user_id": 1,
            "user_code": "user-1",
            "full_name": "User One",
            "status": "active",
            "is_active": True,
            "role_code": "user",
            "rfid_uid": "000FE2767C0045",
            "dispense_restriction_policy": "unlimited",
        },
        {
            "user_id": 2,
            "user_code": "operator-1",
            "full_name": "Operator One",
            "status": "active",
            "is_active": True,
            "role_code": "operator",
            "rfid_uid": None,
            "dispense_restriction_policy": "once_per_day",
        },
        {
            "user_id": 3,
            "user_code": "user-2",
            "full_name": "User Two",
            "status": "active",
            "is_active": True,
            "role_code": "user",
            "rfid_uid": None,
            "dispense_restriction_policy": "unlimited",
        },
    ]


def test_local_usb_users_import_endpoint_returns_clear_error_when_users_csv_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    usb_mount = tmp_path / "media" / "operator" / "USB_DISK"
    usb_mount.mkdir(parents=True)
    monkeypatch.setattr(
        UsbStorageDiscoveryService,
        "get_status",
        lambda self: UsbStorageStatusDTO(
            usb_available=True,
            mount_path=str(usb_mount),
            readable=True,
            writable=True,
            device_name="sda1",
        ),
    )
    app = create_app(_settings(tmp_path, "api_local_usb_users_import_missing.sqlite3"))
    _seed_users_export_domain(app)

    with TestClient(app) as client:
        response = client.post("/local/usb/import/users", json={})

    assert response.status_code == 400
    assert response.json() == {
        "error": "validation_error",
        "detail": "Файл users_import.csv не найден",
    }


def test_ui_mvp_page_and_asset_do_not_include_legacy_usb_status_wiring(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_ui_usb_status.sqlite3"))

    with TestClient(app) as client:
        page_response = client.get("/ui/mvp")
        asset_response = client.get("/ui-assets/mvp.js")

    assert page_response.status_code == 200
    assert '"usbStatusEndpoint"' not in page_response.text
    assert '"localUsbOperationsExportEndpoint"' not in page_response.text
    assert '"localUsbUsersExportEndpoint"' not in page_response.text
    assert '"localUsbUsersImportEndpoint"' not in page_response.text
    assert 'id="usb-status-title"' not in page_response.text
    assert 'id="usb-status-detail"' not in page_response.text
    assert 'id="usb-export-date-from"' not in page_response.text
    assert 'id="usb-export-date-to"' not in page_response.text
    assert 'id="usb-export-operations-button"' not in page_response.text
    assert 'id="usb-export-users-button"' not in page_response.text
    assert 'id="usb-import-users-button"' not in page_response.text
    assert 'id="usb-users-import-result-detail"' not in page_response.text
    assert 'id="usb-users-export-result-detail"' not in page_response.text
    assert 'id="usb-export-result-detail"' not in page_response.text

    assert asset_response.status_code == 200
    assert "refreshUsbStatus" not in asset_response.text
    assert "renderUsbStatus" not in asset_response.text
    assert "usbStatusEndpoint" not in asset_response.text
    assert "localUsbOperationsExportEndpoint" not in asset_response.text
    assert "localUsbUsersExportEndpoint" not in asset_response.text
    assert "localUsbUsersImportEndpoint" not in asset_response.text
    assert "exportOperationsToUsb" not in asset_response.text
    assert "exportUsersToUsb" not in asset_response.text
    assert "importUsersFromUsb" not in asset_response.text
    assert "initializeUsbExportForm" not in asset_response.text


def _settings(tmp_path: Path, sqlite_filename: str) -> AppSettings:
    return AppSettings(
        data_dir=tmp_path,
        sqlite_filename=sqlite_filename,
        alembic_config_path=Path("alembic.ini"),
    )


class _StubUsbStorage:
    def __init__(self, status: UsbStorageStatusDTO) -> None:
        self._status = status

    def get_status(self) -> UsbStorageStatusDTO:
        return self._status


def _build_admin_operations_service(tmp_path: Path, sqlite_filename: str) -> tuple[AdminOperationService, Session]:
    engine = create_engine(
        f"sqlite:///{(tmp_path / sqlite_filename).resolve()}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_factory()
    _seed_operations_export_domain_for_session(session)
    return AdminOperationService(OperationRepository(session)), session


def _build_admin_users_service(tmp_path: Path, sqlite_filename: str) -> tuple[AdminUserService, Session]:
    engine = create_engine(
        f"sqlite:///{(tmp_path / sqlite_filename).resolve()}",
        future=True,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = session_factory()
    _seed_users_export_domain_for_session(session)
    return AdminUserService(UserRepository(session)), session


def _seed_operations_export_domain(app) -> None:
    with app.state.session_factory() as session:
        _seed_operations_export_domain_for_session(session)


def _seed_operations_export_domain_for_session(session: Session) -> None:
    role = Role(code=RoleCode.USER, name="User")
    session.add(role)
    session.flush()

    user = User(
        role_id=role.id,
        user_code="user-1",
        full_name="User One",
        status=UserStatus.ACTIVE,
        dispense_restriction_policy=DispenseRestrictionPolicy.UNLIMITED,
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
        drum_position=1,
        board_address=1,
        lock_number=1,
        capacity=10,
        status=SlotStatus.ACTIVE,
    )
    session.add_all((user, item, slot))
    session.flush()
    session.add(
        Operation(
            session_id=None,
            operation_type=OperationType.DISPENSE,
            operation_state=OperationState.COMPLETED,
            user_id=user.id,
            item_id=item.id,
            slot_id=slot.id,
            qty_requested=1,
            qty_confirmed=1,
            result="ok",
            error_code=None,
            error_message=None,
            hardware_context_json={},
            business_context_json={},
            started_at=datetime(2026, 4, 14, 9, 0, 0),
            finished_at=datetime(2026, 4, 14, 9, 10, 0),
        )
    )
    session.commit()


def _seed_users_export_domain(app) -> None:
    with app.state.session_factory() as session:
        _seed_users_export_domain_for_session(session)


def _seed_users_export_domain_for_session(session: Session) -> None:
    user_role = Role(code=RoleCode.USER, name="User")
    operator_role = Role(code=RoleCode.OPERATOR, name="Operator")
    session.add_all((user_role, operator_role))
    session.flush()

    user = User(
        role_id=user_role.id,
        user_code="user-1",
        full_name="User One",
        status=UserStatus.ACTIVE,
        dispense_restriction_policy=DispenseRestrictionPolicy.UNLIMITED,
        is_active=True,
    )
    operator = User(
        role_id=operator_role.id,
        user_code="operator-1",
        full_name="Operator One",
        status=UserStatus.ACTIVE,
        dispense_restriction_policy=DispenseRestrictionPolicy.ONCE_PER_DAY,
        is_active=True,
    )
    session.add_all((user, operator))
    session.flush()
    session.add(
        UserRfidCard(
            user_id=user.id,
            card_uid="000FE2767C0045",
            is_active=True,
            issued_at=datetime(2026, 4, 14, 9, 0, 0),
            revoked_at=None,
        )
    )
    session.commit()


def _seed_balances_export_domain_for_session(session: Session) -> None:
    item_one = Item(
        item_group_id=None,
        sku="balance-item-1",
        name="Item One",
        description=None,
        unit="pcs",
        return_allowed=True,
        min_level=0,
        status=ItemStatus.ACTIVE,
    )
    item_two = Item(
        item_group_id=None,
        sku="balance-item-2",
        name="Item Two",
        description=None,
        unit="pcs",
        return_allowed=True,
        min_level=0,
        status=ItemStatus.ACTIVE,
    )
    slot_one = Slot(
        code="balance-slot-1",
        slot_type=SlotType.UNIVERSAL,
        drum_position=2,
        board_address=1,
        lock_number=2,
        capacity=10,
        status=SlotStatus.ACTIVE,
    )
    slot_two = Slot(
        code="balance-slot-2",
        slot_type=SlotType.UNIVERSAL,
        drum_position=3,
        board_address=1,
        lock_number=3,
        capacity=10,
        status=SlotStatus.ACTIVE,
    )
    slot_three = Slot(
        code="balance-slot-3",
        slot_type=SlotType.UNIVERSAL,
        drum_position=4,
        board_address=1,
        lock_number=4,
        capacity=10,
        status=SlotStatus.ACTIVE,
    )
    session.add_all((item_one, item_two, slot_one, slot_two, slot_three))
    session.flush()
    session.add_all(
        (
            InventoryBalance(slot_id=slot_one.id, item_id=item_one.id, quantity=3),
            InventoryBalance(slot_id=slot_two.id, item_id=item_one.id, quantity=2),
            InventoryBalance(slot_id=slot_three.id, item_id=item_two.id, quantity=2),
        )
    )
    session.commit()
