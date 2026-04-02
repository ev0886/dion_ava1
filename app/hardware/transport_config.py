from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


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


class SerialTransportSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transport: Literal["serial"]
    port: str = Field(min_length=1, max_length=255)
    baudrate: int = Field(gt=0, le=921600)
    data_bits: Literal[5, 6, 7, 8] = 8
    parity: Literal["none", "even", "odd"] = "none"
    stop_bits: Literal[1, 2] = 1


class TcpTransportSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transport: Literal["tcp"]
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)


TransportSettings = Annotated[SerialTransportSettings | TcpTransportSettings, Field(discriminator="transport")]


class HardwareEndpointTransportConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: CommonEndpointSettings
    transport: TransportSettings


class RealHardwareSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    drum_controller: HardwareEndpointTransportConfig | None = None
    lock_controller: HardwareEndpointTransportConfig | None = None
    rfid_reader: HardwareEndpointTransportConfig | None = None
