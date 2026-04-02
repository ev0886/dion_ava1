from __future__ import annotations

from dataclasses import dataclass

from app.config import AppSettings, HardwareProvider
from app.hardware.contracts import DrumControllerContract, LockControllerContract, RfidReaderContract
from app.hardware.drum_mock import MockDrumAdapter
from app.hardware.drum_stub_real import StubRealDrumAdapter
from app.hardware.facade import HardwareFacade
from app.hardware.lock_mock import MockLockAdapter
from app.hardware.lock_stub_real import StubRealLockAdapter
from app.hardware.rfid_mock import MockRfidAdapter
from app.hardware.rfid_stub_real import StubRealRfidAdapter
from app.hardware.dto import LockState


@dataclass(frozen=True, slots=True)
class HardwareBundle:
    provider: HardwareProvider
    drum_controller: DrumControllerContract
    lock_controller: LockControllerContract
    rfid_reader: RfidReaderContract
    facade: HardwareFacade


def create_hardware_bundle(settings: AppSettings) -> HardwareBundle:
    provider = settings.hardware_provider
    if provider is HardwareProvider.STUB_REAL:
        return _build_stub_real_hardware(provider)
    return _build_mock_hardware(provider)


def _build_mock_hardware(provider: HardwareProvider) -> HardwareBundle:
    drum_controller = MockDrumAdapter()
    lock_controller = MockLockAdapter(lock_states={(1, 1): LockState.LOCKED})
    rfid_reader = MockRfidAdapter()
    return HardwareBundle(
        provider=provider,
        drum_controller=drum_controller,
        lock_controller=lock_controller,
        rfid_reader=rfid_reader,
        facade=HardwareFacade(
            drum_controller=drum_controller,
            lock_controller=lock_controller,
            rfid_reader=rfid_reader,
        ),
    )


def _build_stub_real_hardware(provider: HardwareProvider) -> HardwareBundle:
    drum_controller = StubRealDrumAdapter()
    lock_controller = StubRealLockAdapter()
    rfid_reader = StubRealRfidAdapter()
    return HardwareBundle(
        provider=provider,
        drum_controller=drum_controller,
        lock_controller=lock_controller,
        rfid_reader=rfid_reader,
        facade=HardwareFacade(
            drum_controller=drum_controller,
            lock_controller=lock_controller,
            rfid_reader=rfid_reader,
        ),
    )
