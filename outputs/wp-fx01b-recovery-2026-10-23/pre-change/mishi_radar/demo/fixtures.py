"""Versioned fixed fixtures for the WP-FX01 product vertical slice.

The fixture emulates a small, closed market with 12 securities in three
industry groups and 130 synthetic business days.  It is intentionally minimal
and deterministic: no random numbers, no wall-clock input, no network access.

Kernel outputs are never written into this module.  Conditions, signals,
ranks, diagnostics and cash results are always computed at request time by the
accepted OD-1 and OD-2 engines.
"""

from __future__ import annotations

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
from . import FIXTURE_MARKER, FIXTURE_VERSION

BUSINESS_DATE = "2026-10-16"
FIXTURE_COMPUTED_AT = f"{BUSINESS_DATE}T18:00:00"
FIXTURE_PUBLISHED_AT = f"{BUSINESS_DATE}T18:05:00"

SECURITY_NAMES: Mapping[str, str] = {
    "SH:600001": "合成甲 · 非真实证券",
    "SH:600002": "合成乙 · 非真实证券",
    "SZ:000003": "合成丙 · 非真实证券",
    "SH:600004": "合成丁 · 非真实证券",
    "SZ:000005": "合成戊 · 非真实证券",
    "SZ:000006": "合成己 · 非真实证券",
    "SH:600007": "合成庚 · 非真实证券",
    "SH:600008": "合成辛 · 非真实证券",
    "SZ:000009": "合成壬 · 非真实证券",
    "SZ:000010": "合成癸 · 非真实证券",
    "SH:600011": "合成子 · 非真实证券",
    "SH:600012": "合成丑 · 非真实证券",
}

INDUSTRY_NAMES: Mapping[str, str] = {
    "IND_ALPHA": "合成行业·阿尔法",
    "IND_BETA": "合成行业·贝塔",
    "IND_GAMMA": "合成行业·伽马",
}

INDUSTRY_BY_ID: Mapping[str, str] = {
    "SH:600001": "IND_ALPHA",
    "SH:600002": "IND_ALPHA",
    "SZ:000003": "IND_ALPHA",
    "SH:600004": "IND_ALPHA",
    "SZ:000005": "IND_BETA",
    "SZ:000006": "IND_BETA",
    "SH:600007": "IND_BETA",
    "SH:600008": "IND_BETA",
    "SZ:000009": "IND_GAMMA",
    "SZ:000010": "IND_GAMMA",
    "SH:600011": "IND_GAMMA",
    "SH:600012": "IND_GAMMA",
}

ROE_BY_ID: Mapping[str, Decimal] = {
    "SH:600001": Decimal("0.15"),
    "SH:600002": Decimal("0.20"),
    "SZ:000003": Decimal("0.12"),
    "SH:600004": Decimal("0.18"),
    "SZ:000005": Decimal("0.09"),
    "SZ:000006": Decimal("0.11"),
    "SH:600007": Decimal("0.16"),
    "SH:600008": Decimal("0.08"),
    "SZ:000009": Decimal("0.25"),
    "SZ:000010": Decimal("0.14"),
    "SH:600011": Decimal("0.22"),
    "SH:600012": Decimal("0.19"),
}

PE_BY_ID: Mapping[str, str] = {
    "SH:600001": "8",
    "SH:600002": "12",
    "SZ:000003": "15",
    "SH:600004": "25",
    "SZ:000005": "9",
    "SZ:000006": "11",
    "SH:600007": "14",
    "SH:600008": "18",
    "SZ:000009": "30",
    "SZ:000010": "22",
    "SH:600011": "10",
    "SH:600012": "13",
}

SCENARIOS: Mapping[str, Mapping[str, str]] = {
    "normal": {
        "label": "正常候选",
        "description": "完整固定输入，八策略实际计算；含多策略命中、S06 行业限额与稳定名次。",
    },
    "empty": {
        "label": "正常空结果",
        "description": "完整固定输入，但八策略均无候选；空榜是成功结果，不是数据失败。",
    },
    "unknown": {
        "label": "输入缺失 / UNKNOWN",
        "description": "合成丑缺少最近交易日与财务输入；池不完整时只显示 PREVIEW/UNKNOWN，不产生正式名次。",
    },
}

BACKTEST_SCENARIOS: Mapping[str, Mapping[str, str]] = {
    "u3": {
        "label": "U3 已验收合成现金场景",
        "description": "复用 OD-2 已验收的合成算例：补买、逐批股息税、卖出与 NAV 对账。",
    },
    "failures": {
        "label": "执行受阻与重试",
        "description": "合成买入停牌、持仓跌停卖不出并在后续开盘重试；失败原因来自内核订单记录。",
    },
    "empty": {
        "label": "无信号现金曲线",
        "description": "完整输入但没有信号；成功保持现金，NAV=1，交易指标为 N/A。",
    },
    "blocked": {
        "label": "输入 UNKNOWN 阻断",
        "description": "信号可用时刻未知；内核保留已知前缀并 BLOCKED，不伪装成成功回测。",
    },
}


def trading_dates(count: int, end: date = date(2026, 10, 16)) -> tuple[str, ...]:
    values: list[str] = []
    cursor = end
    while len(values) < count:
        if cursor.weekday() < 5:
            values.append(cursor.isoformat())
        cursor -= timedelta(days=1)
    return tuple(reversed(values))


def _dec(value: Decimal | int | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _bar(
    day: str,
    *,
    close: Decimal | None,
    open_: Decimal | None = None,
    high: Decimal | None = None,
    low: Decimal | None = None,
    volume: Decimal | None,
    amount: Decimal | None,
) -> MarketBar:
    if close is None:
        missing = Numeric(None, ValueStatus.MISSING, "FIXTURE_INPUT_MISSING")
        return MarketBar(
            date=day,
            open=Numeric(None, ValueStatus.MISSING, "FIXTURE_INPUT_MISSING"),
            high=missing,
            low=missing,
            close=missing,
            volume=Numeric(None, ValueStatus.MISSING, "FIXTURE_INPUT_MISSING"),
            amount=Numeric(None, ValueStatus.MISSING, "FIXTURE_INPUT_MISSING"),
        )
    open_value = open_ if open_ is not None else close
    high_value = high if high is not None else close * Decimal("1.004")
    low_value = low if low is not None else close * Decimal("0.996")
    return MarketBar(
        date=day,
        open=num(open_value, source="FIXTURE", input_version=FIXTURE_VERSION),
        high=num(high_value, source="FIXTURE", input_version=FIXTURE_VERSION),
        low=num(low_value, source="FIXTURE", input_version=FIXTURE_VERSION),
        close=num(close, source="FIXTURE", input_version=FIXTURE_VERSION),
        volume=num(volume, unit="share", source="FIXTURE", input_version=FIXTURE_VERSION),
        amount=num(amount, unit="CNY", source="FIXTURE", input_version=FIXTURE_VERSION),
    )


def _trend_series(
    dates: Sequence[str],
    start: Decimal,
    rate: Decimal,
    *,
    volume: Decimal = Decimal("5000000"),
) -> list[MarketBar]:
    bars: list[MarketBar] = []
    close = start
    for day in dates:
        amount = (close * volume).quantize(Decimal("0.01"))
        bars.append(_bar(day, close=close, volume=volume, amount=amount))
        close = close * (Decimal(1) + rate)
    return bars


def _decline_series(
    dates: Sequence[str],
    start: Decimal = Decimal("10"),
    rate: Decimal = Decimal("-0.001"),
    *,
    volume: Decimal = Decimal("5000000"),
) -> list[MarketBar]:
    return _trend_series(dates, start, rate, volume=volume)


def _platform_breakout_series(dates: Sequence[str]) -> list[MarketBar]:
    bars: list[MarketBar] = []
    last = len(dates) - 1
    for index, day in enumerate(dates):
        if index < last - 20:
            close = Decimal("9.5")
            volume = Decimal("4200000")
            high = Decimal("9.6")
            low = Decimal("9.4")
        elif index < last:
            close = Decimal("9.5")
            high = Decimal("9.6")
            low = Decimal("9.4")
            volume = Decimal("4200000") if index < last - 5 else Decimal("2500000")
        else:
            close = Decimal("10.1")
            high = Decimal("10.4")
            low = Decimal("9.6")
            volume = Decimal("6000000")
        bars.append(
            _bar(
                day,
                close=close,
                open_=Decimal("9.7") if index == last else close,
                high=high,
                low=low,
                volume=volume,
                amount=(close * volume).quantize(Decimal("0.01")),
            )
        )
    return bars


def _rebound_series(dates: Sequence[str]) -> list[MarketBar]:
    tail = [Decimal("9.8"), Decimal("9.5"), Decimal("9.3"), Decimal("9.1"), Decimal("8.9"), Decimal("8.8"), Decimal("9.8")]
    closes = [Decimal("10.5")] * (len(dates) - len(tail)) + tail
    bars: list[MarketBar] = []
    volume = Decimal("4000000")
    for day, close in zip(dates, closes):
        bars.append(
            _bar(
                day,
                close=close,
                volume=volume,
                amount=(close * volume).quantize(Decimal("0.01")),
            )
        )
    return bars


def _pullback_series(dates: Sequence[str]) -> list[MarketBar]:
    head = _trend_series(dates[: len(dates) - 20], Decimal("15"), Decimal("0.0025"), volume=Decimal("5000000"))
    tail_closes = [
        "20.0",
        "20.2",
        "20.5",
        "21.0",
        "20.6",
        "20.0",
        "19.8",
        "19.6",
        "19.4",
        "19.2",
        "19.3",
        "19.4",
        "19.5",
        "19.4",
        "19.35",
        "19.3",
        "19.25",
        "19.3",
        "19.45",
        "19.9",
    ]
    volume = Decimal("5000000")
    tail: list[MarketBar] = []
    for day, text in zip(dates[-20:], tail_closes):
        close = Decimal(text)
        tail.append(
            _bar(
                day,
                close=close,
                volume=volume,
                amount=(close * volume).quantize(Decimal("0.01")),
            )
        )
    return head + tail


def _flat_down_series(dates: Sequence[str]) -> list[MarketBar]:
    return _decline_series(dates, Decimal("10.5"), Decimal("-0.0005"))


_SERIES_BUILDERS = {
    "trend": _trend_series,
    "decline": _decline_series,
    "platform": _platform_breakout_series,
    "rebound": _rebound_series,
    "pullback": _pullback_series,
    "flat_down": _flat_down_series,
}

_PROFILE_BY_ID: Mapping[str, tuple[str, Decimal | None, Decimal | None]] = {
    "SH:600001": ("trend", Decimal("8"), Decimal("0.004")),
    "SH:600002": ("trend", Decimal("12"), Decimal("0.0035")),
    "SZ:000003": ("trend", Decimal("20"), Decimal("0.003")),
    "SH:600004": ("platform", None, None),
    "SZ:000005": ("rebound", None, None),
    "SZ:000006": ("trend", Decimal("10"), Decimal("0.001")),
    "SH:600007": ("pullback", None, None),
    "SH:600008": ("flat_down", None, None),
    "SZ:000009": ("decline", Decimal("10"), Decimal("-0.001")),
    "SZ:000010": ("decline", Decimal("10"), Decimal("-0.002")),
    "SH:600011": ("trend", Decimal("30"), Decimal("0.003")),
    "SH:600012": ("trend", Decimal("6"), Decimal("0.0045")),
}


def _financial(security_id: str, business_date: str, *, roe: Decimal) -> FinancialSnapshot:
    equity = Decimal("1000")
    np_ttm = (roe * equity).quantize(Decimal("0.01"))
    ocf_ttm = (np_ttm * Decimal("1.2")).quantize(Decimal("0.01"))
    return FinancialSnapshot.from_ttm(
        np_ttm=np_ttm,
        ocf_ttm=ocf_ttm,
        equity_average=equity,
        pe_ttm=PE_BY_ID[security_id],
        report_period="2025-12-31",
        pe_business_date=business_date,
        available_at=business_date,
        is_financial=False,
        industry_id=INDUSTRY_BY_ID[security_id],
        input_version="SYNTHETIC-FX01-FIN-v1",
    )


def _fund_flows(
    dates: Sequence[str],
    *,
    empty: bool,
    drop_security: str | None = None,
) -> dict[str, dict[str, Numeric]]:
    last_five = dates[-5:]
    flows: dict[str, dict[str, Numeric]] = {}
    for security_id in SECURITY_NAMES:
        if security_id == drop_security:
            continue
        values: dict[str, Numeric] = {}
        for day in dates:
            values[day] = num(0, source="FIXTURE", unit="CNY", input_version=FIXTURE_VERSION)
        if empty:
            tail = ("-1000000", "-1000000", "-1000000", "-1000000", "-1000000")
        else:
            tail = ("2000000", "3000000", "1000000", "-500000", "-500000")
        for day, value in zip(last_five, tail):
            values[day] = num(value, source="FIXTURE", unit="CNY", input_version=FIXTURE_VERSION)
        flows[security_id] = values
    return flows


def _empty_scenario_bars(dates: Sequence[str]) -> dict[str, dict[str, MarketBar]]:
    bars: dict[str, dict[str, MarketBar]] = {}
    for security_id in SECURITY_NAMES:
        series = _decline_series(dates, Decimal("10"), Decimal("-0.001"))
        bars[security_id] = {item.date: item for item in series}
    return bars


def build_snapshot(scenario: str) -> MarketSnapshot:
    if scenario not in SCENARIOS:
        raise KeyError(f"unknown fixture scenario {scenario!r}")
    dates = trading_dates(130)
    business_date = dates[-1]
    bars: dict[str, dict[str, MarketBar]] = {}
    for security_id, (builder_name, start, rate) in _PROFILE_BY_ID.items():
        if scenario != "normal" and scenario != "unknown":
            continue
        builder = _SERIES_BUILDERS[builder_name]
        if builder_name == "trend":
            assert start is not None and rate is not None
            series = builder(dates, start, rate)
        elif builder_name == "decline":
            assert start is not None and rate is not None
            series = builder(dates, start, rate)
        else:
            series = builder(dates)
        bars[security_id] = {item.date: item for item in series}
    if scenario == "empty":
        bars = _empty_scenario_bars(dates)
    if scenario == "unknown":
        unknown_id = "SH:600012"
        for day in dates[-3:]:
            existing = bars[unknown_id][day]
            bars[unknown_id][day] = _bar(
                day,
                close=None,
                volume=None,
                amount=None,
            )

    securities: dict[str, SecurityInfo] = {}
    for security_id in sorted(SECURITY_NAMES):
        exchange, _ticker = security_id.split(":", 1)
        securities[security_id] = SecurityInfo(
            security_id=security_id,
            exchange=exchange,
            board="MAIN",
            instrument_type="STOCK",
            listed_on="2020-01-02",
            listed_trading_days=300,
            is_st=False,
            is_delisting=False,
            suspended=False,
            industry_id=INDUSTRY_BY_ID[security_id],
            industry_known=True,
        )

    benchmark_closes = [Decimal("100")]
    for _ in range(len(dates) - 1):
        benchmark_closes.append(benchmark_closes[-1] * Decimal("1.0002"))
    benchmark = {day: num(value.quantize(Decimal("0.0001"))) for day, value in zip(dates, benchmark_closes)}

    if scenario == "empty":
        financials = {
            security_id: _financial(security_id, business_date, roe=Decimal("0.05"))
            for security_id in SECURITY_NAMES
        }
    elif scenario == "unknown":
        financials = {
            security_id: _financial(security_id, business_date, roe=ROE_BY_ID[security_id])
            for security_id in SECURITY_NAMES
            if security_id != "SH:600012"
        }
    else:
        financials = {
            security_id: _financial(security_id, business_date, roe=ROE_BY_ID[security_id])
            for security_id in SECURITY_NAMES
        }

    industry_members: dict[str, list[str]] = {}
    for security_id, industry_id in INDUSTRY_BY_ID.items():
        industry_members.setdefault(industry_id, []).append(security_id)

    return MarketSnapshot(
        business_date=business_date,
        calendar=dates,
        securities=securities,
        bars=bars,
        benchmark=benchmark,
        industry_members={key: tuple(sorted(value)) for key, value in industry_members.items()},
        industry_mapping_complete=True,
        universe_complete=scenario != "unknown",
        financials=financials,
        fund_flows=_fund_flows(
            dates,
            empty=scenario == "empty",
            drop_security="SH:600012" if scenario == "unknown" else None,
        ),
        taxonomy_id="FX01-SYNTHETIC-INDUSTRY",
        taxonomy_version="v1",
        input_version=f"SYNTHETIC-{FIXTURE_VERSION}:{scenario}",
        available_at=business_date,
    )


def fixture_metadata(scenario: str) -> dict[str, str]:
    meta = SCENARIOS[scenario]
    return {
        "marker": FIXTURE_MARKER,
        "fixture_version": FIXTURE_VERSION,
        "scenario": scenario,
        "scenario_label": meta["label"],
        "scenario_description": meta["description"],
        "business_date": BUSINESS_DATE,
        "computed_at": FIXTURE_COMPUTED_AT,
        "published_at": FIXTURE_PUBLISHED_AT,
        "source": "FIXTURE",
        "price_basis": "SYNTHETIC_RAW_CNY",
        "currency": "CNY",
    }
