from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UsbStorageStatusDTO:
    usb_available: bool
    mount_path: str | None
    readable: bool
    writable: bool
    device_name: str | None = None
