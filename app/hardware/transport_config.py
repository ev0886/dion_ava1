from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EndpointTimeoutSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connect_timeout_ms: int = Field(default=1000, ge=1, le=60000)
    read_timeout_ms: int = Field(default=1000, ge=1, le=60000)
    write_timeout_ms: int = Field(default=1000, ge=1, le=60000)


class CommonEndpointSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=100)
    driver_name: str = Field(min_length=1, max_length=100)
    enabled: bool = True
    timeouts: EndpointTimeoutSettings = Field(default_factory=EndpointTimeoutSettings)

    @field_validator("code", "driver_name")
    @classmethod
    def _validate_non_blank_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


class SerialTransportSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transport: Literal["serial"]
    port: str = Field(min_length=1, max_length=255)
    baudrate: int = Field(gt=0, le=921600)
    data_bits: Literal[5, 6, 7, 8] = 8
    parity: Literal["none", "even", "odd"] = "none"
    stop_bits: Literal[1, 2] = 1

    @field_validator("port")
    @classmethod
    def _validate_port(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


class TcpTransportSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transport: Literal["tcp"]
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)

    @field_validator("host")
    @classmethod
    def _validate_host(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        if cleaned == "0.0.0.0":
            raise ValueError("must be a reachable remote host, not 0.0.0.0")
        return cleaned


TransportSettings = Annotated[SerialTransportSettings | TcpTransportSettings, Field(discriminator="transport")]


REAL_HARDWARE_ENDPOINT_NAMES: tuple[str, ...] = (
    "drum_controller",
    "lock_controller",
    "rfid_reader",
)


class HardwareEndpointTransportConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: CommonEndpointSettings
    transport: TransportSettings


class LockControllerProtocolSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    board_address: int = Field(default=0, ge=0, le=255)


class DrumHardwareEndpointTransportConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: CommonEndpointSettings
    transport: SerialTransportSettings
    protocol: "DrumControllerProtocolSettings" = Field(default_factory=lambda: DrumControllerProtocolSettings())


class DrumControllerProtocolSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    move_completion_timeout_ms: int = Field(default=30000, ge=1, le=60000)
    post_move_unlock_delay_ms: int = Field(default=0, ge=0, le=60000)


class LockHardwareEndpointTransportConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: CommonEndpointSettings
    transport: SerialTransportSettings
    protocol: LockControllerProtocolSettings = Field(default_factory=LockControllerProtocolSettings)


class RfidSerialTransportSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transport: Literal["serial"]
    port: str = Field(min_length=1, max_length=255)
    sdk_library: str | None = Field(default=None, min_length=1, max_length=1024)
    baudrate: int = Field(default=9600, gt=0, le=921600)
    data_bits: Literal[5, 6, 7, 8] = 8
    parity: Literal["none", "even", "odd"] = "none"
    stop_bits: Literal[1, 2] = 1

    @field_validator("port", "sdk_library")
    @classmethod
    def _validate_optional_path_like_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


class RfidHardwareEndpointTransportConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: CommonEndpointSettings
    transport: RfidSerialTransportSettings


AnyHardwareEndpointTransportConfig = (
    HardwareEndpointTransportConfig
    | DrumHardwareEndpointTransportConfig
    | LockHardwareEndpointTransportConfig
    | RfidHardwareEndpointTransportConfig
)


class RealHardwareSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    drum_controller: DrumHardwareEndpointTransportConfig | None = None
    lock_controller: LockHardwareEndpointTransportConfig | None = None
    rfid_reader: RfidHardwareEndpointTransportConfig | None = None


def real_hardware_endpoints_example() -> dict[str, object]:
    return {
        "drum_controller": {
            "endpoint": {
                "code": "drum-1",
                "driver_name": "drum-driver",
                "enabled": True,
                "timeouts": {
                    "connect_timeout_ms": 1000,
                    "read_timeout_ms": 1000,
                    "write_timeout_ms": 1000,
                },
            },
            "protocol": {
                "move_completion_timeout_ms": 35000,
                "post_move_unlock_delay_ms": 3000,
            },
            "transport": {
                "transport": "serial",
                "port": "/dev/serial/by-path/platform-1000110000.pcie-pci-0001:01:00.0-usb-0:1.2:1.0-port0",
                "baudrate": 9600,
                "data_bits": 8,
                "parity": "none",
                "stop_bits": 1,
            },
        },
        "lock_controller": {
            "endpoint": {
                "code": "lock-1",
                "driver_name": "lock-driver",
                "enabled": True,
                "timeouts": {
                    "connect_timeout_ms": 1000,
                    "read_timeout_ms": 1000,
                    "write_timeout_ms": 1000,
                },
            },
            "protocol": {
                "board_address": 0,
            },
            "transport": {
                "transport": "serial",
                "port": "/dev/serial/by-path/platform-1000110000.pcie-pci-0001:01:00.0-usb-0:1.1:1.0-port0",
                "baudrate": 19200,
                "data_bits": 8,
                "parity": "none",
                "stop_bits": 1,
            },
        },
        "rfid_reader": {
            "endpoint": {
                "code": "rfid-1",
                "driver_name": "rfid-driver",
                "enabled": True,
                "timeouts": {
                    "connect_timeout_ms": 1000,
                    "read_timeout_ms": 1000,
                    "write_timeout_ms": 1000,
                },
            },
            "transport": {
                "transport": "serial",
                "port": "/dev/ttyACM0",
            },
        },
    }


def real_hardware_endpoints_example_json() -> str:
    return json.dumps(real_hardware_endpoints_example(), separators=(",", ":"))
