"""Synthetic fixtures for the OD-1 kernel tests.

All market, financial and fund-flow values here are explicitly synthetic.
They are not evidence of any real security, market state or strategy return.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable, Mapping, Sequence

from mishi_radar.strategy_core.model import (
    FinancialSnapshot,
    MarketBar,
    MarketSnapshot,
    Numeric,
    SecurityInfo,
    ValueStatus,
    confirmed_zero,
    num,
    raw_zero_unknown,
)

D = "2026-10-16"
BASE_AMOUNT = Decimal("50000000")
BASE_VOLUME = Decimal("1000000")


def trading_dates(count: int, end: date = date(2026, 10, 16)) -> tuple[str, ...]:
    dates: list[str] = []
    cursor = end
    while len(dates) < count:
        if cursor.weekday() < 5:
            dates.append(cursor.isoformat())
        cursor -= timedelta(days=1)
    return tuple(reversed(dates))


def dec(value: Decimal | int | str | float) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def make_bar(
    day: str,
    close: Decimal | int | str | None,
    *,
    high: Decimal | int | str | None = None,
    low: Decimal | int | str | None = None,
    open_: Decimal | int | str | None = None,
    volume: Decimal | int | str = BASE_VOLUME,
    amount: Decimal | int | str | Numeric = BASE_AMOUNT,
    adjustment_factor: Decimal | int | str = 1,
    volume_factor: Decimal | int | str = 1,
    amount_status: ValueStatus = ValueStatus.VALUE,
    volume_status: ValueStatus = ValueStatus.VALUE,
) -> MarketBar:
    if close is None:
        close_n = Numeric(None, ValueStatus.MISSING, "CLOSE_MISSING")
        high_n = Numeric(None, ValueStatus.MISSING, "HIGH_MISSING")
        low_n = Numeric(None, ValueStatus.MISSING, "LOW_MISSING")
        open_n = Numeric(None, ValueStatus.MISSING, "OPEN_MISSING")
    else:
        close_d = dec(close)
        high_d = dec(high) if high is not None else close_d * Decimal("1.005")
        low_d = dec(low) if low is not None else close_d * Decimal("0.995")
        open_d = dec(open_) if open_ is not None else close_d
        close_n = num(close_d)
        high_n = num(high_d)
        low_n = num(low_d)
        open_n = num(open_d)
    if isinstance(amount, Numeric):
        amount_n = amount
    else:
        amount_n = num(amount, status=amount_status)
    volume_n = num(volume, status=volume_status)
    return MarketBar(
        date=day,
        open=open_n,
        high=high_n,
        low=low_n,
        close=close_n,
        volume=volume_n,
        amount=amount_n,
        adjustment_factor=num(adjustment_factor),
        volume_factor=num(volume_factor),
    )


def make_series(
    dates: Sequence[str],
    closes: Sequence[Decimal | int | str | None],
    *,
    volumes: Sequence[Decimal | int | str] | None = None,
    amounts: Sequence[Decimal | int | str | Numeric] | None = None,
    amount_numerics: Mapping[str, Numeric] | None = None,
    adjustment_factors: Sequence[Decimal | int | str] | None = None,
    volume_factors: Sequence[Decimal | int | str] | None = None,
    highs: Sequence[Decimal | int | str | None] | None = None,
    lows: Sequence[Decimal | int | str | None] | None = None,
) -> dict[str, MarketBar]:
    if len(closes) != len(dates):
        raise ValueError("closes and dates must have the same length")
    bars: dict[str, MarketBar] = {}
    for index, day in enumerate(dates):
        amount_item = amounts[index] if amounts is not None else BASE_AMOUNT
        if amount_numerics is not None and day in amount_numerics:
            amount_item = amount_numerics[day]
        bars[day] = make_bar(
            day,
            closes[index],
            high=highs[index] if highs is not None else None,
            low=lows[index] if lows is not None else None,
            volume=volumes[index] if volumes is not None else BASE_VOLUME,
            amount=amount_item,
            adjustment_factor=adjustment_factors[index] if adjustment_factors is not None else 1,
            volume_factor=volume_factors[index] if volume_factors is not None else 1,
        )
    return bars


def default_financial(
    industry_id: str,
    business_date: str,
    *,
    pe: Decimal | int | str = 10,
    np_ttm: Decimal | int | str = 10,
    ocf_ttm: Decimal | int | str = 12,
    equity_average: Decimal | int | str = 100,
    is_financial: bool = False,
    available_at: str | None = None,
    pe_business_date: str | None = None,
) -> FinancialSnapshot:
    return FinancialSnapshot.from_ttm(
        np_ttm=np_ttm,
        ocf_ttm=ocf_ttm,
        equity_average=equity_average,
        pe_ttm=pe,
        report_period="2026-06-30",
        pe_business_date=pe_business_date or business_date,
        available_at=available_at or business_date,
        is_financial=is_financial,
        industry_id=industry_id,
    )


def make_snapshot(
    dates: Sequence[str],
    closes_by_id: Mapping[str, Sequence[Decimal | int | str | None]],
    *,
    benchmark_closes: Sequence[Decimal | int | str] | None = None,
    industry_by_id: Mapping[str, str] | None = None,
    industry_members: Mapping[str, Sequence[str]] | None = None,
    financials: Mapping[str, FinancialSnapshot] | None = None,
    fund_flows: Mapping[str, Mapping[str, Numeric]] | None = None,
    bars_override: Mapping[str, Mapping[str, MarketBar]] | None = None,
    universe_complete: bool = True,
    industry_mapping_complete: bool = True,
    securities_override: Mapping[str, SecurityInfo] | None = None,
) -> MarketSnapshot:
    ids = sorted(closes_by_id)
    business_date = dates[-1]
    industry_by_id = dict(industry_by_id or {sid: "IND_A" for sid in ids})
    if industry_members is None:
        groups: dict[str, list[str]] = {}
        for sid in ids:
            groups.setdefault(industry_by_id.get(sid, "IND_A"), []).append(sid)
        industry_members = {key: tuple(value) for key, value in groups.items()}
    securities: dict[str, SecurityInfo] = {}
    for sid in ids:
        if securities_override is not None and sid in securities_override:
            securities[sid] = securities_override[sid]
            continue
        exchange, _ticker = sid.split(":", 1)
        securities[sid] = SecurityInfo(
            security_id=sid,
            exchange=exchange,
            board="MAIN",
            listed_trading_days=300,
            listed_on="2020-01-02",
            industry_id=industry_by_id.get(sid, "IND_A"),
            industry_known=True,
        )
    bars: dict[str, dict[str, MarketBar]] = {}
    for sid in ids:
        bars[sid] = make_series(dates, closes_by_id[sid])
    if bars_override:
        for sid, overrides in bars_override.items():
            bars.setdefault(sid, {}).update(overrides)
    if benchmark_closes is None:
        benchmark_closes = [Decimal(100)] * len(dates)
    benchmark = {day: num(value) for day, value in zip(dates, benchmark_closes)}
    if financials is None:
        financials = {
            sid: default_financial(industry_by_id.get(sid, "IND_A"), business_date)
            for sid in ids
        }
    if fund_flows is None:
        fund_flows = {}
        for sid in ids:
            values: dict[str, Numeric] = {}
            for day in dates:
                values[day] = num(1)
            for day, value in zip(dates[-5:], (1, 1, 1, -1, -1)):
                values[day] = num(value)
            fund_flows[sid] = values
    return MarketSnapshot(
        business_date=business_date,
        calendar=tuple(dates),
        securities=securities,
        bars=bars,
        benchmark=benchmark,
        industry_members={key: tuple(value) for key, value in industry_members.items()},
        industry_mapping_complete=industry_mapping_complete,
        universe_complete=universe_complete,
        financials=dict(financials),
        fund_flows={sid: dict(values) for sid, values in fund_flows.items()},
        taxonomy_id="SYNTHETIC",
        taxonomy_version="A-1",
        input_version="SYNTHETIC-A-1",
        available_at=business_date,
    )


def trend(count: int, start: Decimal | int | str = 10, rate: Decimal | int | str = "0.002") -> list[Decimal]:
    base = dec(start)
    step = dec(rate)
    return [base * (Decimal(1) + step) ** index for index in range(count)]


def flat(count: int, value: Decimal | int | str = 10) -> list[Decimal]:
    return [dec(value)] * count
