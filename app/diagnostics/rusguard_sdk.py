from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


_DEFAULT_LIBRARY_PATH = Path(__file__).resolve().parents[2] / "vendor" / "rusguard" / "sdk" / "librgsec.so"
_LIBRARY_PATH_ENV_VAR = "DION_RUSGUARD_SDK_LIBRARY_PATH"

RG_ENDPOINT_TYPE_USB_HID = 0x01
RG_ENDPOINT_TYPE_SERIAL = 0x02


class _RgEndpointInfo(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("type", ctypes.c_uint8),
        ("address", ctypes.c_char * 64),
        ("friendly_name", ctypes.c_char * 128),
    ]


class RusGuardSdkError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EndpointInfo:
    index: int
    type: int
    address: str
    friendly_name: str


class RusGuardSdkProtocol(Protocol):
    library_path: Path

    def initialize(self) -> None: ...

    def find_endpoint_infos(self, endpoint_type_mask: int) -> tuple[EndpointInfo, ...]: ...

    def uninitialize(self) -> None: ...


@dataclass(frozen=True, slots=True)
class DiagnosticSection:
    title: str
    lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DiagnosticReport:
    library_path: Path
    sections: tuple[DiagnosticSection, ...]


class CountOnlyRusGuardSdk:
    def __init__(self, library_path: Path) -> None:
        self.library_path = library_path
        try:
            self._library = ctypes.CDLL(str(library_path))
        except OSError as error:
            raise RusGuardSdkError(f"failed to load SDK library: {library_path}") from error

        self._library.RG_InitializeLib.argtypes = []
        self._library.RG_InitializeLib.restype = ctypes.c_uint32
        self._library.RG_Uninitialize.argtypes = []
        self._library.RG_Uninitialize.restype = ctypes.c_uint32
        self._library.RG_CloseResource.argtypes = [ctypes.c_void_p]
        self._library.RG_CloseResource.restype = ctypes.c_uint32
        self._library.RG_FindEndPoints.argtypes = [
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_uint32),
        ]
        self._library.RG_FindEndPoints.restype = ctypes.c_uint32
        self._library.RG_GetFoundEndPointInfo.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(_RgEndpointInfo),
        ]
        self._library.RG_GetFoundEndPointInfo.restype = ctypes.c_uint32

    def initialize(self) -> None:
        result = int(self._library.RG_InitializeLib())
        if result != 0:
            raise RusGuardSdkError(f"RG_InitializeLib failed with code {result}")

    def find_endpoint_infos(self, endpoint_type_mask: int) -> tuple[EndpointInfo, ...]:
        list_handle = ctypes.c_void_p()
        count = ctypes.c_uint32()
        result = int(
            self._library.RG_FindEndPoints(
                ctypes.byref(list_handle),
                ctypes.c_uint8(endpoint_type_mask),
                ctypes.byref(count),
            )
        )
        if result != 0:
            raise RusGuardSdkError(f"RG_FindEndPoints failed with code {result} for mask {endpoint_type_mask}")

        try:
            items: list[EndpointInfo] = []
            for index in range(int(count.value)):
                endpoint_info = _RgEndpointInfo()
                result = int(
                    self._library.RG_GetFoundEndPointInfo(
                        list_handle,
                        ctypes.c_uint32(index),
                        ctypes.byref(endpoint_info),
                    )
                )
                if result != 0:
                    raise RusGuardSdkError(
                        f"RG_GetFoundEndPointInfo failed with code {result} for mask {endpoint_type_mask} at index {index}"
                    )
                items.append(
                    EndpointInfo(
                        index=index,
                        type=int(endpoint_info.type),
                        address=_decode_ascii(endpoint_info.address),
                        friendly_name=_decode_ascii(endpoint_info.friendly_name),
                    )
                )
            return tuple(items)
        finally:
            if list_handle.value:
                result = int(self._library.RG_CloseResource(list_handle))
                if result != 0:
                    raise RusGuardSdkError(f"RG_CloseResource failed with code {result}")

    def uninitialize(self) -> None:
        result = int(self._library.RG_Uninitialize())
        if result != 0:
            raise RusGuardSdkError(f"RG_Uninitialize failed with code {result}")


def run_rusguard_sdk_enumeration_command(*, library_path: str | None = None) -> int:
    resolved_library_path = resolve_library_path(library_path)
    try:
        sdk = CountOnlyRusGuardSdk(resolved_library_path)
        report = run_safe_diagnostic(sdk)
    except RusGuardSdkError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(render_report(report))
    return 0


def resolve_library_path(library_path: str | None) -> Path:
    raw_path = library_path or os.environ.get(_LIBRARY_PATH_ENV_VAR) or str(_DEFAULT_LIBRARY_PATH)
    return Path(raw_path).expanduser().resolve()


def run_safe_diagnostic(sdk: RusGuardSdkProtocol) -> DiagnosticReport:
    sdk.initialize()
    try:
        return DiagnosticReport(
            library_path=sdk.library_path,
            sections=(
                _build_section("USB_HID", RG_ENDPOINT_TYPE_USB_HID, sdk),
                _build_section("SERIAL", RG_ENDPOINT_TYPE_SERIAL, sdk),
            ),
        )
    finally:
        sdk.uninitialize()


def render_report(report: DiagnosticReport) -> str:
    lines = [
        "[RusGuard SDK]",
        f"library path: {report.library_path.as_posix()}",
        "library load ok",
        "initialize ok",
        "",
    ]
    for position, section in enumerate(report.sections):
        lines.append(f"[{section.title}]")
        lines.extend(section.lines)
        if position != len(report.sections) - 1:
            lines.append("")
    lines.extend(("", "uninitialize ok"))
    return "\n".join(lines)


def _build_section(title: str, endpoint_type_mask: int, sdk: RusGuardSdkProtocol) -> DiagnosticSection:
    endpoint_infos = sdk.find_endpoint_infos(endpoint_type_mask)
    lines = [f"count: {len(endpoint_infos)}"]
    for endpoint_info in endpoint_infos:
        lines.append(
            f"- index: {endpoint_info.index}, type: {endpoint_info.type}, address: {endpoint_info.address}, "
            f"friendly_name: {endpoint_info.friendly_name}"
        )
    return DiagnosticSection(title=title, lines=tuple(lines))


def _decode_ascii(value: bytes | ctypes.Array[ctypes.c_char]) -> str:
    raw = bytes(value)
    return raw.split(b"\x00", 1)[0].decode("ascii", errors="replace")
