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
_FIND_ENDPOINTS_SKIP_REASON = "find_endpoints skipped: vendor ABI for RG_FindEndPoints is unproven in repo"


class RusGuardSdkError(RuntimeError):
    pass


class RusGuardSdkProtocol(Protocol):
    library_path: Path

    def initialize(self) -> None: ...

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
        self._library.RG_InitializeLib.restype = ctypes.c_int
        self._library.RG_Uninitialize.argtypes = []
        self._library.RG_Uninitialize.restype = ctypes.c_int

    def initialize(self) -> None:
        result = int(self._library.RG_InitializeLib())
        if result != 0:
            raise RusGuardSdkError(f"RG_InitializeLib failed with code {result}")

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
                DiagnosticSection(title="USB_HID", lines=(_FIND_ENDPOINTS_SKIP_REASON,)),
                DiagnosticSection(title="SERIAL", lines=(_FIND_ENDPOINTS_SKIP_REASON,)),
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
