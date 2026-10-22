"""Typed inputs and outputs for the OD-1 calculation kernel.

The kernel is deliberately data-source agnostic.  A caller supplies a
:class:`MarketSnapshot` that is already reconstructed *as of* ``business_date``
and carries the then-known values.  Missing, invalid, not-applicable and
unknown inputs are represented explicitly instead of being coerced to zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Mapping

from ..time_contract import validate_local_date, validate_local_datetime


class ValueStatus(str, Enum):
    VALUE = "VALUE"
    CONFIRMED_ZERO = "CONFIRMED_ZERO"
    RAW_ZERO_SEMANTICS_UNKNOWN = "RAW_ZERO_SEMANTICS_UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    MISSING = "MISSING"
    INVALID = "INVALID"
    CONFLICT = "CONFLICT"
    REQUEST_FAILED = "REQUEST_FAILED"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class ConditionStatus(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


class Eligibility(str, Enum):
    SCORABLE = "SCORABLE"
    BASE_EXCLUDED = "BASE_EXCLUDED"
    STRATEGY_NOT_APPLICABLE = "STRATEGY_NOT_APPLICABLE"
    INPUT_UNKNOWN = "INPUT_UNKNOWN"
    MISSING = "MISSING"
    FAILED = "FAILED"
    STALE = "STALE"
    INVALID = "INVALID"
    CONFLICT = "CONFLICT"


class SignalState(str, Enum):
    CANDIDATE = "CANDIDATE"
    ELIGIBLE_NOT_TRIGGERED = "ELIGIBLE_NOT_TRIGGERED"
    CONCENTRATION_EXCLUDED = "CONCENTRATION_EXCLUDED"
    BASE_EXCLUDED = "BASE_EXCLUDED"
    STRATEGY_NOT_APPLICABLE = "STRATEGY_NOT_APPLICABLE"
    INPUT_UNKNOWN = "INPUT_UNKNOWN"
    MISSING = "MISSING"
    FAILED = "FAILED"
    STALE = "STALE"
    INVALID = "INVALID"
    CONFLICT = "CONFLICT"


USABLE_STATUSES = frozenset({ValueStatus.VALUE, ValueStatus.CONFIRMED_ZERO})


@dataclass(frozen=True)
class Numeric:
    """A decimal value plus its data-quality state."""

    value: Decimal | None
    status: ValueStatus = ValueStatus.VALUE
    reason: str | None = None
    available_at: str | None = None
    unit: str | None = None
    source: str | None = None
    input_version: str | None = None

    def __post_init__(self) -> None:
        if self.status in USABLE_STATUSES and self.value is None:
            raise ValueError(f"{self.status.value} requires a value")
        if self.status is ValueStatus.CONFIRMED_ZERO and self.value != 0:
            raise ValueError("CONFIRMED_ZERO requires value 0")
        if self.available_at is not None:
            validate_local_datetime(self.available_at, field="available_at", allow_date=True)

    @property
    def usable(self) -> bool:
        return self.status in USABLE_STATUSES and self.value is not None

    def require(self) -> Decimal:
        if not self.usable:
            raise ValueError(f"value is not usable: {self.status.value} {self.reason or ''}")
        assert self.value is not None
        return self.value


def num(
    value: Decimal | int | str,
    *,
    status: ValueStatus = ValueStatus.VALUE,
    reason: str | None = None,
    available_at: str | None = None,
    unit: str | None = None,
    source: str | None = None,
    input_version: str | None = None,
) -> Numeric:
    if isinstance(value, Decimal):
        parsed = value
    else:
        parsed = Decimal(str(value))
    return Numeric(
        parsed,
        status,
        reason,
        available_at,
        unit,
        source,
        input_version,
    )


def confirmed_zero(**kwargs) -> Numeric:
    return Numeric(Decimal(0), ValueStatus.CONFIRMED_ZERO, **kwargs)


def raw_zero_unknown(**kwargs) -> Numeric:
    return Numeric(Decimal(0), ValueStatus.RAW_ZERO_SEMANTICS_UNKNOWN, **kwargs)


def not_applicable(reason: str, **kwargs) -> Numeric:
    return Numeric(None, ValueStatus.NOT_APPLICABLE, reason, **kwargs)


def missing(reason: str | None = None, **kwargs) -> Numeric:
    return Numeric(None, ValueStatus.MISSING, reason, **kwargs)


def invalid(reason: str | None = None, **kwargs) -> Numeric:
    return Numeric(None, ValueStatus.INVALID, reason, **kwargs)


def conflict(reason: str | None = None, **kwargs) -> Numeric:
    return Numeric(None, ValueStatus.CONFLICT, reason, **kwargs)


def unknown(reason: str | None = None, **kwargs) -> Numeric:
    return Numeric(None, ValueStatus.UNKNOWN, reason, **kwargs)


def request_failed(reason: str | None = None, **kwargs) -> Numeric:
    return Numeric(None, ValueStatus.REQUEST_FAILED, reason, **kwargs)


def stale(reason: str | None = None, **kwargs) -> Numeric:
    return Numeric(None, ValueStatus.STALE, reason, **kwargs)


def _multiply(a: Numeric, b: Numeric) -> Numeric:
    if a.status is ValueStatus.NOT_APPLICABLE:
        return a
    if b.status is ValueStatus.NOT_APPLICABLE:
        return b
    if not a.usable:
        return a
    if not b.usable:
        return b
    assert a.value is not None and b.value is not None
    return Numeric(a.value * b.value, ValueStatus.VALUE)


@dataclass(frozen=True)
class MarketBar:
    """One market day of raw and analysis-adjusted data.

    ``adjustment_factor`` is ``K(t, D)`` for the caller's anchor date D.
    ``volume_factor`` puts past volume on the same share basis as D.  Actual
    traded amount is never adjusted and is never inferred from close * volume.
    """

    date: str
    open: Numeric
    high: Numeric
    low: Numeric
    close: Numeric
    volume: Numeric
    amount: Numeric
    adjustment_factor: Numeric = field(default_factory=lambda: num(1))
    volume_factor: Numeric = field(default_factory=lambda: num(1))
    confirmed_no_trade: bool = False

    def adjusted_open(self) -> Numeric:
        return _multiply(self.open, self.adjustment_factor)

    def adjusted_high(self) -> Numeric:
        return _multiply(self.high, self.adjustment_factor)

    def adjusted_low(self) -> Numeric:
        return _multiply(self.low, self.adjustment_factor)

    def adjusted_close(self) -> Numeric:
        return _multiply(self.close, self.adjustment_factor)

    def adjusted_volume(self) -> Numeric:
        return _multiply(self.volume, self.volume_factor)


@dataclass(frozen=True)
class SecurityInfo:
    security_id: str
    exchange: str
    board: str
    instrument_type: str = "STOCK"
    listed_on: str | None = None
    listed_trading_days: int | None = None
    is_st: bool | None = False
    is_delisting: bool | None = False
    suspended: bool | None = False
    suspension_reason: str | None = None
    industry_id: str | None = None
    industry_known: bool = True

    @property
    def is_common_stock(self) -> bool:
        return self.instrument_type == "STOCK" and self.board in {"MAIN", "CHINEXT", "STAR"}


@dataclass(frozen=True)
class FinancialSnapshot:
    """Financial values known at ``business_date``.

    The TTM components are kept separately so the kernel, not the caller, can
    apply the approved TTM and average-equity formula.  ``available_at`` is the
    first market date on which the value may be used at the close.
    """

    report_period: str
    is_year_end: bool
    np_ytd: Numeric
    ocf_ytd: Numeric
    equity: Numeric
    pe_ttm: Numeric
    np_fy_prior: Numeric | None = None
    ocf_fy_prior: Numeric | None = None
    np_ytd_prior_same: Numeric | None = None
    ocf_ytd_prior_same: Numeric | None = None
    equity_prior_same: Numeric | None = None
    pe_business_date: str | None = None
    is_financial: bool | None = None
    industry_id: str | None = None
    available_at: str | None = None
    announced_on: str | None = None
    input_version: str = "SYNTHETIC"
    conflict: bool = False

    def __post_init__(self) -> None:
        if self.available_at is not None:
            validate_local_datetime(self.available_at, field="available_at", allow_date=True)
        if self.announced_on is not None:
            validate_local_date(self.announced_on, field="announced_on")

    @classmethod
    def from_ttm(
        cls,
        *,
        np_ttm: Decimal | int | str,
        ocf_ttm: Decimal | int | str,
        equity_average: Decimal | int | str,
        pe_ttm: Decimal | int | str,
        report_period: str,
        pe_business_date: str,
        available_at: str,
        is_financial: bool = False,
        industry_id: str | None = None,
        announced_on: str | None = None,
        input_version: str = "SYNTHETIC",
    ) -> "FinancialSnapshot":
        """Convenience constructor for already-computed TTM fixture values."""

        equity = num(equity_average)
        return cls(
            report_period=report_period,
            is_year_end=True,
            np_ytd=num(np_ttm),
            ocf_ytd=num(ocf_ttm),
            equity=equity,
            equity_prior_same=equity,
            pe_ttm=num(pe_ttm),
            pe_business_date=pe_business_date,
            is_financial=is_financial,
            industry_id=industry_id,
            available_at=available_at,
            announced_on=announced_on,
            input_version=input_version,
        )


@dataclass(frozen=True)
class MarketSnapshot:
    business_date: str
    calendar: tuple[str, ...]
    securities: Mapping[str, SecurityInfo]
    bars: Mapping[str, Mapping[str, MarketBar]]
    benchmark: Mapping[str, Numeric]
    industry_members: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    industry_mapping_complete: bool = True
    universe_complete: bool = True
    financials: Mapping[str, FinancialSnapshot] = field(default_factory=dict)
    fund_flows: Mapping[str, Mapping[str, Numeric]] = field(default_factory=dict)
    taxonomy_id: str = "SYNTHETIC"
    taxonomy_version: str = "1"
    input_version: str = "SYNTHETIC-1"
    available_at: str | None = None

    def __post_init__(self) -> None:
        if not self.calendar:
            raise ValueError("calendar must not be empty")
        if tuple(sorted(self.calendar)) != tuple(self.calendar):
            raise ValueError("calendar must be sorted ascending")
        if len(set(self.calendar)) != len(self.calendar):
            raise ValueError("calendar must not contain duplicate dates")
        if self.business_date != self.calendar[-1]:
            raise ValueError("business_date must be the last completed market day")
        if self.available_at is not None:
            validate_local_datetime(self.available_at, field="available_at", allow_date=True)


@dataclass(frozen=True)
class IndustryResult:
    industry_id: str
    members: tuple[str, ...]
    e0_members: tuple[str, ...]
    breadth: Decimal | None
    excess: Decimal | None
    score: Decimal | None
    total_rank: int | None
    strong: bool
    status: str
    reasons: tuple[str, ...] = ()


@dataclass
class RowResult:
    security_id: str
    strategy_id: str
    signal_date: str
    config_id: str
    config_version: str
    input_version: str
    eligibility: Eligibility
    signal_state: SignalState
    signal_status: ConditionStatus
    observation_status: ConditionStatus
    confirmation_status: ConditionStatus
    pool_rank: int | None = None
    sample_pool_rank: int | None = None
    candidate_rank: int | None = None
    sample_candidate_rank: int | None = None
    industry_id: str | None = None
    industry_pool_rank: int | None = None
    industry_trigger_rank: int | None = None
    industry_total_rank: int | None = None
    formal_candidate: bool = False
    execution_replacement_order: int | None = None
    entry_conflict_exit: ConditionStatus = ConditionStatus.FALSE
    sort_key: tuple[str, ...] = ()
    metrics: dict[str, Decimal | None] = field(default_factory=dict)
    conditions: dict[str, ConditionStatus] = field(default_factory=dict)
    reasons: tuple[str, ...] = ()
    available_at: str | None = None


@dataclass
class StrategyResult:
    strategy_id: str
    signal_date: str
    config_id: str
    config_version: str
    input_version: str
    pool_complete: bool
    pool_size: int
    candidate_size: int
    rows: dict[str, RowResult]
    industries: dict[str, IndustryResult] = field(default_factory=dict)
    notes: tuple[str, ...] = ()
    bound_s01_config_version: str | None = None


@dataclass(frozen=True)
class ExitContext:
    holding_days: int
    entry_platform_upper: Decimal | None = None
    industry_rank_history: tuple[int | None, ...] = ()
    common_stop_triggered: bool = False
    common_stop_unknown: bool = False
    has_position: bool = True


@dataclass(frozen=True)
class ExitDecision:
    status: ConditionStatus
    reasons: tuple[str, ...] = ()
    primary_reason: str | None = None
    requires_retry: bool = False


@dataclass(frozen=True)
class DimensionResult:
    name: str
    raw_value: Decimal | None
    unit: str | None
    score: Decimal | None
    status: ValueStatus
    pool_id: str
    pool_size: int
    pool_complete: bool
    business_date: str
    window: str
    direction: str
    explanation: str
    reason: str | None = None
    extras: Mapping[str, Decimal | None] = field(default_factory=dict)


@dataclass
class DiagnosticResult:
    business_date: str
    input_version: str
    rows: dict[str, dict[str, DimensionResult]]
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class StyleView:
    style_id: str
    strategy_order: tuple[str, ...]
    diagnostic_priority: tuple[str, ...]
    note: str
