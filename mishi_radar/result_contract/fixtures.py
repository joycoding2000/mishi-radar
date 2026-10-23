"""Versioned synthetic fixture for the WP-FX01A result contract.

The fixture is deliberately small and closed: six synthetic securities in one
synthetic industry over 130 synthetic market days.  It never reads a clock, a
random source or a network.  Kernel output is never stored in this module;
opportunities, diagnostics and status data are always computed by the accepted
OD-1 kernel at request time.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Mapping, Sequence

from ..strategy_core.model import (
    FinancialSnapshot,
    MarketBar,
    MarketSnapshot,
    Numeric,
    SecurityInfo,
    ValueStatus,
    num,
)

FIXTURE_ID = "FX01A-SYNTHETIC-MARKET"
FIXTURE_VERSION = "FX01A-2026-10-23-v1"
FIXTURE_MARKER = "SYNTHETIC / FIXTURE"
BUSINESS_DATE = "2026-10-16"
FIXTURE_COMPUTED_AT = f"{BUSINESS_DATE}T18:00:00"
FIXTURE_DECLARED_PUBLISHED_AT = f"{BUSINESS_DATE}T18:05:00"

SCENARIOS: Mapping[str, Mapping[str, str]] = {
    "normal": {
        "label": "正常固定输入",
        "description": "六只合成证券、完整输入；S01/S06/S07/S08 可同股多命中。",
    },
    "empty": {
        "label": "正常空结果",
        "description": "完整固定输入但无候选；空榜是成功结果，不是数据失败。",
    },
    "unknown": {
        "label": "部分输入 / PREVIEW",
        "description": "一只合成证券最近三日缺失；池不完整，只能产生样本名次。",
    },
    "unavailable": {
        "label": "全部 UNKNOWN",
        "description": "全部合成证券最近三日缺失；无正式或样本名次。",
    },
    "failed": {
        "label": "输入请求失败",
        "description": "全部合成证券的成交额输入为 REQUEST_FAILED；与空结果和 UNKNOWN 分开。",
    },
}

_SECURITY_IDS: tuple[str, ...] = tuple(f"SYN:{index:06d}" for index in range(1, 7))

_PROFILES: Mapping[str, tuple[str, str, str, str, str]] = {
    "SYN:000001": ("trend", "10", "0.006", "0.15", "8"),
    "SYN:000002": ("trend", "12", "0.004", "0.12", "10"),
    "SYN:000003": ("trend", "15", "0.003", "0.08", "12"),
    "SYN:000004": ("trend", "9", "0.002", "0.20", "15"),
    "SYN:000005": ("decline", "10", "-0.002", "0.05", "20"),
    "SYN:000006": ("decline", "11", "-0.003", "0.02", "25"),
}

_FLOW_TAILS: Mapping[str, tuple[str, ...]] = {
    "SYN:000001": ("2000000", "3000000", "1000000", "-500000", "-500000"),
    "SYN:000002": ("1000000", "1000000", "1000000", "-2000000", "-2000000"),
    "SYN:000003": ("1000000", "1000000", "-1000000", "-1000000", "-1000000"),
    "SYN:000004": ("1000000", "1000000", "1000000", "-2000000", "-2000000"),
    "SYN:000005": ("-1000000", "-1000000", "-1000000", "-1000000", "-1000000"),
    "SYN:000006": ("-1000000", "-1000000", "-1000000", "-1000000", "-1000000"),
}

_SOURCE = "FX01A_FIXTURE"
_VOLUME = Decimal("5000000")
_INDUSTRY_ID = "IND_ALPHA"


def trading_dates(count: int, end: date = date(2026, 10, 16)) -> tuple[str, ...]:
    values: list[str] = []
    cursor = end
    while len(values) < count:
        if cursor.weekday() < 5:
            values.append(cursor.isoformat())
        cursor -= timedelta(days=1)
    return tuple(reversed(values))


def _input_version() -> str:
    return f"SYNTHETIC-{FIXTURE_VERSION}"


def _numeric(
    value: Decimal | int | str,
    *,
    unit: str | None = None,
    status: ValueStatus = ValueStatus.VALUE,
) -> Numeric:
    return num(
        value,
        status=status,
        unit=unit,
        source=_SOURCE,
        input_version=_input_version(),
    )


def _missing_numeric(reason: str) -> Numeric:
    return Numeric(
        None,
        ValueStatus.MISSING,
        reason,
        source=_SOURCE,
        input_version=_input_version(),
    )


def _missing_bar(day: str) -> MarketBar:
    return MarketBar(
        date=day,
        open=_missing_numeric("FIXTURE_INPUT_MISSING"),
        high=_missing_numeric("FIXTURE_INPUT_MISSING"),
        low=_missing_numeric("FIXTURE_INPUT_MISSING"),
        close=_missing_numeric("FIXTURE_INPUT_MISSING"),
        volume=_missing_numeric("FIXTURE_INPUT_MISSING"),
        amount=_missing_numeric("FIXTURE_INPUT_MISSING"),
    )


def _bar(day: str, close: Decimal) -> MarketBar:
    volume = _VOLUME
    amount = (close * volume).quantize(Decimal("0.01"))
    return MarketBar(
        date=day,
        open=_numeric(close, unit="CNY"),
        high=_numeric(close * Decimal("1.004"), unit="CNY"),
        low=_numeric(close * Decimal("0.996"), unit="CNY"),
        close=_numeric(close, unit="CNY"),
        volume=_numeric(volume, unit="share"),
        amount=_numeric(amount, unit="CNY"),
    )


def _failed_amount_bar(bar: MarketBar) -> MarketBar:
    failed = Numeric(
        None,
        ValueStatus.REQUEST_FAILED,
        "FIXTURE_REQUEST_FAILED",
        unit="CNY",
        source=_SOURCE,
        input_version=_input_version(),
    )
    return replace(bar, amount=failed)


def _series(dates: Sequence[str], start: str, rate: str) -> dict[str, MarketBar]:
    bars: dict[str, MarketBar] = {}
    close = Decimal(start)
    step = Decimal(rate)
    for day in dates:
        bars[day] = _bar(day, close)
        close = close * (Decimal(1) + step)
    return bars


def _financial(roe: str, pe: str) -> FinancialSnapshot:
    equity = Decimal("1000")
    np_ttm = (Decimal(roe) * equity).quantize(Decimal("0.01"))
    ocf_ttm = (np_ttm * Decimal("1.2")).quantize(Decimal("0.01"))
    return FinancialSnapshot.from_ttm(
        np_ttm=np_ttm,
        ocf_ttm=ocf_ttm,
        equity_average=equity,
        pe_ttm=pe,
        report_period="2025-12-31",
        pe_business_date=BUSINESS_DATE,
        available_at=BUSINESS_DATE,
        is_financial=False,
        industry_id=_INDUSTRY_ID,
        input_version=f"SYNTHETIC-{FIXTURE_VERSION}-FIN",
    )


def _fund_flows(dates: Sequence[str], scenario: str) -> dict[str, dict[str, Numeric]]:
    flows: dict[str, dict[str, Numeric]] = {}
    for security_id in _SECURITY_IDS:
        values: dict[str, Numeric] = {}
        for day in dates:
            values[day] = _numeric(0, unit="CNY", status=ValueStatus.CONFIRMED_ZERO)
        tail = _FLOW_TAILS[security_id]
        if scenario == "empty":
            tail = ("-1000000",) * 5
        for day, value in zip(dates[-5:], tail):
            values[day] = _numeric(value, unit="CNY")
        flows[security_id] = values
    return flows


def _securities() -> dict[str, SecurityInfo]:
    securities: dict[str, SecurityInfo] = {}
    for security_id in _SECURITY_IDS:
        securities[security_id] = SecurityInfo(
            security_id=security_id,
            exchange="SYN",
            board="MAIN",
            instrument_type="STOCK",
            listed_on="2020-01-02",
            listed_trading_days=300,
            is_st=False,
            is_delisting=False,
            suspended=False,
            industry_id=_INDUSTRY_ID,
            industry_known=True,
        )
    return securities


def _benchmark(dates: Sequence[str]) -> dict[str, Numeric]:
    values: dict[str, Numeric] = {}
    level = Decimal("100")
    for day in dates:
        values[day] = _numeric(level.quantize(Decimal("0.0001")))
        level = level * Decimal("1.0002")
    return values


def build_fixture_snapshot(scenario: str) -> MarketSnapshot:
    if scenario not in SCENARIOS:
        raise KeyError(f"unknown fixture scenario {scenario!r}")

    dates = trading_dates(130)
    bars: dict[str, dict[str, MarketBar]] = {}
    for index, security_id in enumerate(_SECURITY_IDS):
        if scenario == "empty":
            bars[security_id] = _series(dates, str(Decimal("10") + index), "-0.002")
            continue
        _kind, start, rate, _roe, _pe = _PROFILES[security_id]
        bars[security_id] = _series(dates, start, rate)

    if scenario == "unknown":
        for day in dates[-3:]:
            bars["SYN:000006"][day] = _missing_bar(day)
    elif scenario == "unavailable":
        for security_id in _SECURITY_IDS:
            for day in dates[-3:]:
                bars[security_id][day] = _missing_bar(day)
    elif scenario == "failed":
        for security_id in _SECURITY_IDS:
            for day in dates[-20:]:
                bars[security_id][day] = _failed_amount_bar(bars[security_id][day])

    financials: dict[str, FinancialSnapshot] = {}
    for security_id in _SECURITY_IDS:
        if scenario == "unknown" and security_id == "SYN:000006":
            continue
        _kind, _start, _rate, roe, pe = _PROFILES[security_id]
        if scenario == "empty":
            roe = "0.05"
        financials[security_id] = _financial(roe, pe)

    return MarketSnapshot(
        business_date=BUSINESS_DATE,
        calendar=dates,
        securities=_securities(),
        bars=bars,
        benchmark=_benchmark(dates),
        industry_members={_INDUSTRY_ID: _SECURITY_IDS},
        industry_mapping_complete=True,
        universe_complete=scenario not in {"unknown", "unavailable"},
        financials=financials,
        fund_flows=_fund_flows(dates, scenario),
        taxonomy_id="FX01A-SYNTHETIC-INDUSTRY",
        taxonomy_version="v1",
        input_version=f"{_input_version()}:{scenario}",
        available_at=None if scenario in {"unavailable", "failed"} else BUSINESS_DATE,
    )


def fixture_metadata(scenario: str) -> dict[str, object]:
    if scenario not in SCENARIOS:
        raise KeyError(f"unknown fixture scenario {scenario!r}")
    meta = SCENARIOS[scenario]
    dates = trading_dates(130)
    return {
        "fixture_id": FIXTURE_ID,
        "fixture_version": FIXTURE_VERSION,
        "scenario": scenario,
        "scenario_label": meta["label"],
        "scenario_description": meta["description"],
        "marker": FIXTURE_MARKER,
        "source": "FIXTURE",
        "business_date": BUSINESS_DATE,
        "calendar": {
            "start": dates[0],
            "end": dates[-1],
            "days": len(dates),
        },
        "computed_at": FIXTURE_COMPUTED_AT,
        "fixture_declared_published_at": FIXTURE_DECLARED_PUBLISHED_AT,
        "price_basis": "SYNTHETIC_RAW_CNY",
        "currency": "CNY",
        "security_ids": list(_SECURITY_IDS),
        "industry_id": _INDUSTRY_ID,
        "input_version": f"{_input_version()}:{scenario}",
    }
