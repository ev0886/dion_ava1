from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class RfidStatusTransport(Protocol):
    def ping(self, timeout_ms: int | None = None) -> None: ...

    def read_card(self, timeout_ms: int | None = None) -> "RusGuardCardRead": ...


@dataclass(frozen=True, slots=True)
class RusGuardCardRead:
    status_type: int
    uid: str | None
    uid_size: int
