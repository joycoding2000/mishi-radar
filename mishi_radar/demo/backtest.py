"""Fixed synthetic inputs for the OD-2 cash-engine demonstration.

These builders intentionally import and call the accepted OD-2 public entry
point (``mishi_radar.cash_backtest.run_backtest``).  They do not reimplement
cash, fee, tax, NAV or order semantics.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Mapping, Sequence

from ..cash_backtest import (
    BacktestConfig,
    BacktestInput,
    CorporateAction,
    DailyBar,
    ExitRequest,
    FeeSchedule,
    MarketDay,
    Signal,
    TradingRule,
    run_backtest,
)
from ..cash_backtest.model import DividendTaxBinding
from . import FIXTURE_MARKER, FIXTURE_VERSION
from .fixtures import BACKTEST_SCENARIOS, trading_dates

ZERO = Decimal("0")


def _dec(value: Decimal | int | str | None) -> Decimal | None:
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _bar(
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
    )


def _market_day(
    day: str,
    bars: Mapping[str, DailyBar],
    *,
    benchmark_open: Decimal | int | str = 100,
    benchmark_close: Decimal | int | str = 100,
    corporate_actions: Sequence[CorporateAction] = (),
) -> MarketDay:
    return MarketDay(
        date=day,
        bars=dict(bars),
        benchmark_open=_dec(benchmark_open),
        benchmark_close=_dec(benchmark_close),
        corporate_actions=tuple(corporate_actions),
    )


def _signal(
    security_id: str,
    signal_date: str,
    *,
    candidate_rank: int | None = 1,
    pool_rank: int | None = 1,
    available_at: str | None | object = ...,
) -> Signal:
    if available_at is ...:
        available_at_value = signal_date
        available_at_kind = "SYNTHETIC_DATE_COMPAT"
    elif available_at is None:
        available_at_value = None
        available_at_kind = "UNKNOWN"
    else:
        available_at_value = str(available_at)
        available_at_kind = "LOCAL_DATETIME" if len(str(available_at)) > 10 else "SYNTHETIC_DATE_COMPAT"
    return Signal(
        security_id=security_id,
        strategy_id="S01",
        config_id="S01_DEFAULT",
        config_version="S01_DEFAULT/R3.2-2026-10-19-OD1-v1",
        signal_date=signal_date,
        input_version=f"SYNTHETIC-{FIXTURE_VERSION}-OD2",
        qualification_status="SCORABLE",
        signal_status="TRUE",
        signal_state="CANDIDATE",
        pool_rank=pool_rank,
        candidate_rank=candidate_rank,
        formal_candidate=True,
        available_at=available_at_value,
        available_at_kind=available_at_kind,
        pool_complete=True,
        signal_id=f"S01:{security_id}:{signal_date}:{FIXTURE_VERSION}",
    )


def _exit_request(security_id: str, trigger_date: str) -> ExitRequest:
    return ExitRequest(
        security_id=security_id,
        reason="FIXTURE_EXIT",
        trigger_date=trigger_date,
        priority=3,
        strategy_id="S01",
    )


def _fees(
    *,
    effective_from: str,
    effective_to: str | None = None,
    buy_tax_rate: Decimal | str = 0,
    sell_tax_rate: Decimal | str = 0,
    known_at: str | None = None,
    version: str,
) -> FeeSchedule:
    return FeeSchedule(
        effective_from=effective_from,
        effective_to=effective_to,
        commission_rate=Decimal("0"),
        min_commission=Decimal("5"),
        slippage_rate=Decimal("0"),
        buy_tax_rate=Decimal(str(buy_tax_rate)),
        sell_tax_rate=Decimal(str(sell_tax_rate)),
        transfer_fee_rate=Decimal("0"),
        source="SYNTHETIC",
        version=version,
        synthetic=True,
        known_at=known_at,
    )


def _rule(*, lot_size: int = 100) -> TradingRule:
    return TradingRule(
        effective_from="2000-01-01",
        exchange="SH",
        board="MAIN",
        security_type="STOCK",
        tick_size=Decimal("0.01"),
        lot_size=lot_size,
        sell_lot_size=1,
        sell_delay_days=1,
        price_limit_pct=None,
        no_price_limit=True,
        source="SYNTHETIC",
        version="SYNTHETIC-FX01-RULES-1",
        synthetic=True,
    )


def _u3_scenario() -> tuple[BacktestInput, BacktestConfig, dict[str, str]]:
    dates = trading_dates(5, end=date(2026, 10, 16))
    sid = "SH:600001"
    prices = [Decimal(10), Decimal(10), Decimal(6), Decimal(5), Decimal(5)]
    dividend = CorporateAction(
        sid,
        "CASH_DIVIDEND",
        dates[3],
        record_date=dates[2],
        pay_date=dates[4],
        cash_per_share=Decimal(1),
        source="SYNTHETIC",
        version="SYNTHETIC-FX01-DIVIDEND-1",
        dividend_tax_bindings=(
            DividendTaxBinding(
                acquisition_from=dates[1],
                acquisition_to=dates[1],
                tax_rate=Decimal(0),
                known_at=f"{dates[1]}T15:00:00",
                rule_version="SYNTHETIC-TAX-D1",
            ),
            DividendTaxBinding(
                acquisition_from=dates[2],
                acquisition_to=dates[2],
                tax_rate=Decimal("0.20"),
                known_at=f"{dates[1]}T15:00:00",
                rule_version="SYNTHETIC-TAX-D2",
            ),
        ),
    )
    days = [
        _market_day(
            day,
            {sid: _bar(day, prices[index], prices[index])},
            corporate_actions=(dividend,) if index == 3 else (),
        )
        for index, day in enumerate(dates)
    ]
    f1 = _fees(
        effective_from=dates[1],
        effective_to=dates[1],
        buy_tax_rate=0,
        known_at=f"{dates[0]}T15:00:00",
        version="F1",
    )
    f2 = _fees(
        effective_from=dates[2],
        effective_to=dates[4],
        buy_tax_rate=Decimal("0.001"),
        known_at=f"{dates[1]}T15:00:00",
        version="F2",
    )
    data = BacktestInput(
        calendar=dates,
        market_days={day.date: day for day in days},
        signals_by_signal_date={
            dates[0]: (_signal(sid, dates[0]),),
            dates[1]: (_signal(sid, dates[1]),),
        },
        exit_requests_by_signal_date={dates[2]: (_exit_request(sid, dates[2]),)},
        trading_rules=(_rule(lot_size=100),),
        fee_schedule=f1,
        fee_schedules=(f1, f2),
        benchmark_id="SH:000001:INDEX",
    )
    config = BacktestConfig(
        strategy_id="S01",
        initial_cash=Decimal(4000),
        top_n=2,
        rebalance_days=1,
        stop_loss=None,
        start_date=dates[1],
        synthetic=True,
    )
    meta = {
        "scenario": "u3",
        "label": BACKTEST_SCENARIOS["u3"]["label"],
        "description": BACKTEST_SCENARIOS["u3"]["description"],
        "calendar": ",".join(dates),
        "fixture_version": FIXTURE_VERSION,
        "source": "SYNTHETIC",
    }
    return data, config, meta


def _failure_scenario() -> tuple[BacktestInput, BacktestConfig, dict[str, str]]:
    dates = trading_dates(5, end=date(2026, 10, 16))
    bars = {}
    for index, day in enumerate(dates):
        a_suspended = index == 1
        c_limit = Decimal(9) if index == 2 else None
        bars[day] = _market_day(
            day,
            {
                "SH:600001": _bar(day, 10, 10, suspended=a_suspended),
                "SH:600002": _bar(day, 10, 10),
                "SH:600003": _bar(
                    day,
                    Decimal(9) if index >= 2 else 10,
                    Decimal(9) if index >= 2 else 10,
                    limit_down=c_limit,
                ),
            },
        )
    signals = {
        dates[0]: (
            _signal("SH:600001", dates[0], candidate_rank=1, pool_rank=1),
            _signal("SH:600002", dates[0], candidate_rank=2, pool_rank=2),
            _signal("SH:600003", dates[0], candidate_rank=3, pool_rank=3),
        )
    }
    exits = {dates[1]: (_exit_request("SH:600003", dates[1]),)}
    data = BacktestInput(
        calendar=dates,
        market_days={day.date: day for day in bars.values()},
        signals_by_signal_date=signals,
        exit_requests_by_signal_date=exits,
        trading_rules=(_rule(lot_size=100),),
        fee_schedule=_fees(effective_from="2000-01-01", version="SYNTHETIC-FEES-FAIL"),
        benchmark_id="SH:000001:INDEX",
    )
    config = BacktestConfig(
        strategy_id="S01",
        initial_cash=Decimal("100000"),
        top_n=2,
        rebalance_days=5,
        stop_loss=None,
        start_date=dates[1],
        synthetic=True,
    )
    meta = {
        "scenario": "failures",
        "label": BACKTEST_SCENARIOS["failures"]["label"],
        "description": BACKTEST_SCENARIOS["failures"]["description"],
        "calendar": ",".join(dates),
        "fixture_version": FIXTURE_VERSION,
        "source": "SYNTHETIC",
    }
    return data, config, meta


def _empty_scenario() -> tuple[BacktestInput, BacktestConfig, dict[str, str]]:
    dates = trading_dates(10, end=date(2026, 10, 16))
    days = [_market_day(day, {"SH:600001": _bar(day, 10, 10)}) for day in dates]
    data = BacktestInput(
        calendar=dates,
        market_days={day.date: day for day in days},
        trading_rules=(_rule(),),
        fee_schedule=_fees(effective_from="2000-01-01", version="SYNTHETIC-FEES-EMPTY"),
        benchmark_id="SH:000001:INDEX",
    )
    config = BacktestConfig(
        strategy_id="S01",
        initial_cash=Decimal("100000"),
        top_n=2,
        rebalance_days=5,
        stop_loss=None,
        start_date=dates[0],
        synthetic=True,
    )
    meta = {
        "scenario": "empty",
        "label": BACKTEST_SCENARIOS["empty"]["label"],
        "description": BACKTEST_SCENARIOS["empty"]["description"],
        "calendar": ",".join(dates),
        "fixture_version": FIXTURE_VERSION,
        "source": "SYNTHETIC",
    }
    return data, config, meta


def _blocked_scenario() -> tuple[BacktestInput, BacktestConfig, dict[str, str]]:
    dates = trading_dates(3, end=date(2026, 10, 16))
    days = [_market_day(day, {"SH:600001": _bar(day, 10, 10)}) for day in dates]
    signals = {
        dates[0]: (_signal("SH:600001", dates[0], available_at=None),),
    }
    data = BacktestInput(
        calendar=dates,
        market_days={day.date: day for day in days},
        signals_by_signal_date=signals,
        trading_rules=(_rule(),),
        fee_schedule=_fees(effective_from="2000-01-01", version="SYNTHETIC-FEES-BLOCKED"),
        benchmark_id="SH:000001:INDEX",
    )
    config = BacktestConfig(
        strategy_id="S01",
        initial_cash=Decimal("100000"),
        top_n=2,
        rebalance_days=5,
        stop_loss=None,
        start_date=dates[1],
        synthetic=True,
    )
    meta = {
        "scenario": "blocked",
        "label": BACKTEST_SCENARIOS["blocked"]["label"],
        "description": BACKTEST_SCENARIOS["blocked"]["description"],
        "calendar": ",".join(dates),
        "fixture_version": FIXTURE_VERSION,
        "source": "SYNTHETIC",
    }
    return data, config, meta


_BUILDERS = {
    "u3": _u3_scenario,
    "failures": _failure_scenario,
    "empty": _empty_scenario,
    "blocked": _blocked_scenario,
}


def run_fixture_backtest(scenario: str):
    if scenario not in _BUILDERS:
        raise KeyError(f"unknown backtest scenario {scenario!r}")
    data, config, meta = _BUILDERS[scenario]()
    result = run_backtest(data, config)
    meta = dict(meta)
    meta["marker"] = FIXTURE_MARKER
    meta["engine"] = "mishi_radar.cash_backtest.run_backtest"
    meta["config"] = {
        "strategy_id": config.strategy_id,
        "initial_cash": str(config.initial_cash),
        "top_n": config.top_n,
        "rebalance_days": config.rebalance_days,
        "stop_loss": None if config.stop_loss is None else str(config.stop_loss),
        "start_date": config.start_date,
        "end_date": config.end_date,
    }
    return result, meta
