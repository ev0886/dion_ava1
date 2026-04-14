from __future__ import annotations

import os
from pathlib import Path

from app.application.dto.usb_storage import UsbStorageStatusDTO

_DEFAULT_CANDIDATE_ROOTS = (Path("/media"), Path("/mnt"))
_PSEUDO_FILESYSTEM_TYPES = {
    "autofs",
    "bpf",
    "cgroup",
    "cgroup2",
    "configfs",
    "debugfs",
    "devpts",
    "devtmpfs",
    "fusectl",
    "hugetlbfs",
    "mqueue",
    "nsfs",
    "overlay",
    "proc",
    "pstore",
    "ramfs",
    "securityfs",
    "selinuxfs",
    "squashfs",
    "sysfs",
    "tmpfs",
    "tracefs",
}


class UsbStorageDiscoveryService:
    def __init__(
        self,
        *,
        mounts_file: Path = Path("/proc/self/mounts"),
        candidate_roots: tuple[Path, ...] = _DEFAULT_CANDIDATE_ROOTS,
    ) -> None:
        self._mounts_file = mounts_file
        self._candidate_roots = candidate_roots

    def get_status(self) -> UsbStorageStatusDTO:
        for mount_source, mount_path, _filesystem_type in self._iter_candidate_mounts():
            return UsbStorageStatusDTO(
                usb_available=True,
                mount_path=str(mount_path),
                readable=os.access(mount_path, os.R_OK),
                writable=os.access(mount_path, os.W_OK),
                device_name=self._device_name_from_source(mount_source),
            )

        return UsbStorageStatusDTO(
            usb_available=False,
            mount_path=None,
            readable=False,
            writable=False,
        )

    def get_status_payload(self) -> dict[str, object]:
        status = self.get_status()
        payload: dict[str, object] = {
            "usb_available": status.usb_available,
            "mount_path": status.mount_path,
            "readable": status.readable,
            "writable": status.writable,
        }
        if status.device_name:
            payload["device_name"] = status.device_name
        return payload

    def _iter_candidate_mounts(self) -> list[tuple[str, Path, str]]:
        candidates: list[tuple[str, Path, str]] = []
        for mount_source, mount_target, filesystem_type in self._read_mount_entries():
            mount_path = Path(mount_target)
            if not mount_source.startswith("/dev/"):
                continue
            if filesystem_type in _PSEUDO_FILESYSTEM_TYPES:
                continue
            if not self._is_candidate_mount_path(mount_path):
                continue
            candidates.append((mount_source, mount_path, filesystem_type))
        return candidates

    def _read_mount_entries(self) -> list[tuple[str, str, str]]:
        if not self._mounts_file.exists():
            return []

        entries: list[tuple[str, str, str]] = []
        for raw_line in self._mounts_file.read_text(encoding="utf-8").splitlines():
            parts = raw_line.split()
            if len(parts) < 3:
                continue
            entries.append((parts[0], self._decode_mount_field(parts[1]), parts[2]))
        return entries

    def _is_candidate_mount_path(self, mount_path: Path) -> bool:
        for candidate_root in self._candidate_roots:
            try:
                relative_path = mount_path.relative_to(candidate_root)
            except ValueError:
                continue
            return len(relative_path.parts) >= 1
        return False

    @staticmethod
    def _decode_mount_field(value: str) -> str:
        return value.replace("\\040", " ")

    @staticmethod
    def _device_name_from_source(mount_source: str) -> str | None:
        if not mount_source.startswith("/dev/"):
            return None
        return Path(mount_source).name or None
