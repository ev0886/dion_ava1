from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UsbStorageStatusDTO:
    usb_available: bool
    mount_path: str | None
    readable: bool
    writable: bool
    device_name: str | None = None


@dataclass(frozen=True, slots=True)
class UsbOperationsExportResultDTO:
    success: bool
    file_path: str
    file_name: str
    mount_path: str


@dataclass(frozen=True, slots=True)
class UsbUsersExportResultDTO:
    success: bool
    file_path: str
    file_name: str
    mount_path: str


@dataclass(frozen=True, slots=True)
class UsbBalancesExportResultDTO:
    success: bool
    file_path: str
    file_name: str
    mount_path: str


@dataclass(frozen=True, slots=True)
class UsbUsersImportResultDTO:
    success: bool
    file_path: str
    file_name: str
    mount_path: str
    created_count: int
    updated_count: int
    total_rows: int


@dataclass(frozen=True, slots=True)
class UsbUsersImportCheckResultDTO:
    success: bool
    file_path: str
    file_name: str
    mount_path: str
