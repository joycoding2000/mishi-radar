"""U1 local-time contract shared by the OD-1 and OD-2 kernels.

All accepted timestamps are explicit Asia/Shanghai wall-clock ISO values.  The
kernel never applies the host machine's timezone and never accepts UTC/offset
suffixes on local-clock fields.  Date-only values remain dates; callers that
need legacy synthetic compatibility must opt in explicitly.
"""

from __future__ import annotations

import re
from datetime import date, datetime

LOCAL_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LOCAL_DATETIME_PATTERN = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?$"
)
OFFSET_SUFFIX_PATTERN = re.compile(r"(?:Z|z|[+-]\d{2}:?\d{2})$")


class TimeContractError(ValueError):
    """Raised when a value is not an explicit local time/date."""


def _reject_offset(value: str, field: str) -> None:
    if OFFSET_SUFFIX_PATTERN.search(value):
        raise TimeContractError(f"{field}_OFFSET_NOT_ALLOWED:{value}")


def validate_local_date(value: str, *, field: str = "date") -> str:
    if not isinstance(value, str) or not LOCAL_DATE_PATTERN.fullmatch(value):
        raise TimeContractError(f"{field}_INVALID_LOCAL_DATE:{value!r}")
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise TimeContractError(f"{field}_INVALID_LOCAL_DATE:{value!r}") from exc
    return value


def parse_local_datetime(
    value: str,
    *,
    field: str = "timestamp",
    allow_date: bool = False,
) -> datetime:
    if not isinstance(value, str) or not value or value != value.strip():
        raise TimeContractError(f"{field}_INVALID_LOCAL_DATETIME:{value!r}")
    _reject_offset(value, field)
    if LOCAL_DATE_PATTERN.fullmatch(value):
        if not allow_date:
            raise TimeContractError(f"{field}_DATE_ONLY_NOT_ALLOWED:{value}")
        validate_local_date(value, field=field)
        return datetime.combine(date.fromisoformat(value), datetime.min.time())
    if not LOCAL_DATETIME_PATTERN.fullmatch(value):
        raise TimeContractError(f"{field}_INVALID_LOCAL_DATETIME:{value!r}")
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise TimeContractError(f"{field}_INVALID_LOCAL_DATETIME:{value!r}") from exc


def validate_local_datetime(
    value: str,
    *,
    field: str = "timestamp",
    allow_date: bool = False,
) -> str:
    parse_local_datetime(value, field=field, allow_date=allow_date)
    return value


def is_before_open(value: str, trade_date: str, *, open_time: str = "09:30:00") -> bool:
    """Return True only for a local timestamp strictly before that day's open."""

    validate_local_date(trade_date, field="trade_date")
    candidate = parse_local_datetime(value, field="available_at")
    boundary = datetime.fromisoformat(f"{trade_date}T{open_time}")
    return candidate < boundary
