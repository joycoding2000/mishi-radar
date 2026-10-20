"""Deterministic decimal math and ranking helpers."""

from __future__ import annotations

from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, ROUND_HALF_UP
from typing import Iterable, Sequence

from .model import (
    Numeric,
    ValueStatus,
)

TWELVE_PLACES = Decimal("0.000000000001")
CENT = Decimal("0.01")
ZERO = Decimal(0)
ONE = Decimal(1)


def dec(value: Decimal | int | str | float) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    return Decimal(str(value))


def q12(value: Decimal) -> Decimal:
    return value.quantize(TWELVE_PLACES, rounding=ROUND_HALF_EVEN)


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def mean(values: Sequence[Decimal]) -> Decimal:
    if not values:
        raise ValueError("mean of empty sequence")
    return sum(values, ZERO) / Decimal(len(values))


def sample_std(values: Sequence[Decimal]) -> Decimal:
    if len(values) < 2:
        raise ValueError("sample standard deviation needs at least two values")
    avg = mean(values)
    variance = sum(((v - avg) ** 2 for v in values), ZERO) / Decimal(len(values) - 1)
    return variance.sqrt()


def percentile_high(value: Decimal, population: Sequence[Decimal]) -> Decimal | None:
    """Q+ = (count(x < value) + 0.5 * count(x == value)) / len(population)."""

    n = len(population)
    if n == 0:
        return None
    less = sum(1 for item in population if item < value)
    equal = sum(1 for item in population if item == value)
    return (Decimal(less) + Decimal(equal) / Decimal(2)) / Decimal(n)


def percentile_low(value: Decimal, population: Sequence[Decimal]) -> Decimal | None:
    q = percentile_high(value, population)
    return None if q is None else ONE - q


def ceil_to_tick(price: Decimal, tick: Decimal) -> Decimal:
    if tick <= 0:
        raise ValueError("tick must be positive")
    return (price / tick).to_integral_value(rounding=ROUND_CEILING) * tick


def floor_to_tick(price: Decimal, tick: Decimal) -> Decimal:
    if tick <= 0:
        raise ValueError("tick must be positive")
    return (price / tick).to_integral_value(rounding=ROUND_FLOOR) * tick


def safe_div(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return numerator / denominator


def compound(values: Iterable[Decimal]) -> Decimal:
    result = ONE
    for value in values:
        result *= ONE + value
    return result


def key_decimal(value: Decimal) -> Decimal:
    return q12(value)


def negative(value: Decimal) -> Decimal:
    return -q12(value)


def window(sequence: Sequence, end_index: int, count: int) -> Sequence | None:
    """Return the last ``count`` items ending at ``end_index`` (inclusive)."""

    start = end_index - count + 1
    if count <= 0 or start < 0 or end_index >= len(sequence):
        return None
    return sequence[start : end_index + 1]


def numeric_values(items: Sequence[Numeric]) -> tuple[list[Decimal], Numeric | None]:
    """Extract usable values or return the first blocking Numeric."""

    values: list[Decimal] = []
    for item in items:
        if item.status is ValueStatus.NOT_APPLICABLE:
            return [], item
        if not item.usable:
            return [], item
        assert item.value is not None
        values.append(item.value)
    return values, None
