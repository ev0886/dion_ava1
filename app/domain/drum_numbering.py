from __future__ import annotations

TOTAL_DRUM_POSITIONS = 32
CELLS_PER_SECTOR = 15
SECTORS_PER_QUARTER = 8
TOTAL_LOGICAL_SECTORS = TOTAL_DRUM_POSITIONS

_OPERATOR_QUARTER_ACCESS_POSITIONS: dict[int, int] = {
    1: 26,
    2: 18,
    3: 10,
    4: 2,
}


def logical_sector_from_drum_position(drum_position: int) -> int:
    _validate_drum_position(drum_position)
    return ((TOTAL_DRUM_POSITIONS - drum_position) % TOTAL_DRUM_POSITIONS) + 1


def drum_position_from_logical_sector(logical_sector: int) -> int:
    _validate_logical_sector(logical_sector)
    return (TOTAL_DRUM_POSITIONS - (logical_sector - 1)) % TOTAL_DRUM_POSITIONS


def logical_quarter_from_sector(logical_sector: int) -> int:
    _validate_logical_sector(logical_sector)
    return ((logical_sector - 1) // SECTORS_PER_QUARTER) + 1


def logical_quarter_from_drum_position(drum_position: int) -> int:
    return logical_quarter_from_sector(logical_sector_from_drum_position(drum_position))


def human_cell_number(drum_position: int, lock_number: int) -> int:
    _validate_lock_number(lock_number)
    logical_sector = logical_sector_from_drum_position(drum_position)
    return ((logical_sector - 1) * CELLS_PER_SECTOR) + lock_number


def operator_quarter_access_pos(quarter_number: int) -> int:
    try:
        return _OPERATOR_QUARTER_ACCESS_POSITIONS[quarter_number]
    except KeyError as exc:
        raise ValueError(f"Unsupported operator quarter: {quarter_number}") from exc


def _validate_drum_position(drum_position: int) -> None:
    if not 0 <= drum_position < TOTAL_DRUM_POSITIONS:
        raise ValueError(f"drum_position must be between 0 and {TOTAL_DRUM_POSITIONS - 1}")


def _validate_logical_sector(logical_sector: int) -> None:
    if not 1 <= logical_sector <= TOTAL_LOGICAL_SECTORS:
        raise ValueError(f"logical_sector must be between 1 and {TOTAL_LOGICAL_SECTORS}")


def _validate_lock_number(lock_number: int) -> None:
    if not 1 <= lock_number <= CELLS_PER_SECTOR:
        raise ValueError(f"lock_number must be between 1 and {CELLS_PER_SECTOR}")
