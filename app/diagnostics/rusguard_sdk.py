from __future__ import annotations

import ctypes
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


_DEFAULT_LIBRARY_PATH = (
    Path(__file__).resolve().parents[2] / "vendor" / "rusguard" / "linux_arm64_release" / "librgsec.so"
)
_LIBRARY_PATH_ENV_VAR = "DION_RUSGUARD_SDK_LIBRARY_PATH"

RG_ENDPOINT_TYPE_USB_HID = 0x01
RG_ENDPOINT_TYPE_SERIAL = 0x02
_DEFAULT_DEVICE_ADDRESS = 0
_API_ERROR_DETAILS = {
    0: ("EC_OK", "all good"),
    1: ("EC_FAIL", "generic failure"),
    2: ("EC_NOT_IMPLEMENTED", "functionality not implemented"),
    3: ("EC_BAD_ARGUMENT", "invalid argument"),
    4: ("EC_INVALID_HANDLE", "invalid or closed resource handle"),
    5: ("EC_INVALID_RESOURCE", "resource type is incompatible"),
    6: ("EC_INVALID_CONNECTION_TYPE", "unsupported connection type"),
    7: ("EC_INVALID_CONNECTION_ADDRESS", "connection address does not match connection type"),
    8: ("EC_INVALID_DEVICE_ADDRESS", "device address is invalid for this connection type"),
    9: ("EC_DEVICE_OPERATION_UNSUPPORTED", "device does not support this operation"),
    10: ("EC_DEVICE_NOT_CONNECTED", "device disconnected during exchange"),
    11: ("EC_DEVICE_NO_RESPOND", "device does not respond to requests"),
    12: ("EC_DEVICE_COMM_FAILURE", "device communication failure"),
    13: ("EC_DEVICE_PROTOCOL_FAILURE", "device protocol processing failure"),
    14: ("EC_POLL_NO_EVENTS", "event queue is empty"),
    15: ("EC_POLL_QUEUE_CLOSED", "event queue is closed or destroyed"),
    16: ("EC_CALL_INIT", "device initialization required"),
    17: ("EC_DEVICE_INVALID_COMMAND", "device command is unsupported or missing"),
    18: ("EC_DEVICE_INVALID_PARAM", "invalid device command parameter"),
    19: ("EC_DEVICE_INVALID_PIN", "invalid device settings PIN"),
    20: ("EC_DEVICE_COMMAND_TIMEOUT", "device command timed out"),
    21: ("EC_DEVICE_NO_CARD", "no card on reader"),
    22: ("EC_DEVICE_UOWN_CARD", "device could not recognize the card"),
    23: ("EC_DEVICE_INCOMPATIBLE_CARD", "card is incompatible with this operation"),
    24: ("EC_DEVICE_AUTH_FAIL", "card authorization failed"),
    25: ("EC_DEVICE_PROFILE_FAIL", "incorrect profile in use"),
    26: ("EC_DEVICE_RW_FAIL", "card read/write authorization failed"),
    27: ("EC_IO_OPEN_FAIL", "connection open failed"),
    28: ("EC_IO_CLOSE_FAIL", "connection close failed"),
    29: ("EC_IO_READ_FAIL", "data send failed"),
    30: ("EC_IO_WRITE_FAIL", "data read failed"),
    31: ("EC_IO_CLOSED", "operation interrupted because the connection was closed"),
    32: ("EC_DEVICE_IN_BOOT", "device in boot mode"),
    33: ("EC_DEVICE_FW_INVALID_MODEL", "firmware file does not match device model"),
    34: ("EC_FILE_NOT_FOUND", "file not found"),
    35: ("EC_FINGERPRINT_UNFOUND", "fingerprint not found"),
}


class _RgEndpointInfo(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("type", ctypes.c_uint8),
        ("address", ctypes.c_char * 64),
        ("friendly_name", ctypes.c_char * 128),
    ]


class _RgEndpoint(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("type", ctypes.c_uint8),
        ("address", ctypes.c_char_p),
    ]


class _RgCardInfo(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("type", ctypes.c_uint8),
        ("uid", ctypes.c_uint8 * 7),
    ]


class _RgCardMemory(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("profile_block", ctypes.c_uint8),
        ("block_data", ctypes.c_uint8 * 16),
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

    def diagnose_serial_endpoint(self, endpoint_info: EndpointInfo) -> "SerialEndpointDiagnosticResult": ...

    def uninitialize(self) -> None: ...


@dataclass(frozen=True, slots=True)
class DiagnosticSection:
    title: str
    lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DiagnosticReport:
    library_path: Path
    sections: tuple[DiagnosticSection, ...]


@dataclass(frozen=True, slots=True)
class SerialEndpointDiagnosticResult:
    endpoint_info: EndpointInfo
    open_ok: bool
    open_code: int
    open_code_name: str
    open_code_message: str
    status_ok: bool | None
    status_code: int | None


@dataclass(frozen=True, slots=True)
class SerialOpenDiagnosticReport:
    library_path: Path
    serial_results: tuple[SerialEndpointDiagnosticResult, ...]


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
        self._library.RG_InitDevice.argtypes = [ctypes.POINTER(_RgEndpoint), ctypes.c_uint8]
        self._library.RG_InitDevice.restype = ctypes.c_uint32
        self._library.RG_GetStatus.argtypes = [
            ctypes.POINTER(_RgEndpoint),
            ctypes.c_uint8,
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.POINTER(ctypes.c_uint8),
            ctypes.POINTER(_RgCardInfo),
            ctypes.POINTER(_RgCardMemory),
        ]
        self._library.RG_GetStatus.restype = ctypes.c_uint32
        self._library.RG_CloseDevice.argtypes = [ctypes.POINTER(_RgEndpoint), ctypes.c_uint8]
        self._library.RG_CloseDevice.restype = ctypes.c_uint32

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

    def diagnose_serial_endpoint(self, endpoint_info: EndpointInfo) -> SerialEndpointDiagnosticResult:
        endpoint_address = ctypes.create_string_buffer(endpoint_info.address.encode("ascii"))
        endpoint = _RgEndpoint(type=endpoint_info.type, address=ctypes.cast(endpoint_address, ctypes.c_char_p))
        close_error: RusGuardSdkError | None = None
        result: SerialEndpointDiagnosticResult | None = None
        open_code = int(self._library.RG_InitDevice(ctypes.byref(endpoint), ctypes.c_uint8(_DEFAULT_DEVICE_ADDRESS)))
        open_code_name, open_code_message = decode_api_error(open_code)
        if open_code != 0:
            return SerialEndpointDiagnosticResult(
                endpoint_info=endpoint_info,
                open_ok=False,
                open_code=open_code,
                open_code_name=open_code_name,
                open_code_message=open_code_message,
                status_ok=None,
                status_code=None,
            )

        try:
            status_type = ctypes.c_uint8()
            pin_states = ctypes.c_uint8()
            card_info = _RgCardInfo()
            card_memory = _RgCardMemory()
            status_code = int(
                self._library.RG_GetStatus(
                    ctypes.byref(endpoint),
                    ctypes.c_uint8(_DEFAULT_DEVICE_ADDRESS),
                    ctypes.byref(status_type),
                    ctypes.byref(pin_states),
                    ctypes.byref(card_info),
                    ctypes.byref(card_memory),
                )
            )
            result = SerialEndpointDiagnosticResult(
                endpoint_info=endpoint_info,
                open_ok=True,
                open_code=open_code,
                open_code_name=open_code_name,
                open_code_message=open_code_message,
                status_ok=status_code == 0,
                status_code=status_code,
            )
        finally:
            close_code = int(self._library.RG_CloseDevice(ctypes.byref(endpoint), ctypes.c_uint8(_DEFAULT_DEVICE_ADDRESS)))
            if close_code != 0:
                close_error = RusGuardSdkError(
                    f"RG_CloseDevice failed with code {close_code} for address {endpoint_info.address}"
                )
        if close_error is not None:
            raise close_error
        assert result is not None
        return result


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


def run_rusguard_sdk_serial_open_diagnostic_command(*, library_path: str | None = None) -> int:
    resolved_library_path = resolve_library_path(library_path)
    try:
        sdk = CountOnlyRusGuardSdk(resolved_library_path)
        report = run_serial_open_diagnostic(sdk)
    except RusGuardSdkError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(render_serial_open_report(report))
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


def run_serial_open_diagnostic(sdk: RusGuardSdkProtocol) -> SerialOpenDiagnosticReport:
    sdk.initialize()
    try:
        serial_endpoints = sdk.find_endpoint_infos(RG_ENDPOINT_TYPE_SERIAL)
        return SerialOpenDiagnosticReport(
            library_path=sdk.library_path,
            serial_results=tuple(sdk.diagnose_serial_endpoint(endpoint_info) for endpoint_info in serial_endpoints),
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


def render_serial_open_report(report: SerialOpenDiagnosticReport) -> str:
    lines = [
        "[RusGuard SDK]",
        f"library path: {report.library_path.as_posix()}",
        "library load ok",
        "initialize ok",
        "",
        "[SERIAL]",
        f"count: {len(report.serial_results)}",
    ]
    for result in report.serial_results:
        line = f"- index: {result.endpoint_info.index}, address: {result.endpoint_info.address}, open: "
        if not result.open_ok:
            lines.append(
                f"{line}fail(code={result.open_code}, name={result.open_code_name}, message={result.open_code_message})"
            )
            continue
        status_fragment = "ok" if result.status_ok else f"fail(code={result.status_code})"
        lines.append(f"{line}ok, status: {status_fragment}")
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


def decode_api_error(code: int) -> tuple[str, str]:
    return _API_ERROR_DETAILS.get(code, ("UNKNOWN_API_ERROR", "unknown RusGuard SDK error"))
