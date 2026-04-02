from __future__ import annotations

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


class HardwareEndpointTransportConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: CommonEndpointSettings
    transport: TransportSettings


class RealHardwareSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    drum_controller: HardwareEndpointTransportConfig | None = None
    lock_controller: HardwareEndpointTransportConfig | None = None
    rfid_reader: HardwareEndpointTransportConfig | None = None
