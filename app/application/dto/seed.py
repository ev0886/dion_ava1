from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SeedWorkflowResultDTO:
    workflow: str
    created_count: int
    skipped_count: int
    deleted_count: int
    created: tuple[str, ...]
    skipped: tuple[str, ...]
    deleted: tuple[str, ...]

