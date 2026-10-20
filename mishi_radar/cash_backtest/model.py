"""Typed inputs and outputs for the OD-2 daily cash backtest kernel.

The model is deliberately explicit about synthetic execution facts.  Real
trading rules, statutory fees and corporate-action facts must be supplied by a
versioned rule table; the kernel does not infer them from exchange names.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Mapping, Sequence


def dec(value: Decimal | int | str | float | None) -> Decimal | None:
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


@dataclass(frozen=True)
class DailyBar:
    date: str
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    volume: Decimal | None = None
    amount: Decimal | None = None
    suspended: bool | None = False
    limit_up: Decimal | None = None
    limit_down: Decimal | None = None
    no_price_limit: bool = False
    data_status: str = "OK"  # OK, UNKNOWN, CONFLICT, STALE

    def __post_init__(self) -> None:
        for name in ("open", "high", "low", "close", "volume", "amount", "limit_up", "limit_down"):
            object.__setattr__(self, name, dec(getattr(self, name)))


@dataclass(frozen=True)
class CorporateAction:
    security_id: str
    action_type: str
    effective_date: str
    status: str = "IMPLEMENTED"  # IMPLEMENTED, ANNOUNCED, CANCELLED, UNKNOWN, CONFLICT
    record_date: str | None = None
    pay_date: str | None = None
    cash_per_share: Decimal | None = None
    share_multiplier: Decimal | None = None
    new_share_sellable_date: str | None = None
    dividend_tax_rate: Decimal | None = None
    cash_in_lieu: Decimal | None = None
    source: str = "SYNTHETIC"
    version: str = "SYNTHETIC-CA-1"
    note: str | None = None

    def __post_init__(self) -> None:
        for name in ("cash_per_share", "share_multiplier", "dividend_tax_rate", "cash_in_lieu"):
            object.__setattr__(self, name, dec(getattr(self, name)))


@dataclass(frozen=True)
class MarketDay:
    date: str
    bars: Mapping[str, DailyBar]
    benchmark_open: Decimal | None = None
    benchmark_close: Decimal | None = None
    corporate_actions: tuple[CorporateAction, ...] = ()
    corporate_actions_complete: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "benchmark_open", dec(self.benchmark_open))
        object.__setattr__(self, "benchmark_close", dec(self.benchmark_close))


@dataclass(frozen=True)
class TradingRule:
    effective_from: str
    exchange: str
    board: str
    security_type: str = "STOCK"
    effective_to: str | None = None
    tick_size: Decimal = Decimal("0.01")
    lot_size: int = 100
    sell_lot_size: int = 1
    sell_delay_days: int = 1
    price_limit_pct: Decimal | None = Decimal("0.10")
    no_price_limit: bool = False
    source: str = "SYNTHETIC"
    version: str = "SYNTHETIC-RULES-1"
    synthetic: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "tick_size", dec(self.tick_size))
        object.__setattr__(self, "price_limit_pct", dec(self.price_limit_pct))

    def applies(self, date: str, exchange: str, board: str, security_type: str) -> bool:
        return (
            self.effective_from <= date
            and (self.effective_to is None or date <= self.effective_to)
            and self.exchange == exchange
            and self.board == board
            and self.security_type == security_type
        )


@dataclass(frozen=True)
class FeeSchedule:
    effective_from: str
    effective_to: str | None = None
    commission_rate: Decimal = Decimal("0.0003")
    min_commission: Decimal = Decimal("5")
    slippage_rate: Decimal = Decimal("0.0005")
    buy_tax_rate: Decimal = Decimal("0")
    sell_tax_rate: Decimal = Decimal("0")
    transfer_fee_rate: Decimal = Decimal("0")
    source: str = "SYNTHETIC"
    version: str = "SYNTHETIC-FEES-1"
    synthetic: bool = True

    def __post_init__(self) -> None:
        for name in (
            "commission_rate",
            "min_commission",
            "slippage_rate",
            "buy_tax_rate",
            "sell_tax_rate",
            "transfer_fee_rate",
        ):
            object.__setattr__(self, name, dec(getattr(self, name)))

    def applies(self, date: str) -> bool:
        return self.effective_from <= date and (self.effective_to is None or date <= self.effective_to)


@dataclass(frozen=True)
class Signal:
    """Structured signal record produced by the OD-1 kernel.

    ``from_dict`` accepts the JSON-compatible records returned by
    ``mishi_radar.strategy_core.engine.signal_records``.
    """

    security_id: str
    strategy_id: str
    config_version: str
    signal_date: str
    input_version: str
    qualification_status: str
    signal_status: str
    signal_state: str = "CANDIDATE"
    pool_rank: int | None = None
    candidate_rank: int | None = None
    industry_id: str | None = None
    industry_pool_rank: int | None = None
    industry_trigger_rank: int | None = None
    industry_total_rank: int | None = None
    formal_candidate: bool = True
    execution_replacement_order: int | None = None
    entry_conflict_exit: str = "FALSE"
    available_at: str | None = None
    pool_complete: bool = True
    signal_id: str | None = None
    reasons: tuple[str, ...] = ()
    entry_platform_upper: Decimal | None = None
    metrics: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.available_at == "UNKNOWN":
            object.__setattr__(self, "available_at", None)
        object.__setattr__(self, "entry_platform_upper", dec(self.entry_platform_upper))
        if self.entry_platform_upper is None:
            raw = self.metrics.get("u20") if self.metrics else None
            if raw is not None:
                object.__setattr__(self, "entry_platform_upper", dec(raw))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Signal":
        return cls(
            security_id=str(payload["security_id"]),
            strategy_id=str(payload["strategy_id"]),
            config_version=str(payload["config_version"]),
            signal_date=str(payload["signal_date"]),
            input_version=str(payload["input_version"]),
            qualification_status=str(payload["qualification_status"]),
            signal_status=str(payload["signal_status"]),
            signal_state=str(payload.get("signal_state", "CANDIDATE")),
            pool_rank=payload.get("pool_rank"),
            candidate_rank=payload.get("candidate_rank"),
            industry_id=payload.get("industry_id"),
            industry_pool_rank=payload.get("industry_pool_rank"),
            industry_trigger_rank=payload.get("industry_trigger_rank"),
            industry_total_rank=payload.get("industry_total_rank"),
            formal_candidate=bool(payload.get("formal_candidate", True)),
            execution_replacement_order=payload.get("execution_replacement_order"),
            entry_conflict_exit=str(payload.get("entry_conflict_exit", "FALSE")),
            available_at=(
                None if payload.get("available_at") in (None, "UNKNOWN") else str(payload.get("available_at"))
            ),
            pool_complete=bool(payload.get("pool_complete", True)),
            signal_id=payload.get("signal_id"),
            reasons=tuple(payload.get("reasons", ())),
            entry_platform_upper=dec(payload.get("entry_platform_upper")),
            metrics=dict(payload.get("metrics", {})),
        )


@dataclass(frozen=True)
class ExitRequest:
    security_id: str
    reason: str
    trigger_date: str
    priority: int = 3
    strategy_id: str | None = None


@dataclass(frozen=True)
class BacktestConfig:
    strategy_id: str = "S01"
    initial_cash: Decimal = Decimal("100000")
    top_n: int = 10
    rebalance_days: int = 5
    s06_industry_cap: int = 2
    stop_loss: Decimal | None = Decimal("0.08")
    require_known_signal_availability: bool = True
    synthetic: bool = True
    start_date: str | None = None
    end_date: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "initial_cash", dec(self.initial_cash))
        object.__setattr__(self, "stop_loss", dec(self.stop_loss))
        if self.initial_cash is None or self.initial_cash <= 0:
            raise ValueError("initial_cash must be positive")
        if self.top_n <= 0:
            raise ValueError("top_n must be positive")
        if self.rebalance_days <= 0:
            raise ValueError("rebalance_days must be positive")
        if self.s06_industry_cap <= 0:
            raise ValueError("s06_industry_cap must be positive")


@dataclass(frozen=True)
class BacktestInput:
    calendar: tuple[str, ...]
    market_days: Mapping[str, MarketDay]
    signals_by_signal_date: Mapping[str, Sequence[Signal]] = field(default_factory=dict)
    exit_requests_by_signal_date: Mapping[str, Sequence[ExitRequest]] = field(default_factory=dict)
    trading_rules: tuple[TradingRule, ...] = ()
    fee_schedule: FeeSchedule | None = None
    benchmark_id: str = "SH:000001:INDEX"
    board_by_security: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.calendar:
            raise ValueError("calendar must not be empty")
        if tuple(sorted(self.calendar)) != tuple(self.calendar):
            raise ValueError("calendar must be sorted ascending")
        if len(set(self.calendar)) != len(self.calendar):
            raise ValueError("calendar must not contain duplicate dates")
        if self.fee_schedule is None:
            raise ValueError("fee_schedule is required")


@dataclass
class Lot:
    quantity: int
    acquired_date: str
    sellable_date: str


@dataclass
class Position:
    security_id: str
    strategy_id: str
    quantity: int
    cost_open: Decimal
    dividend_open: Decimal
    dividend_units: int
    lots: list[Lot]
    holding_start: str
    holding_days: int
    last_mark: Decimal | None = None
    entry_platform_upper: Decimal | None = None
    industry_id: str | None = None
    realized_trading_pnl: Decimal = Decimal("0")
    realized_dividend: Decimal = Decimal("0")

    def sellable_quantity(self, date: str) -> int:
        return sum(lot.quantity for lot in self.lots if lot.sellable_date <= date)

    def unrealized_pnl(self, mark: Decimal) -> Decimal:
        return Decimal(self.quantity) * mark + self.dividend_open - self.cost_open

    def r_open(self, mark: Decimal) -> Decimal | None:
        if self.cost_open <= 0:
            return None
        return self.unrealized_pnl(mark) / self.cost_open


@dataclass(frozen=True)
class Order:
    order_id: str
    security_id: str
    side: str
    attempt_date: str
    signal_date: str | None
    status: str
    requested_quantity: int
    filled_quantity: int = 0
    price: Decimal | None = None
    gross: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")
    other_fees: Decimal = Decimal("0")
    reason: str | None = None
    strategy_id: str | None = None
    replacement_for: str | None = None
    replacement_reason: str | None = None
    original_candidate_rank: int | None = None
    formal_candidate: bool | None = None
    industry_trigger_rank: int | None = None
    pool_rank: int | None = None
    signal_id: str | None = None


@dataclass(frozen=True)
class Fill:
    order_id: str
    security_id: str
    side: str
    date: str
    quantity: int
    price: Decimal
    gross: Decimal
    commission: Decimal
    other_fees: Decimal


@dataclass(frozen=True)
class NavPoint:
    date: str
    cash: Decimal
    receivables: Decimal
    payables: Decimal
    market_value: Decimal
    equity: Decimal
    nav: Decimal
    benchmark: Decimal | None
    daily_return: Decimal | None
    drawdown: Decimal | None
    position_count: int
    open_equity: Decimal
    target_weight: Decimal
    turnover: Decimal | None = None
    position_ratio: Decimal | None = None


@dataclass(frozen=True)
class PositionSnapshot:
    date: str
    security_id: str
    strategy_id: str
    quantity: int
    sellable_quantity: int
    cost_open: Decimal
    dividend_open: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal
    r_open: Decimal | None
    holding_days: int
    industry_id: str | None
    mark_status: str = "RAW_CLOSE"


@dataclass(frozen=True)
class ClosedCycle:
    security_id: str
    strategy_id: str
    opened_on: str
    closed_on: str
    realized_trading_pnl: Decimal
    realized_dividend: Decimal
    total_pnl: Decimal


@dataclass
class BacktestResult:
    status: str
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    initial_cash: Decimal
    nav_points: list[NavPoint]
    orders: list[Order]
    fills: list[Fill]
    closed_cycles: list[ClosedCycle]
    position_history: list[PositionSnapshot]
    final_positions: list[PositionSnapshot]
    metrics: dict[str, Decimal | float | None]
    monthly_returns: dict[str, Decimal]
    yearly_returns: dict[str, Decimal]
    reconciliation: list[dict[str, Any]]
    synthetic: bool

    @property
    def succeeded(self) -> bool:
        return self.status == "SUCCEEDED"
