from app.hardware.contracts import DrumControllerContract, LockControllerContract, RfidReaderContract
from app.hardware.dto import (
    DrumPositionResult,
    HardwareHealthEntry,
    HardwareHealthSnapshot,
    LockBoardStatusResult,
    HardwareOperationResult,
    HardwareOperationStatus,
    LockState,
    LockStatusResult,
    MockHardwareMode,
    RfidReadResult,
    UnlockResult,
    UnlockTimeResult,
)
from app.hardware.drum_mock import MockDrumAdapter
from app.hardware.drum_real import RealDrumAdapter
from app.hardware.drum_stub_real import StubRealDrumAdapter
from app.hardware.exceptions import (
    HardwareBusyError,
    HardwareError,
    HardwareFailureError,
    HardwareProtocolNotImplementedError,
    HardwareTimeoutError,
    HardwareUnavailableError,
)
from app.hardware.facade import HardwareFacade
from app.hardware.factory import HardwareBundle, create_hardware_bundle
from app.hardware.lock_mock import MockLockAdapter
from app.hardware.lock_real import RealLockAdapter
from app.hardware.lock_stub_real import StubRealLockAdapter
from app.hardware.rfid_mock import MockRfidAdapter
from app.hardware.rfid_real import RealRfidAdapter
from app.hardware.rfid_rusguard import RfidStatusTransport, RusGuardAcmStatusTransport
from app.hardware.rfid_stub_real import StubRealRfidAdapter
from app.hardware.transport_config import (
    AnyHardwareEndpointTransportConfig,
    CommonEndpointSettings,
    DrumHardwareEndpointTransportConfig,
    EndpointTimeoutSettings,
    HardwareEndpointTransportConfig,
    LockControllerProtocolSettings,
    LockHardwareEndpointTransportConfig,
    REAL_HARDWARE_ENDPOINT_NAMES,
    RealHardwareSettings,
    RfidHardwareEndpointTransportConfig,
    RfidSerialTransportSettings,
    SerialTransportSettings,
    TcpTransportSettings,
    real_hardware_endpoints_example,
    real_hardware_endpoints_example_json,
)
from app.hardware.transports import (
    SerialRequestResponseTransport,
    SerialTransport,
    SerialTransportSkeleton,
    TcpRequestResponseTransport,
    TcpTransport,
    TcpTransportSkeleton,
)

__all__ = [
    "DrumControllerContract",
    "DrumPositionResult",
    "HardwareBusyError",
    "HardwareBundle",
    "HardwareError",
    "HardwareFacade",
    "HardwareFailureError",
    "HardwareHealthEntry",
    "HardwareHealthSnapshot",
    "HardwareOperationResult",
    "HardwareOperationStatus",
    "HardwareProtocolNotImplementedError",
    "HardwareTimeoutError",
    "HardwareUnavailableError",
    "AnyHardwareEndpointTransportConfig",
    "HardwareEndpointTransportConfig",
    "LockControllerContract",
    "LockControllerProtocolSettings",
    "LockBoardStatusResult",
    "LockHardwareEndpointTransportConfig",
    "LockState",
    "LockStatusResult",
    "MockDrumAdapter",
    "MockHardwareMode",
    "MockLockAdapter",
    "MockRfidAdapter",
    "REAL_HARDWARE_ENDPOINT_NAMES",
    "RealDrumAdapter",
    "RealHardwareSettings",
    "RealLockAdapter",
    "RealRfidAdapter",
    "RfidHardwareEndpointTransportConfig",
    "RfidSerialTransportSettings",
    "RfidStatusTransport",
    "RfidReadResult",
    "RfidReaderContract",
    "RusGuardAcmStatusTransport",
    "CommonEndpointSettings",
    "DrumHardwareEndpointTransportConfig",
    "EndpointTimeoutSettings",
    "SerialRequestResponseTransport",
    "SerialTransport",
    "SerialTransportSettings",
    "SerialTransportSkeleton",
    "StubRealDrumAdapter",
    "StubRealLockAdapter",
    "StubRealRfidAdapter",
    "TcpRequestResponseTransport",
    "TcpTransport",
    "TcpTransportSettings",
    "TcpTransportSkeleton",
    "UnlockResult",
    "UnlockTimeResult",
    "create_hardware_bundle",
    "real_hardware_endpoints_example",
    "real_hardware_endpoints_example_json",
]
