from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.config import AppSettings, HardwareProvider
from app.domain.enums import HardwareEndpointType
from app.hardware import HardwareFacade, LockState, MockDrumAdapter, MockLockAdapter, MockRfidAdapter
from app.hardware.dto import HardwareOperationStatus, RfidReadResult
from app.hardware.factory import HardwareBundle
from app.domain.enums import BindingType, ItemStatus, OperationState, RoleCode, SlotStatus, SlotType, UserStatus
from app.persistence.models import (
    InventoryBalance,
    Item,
    Operation,
    OperationStateHistory,
    RecoveryCase,
    Role,
    Slot,
    SlotItemBinding,
    User,
    UserRfidCard,
)


def test_app_creation_smoke(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_smoke.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_and_readiness(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_readiness.sqlite3"))

    with TestClient(app) as client:
        health = client.get("/health")
        readiness = client.get("/readiness")

    assert health.status_code == 200
    assert readiness.status_code == 200
    assert readiness.json()["readiness_status"] == "ready"


def test_auth_and_inventory_happy_path(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_auth_inventory.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        auth_response = client.post("/auth/resolve", json={"user_id": 1})
        inventory_response = client.get("/inventory/1/1")

    assert auth_response.status_code == 200
    assert auth_response.json()["user_code"] == "user-1"
    assert inventory_response.status_code == 200
    assert inventory_response.json()["balance"]["quantity"] == 5


def test_auth_read_and_resolve_rfid_happy_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app(_settings(tmp_path, "api_auth_rfid.sqlite3"))
    _seed_base_domain(app)
    rfid_reader = MockRfidAdapter()
    rfid_reader.queue_card("00 0f-e2 76 7c 00 45")
    hardware_bundle = HardwareBundle(
        provider=HardwareProvider.MOCK,
        drum_controller=MockDrumAdapter(),
        lock_controller=MockLockAdapter(lock_states={(1, 1): LockState.LOCKED}),
        rfid_reader=rfid_reader,
        facade=HardwareFacade(
            drum_controller=MockDrumAdapter(),
            lock_controller=MockLockAdapter(lock_states={(1, 1): LockState.LOCKED}),
            rfid_reader=rfid_reader,
        ),
    )
    monkeypatch.setattr("app.application.composition.create_hardware_bundle", lambda _settings: hardware_bundle)

    with TestClient(app) as client:
        response = client.post("/auth/read-and-resolve-rfid", json={})

    assert response.status_code == 200
    assert response.json() == {
        "rfid_uid": "000FE2767C0045",
        "is_duplicate": False,
        "user": {
            "user_id": 1,
            "user_code": "user-1",
            "full_name": "User One",
            "status": "active",
            "is_active": True,
            "role_code": "user",
        },
    }


def test_auth_read_and_resolve_rfid_api_retries_past_partial_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(_settings(tmp_path, "api_auth_rfid_retry.sqlite3"))
    _seed_base_domain(app)

    class _PartialThenFullRfidReader:
        def __init__(self) -> None:
            self.reads = [
                (None, False, "Ignoring transient partial RFID read (2/7 bytes)."),
                ("000FE2767C0045", False, None),
            ]
            self.index = 0

        def ping(self):
            raise NotImplementedError

        def read_card(self):
            uid, is_duplicate, message = self.reads[min(self.index, len(self.reads) - 1)]
            self.index += 1
            return RfidReadResult(
                device_type=HardwareEndpointType.RFID_READER,
                status=HardwareOperationStatus.NO_CARD if uid is None else HardwareOperationStatus.SUCCESS,
                ok=True,
                uid=uid,
                is_duplicate=is_duplicate,
                message=message,
            )

        def clear_buffer(self):
            raise NotImplementedError

    rfid_reader = _PartialThenFullRfidReader()
    hardware_bundle = HardwareBundle(
        provider=HardwareProvider.MOCK,
        drum_controller=MockDrumAdapter(),
        lock_controller=MockLockAdapter(lock_states={(1, 1): LockState.LOCKED}),
        rfid_reader=rfid_reader,
        facade=HardwareFacade(
            drum_controller=MockDrumAdapter(),
            lock_controller=MockLockAdapter(lock_states={(1, 1): LockState.LOCKED}),
            rfid_reader=rfid_reader,
        ),
    )
    monkeypatch.setattr("app.application.composition.create_hardware_bundle", lambda _settings: hardware_bundle)

    with TestClient(app) as client:
        response = client.post("/auth/read-and-resolve-rfid", json={})

    assert response.status_code == 200
    assert response.json()["rfid_uid"] == "000FE2767C0045"



def test_dispense_operation_happy_path(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_dispense.sqlite3"))
    _seed_base_domain(app)

    with TestClient(app) as client:
        response = client.post(
            "/operations/dispense",
            json={"user_id": 1, "item_id": 1, "slot_id": 1, "quantity": 1},
        )

    assert response.status_code == 200
    assert response.json()["operation_state"] == "completed"
    assert response.json()["qty_confirmed"] == 1


def test_real_dispense_realigns_stale_slot_board_address_before_unlock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.hardware import factory as hardware_factory

    sqlite_filename = "api_real_dispense.sqlite3"
    setup_app = create_app(_settings(tmp_path, sqlite_filename))
    _seed_base_domain(setup_app)

    monkeypatch.setattr(hardware_factory, "_create_transport_client", _fake_real_dispense_transport_client)
    real_app = create_app(_real_settings(tmp_path, sqlite_filename))

    with TestClient(real_app) as client:
        response = client.post(
            "/operations/dispense",
            json={"user_id": 1, "item_id": 1, "slot_id": 1, "quantity": 1},
        )
        inventory_response = client.get("/inventory/1/1")

    assert response.status_code == 200
    assert response.json()["operation_state"] == "completed"
    assert response.json()["hardware_context"]["slot"]["board_address"] == 0
    assert response.json()["hardware_context"]["slot"]["lock_number"] == 1
    assert inventory_response.status_code == 200
    assert inventory_response.json()["balance"]["quantity"] == 4


def test_recovery_endpoints_happy_path(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_recovery.sqlite3"))
    _seed_base_domain(app)
    _seed_recovery_operation(app)

    with TestClient(app) as client:
        scan_response = client.post("/recovery/scan")

        assert scan_response.status_code == 200
        payload = scan_response.json()
        assert payload["candidate_operation_ids"] == [1]

        recovery_case_id = payload["open_cases"][0]["recovery_case_id"]
        case_response = client.get(f"/recovery/cases/{recovery_case_id}")
        manual_response = client.get(f"/recovery/cases/{recovery_case_id}/manual-resolution")

    assert case_response.status_code == 200
    assert manual_response.status_code == 200
    assert manual_response.json()["recovery_case_id"] == recovery_case_id


def test_error_mapping_returns_400_for_validation_error(tmp_path: Path) -> None:
    app = create_app(_settings(tmp_path, "api_errors.sqlite3"))

    with TestClient(app) as client:
        response = client.get("/inventory/0/1")

    assert response.status_code == 400
    assert response.json()["error"] == "validation_error"


def _settings(tmp_path: Path, sqlite_filename: str) -> AppSettings:
    return AppSettings(
        data_dir=tmp_path,
        sqlite_filename=sqlite_filename,
        alembic_config_path=Path("alembic.ini"),
    )


def _real_settings(tmp_path: Path, sqlite_filename: str) -> AppSettings:
    return AppSettings(
        data_dir=tmp_path,
        sqlite_filename=sqlite_filename,
        alembic_config_path=Path("alembic.ini"),
        hardware_provider=HardwareProvider.REAL,
        hardware_real_endpoints={
            "drum_controller": _serial_endpoint_config(code="drum-1", driver_name="drum-driver", port="COM1"),
            "lock_controller": _lock_serial_endpoint_config(code="lock-1", driver_name="lock-driver", port="COM2"),
            "rfid_reader": _serial_endpoint_config(code="rfid-1", driver_name="rfid-driver", port="COM3"),
        },
    )


def _seed_base_domain(app) -> None:
    with app.state.session_factory() as session:
        role = Role(code=RoleCode.USER, name="User")
        session.add(role)
        session.flush()

        user = User(
            role_id=role.id,
            user_code="user-1",
            full_name="User One",
            status=UserStatus.ACTIVE,
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
            drum_position=3,
            board_address=1,
            lock_number=1,
            capacity=10,
            status=SlotStatus.ACTIVE,
        )
        session.add_all((user, item, slot))
        session.flush()
        session.add(
            SlotItemBinding(
                slot_id=slot.id,
                item_id=item.id,
                binding_type=BindingType.RETURN,
                is_active=True,
                valid_from=None,
                valid_to=None,
            )
        )
        session.add(InventoryBalance(slot_id=slot.id, item_id=item.id, quantity=5))
        session.add(
            UserRfidCard(
                user_id=user.id,
                card_uid="000FE2767C0045",
                is_active=True,
                issued_at=user.created_at,
                revoked_at=None,
            )
        )
        session.commit()


class _FakeRealDispenseTransport:
    def __init__(self, responses: list[bytes], *, sequence_responses: list[bytes] | None = None) -> None:
        self._responses = list(responses)
        self._sequence_responses = list(sequence_responses or [])

    def request(self, payload: bytes, *, timeout_ms: int | None = None) -> bytes:
        if not self._responses:
            raise AssertionError("No fake transport responses remain.")
        return self._responses.pop(0)

    def send(self, payload: bytes) -> None:
        return None

    def request_sequence(
        self,
        payloads: list[bytes],
        *,
        timeout_ms: int | None = None,
        response_timeouts_ms: list[int] | None = None,
    ) -> list[bytes]:
        if len(self._sequence_responses) < len(payloads):
            raise AssertionError("Not enough fake sequence responses remain.")
        responses = self._sequence_responses[: len(payloads)]
        del self._sequence_responses[: len(payloads)]
        return responses


def _fake_real_dispense_transport_client(config):
    if config is None:
        return None
    if config.endpoint.code == "lock-1":
        return _FakeRealDispenseTransport([bytes.fromhex("02 00 00 81 10 00 03 96")])
    if config.endpoint.code == "rfid-1":
        return _FakeRealDispenseTransport([b"PONG\n"])
    return _FakeRealDispenseTransport([], sequence_responses=[bytes.fromhex("21 AA AA C4"), bytes.fromhex("25 C0")])


def _serial_endpoint_config(*, code: str, driver_name: str, port: str) -> dict[str, object]:
    return {
        "endpoint": {
            "code": code,
            "driver_name": driver_name,
            "enabled": True,
            "timeouts": {
                "connect_timeout_ms": 1000,
                "read_timeout_ms": 1000,
                "write_timeout_ms": 1000,
            },
        },
        "transport": {
            "transport": "serial",
            "port": port,
            "baudrate": 9600,
            "data_bits": 8,
            "parity": "none",
            "stop_bits": 1,
        },
    }


def _lock_serial_endpoint_config(*, code: str, driver_name: str, port: str, board_address: int = 0) -> dict[str, object]:
    return {
        "endpoint": {
            "code": code,
            "driver_name": driver_name,
            "enabled": True,
            "timeouts": {
                "connect_timeout_ms": 1000,
                "read_timeout_ms": 1000,
                "write_timeout_ms": 1000,
            },
        },
        "protocol": {
            "board_address": board_address,
        },
        "transport": {
            "transport": "serial",
            "port": port,
            "baudrate": 19200,
            "data_bits": 8,
            "parity": "none",
            "stop_bits": 1,
        },
    }


def _seed_recovery_operation(app) -> None:
    with app.state.session_factory() as session:
        operation = Operation(
            session_id=None,
            operation_type="dispense",
            operation_state=OperationState.USER_ACTION_PENDING,
            user_id=1,
            item_id=1,
            slot_id=1,
            qty_requested=1,
            qty_confirmed=None,
            result=None,
            error_code=None,
            error_message=None,
            hardware_context_json={},
            business_context_json={},
            started_at=None,
            finished_at=None,
        )
        session.add(operation)
        session.flush()
        session.add(
            OperationStateHistory(
                operation_id=operation.id,
                state=OperationState.USER_ACTION_PENDING,
                comment="seeded recovery candidate",
                context_json={},
            )
        )
        session.commit()
