"""Synthetic fixtures for the OD-2 cash-model tests.

Every fee, trading rule and corporate action here is SYNTHETIC.  No value is a
verified historical exchange rule or statutory tax rate.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable, Mapping, Sequence

from mishi_radar.cash_backtest.model import (
    BacktestConfig,
    BacktestInput,
    DailyBar,
    EligibilitySnapshot,
    ExitRequest,
    FeeSchedule,
    MarketDay,
    Signal,
    SignalBatch,
    TradingRule,
)

ZERO = Decimal("0")


def trading_dates(count: int, end: date = date(2026, 10, 16)) -> tuple[str, ...]:
    values: list[str] = []
    cursor = end
    while len(values) < count:
        if cursor.weekday() < 5:
            values.append(cursor.isoformat())
        cursor -= timedelta(days=1)
    return tuple(reversed(values))


def dec(value: Decimal | int | str | float | None) -> Decimal | None:
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


def bar(
    day: str,
    open_: Decimal | int | str | None,
    close: Decimal | int | str | None,
    *,
    high: Decimal | int | str | None = None,
    low: Decimal | int | str | None = None,
    volume: Decimal | int | str | None = 1_000_000,
    amount: Decimal | int | str | None = 50_000_000,
    suspended: bool | None = False,
    limit_up: Decimal | int | str | None = None,
    limit_down: Decimal | int | str | None = None,
    no_price_limit: bool = True,
    data_status: str = "OK",
) -> DailyBar:
    return DailyBar(
        date=day,
        open=open_,
        high=high if high is not None else close,
        low=low if low is not None else close,
        close=close,
        volume=volume,
        amount=amount,
        suspended=suspended,
        limit_up=limit_up,
        limit_down=limit_down,
        no_price_limit=no_price_limit,
        data_status=data_status,
    )


def market_day(
    day: str,
    bars: Mapping[str, DailyBar],
    *,
    benchmark_open: Decimal | int | str = 100,
    benchmark_close: Decimal | int | str = 100,
    corporate_actions: Sequence = (),
    corporate_actions_complete: bool = True,
) -> MarketDay:
    return MarketDay(
        date=day,
        bars=dict(bars),
        benchmark_open=dec(benchmark_open),
        benchmark_close=dec(benchmark_close),
        corporate_actions=tuple(corporate_actions),
        corporate_actions_complete=corporate_actions_complete,
    )


def signal(
    security_id: str,
    signal_date: str,
    *,
    strategy_id: str = "S01",
    candidate_rank: int | None = 1,
    pool_rank: int | None = 1,
    signal_status: str = "TRUE",
    qualification_status: str = "SCORABLE",
    formal_candidate: bool = True,
    industry_id: str | None = None,
    industry_pool_rank: int | None = None,
    industry_trigger_rank: int | None = None,
    execution_replacement_order: int | None = None,
    entry_conflict_exit: str = "FALSE",
    entry_platform_upper: Decimal | int | str | None = None,
    available_at: str | None = None,
    pool_complete: bool = True,
    signal_state: str = "CANDIDATE",
) -> Signal:
    return Signal(
        security_id=security_id,
        strategy_id=strategy_id,
        config_version=f"{strategy_id}_DEFAULT/SYNTHETIC",
        signal_date=signal_date,
        input_version="SYNTHETIC-B-1",
        qualification_status=qualification_status,
        signal_status=signal_status,
        signal_state=signal_state,
        pool_rank=pool_rank,
        candidate_rank=candidate_rank,
        industry_id=industry_id,
        industry_pool_rank=industry_pool_rank,
        industry_trigger_rank=industry_trigger_rank,
        formal_candidate=formal_candidate,
        execution_replacement_order=execution_replacement_order,
        entry_conflict_exit=entry_conflict_exit,
        available_at=available_at if available_at is not None else signal_date,
        available_at_kind="SYNTHETIC_DATE_COMPAT",
        pool_complete=pool_complete,
        signal_id=f"{strategy_id}:{security_id}:{signal_date}:SYNTHETIC",
        entry_platform_upper=dec(entry_platform_upper),
    )


def exit_request(
    security_id: str,
    trigger_date: str,
    *,
    reason: str = "TEST_EXIT",
    priority: int = 3,
    strategy_id: str | None = "S01",
) -> ExitRequest:
    return ExitRequest(
        security_id=security_id,
        reason=reason,
        trigger_date=trigger_date,
        priority=priority,
        strategy_id=strategy_id,
    )


def synthetic_rule(
    *,
    lot_size: int = 100,
    sell_delay_days: int = 1,
    no_price_limit: bool = True,
    tick_size: Decimal | int | str = "0.01",
) -> TradingRule:
    return TradingRule(
        effective_from="2000-01-01",
        exchange="SH",
        board="MAIN",
        security_type="STOCK",
        tick_size=dec(tick_size),
        lot_size=lot_size,
        sell_lot_size=1,
        sell_delay_days=sell_delay_days,
        price_limit_pct=None,
        no_price_limit=no_price_limit,
        source="SYNTHETIC",
        version="SYNTHETIC-RULES-1",
        synthetic=True,
    )


def synthetic_fees(
    *,
    commission_rate: Decimal | int | str = "0",
    min_commission: Decimal | int | str = 5,
    slippage_rate: Decimal | int | str = "0",
    buy_tax_rate: Decimal | int | str = "0",
    sell_tax_rate: Decimal | int | str = "0",
    transfer_fee_rate: Decimal | int | str = "0",
    effective_from: str = "2000-01-01",
    effective_to: str | None = None,
    market: str | None = None,
    security_id: str | None = None,
    side: str | None = None,
    known_at: str | None = None,
    version: str = "SYNTHETIC-FEES-1",
) -> FeeSchedule:
    return FeeSchedule(
        effective_from=effective_from,
        effective_to=effective_to,
        commission_rate=dec(commission_rate),
        min_commission=dec(min_commission),
        slippage_rate=dec(slippage_rate),
        buy_tax_rate=dec(buy_tax_rate),
        sell_tax_rate=dec(sell_tax_rate),
        transfer_fee_rate=dec(transfer_fee_rate),
        source="SYNTHETIC",
        version=version,
        synthetic=True,
        market=market,
        security_id=security_id,
        side=side,
        known_at=known_at,
    )


def make_input(
    dates: Sequence[str],
    days: Sequence[MarketDay],
    *,
    signals_by_signal_date: Mapping[str, Sequence[Signal]] | None = None,
    exit_requests_by_signal_date: Mapping[str, Sequence[ExitRequest]] | None = None,
    rules: Sequence[TradingRule] | None = None,
    fees: FeeSchedule | None = None,
    signal_batches: Sequence[SignalBatch] | None = None,
    eligibility_by_date: Mapping[str, EligibilitySnapshot] | None = None,
    fee_schedules: Sequence[FeeSchedule] | None = None,
) -> BacktestInput:
    return BacktestInput(
        calendar=tuple(dates),
        market_days={day.date: day for day in days},
        signals_by_signal_date={key: tuple(value) for key, value in (signals_by_signal_date or {}).items()},
        exit_requests_by_signal_date={
            key: tuple(value) for key, value in (exit_requests_by_signal_date or {}).items()
        },
        trading_rules=tuple(rules) if rules is not None else (synthetic_rule(),),
        fee_schedule=fees or synthetic_fees(),
        benchmark_id="SH:000001:INDEX",
        signal_batches=tuple(signal_batches or ()),
        eligibility_by_date=dict(eligibility_by_date or {}),
        fee_schedules=tuple(fee_schedules or ()),
    )


def config(**kwargs) -> BacktestConfig:
    defaults = {
        "strategy_id": "S01",
        "initial_cash": Decimal("100000"),
        "top_n": 2,
        "rebalance_days": 5,
        "stop_loss": None,
        "require_known_signal_availability": True,
        "synthetic": True,
    }
    defaults.update(kwargs)
    return BacktestConfig(**defaults)
