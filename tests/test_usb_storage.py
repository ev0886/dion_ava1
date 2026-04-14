from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.api import create_app
from app.application.usb_storage_service import UsbStorageDiscoveryService
from app.config import AppSettings


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


def test_ui_mvp_page_and_asset_include_usb_status_wiring(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_ui_usb_status.sqlite3"))

    with TestClient(app) as client:
        page_response = client.get("/ui/mvp")
        asset_response = client.get("/ui-assets/mvp.js")

    assert page_response.status_code == 200
    assert '"usbStatusEndpoint": "/local/usb/status"' in page_response.text
    assert 'id="usb-status-title"' in page_response.text
    assert 'id="usb-status-detail"' in page_response.text

    assert asset_response.status_code == 200
    assert "refreshUsbStatus" in asset_response.text
    assert "renderUsbStatus" in asset_response.text
    assert "usbStatusEndpoint" in asset_response.text


def _settings(tmp_path: Path, sqlite_filename: str) -> AppSettings:
    return AppSettings(
        data_dir=tmp_path,
        sqlite_filename=sqlite_filename,
        alembic_config_path=Path("alembic.ini"),
    )
