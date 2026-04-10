from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def runtime_today() -> date:
    return utc_now().date()


def runtime_day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min)
    return start, start + timedelta(days=1)
