"""Approved S01-S08 calculations and stable ranking."""

from __future__ import annotations

from dataclasses import replace as dataclass_replace
from decimal import Decimal
from typing import Callable, Iterable, Mapping, Sequence

from .config import (
    S01_DEFAULT_CONFIG,
    S01_DEFAULT_CONFIG_VERSION,
    ConfigBundle,
)
from .mathx import (
    ZERO,
    dec,
    key_decimal,
    mean,
    money,
    negative,
    percentile_high,
    percentile_low,
    q12,
    sample_std,
)
from .model import (
    ConditionStatus,
    Eligibility,
    FinancialSnapshot,
    IndustryResult,
    MarketBar,
    MarketSnapshot,
    Numeric,
    RowResult,
    SecurityInfo,
    SignalState,
    StrategyResult,
    ValueStatus,
)

STRATEGY_IDS = ("S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08")

_DEFAULT_CONFIG_IDS = {sid: f"{sid}_DEFAULT" for sid in STRATEGY_IDS}
_DEFAULT_CONFIG_VERSIONS = {sid: f"{sid}_DEFAULT/R3.2-2026-10-19-OD1-v1" for sid in STRATEGY_IDS}


# ---------------------------------------------------------------------------
# Basic access and propagation
# ---------------------------------------------------------------------------


def _index(snapshot: MarketSnapshot, date: str) -> int | None:
    try:
        return snapshot.calendar.index(date)
    except ValueError:
        return None


def _shift(snapshot: MarketSnapshot, date: str, k: int) -> str | None:
    idx = _index(snapshot, date)
    if idx is None:
        return None
    target = idx + k
    if target < 0 or target >= len(snapshot.calendar):
        return None
    return snapshot.calendar[target]


def _bar(snapshot: MarketSnapshot, security_id: str, date: str) -> MarketBar | None:
    return snapshot.bars.get(security_id, {}).get(date)


def _is_available(available_at: str | None, business_date: str) -> bool:
    if available_at is None:
        return True
    date_part = available_at[:10]
    if date_part < business_date:
        return True
    if date_part > business_date:
        return False
    if len(available_at) > 10 and ("T" in available_at or " " in available_at):
        return available_at[11:19] <= "15:00:00"
    return True


def _check_available(value: Numeric, business_date: str) -> Numeric:
    if value.usable and not _is_available(value.available_at, business_date):
        return Numeric(None, ValueStatus.UNKNOWN, "VALUE_NOT_YET_AVAILABLE")
    return value


def _bar_validation_reason(bar: MarketBar, date: str) -> str | None:
    if bar.date != date:
        return "BAR_BUSINESS_DATE_MISMATCH"
    prices = (bar.open, bar.high, bar.low, bar.close)
    if any(item.usable and item.value is not None and item.value <= 0 for item in prices):
        return "NON_POSITIVE_PRICE"
    if all(item.usable and item.value is not None for item in prices):
        open_value = bar.open.value
        high_value = bar.high.value
        low_value = bar.low.value
        close_value = bar.close.value
        assert open_value is not None and high_value is not None
        assert low_value is not None and close_value is not None
        if high_value < max(open_value, close_value) or low_value > min(open_value, close_value):
            return "OHLC_CONTRADICTION"
        if high_value < low_value:
            return "OHLC_CONTRADICTION"
    if bar.volume.usable and bar.volume.value is not None and bar.volume.value < 0:
        return "NEGATIVE_VOLUME"
    if bar.amount.usable and bar.amount.value is not None and bar.amount.value < 0:
        return "NEGATIVE_AMOUNT"
    if bar.adjustment_factor.usable and bar.adjustment_factor.value is not None and bar.adjustment_factor.value <= 0:
        return "NON_POSITIVE_ADJUSTMENT_FACTOR"
    if bar.volume_factor.usable and bar.volume_factor.value is not None and bar.volume_factor.value <= 0:
        return "NON_POSITIVE_VOLUME_FACTOR"
    return None


def _bar_value(snapshot: MarketSnapshot, security_id: str, date: str, field: str) -> Numeric:
    bar = _bar(snapshot, security_id, date)
    if bar is None:
        return Numeric(None, ValueStatus.MISSING, "BAR_MISSING")
    invalid_reason = _bar_validation_reason(bar, date)
    if invalid_reason is not None:
        return Numeric(None, ValueStatus.INVALID, invalid_reason)
    business_date = snapshot.business_date
    if field == "adjusted_open":
        raw = _check_available(bar.open, business_date)
        factor = _check_available(bar.adjustment_factor, business_date)
        if not raw.usable:
            return raw
        if not factor.usable:
            return factor
        return bar.adjusted_open()
    if field == "adjusted_high":
        raw = _check_available(bar.high, business_date)
        factor = _check_available(bar.adjustment_factor, business_date)
        if not raw.usable:
            return raw
        if not factor.usable:
            return factor
        return bar.adjusted_high()
    if field == "adjusted_low":
        raw = _check_available(bar.low, business_date)
        factor = _check_available(bar.adjustment_factor, business_date)
        if not raw.usable:
            return raw
        if not factor.usable:
            return factor
        return bar.adjusted_low()
    if field == "adjusted_close":
        raw = _check_available(bar.close, business_date)
        factor = _check_available(bar.adjustment_factor, business_date)
        if not raw.usable:
            return raw
        if not factor.usable:
            return factor
        return bar.adjusted_close()
    if field == "adjusted_volume":
        raw = _check_available(bar.volume, business_date)
        factor = _check_available(bar.volume_factor, business_date)
        if not raw.usable:
            return raw
        if not factor.usable:
            return factor
        return bar.adjusted_volume()
    if field == "amount":
        return _check_available(bar.amount, business_date)
    if field == "raw_open":
        return _check_available(bar.open, business_date)
    if field == "raw_close":
        return _check_available(bar.close, business_date)
    raise ValueError(f"unknown bar field {field}")


def _series(
    snapshot: MarketSnapshot,
    security_id: str,
    field: str,
    count: int,
    end_date: str | None = None,
) -> tuple[list[tuple[str, Numeric]], Numeric | None]:
    end_date = end_date or snapshot.business_date
    end_index = _index(snapshot, end_date)
    if end_index is None or count <= 0 or end_index - count + 1 < 0:
        return [], Numeric(None, ValueStatus.MISSING, "INSUFFICIENT_HISTORY")
    dates = snapshot.calendar[end_index - count + 1 : end_index + 1]
    values: list[tuple[str, Numeric]] = []
    for date in dates:
        value = _bar_value(snapshot, security_id, date, field)
        values.append((date, value))
        if value.status is ValueStatus.NOT_APPLICABLE:
            return values, value
        if not value.usable:
            return values, value
    return values, None


def _mean_series(
    snapshot: MarketSnapshot,
    security_id: str,
    field: str,
    count: int,
    end_date: str | None = None,
) -> Numeric:
    values, blocker = _series(snapshot, security_id, field, count, end_date)
    if blocker is not None:
        return blocker
    assert all(v.value is not None for _, v in values)
    return Numeric(mean([v.value for _, v in values]), ValueStatus.VALUE)  # type: ignore[arg-type]


def _value_at(snapshot: MarketSnapshot, security_id: str, date: str, field: str) -> Numeric:
    return _bar_value(snapshot, security_id, date, field)


def ma_value(snapshot: MarketSnapshot, security_id: str, n: int, end_date: str | None = None) -> Numeric:
    return _mean_series(snapshot, security_id, "adjusted_close", n, end_date)


def return_value(
    snapshot: MarketSnapshot,
    security_id: str,
    n: int,
    end_date: str | None = None,
) -> Numeric:
    end_date = end_date or snapshot.business_date
    end_index = _index(snapshot, end_date)
    if end_index is None or end_index - n < 0:
        return Numeric(None, ValueStatus.MISSING, "INSUFFICIENT_HISTORY")
    start_date = snapshot.calendar[end_index - n]
    start = _value_at(snapshot, security_id, start_date, "adjusted_close")
    end = _value_at(snapshot, security_id, end_date, "adjusted_close")
    if start.status is ValueStatus.NOT_APPLICABLE:
        return start
    if end.status is ValueStatus.NOT_APPLICABLE:
        return end
    if not start.usable:
        return start
    if not end.usable:
        return end
    assert start.value is not None and end.value is not None
    if start.value <= 0:
        return Numeric(None, ValueStatus.INVALID, "NON_POSITIVE_PRICE")
    return Numeric(end.value / start.value - 1, ValueStatus.VALUE)


def benchmark_return_value(snapshot: MarketSnapshot, n: int, end_date: str | None = None) -> Numeric:
    end_date = end_date or snapshot.business_date
    end_index = _index(snapshot, end_date)
    if end_index is None or end_index - n < 0:
        return Numeric(None, ValueStatus.MISSING, "INSUFFICIENT_BENCHMARK_HISTORY")
    start_date = snapshot.calendar[end_index - n]
    start = snapshot.benchmark.get(start_date)
    end = snapshot.benchmark.get(end_date)
    if start is None or end is None:
        return Numeric(None, ValueStatus.MISSING, "BENCHMARK_MISSING")
    start = _check_available(start, snapshot.business_date)
    end = _check_available(end, snapshot.business_date)
    if start.status is ValueStatus.NOT_APPLICABLE:
        return start
    if end.status is ValueStatus.NOT_APPLICABLE:
        return end
    if not start.usable:
        return start
    if not end.usable:
        return end
    assert start.value is not None and end.value is not None
    if start.value <= 0:
        return Numeric(None, ValueStatus.INVALID, "NON_POSITIVE_BENCHMARK")
    return Numeric(end.value / start.value - 1, ValueStatus.VALUE)


def excess_return_value(
    snapshot: MarketSnapshot,
    security_id: str,
    n: int,
    end_date: str | None = None,
) -> Numeric:
    stock = return_value(snapshot, security_id, n, end_date)
    benchmark = benchmark_return_value(snapshot, n, end_date)
    if stock.status is ValueStatus.NOT_APPLICABLE:
        return stock
    if benchmark.status is ValueStatus.NOT_APPLICABLE:
        return benchmark
    if not stock.usable:
        return stock
    if not benchmark.usable:
        return benchmark
    assert stock.value is not None and benchmark.value is not None
    return Numeric(stock.value - benchmark.value, ValueStatus.VALUE)


def _avg_amount(snapshot: MarketSnapshot, security_id: str, count: int) -> Numeric:
    values, blocker = _series(snapshot, security_id, "amount", count)
    if blocker is not None:
        return blocker
    assert all(v.value is not None for _, v in values)
    return Numeric(mean([v.value for _, v in values]), ValueStatus.VALUE)  # type: ignore[arg-type]


def _sigma60(snapshot: MarketSnapshot, security_id: str) -> Numeric:
    end_index = _index(snapshot, snapshot.business_date)
    if end_index is None or end_index - 60 < 0:
        return Numeric(None, ValueStatus.MISSING, "INSUFFICIENT_HISTORY")
    returns: list[Decimal] = []
    for offset in range(59, -1, -1):
        date = snapshot.calendar[end_index - offset]
        prev = snapshot.calendar[end_index - offset - 1]
        current_value = _value_at(snapshot, security_id, date, "adjusted_close")
        previous_value = _value_at(snapshot, security_id, prev, "adjusted_close")
        if current_value.status is ValueStatus.NOT_APPLICABLE:
            return current_value
        if previous_value.status is ValueStatus.NOT_APPLICABLE:
            return previous_value
        if not current_value.usable:
            return current_value
        if not previous_value.usable:
            return previous_value
        assert current_value.value is not None and previous_value.value is not None
        if previous_value.value <= 0:
            return Numeric(None, ValueStatus.INVALID, "NON_POSITIVE_PRICE")
        returns.append(current_value.value / previous_value.value - 1)
    return Numeric(sample_std(returns), ValueStatus.VALUE)


def _illiq60(snapshot: MarketSnapshot, security_id: str) -> Numeric:
    end_index = _index(snapshot, snapshot.business_date)
    if end_index is None or end_index - 60 < 0:
        return Numeric(None, ValueStatus.MISSING, "INSUFFICIENT_HISTORY")
    values: list[Decimal] = []
    for offset in range(59, -1, -1):
        date = snapshot.calendar[end_index - offset]
        prev = snapshot.calendar[end_index - offset - 1]
        current_value = _value_at(snapshot, security_id, date, "adjusted_close")
        previous_value = _value_at(snapshot, security_id, prev, "adjusted_close")
        amount = _value_at(snapshot, security_id, date, "amount")
        for item in (current_value, previous_value, amount):
            if item.status is ValueStatus.NOT_APPLICABLE:
                return item
            if not item.usable:
                return item
        assert current_value.value is not None and previous_value.value is not None and amount.value is not None
        if previous_value.value <= 0:
            return Numeric(None, ValueStatus.INVALID, "NON_POSITIVE_PRICE")
        if amount.value <= 0:
            return Numeric(None, ValueStatus.NOT_APPLICABLE, "NOT_APPLICABLE_ZERO_AMOUNT")
        daily_return = current_value.value / previous_value.value - 1
        values.append(abs(daily_return) / amount.value)
    return Numeric(mean(values), ValueStatus.VALUE)


# ---------------------------------------------------------------------------
# Common eligibility
# ---------------------------------------------------------------------------


def _base_eligibility(snapshot: MarketSnapshot, security: SecurityInfo, bundle: ConfigBundle) -> tuple[Eligibility, list[str]]:
    reasons: list[str] = []
    if not security.is_common_stock:
        return Eligibility.BASE_EXCLUDED, ["NOT_COMMON_A_SHARE"]

    known_failure = False
    unknown_reasons: list[str] = []
    blocked_eligibility: Eligibility | None = None

    if security.is_st is True:
        known_failure = True
        reasons.append("ST_OR_RISK_WARNING")
    elif security.is_st is None:
        unknown_reasons.append("ST_STATUS_UNKNOWN")

    if security.is_delisting is True:
        known_failure = True
        reasons.append("DELISTING")
    elif security.is_delisting is None:
        unknown_reasons.append("DELISTING_STATUS_UNKNOWN")

    if security.suspended is True:
        known_failure = True
        reasons.append(security.suspension_reason or "FULL_DAY_SUSPENSION")
    elif security.suspended is None:
        unknown_reasons.append("SUSPENSION_STATUS_UNKNOWN")

    if security.listed_trading_days is None:
        unknown_reasons.append("LISTED_TRADING_DAYS_UNKNOWN")
    elif security.listed_trading_days < bundle.common.min_listed_days:
        known_failure = True
        reasons.append("LISTED_DAYS_BELOW_MINIMUM")

    amount = _avg_amount(snapshot, security.security_id, 20)
    if amount.status is ValueStatus.NOT_APPLICABLE:
        unknown_reasons.append("AVG_AMOUNT_NOT_APPLICABLE")
    elif not amount.usable:
        unknown_reasons.append(f"AVG_AMOUNT_{amount.status.value}")
        blocked_eligibility = _eligibility_from_blocker(amount)
    else:
        assert amount.value is not None
        if amount.value < bundle.common.min_avg_amount_20:
            known_failure = True
            reasons.append("AVG_AMOUNT_BELOW_MINIMUM")

    reasons.extend(unknown_reasons)
    if known_failure:
        return Eligibility.BASE_EXCLUDED, reasons
    if unknown_reasons:
        return blocked_eligibility or Eligibility.INPUT_UNKNOWN, reasons
    return Eligibility.SCORABLE, reasons


def _eligibility_from_blocker(blocker: Numeric) -> Eligibility:
    mapping = {
        ValueStatus.NOT_APPLICABLE: Eligibility.STRATEGY_NOT_APPLICABLE,
        ValueStatus.MISSING: Eligibility.MISSING,
        ValueStatus.REQUEST_FAILED: Eligibility.FAILED,
        ValueStatus.STALE: Eligibility.STALE,
        ValueStatus.INVALID: Eligibility.INVALID,
        ValueStatus.CONFLICT: Eligibility.CONFLICT,
    }
    return mapping.get(blocker.status, Eligibility.INPUT_UNKNOWN)


def _state_from_eligibility(eligibility: Eligibility) -> SignalState:
    mapping = {
        Eligibility.BASE_EXCLUDED: SignalState.BASE_EXCLUDED,
        Eligibility.STRATEGY_NOT_APPLICABLE: SignalState.STRATEGY_NOT_APPLICABLE,
        Eligibility.MISSING: SignalState.MISSING,
        Eligibility.FAILED: SignalState.FAILED,
        Eligibility.STALE: SignalState.STALE,
        Eligibility.INVALID: SignalState.INVALID,
        Eligibility.CONFLICT: SignalState.CONFLICT,
        Eligibility.INPUT_UNKNOWN: SignalState.INPUT_UNKNOWN,
    }
    return mapping[eligibility]


def _blocked_reason(prefix: str, blocker: Numeric) -> str:
    detail = blocker.reason or blocker.status.value
    return f"{prefix}:{detail}"


def _row(
    snapshot: MarketSnapshot,
    security_id: str,
    strategy_id: str,
    *,
    eligibility: Eligibility,
    state: SignalState,
    signal_status: ConditionStatus = ConditionStatus.UNKNOWN,
    observation_status: ConditionStatus = ConditionStatus.UNKNOWN,
    confirmation_status: ConditionStatus = ConditionStatus.UNKNOWN,
    config_id: str | None = None,
    config_version: str | None = None,
    reasons: Iterable[str] = (),
) -> RowResult:
    return RowResult(
        security_id=security_id,
        strategy_id=strategy_id,
        signal_date=snapshot.business_date,
        config_id=config_id or _DEFAULT_CONFIG_IDS[strategy_id],
        config_version=config_version or _DEFAULT_CONFIG_VERSIONS[strategy_id],
        input_version=snapshot.input_version,
        eligibility=eligibility,
        signal_state=state,
        signal_status=signal_status,
        observation_status=observation_status,
        confirmation_status=confirmation_status,
        reasons=tuple(reasons),
        available_at=snapshot.available_at,
    )


def _finalize(
    snapshot: MarketSnapshot,
    strategy_id: str,
    rows: dict[str, RowResult],
    key_fn: Callable[[RowResult], tuple],
    *,
    pool_complete: bool,
    config_id: str,
    config_version: str,
    industries: Mapping[str, IndustryResult] | None = None,
    notes: Iterable[str] = (),
    bound_s01_config_version: str | None = None,
) -> StrategyResult:
    for row in rows.values():
        row.config_id = config_id
        row.config_version = config_version
    scorable = [row for row in rows.values() if row.eligibility is Eligibility.SCORABLE]
    scorable.sort(key=key_fn)
    for rank, row in enumerate(scorable, 1):
        row.sample_pool_rank = rank
        if pool_complete:
            row.pool_rank = rank
        row.sort_key = tuple(str(item) for item in key_fn(row))

    candidates = [row for row in scorable if row.formal_candidate]
    candidates.sort(key=key_fn)
    for rank, row in enumerate(candidates, 1):
        row.sample_candidate_rank = rank
        if pool_complete:
            row.candidate_rank = rank

    return StrategyResult(
        strategy_id=strategy_id,
        signal_date=snapshot.business_date,
        config_id=config_id,
        config_version=config_version,
        input_version=snapshot.input_version,
        pool_complete=pool_complete,
        pool_size=len(scorable),
        candidate_size=len(candidates),
        rows={sid: rows[sid] for sid in sorted(rows)},
        industries=dict(sorted((industries or {}).items())),
        notes=tuple(notes),
        bound_s01_config_version=bound_s01_config_version,
    )


def _pool_inputs_complete(snapshot: MarketSnapshot, rows: Mapping[str, RowResult]) -> bool:
    if not snapshot.universe_complete:
        return False
    determinate = {
        Eligibility.SCORABLE,
        Eligibility.BASE_EXCLUDED,
        Eligibility.STRATEGY_NOT_APPLICABLE,
    }
    return all(row.eligibility in determinate for row in rows.values())


def _pool_is_complete(snapshot: MarketSnapshot, rows: Mapping[str, RowResult]) -> bool:
    if not _pool_inputs_complete(snapshot, rows):
        return False
    return not any(
        row.eligibility is Eligibility.SCORABLE and row.signal_status is ConditionStatus.UNKNOWN
        for row in rows.values()
    )


# ---------------------------------------------------------------------------
# S01
# ---------------------------------------------------------------------------


def _s01_metrics(snapshot: MarketSnapshot, security_id: str, cfg) -> tuple[dict[str, Decimal], Numeric | None]:
    price = _value_at(snapshot, security_id, snapshot.business_date, "adjusted_close")
    ma_short = ma_value(snapshot, security_id, cfg.ma_short)
    ma_long = ma_value(snapshot, security_id, cfg.ma_long)
    er20 = excess_return_value(snapshot, security_id, 20)
    er60 = excess_return_value(snapshot, security_id, 60)
    for item in (price, ma_short, ma_long, er20, er60):
        if item.status is ValueStatus.NOT_APPLICABLE:
            return {}, item
        if not item.usable:
            return {}, item
    assert price.value is not None and ma_short.value is not None and ma_long.value is not None
    assert er20.value is not None and er60.value is not None
    if price.value <= 0 or ma_short.value <= 0 or ma_long.value <= 0:
        return {}, Numeric(None, ValueStatus.INVALID, "NON_POSITIVE_PRICE")
    return {
        "price": price.value,
        "ma_short": ma_short.value,
        "ma_long": ma_long.value,
        "er20": er20.value,
        "er60": er60.value,
    }, None


def _s01_trigger(metrics: Mapping[str, Decimal]) -> ConditionStatus:
    p = metrics["price"]
    ma_s = metrics["ma_short"]
    ma_l = metrics["ma_long"]
    er20 = metrics["er20"]
    if p is None or ma_s is None or ma_l is None or er20 is None:
        return ConditionStatus.UNKNOWN
    return ConditionStatus.TRUE if (p > ma_s > ma_l and er20 > 0) else ConditionStatus.FALSE


def compute_s01(snapshot: MarketSnapshot, bundle: ConfigBundle) -> StrategyResult:
    cfg = bundle.s01
    config_id, config_version = bundle.effective_identity("S01")
    rows: dict[str, RowResult] = {}
    metrics_by_id: dict[str, dict[str, Decimal]] = {}
    for sid in sorted(snapshot.securities):
        security = snapshot.securities[sid]
        base_eligibility, base_reasons = _base_eligibility(snapshot, security, bundle)
        if base_eligibility is not Eligibility.SCORABLE:
            rows[sid] = _row(
                snapshot,
                sid,
                "S01",
                eligibility=base_eligibility,
                state=_state_from_eligibility(base_eligibility),
                config_id=cfg.config_id,
                config_version=cfg.config_version,
                reasons=base_reasons,
            )
            continue
        metrics, blocker = _s01_metrics(snapshot, sid, cfg)
        if blocker is not None:
            eligibility = _eligibility_from_blocker(blocker)
            rows[sid] = _row(
                snapshot,
                sid,
                "S01",
                eligibility=eligibility,
                state=_state_from_eligibility(eligibility),
                config_id=cfg.config_id,
                config_version=cfg.config_version,
                reasons=(_blocked_reason("S01_INPUT", blocker),),
            )
            continue
        metrics_by_id[sid] = metrics
        rows[sid] = _row(
            snapshot,
            sid,
            "S01",
            eligibility=Eligibility.SCORABLE,
            state=SignalState.ELIGIBLE_NOT_TRIGGERED,
            signal_status=_s01_trigger(metrics),
            observation_status=_s01_trigger(metrics),
            confirmation_status=_s01_trigger(metrics),
            config_id=cfg.config_id,
            config_version=cfg.config_version,
        )

    scorable = [rows[sid] for sid in metrics_by_id]
    if scorable:
        er20_population = [metrics_by_id[sid]["er20"] for sid in metrics_by_id]
        er60_population = [metrics_by_id[sid]["er60"] for sid in metrics_by_id]
        for sid, metrics in metrics_by_id.items():
            q20 = percentile_high(metrics["er20"], er20_population)
            q60 = percentile_high(metrics["er60"], er60_population)
            assert q20 is not None and q60 is not None
            score = (q20 + q60) / 2
            row = rows[sid]
            row.metrics.update(
                {
                    "er20": metrics["er20"],
                    "er60": metrics["er60"],
                    "q_er20": q20,
                    "q_er60": q60,
                    "score01": score,
                    "ma_short": metrics["ma_short"],
                    "ma_long": metrics["ma_long"],
                    "price": metrics["price"],
                }
            )
            row.conditions["trend"] = ConditionStatus.TRUE if metrics["price"] > metrics["ma_short"] > metrics["ma_long"] else ConditionStatus.FALSE
            row.conditions["er20_positive"] = ConditionStatus.TRUE if metrics["er20"] > 0 else ConditionStatus.FALSE
            if row.signal_status is ConditionStatus.TRUE:
                row.formal_candidate = True
                row.signal_state = SignalState.CANDIDATE

    def key(row: RowResult) -> tuple:
        return (
            negative(row.metrics["score01"]),  # type: ignore[arg-type]
            negative(row.metrics["er60"]),  # type: ignore[arg-type]
            negative(row.metrics["er20"]),  # type: ignore[arg-type]
            row.security_id,
        )

    pool_complete = _pool_is_complete(snapshot, rows)
    return _finalize(
        snapshot,
        "S01",
        rows,
        key,
        pool_complete=pool_complete,
        config_id=config_id,
        config_version=config_version,
        bound_s01_config_version=cfg.config_version,
    )


# ---------------------------------------------------------------------------
# S02
# ---------------------------------------------------------------------------


def _s02_metrics(snapshot: MarketSnapshot, security_id: str) -> tuple[dict[str, Decimal], Numeric | None]:
    end_index = _index(snapshot, snapshot.business_date)
    if end_index is None or end_index < 20:
        return {}, Numeric(None, ValueStatus.MISSING, "INSUFFICIENT_HISTORY")
    platform_dates = snapshot.calendar[end_index - 20 : end_index]
    highs: list[Decimal] = []
    lows: list[Decimal] = []
    volumes: list[Decimal] = []
    for date in platform_dates:
        high = _value_at(snapshot, security_id, date, "adjusted_high")
        low = _value_at(snapshot, security_id, date, "adjusted_low")
        volume = _value_at(snapshot, security_id, date, "adjusted_volume")
        for item in (high, low, volume):
            if item.status is ValueStatus.NOT_APPLICABLE:
                return {}, item
            if not item.usable:
                return {}, item
        assert high.value is not None and low.value is not None and volume.value is not None
        highs.append(high.value)
        lows.append(low.value)
        volumes.append(volume.value)
    u20 = max(highs)
    l20 = min(lows)
    v20 = mean(volumes)
    if u20 <= 0 or l20 <= 0:
        return {}, Numeric(None, ValueStatus.INVALID, "NON_POSITIVE_PLATFORM_PRICE")
    if v20 <= 0:
        return {}, Numeric(None, ValueStatus.NOT_APPLICABLE, "PLATFORM_VOLUME_ZERO")
    recent_volumes: list[Decimal] = []
    for date in snapshot.calendar[end_index - 5 : end_index]:
        volume = _value_at(snapshot, security_id, date, "adjusted_volume")
        if volume.status is ValueStatus.NOT_APPLICABLE:
            return {}, volume
        if not volume.usable:
            return {}, volume
        assert volume.value is not None
        recent_volumes.append(volume.value)
    v5 = mean(recent_volumes)
    price = _value_at(snapshot, security_id, snapshot.business_date, "adjusted_close")
    today_volume = _value_at(snapshot, security_id, snapshot.business_date, "adjusted_volume")
    for item in (price, today_volume):
        if item.status is ValueStatus.NOT_APPLICABLE:
            return {}, item
        if not item.usable:
            return {}, item
    assert price.value is not None and today_volume.value is not None
    return {
        "u20": u20,
        "l20": l20,
        "v20": v20,
        "v5": v5,
        "volume_ratio": today_volume.value / v20,
        "breakout": price.value / u20 - 1,
        "width": u20 / l20 - 1,
        "price": price.value,
        "today_volume": today_volume.value,
    }, None


def compute_s02(snapshot: MarketSnapshot, bundle: ConfigBundle) -> StrategyResult:
    cfg = bundle.s02
    config_id, config_version = bundle.effective_identity("S02")
    rows: dict[str, RowResult] = {}
    metrics_by_id: dict[str, dict[str, Decimal]] = {}
    for sid in sorted(snapshot.securities):
        security = snapshot.securities[sid]
        base_eligibility, base_reasons = _base_eligibility(snapshot, security, bundle)
        if base_eligibility is not Eligibility.SCORABLE:
            rows[sid] = _row(
                snapshot,
                sid,
                "S02",
                eligibility=base_eligibility,
                state=_state_from_eligibility(base_eligibility),
                reasons=base_reasons,
            )
            continue
        metrics, blocker = _s02_metrics(snapshot, sid)
        if blocker is not None:
            eligibility = _eligibility_from_blocker(blocker)
            rows[sid] = _row(
                snapshot,
                sid,
                "S02",
                eligibility=eligibility,
                state=_state_from_eligibility(eligibility),
                reasons=(_blocked_reason("S02_INPUT", blocker),),
            )
            continue
        metrics_by_id[sid] = metrics
        observation = (
            metrics["width"] <= cfg.platform_width and metrics["v5"] <= cfg.shrink_ratio * metrics["v20"]
        )
        confirmation = (
            metrics["price"] > metrics["u20"] and metrics["today_volume"] >= cfg.breakout_volume * metrics["v20"]
        )
        signal = observation and confirmation
        row = _row(
            snapshot,
            sid,
            "S02",
            eligibility=Eligibility.SCORABLE,
            state=SignalState.CANDIDATE if signal else SignalState.ELIGIBLE_NOT_TRIGGERED,
            signal_status=ConditionStatus.TRUE if signal else ConditionStatus.FALSE,
            observation_status=ConditionStatus.TRUE if observation else ConditionStatus.FALSE,
            confirmation_status=ConditionStatus.TRUE if confirmation else ConditionStatus.FALSE,
        )
        row.metrics.update(metrics)
        row.conditions["platform_quiet"] = ConditionStatus.TRUE if observation else ConditionStatus.FALSE
        row.conditions["breakout"] = ConditionStatus.TRUE if confirmation else ConditionStatus.FALSE
        row.formal_candidate = signal
        rows[sid] = row

    def key(row: RowResult) -> tuple:
        return (
            negative(row.metrics["volume_ratio"]),  # type: ignore[arg-type]
            negative(row.metrics["breakout"]),  # type: ignore[arg-type]
            row.security_id,
        )

    pool_complete = _pool_is_complete(snapshot, rows)
    return _finalize(
        snapshot,
        "S02",
        rows,
        key,
        pool_complete=pool_complete,
        config_id=config_id,
        config_version=config_version,
    )


# ---------------------------------------------------------------------------
# S03
# ---------------------------------------------------------------------------


def _s03_metrics(snapshot: MarketSnapshot, security_id: str, cfg) -> tuple[dict[str, Decimal], Numeric | None]:
    price = _value_at(snapshot, security_id, snapshot.business_date, "adjusted_close")
    ma20 = ma_value(snapshot, security_id, 20)
    ma60 = ma_value(snapshot, security_id, 60)
    er60 = excess_return_value(snapshot, security_id, 60)
    end_index = _index(snapshot, snapshot.business_date)
    if end_index is None or end_index < 21:
        return {}, Numeric(None, ValueStatus.MISSING, "INSUFFICIENT_HISTORY")
    highs: list[Decimal] = []
    for date in snapshot.calendar[end_index - 20 : end_index]:
        high = _value_at(snapshot, security_id, date, "adjusted_high")
        if high.status is ValueStatus.NOT_APPLICABLE:
            return {}, high
        if not high.usable:
            return {}, high
        assert high.value is not None
        highs.append(high.value)
    yesterday_high = _value_at(snapshot, security_id, snapshot.calendar[end_index - 1], "adjusted_high")
    for item in (price, ma20, ma60, er60, yesterday_high):
        if item.status is ValueStatus.NOT_APPLICABLE:
            return {}, item
        if not item.usable:
            return {}, item
    assert price.value is not None and ma20.value is not None and ma60.value is not None
    assert er60.value is not None and yesterday_high.value is not None
    if price.value <= 0 or ma20.value <= 0 or ma60.value <= 0:
        return {}, Numeric(None, ValueStatus.INVALID, "NON_POSITIVE_PRICE")
    prior_high = max(highs)
    if prior_high <= 0:
        return {}, Numeric(None, ValueStatus.INVALID, "NON_POSITIVE_PRIOR_HIGH")
    distance = abs(price.value / ma20.value - 1)
    drawdown = 1 - price.value / prior_high
    return {
        "price": price.value,
        "ma20": ma20.value,
        "ma60": ma60.value,
        "er60": er60.value,
        "distance": distance,
        "drawdown": drawdown,
        "prior_high": prior_high,
        "yesterday_high": yesterday_high.value,
    }, None


def compute_s03(snapshot: MarketSnapshot, bundle: ConfigBundle) -> StrategyResult:
    cfg = bundle.s03
    config_id, config_version = bundle.effective_identity("S03")
    rows: dict[str, RowResult] = {}
    metrics_by_id: dict[str, dict[str, Decimal]] = {}
    for sid in sorted(snapshot.securities):
        security = snapshot.securities[sid]
        base_eligibility, base_reasons = _base_eligibility(snapshot, security, bundle)
        if base_eligibility is not Eligibility.SCORABLE:
            rows[sid] = _row(
                snapshot,
                sid,
                "S03",
                eligibility=base_eligibility,
                state=_state_from_eligibility(base_eligibility),
                reasons=base_reasons,
            )
            continue
        metrics, blocker = _s03_metrics(snapshot, sid, cfg)
        if blocker is not None:
            eligibility = _eligibility_from_blocker(blocker)
            rows[sid] = _row(
                snapshot,
                sid,
                "S03",
                eligibility=eligibility,
                state=_state_from_eligibility(eligibility),
                reasons=(_blocked_reason("S03_INPUT", blocker),),
            )
            continue
        metrics_by_id[sid] = metrics
        observation = (
            metrics["ma20"] > metrics["ma60"]
            and metrics["distance"] <= cfg.ma_distance
            and cfg.drawdown_low <= metrics["drawdown"] <= cfg.drawdown_high
        )
        confirmation = metrics["price"] > metrics["yesterday_high"]
        signal = observation and confirmation
        row = _row(
            snapshot,
            sid,
            "S03",
            eligibility=Eligibility.SCORABLE,
            state=SignalState.CANDIDATE if signal else SignalState.ELIGIBLE_NOT_TRIGGERED,
            signal_status=ConditionStatus.TRUE if signal else ConditionStatus.FALSE,
            observation_status=ConditionStatus.TRUE if observation else ConditionStatus.FALSE,
            confirmation_status=ConditionStatus.TRUE if confirmation else ConditionStatus.FALSE,
        )
        row.metrics.update(metrics)
        row.conditions["pullback_observation"] = ConditionStatus.TRUE if observation else ConditionStatus.FALSE
        row.conditions["reclaim_yesterday_high"] = ConditionStatus.TRUE if confirmation else ConditionStatus.FALSE
        row.formal_candidate = signal
        rows[sid] = row

    def key(row: RowResult) -> tuple:
        return (
            negative(row.metrics["er60"]),  # type: ignore[arg-type]
            key_decimal(row.metrics["distance"]),  # type: ignore[arg-type]
            row.security_id,
        )

    pool_complete = _pool_is_complete(snapshot, rows)
    return _finalize(
        snapshot,
        "S03",
        rows,
        key,
        pool_complete=pool_complete,
        config_id=config_id,
        config_version=config_version,
    )


# ---------------------------------------------------------------------------
# S04
# ---------------------------------------------------------------------------


def _s04_metrics(snapshot: MarketSnapshot, security_id: str) -> tuple[dict[str, Decimal | None], Numeric | None]:
    end_index = _index(snapshot, snapshot.business_date)
    if end_index is None or end_index < 19:
        return {}, Numeric(None, ValueStatus.MISSING, "INSUFFICIENT_HISTORY")
    d_minus_1 = snapshot.calendar[end_index - 1]
    d_minus_6 = snapshot.calendar[end_index - 6] if end_index >= 6 else None
    if d_minus_6 is None:
        return {}, Numeric(None, ValueStatus.MISSING, "D_MINUS_6_MISSING")
    p_prev = _value_at(snapshot, security_id, d_minus_1, "adjusted_close")
    p_6 = _value_at(snapshot, security_id, d_minus_6, "adjusted_close")
    price = _value_at(snapshot, security_id, snapshot.business_date, "adjusted_close")
    ma5 = ma_value(snapshot, security_id, 5)
    ma20 = ma_value(snapshot, security_id, 20)
    yesterday_high = _value_at(snapshot, security_id, d_minus_1, "adjusted_high")
    for item in (p_prev, p_6, price, ma5, yesterday_high):
        if item.status is ValueStatus.NOT_APPLICABLE:
            return {}, item
        if not item.usable:
            return {}, item
    assert p_prev.value is not None and p_6.value is not None and price.value is not None
    assert ma5.value is not None and yesterday_high.value is not None
    if p_6.value <= 0 or p_prev.value <= 0:
        return {}, Numeric(None, ValueStatus.INVALID, "NON_POSITIVE_PRICE")
    return {
        "price": price.value,
        "p_prev": p_prev.value,
        "p_d6": p_6.value,
        "ma5": ma5.value,
        "ma20": ma20.value if ma20.usable else None,
        "yesterday_high": yesterday_high.value,
        "prior_drop5": p_prev.value / p_6.value - 1,
        "repair": price.value / p_prev.value - 1,
    }, None


def compute_s04(snapshot: MarketSnapshot, bundle: ConfigBundle) -> StrategyResult:
    cfg = bundle.s04
    config_id, config_version = bundle.effective_identity("S04")
    rows: dict[str, RowResult] = {}
    metrics_by_id: dict[str, dict[str, Decimal]] = {}
    for sid in sorted(snapshot.securities):
        security = snapshot.securities[sid]
        base_eligibility, base_reasons = _base_eligibility(snapshot, security, bundle)
        if base_eligibility is not Eligibility.SCORABLE:
            rows[sid] = _row(
                snapshot,
                sid,
                "S04",
                eligibility=base_eligibility,
                state=_state_from_eligibility(base_eligibility),
                reasons=base_reasons,
            )
            continue
        metrics, blocker = _s04_metrics(snapshot, sid)
        if blocker is not None:
            eligibility = _eligibility_from_blocker(blocker)
            rows[sid] = _row(
                snapshot,
                sid,
                "S04",
                eligibility=eligibility,
                state=_state_from_eligibility(eligibility),
                reasons=(_blocked_reason("S04_INPUT", blocker),),
            )
            continue
        metrics_by_id[sid] = metrics
        observation = metrics["prior_drop5"] <= cfg.prior_drop_threshold  # type: ignore[operator]
        confirmation = metrics["price"] > metrics["ma5"] and metrics["price"] > metrics["yesterday_high"]  # type: ignore[operator]
        signal = observation and confirmation
        if metrics["ma20"] is None:
            conflict = ConditionStatus.UNKNOWN
        else:
            conflict = ConditionStatus.TRUE if metrics["price"] >= metrics["ma20"] else ConditionStatus.FALSE  # type: ignore[operator]
        row = _row(
            snapshot,
            sid,
            "S04",
            eligibility=Eligibility.SCORABLE,
            state=SignalState.CANDIDATE if signal else SignalState.ELIGIBLE_NOT_TRIGGERED,
            signal_status=ConditionStatus.TRUE if signal else ConditionStatus.FALSE,
            observation_status=ConditionStatus.TRUE if observation else ConditionStatus.FALSE,
            confirmation_status=ConditionStatus.TRUE if confirmation else ConditionStatus.FALSE,
        )
        row.metrics.update(metrics)
        row.conditions["prior_drop5"] = ConditionStatus.TRUE if observation else ConditionStatus.FALSE
        row.conditions["repair_confirmation"] = ConditionStatus.TRUE if confirmation else ConditionStatus.FALSE
        row.conditions["entry_conflict_exit"] = conflict
        row.entry_conflict_exit = conflict
        row.formal_candidate = signal
        rows[sid] = row

    def key(row: RowResult) -> tuple:
        return (
            negative(row.metrics["repair"]),  # type: ignore[arg-type]
            key_decimal(row.metrics["prior_drop5"]),  # type: ignore[arg-type]
            row.security_id,
        )

    pool_complete = _pool_is_complete(snapshot, rows)
    return _finalize(
        snapshot,
        "S04",
        rows,
        key,
        pool_complete=pool_complete,
        config_id=config_id,
        config_version=config_version,
    )


# ---------------------------------------------------------------------------
# S05
# ---------------------------------------------------------------------------


def _s05_metrics(snapshot: MarketSnapshot, security_id: str) -> tuple[dict[str, Decimal], Numeric | None]:
    price = _value_at(snapshot, security_id, snapshot.business_date, "adjusted_close")
    ma60 = ma_value(snapshot, security_id, 60)
    d_minus_5 = _shift(snapshot, snapshot.business_date, -5)
    if d_minus_5 is None:
        return {}, Numeric(None, ValueStatus.MISSING, "INSUFFICIENT_HISTORY")
    ma60_prev = ma_value(snapshot, security_id, 60, d_minus_5)
    sigma = _sigma60(snapshot, security_id)
    illiq = _illiq60(snapshot, security_id)
    for item in (price, ma60, ma60_prev, sigma, illiq):
        if item.status is ValueStatus.NOT_APPLICABLE:
            return {}, item
        if not item.usable:
            return {}, item
    assert price.value is not None and ma60.value is not None and ma60_prev.value is not None
    assert sigma.value is not None and illiq.value is not None
    if price.value <= 0 or ma60.value <= 0 or ma60_prev.value <= 0:
        return {}, Numeric(None, ValueStatus.INVALID, "NON_POSITIVE_PRICE")
    return {
        "price": price.value,
        "ma60": ma60.value,
        "ma60_prev": ma60_prev.value,
        "sigma60": sigma.value,
        "illiq60": illiq.value,
    }, None


def compute_s05(snapshot: MarketSnapshot, bundle: ConfigBundle) -> StrategyResult:
    cfg = bundle.s05
    config_id, config_version = bundle.effective_identity("S05")
    rows: dict[str, RowResult] = {}
    metrics_by_id: dict[str, dict[str, Decimal]] = {}
    for sid in sorted(snapshot.securities):
        security = snapshot.securities[sid]
        base_eligibility, base_reasons = _base_eligibility(snapshot, security, bundle)
        if base_eligibility is not Eligibility.SCORABLE:
            rows[sid] = _row(
                snapshot,
                sid,
                "S05",
                eligibility=base_eligibility,
                state=_state_from_eligibility(base_eligibility),
                reasons=base_reasons,
            )
            continue
        metrics, blocker = _s05_metrics(snapshot, sid)
        if blocker is not None:
            eligibility = _eligibility_from_blocker(blocker)
            rows[sid] = _row(
                snapshot,
                sid,
                "S05",
                eligibility=eligibility,
                state=_state_from_eligibility(eligibility),
                reasons=(_blocked_reason("S05_INPUT", blocker),),
            )
            continue
        metrics_by_id[sid] = metrics
        rows[sid] = _row(
            snapshot,
            sid,
            "S05",
            eligibility=Eligibility.SCORABLE,
            state=SignalState.ELIGIBLE_NOT_TRIGGERED,
            signal_status=ConditionStatus.UNKNOWN,
            observation_status=ConditionStatus.UNKNOWN,
            confirmation_status=ConditionStatus.UNKNOWN,
        )

    pool_complete = _pool_inputs_complete(snapshot, rows)
    if metrics_by_id:
        sigma_population = [metrics_by_id[sid]["sigma60"] for sid in metrics_by_id]
        illiq_population = [metrics_by_id[sid]["illiq60"] for sid in metrics_by_id]
        for sid, metrics in metrics_by_id.items():
            q_sigma = percentile_high(metrics["sigma60"], sigma_population)
            q_illiq = percentile_high(metrics["illiq60"], illiq_population)
            assert q_sigma is not None and q_illiq is not None
            score = ((1 - q_sigma) + (1 - q_illiq)) / 2
            trend = metrics["price"] > metrics["ma60"] and metrics["ma60"] > metrics["ma60_prev"]
            if pool_complete:
                low_vol = ConditionStatus.TRUE if q_sigma <= cfg.low_vol_percentile else ConditionStatus.FALSE
            else:
                low_vol = ConditionStatus.UNKNOWN
            if not trend:
                overall = ConditionStatus.FALSE
            elif low_vol is ConditionStatus.TRUE:
                overall = ConditionStatus.TRUE
            elif low_vol is ConditionStatus.FALSE:
                overall = ConditionStatus.FALSE
            else:
                overall = ConditionStatus.UNKNOWN
            row = rows[sid]
            row.metrics.update(
                {
                    "sigma60": metrics["sigma60"],
                    "illiq60": metrics["illiq60"],
                    "q_sigma60": q_sigma,
                    "q_illiq60": q_illiq,
                    "score05": score,
                    "ma60": metrics["ma60"],
                    "ma60_prev": metrics["ma60_prev"],
                    "price": metrics["price"],
                }
            )
            row.signal_status = overall
            row.observation_status = ConditionStatus.TRUE if trend else ConditionStatus.FALSE
            row.confirmation_status = low_vol
            row.conditions["trend"] = ConditionStatus.TRUE if trend else ConditionStatus.FALSE
            row.conditions["low_vol_percentile"] = low_vol
            if overall is ConditionStatus.TRUE:
                row.formal_candidate = True
                row.signal_state = SignalState.CANDIDATE
            elif overall is ConditionStatus.UNKNOWN:
                row.signal_state = SignalState.INPUT_UNKNOWN
            else:
                row.signal_state = SignalState.ELIGIBLE_NOT_TRIGGERED

    def key(row: RowResult) -> tuple:
        return (
            negative(row.metrics["score05"]),  # type: ignore[arg-type]
            key_decimal(row.metrics["sigma60"]),  # type: ignore[arg-type]
            key_decimal(row.metrics["illiq60"]),  # type: ignore[arg-type]
            row.security_id,
        )

    return _finalize(
        snapshot,
        "S05",
        rows,
        key,
        pool_complete=pool_complete,
        config_id=config_id,
        config_version=config_version,
    )


# ---------------------------------------------------------------------------
# S06
# ---------------------------------------------------------------------------


def _s06_industry_stats(
    snapshot: MarketSnapshot,
    bundle: ConfigBundle,
    base: Mapping[str, tuple[Eligibility, list[str]]],
    s01_metrics: Mapping[str, dict[str, Decimal]],
    s01_error: Mapping[str, Numeric],
    cfg,
) -> dict[str, IndustryResult]:
    industries: dict[str, IndustryResult] = {}
    all_security_ids = set(snapshot.securities)
    mapped: set[str] = set()
    for industry_id, members in snapshot.industry_members.items():
        members = tuple(sorted(members))
        mapped.update(members)
        reasons: list[str] = []
        status = "OK"
        if not snapshot.industry_mapping_complete:
            status = "UNKNOWN"
            reasons.append("INDUSTRY_MAPPING_INCOMPLETE")
        if any(member not in all_security_ids for member in members):
            status = "UNKNOWN"
            reasons.append("INDUSTRY_MEMBER_NOT_IN_UNIVERSE")
        e0_members: list[str] = []
        unknown_member = False
        for member in members:
            eligibility, member_reasons = base.get(member, (Eligibility.INPUT_UNKNOWN, ["UNKNOWN_SECURITY"]))
            if eligibility is Eligibility.SCORABLE:
                e0_members.append(member)
            elif eligibility not in (Eligibility.BASE_EXCLUDED, Eligibility.STRATEGY_NOT_APPLICABLE):
                unknown_member = True
                reasons.extend(member_reasons)
        if unknown_member:
            status = "UNKNOWN"
            reasons.append("INDUSTRY_MEMBER_STATUS_UNKNOWN")
        breadth: Decimal | None = None
        excess: Decimal | None = None
        if status == "OK":
            if not e0_members:
                status = "EMPTY"
            else:
                above = 0
                excess_values: list[Decimal] = []
                for member in e0_members:
                    if member in s01_error:
                        status = "UNKNOWN"
                        reasons.append(f"MEMBER_S01_UNKNOWN:{member}")
                        break
                    metrics = s01_metrics.get(member)
                    if metrics is None:
                        status = "UNKNOWN"
                        reasons.append(f"MEMBER_S01_MISSING:{member}")
                        break
                    if metrics["price"] > metrics["ma_short"]:
                        above += 1
                    excess_values.append(metrics["er20"])
                if status == "OK":
                    breadth = Decimal(above) / Decimal(len(e0_members))
                    excess = mean(excess_values)
        industries[industry_id] = IndustryResult(
            industry_id=industry_id,
            members=members,
            e0_members=tuple(e0_members),
            breadth=breadth,
            excess=excess,
            score=None,
            total_rank=None,
            strong=False,
            status=status,
            reasons=tuple(reasons),
        )

    for sid, security in snapshot.securities.items():
        if sid not in mapped:
            if security.industry_id:
                # A security claims an industry that is absent from the mapping.
                industry_id = security.industry_id
                existing = industries.get(industry_id)
                if existing is None:
                    industries[industry_id] = IndustryResult(
                        industry_id=industry_id,
                        members=(sid,),
                        e0_members=(),
                        breadth=None,
                        excess=None,
                        score=None,
                        total_rank=None,
                        strong=False,
                        status="UNKNOWN",
                        reasons=("INDUSTRY_MEMBER_MISSING_FROM_MAPPING",),
                    )
                else:
                    industries[industry_id] = IndustryResult(
                        industry_id=existing.industry_id,
                        members=tuple(sorted(set(existing.members) | {sid})),
                        e0_members=existing.e0_members,
                        breadth=None,
                        excess=None,
                        score=None,
                        total_rank=None,
                        strong=False,
                        status="UNKNOWN",
                        reasons=existing.reasons + ("INDUSTRY_MEMBER_MISSING_FROM_MAPPING",),
                    )

    complete = [
        item
        for item in industries.values()
        if item.status == "OK" and item.breadth is not None and item.excess is not None
    ]
    if complete:
        breadth_population = [item.breadth for item in complete]  # type: ignore[misc]
        excess_population = [item.excess for item in complete]  # type: ignore[misc]
        for item in complete:
            q_b = percentile_high(item.breadth, breadth_population)  # type: ignore[arg-type]
            q_e = percentile_high(item.excess, excess_population)  # type: ignore[arg-type]
            assert q_b is not None and q_e is not None
            industries[item.industry_id] = IndustryResult(
                industry_id=item.industry_id,
                members=item.members,
                e0_members=item.e0_members,
                breadth=item.breadth,
                excess=item.excess,
                score=(q_b + q_e) / 2,
                total_rank=None,
                strong=False,
                status=item.status,
                reasons=item.reasons,
            )

    ranked = sorted(
        (item for item in industries.values() if item.score is not None),
        key=lambda item: (
            negative(item.score),  # type: ignore[arg-type]
            negative(item.breadth),  # type: ignore[arg-type]
            negative(item.excess),  # type: ignore[arg-type]
            item.industry_id,
        ),
    )
    for rank, item in enumerate(ranked, 1):
        industries[item.industry_id] = IndustryResult(
            industry_id=item.industry_id,
            members=item.members,
            e0_members=item.e0_members,
            breadth=item.breadth,
            excess=item.excess,
            score=item.score,
            total_rank=rank,
            strong=False,
            status=item.status,
            reasons=item.reasons,
        )

    strong_candidates = [
        item
        for item in industries.values()
        if item.total_rank is not None
        and item.breadth is not None
        and item.excess is not None
        and item.breadth >= cfg.breadth_threshold
        and item.excess > 0
    ]
    strong_candidates.sort(key=lambda item: item.total_rank or 10**9)
    strong_ids = {item.industry_id for item in strong_candidates[: cfg.strong_industry_count]}
    for industry_id, item in industries.items():
        industries[industry_id] = IndustryResult(
            industry_id=item.industry_id,
            members=item.members,
            e0_members=item.e0_members,
            breadth=item.breadth,
            excess=item.excess,
            score=item.score,
            total_rank=item.total_rank,
            strong=industry_id in strong_ids,
            status=item.status,
            reasons=item.reasons,
        )
    return industries


def compute_s06(snapshot: MarketSnapshot, bundle: ConfigBundle) -> StrategyResult:
    cfg = bundle.s06
    config_id, config_version = bundle.effective_identity("S06")
    # S06 always uses the fixed default S01 identity, never the personal S01.
    s01_cfg = S01_DEFAULT_CONFIG
    rows: dict[str, RowResult] = {}
    base: dict[str, tuple[Eligibility, list[str]]] = {}
    s01_metrics: dict[str, dict[str, Decimal]] = {}
    s01_error: dict[str, Numeric] = {}
    for sid in sorted(snapshot.securities):
        security = snapshot.securities[sid]
        base_eligibility, base_reasons = _base_eligibility(snapshot, security, bundle)
        base[sid] = (base_eligibility, base_reasons)
        if base_eligibility is not Eligibility.SCORABLE:
            continue
        metrics, blocker = _s01_metrics(snapshot, sid, s01_cfg)
        if blocker is not None:
            s01_error[sid] = blocker
        else:
            s01_metrics[sid] = metrics

    industries = _s06_industry_stats(snapshot, bundle, base, s01_metrics, s01_error, cfg)
    industry_cross_complete = (
        snapshot.universe_complete
        and snapshot.industry_mapping_complete
        and all(item.status in ("OK", "EMPTY") for item in industries.values())
    )
    if not industry_cross_complete:
        industries = {
            industry_id: dataclass_replace(
                item,
                total_rank=None,
                strong=False,
                reasons=item.reasons + ("INDUSTRY_CROSS_SECTION_INCOMPLETE",),
            )
            for industry_id, item in industries.items()
        }

    industry_members: dict[str, list[str]] = {}
    for industry_id, item in industries.items():
        for member in item.members:
            industry_members.setdefault(industry_id, []).append(member)
    for industry_id in industry_members:
        industry_members[industry_id].sort()

    industry_pool_ranks: dict[str, int] = {}
    industry_trigger_ranks: dict[str, int] = {}

    # Compute S01 score/order on the full E01 for S06's bound default config.
    e01_ids = sorted(s01_metrics)
    er20_population = [s01_metrics[sid]["er20"] for sid in e01_ids]
    er60_population = [s01_metrics[sid]["er60"] for sid in e01_ids]
    s01_score: dict[str, Decimal] = {}
    for sid in e01_ids:
        q20 = percentile_high(s01_metrics[sid]["er20"], er20_population)
        q60 = percentile_high(s01_metrics[sid]["er60"], er60_population)
        assert q20 is not None and q60 is not None
        s01_score[sid] = (q20 + q60) / 2

    def s01_key(sid: str) -> tuple:
        return (
            negative(s01_score[sid]),
            negative(s01_metrics[sid]["er60"]),
            negative(s01_metrics[sid]["er20"]),
            sid,
        )

    for industry_id, item in industries.items():
        members = sorted((member for member in item.members if member in s01_metrics), key=s01_key)
        triggers = [member for member in members if _s01_trigger(s01_metrics[member]) is ConditionStatus.TRUE]
        for rank, member in enumerate(members, 1):
            industry_pool_ranks[f"{industry_id}:{member}"] = rank
        for rank, member in enumerate(triggers, 1):
            industry_trigger_ranks[f"{industry_id}:{member}"] = rank

    for sid in sorted(snapshot.securities):
        security = snapshot.securities[sid]
        base_eligibility, base_reasons = base[sid]
        if base_eligibility is not Eligibility.SCORABLE:
            rows[sid] = _row(
                snapshot,
                sid,
                "S06",
                eligibility=base_eligibility,
                state=_state_from_eligibility(base_eligibility),
                reasons=base_reasons,
            )
            continue
        industry_id = security.industry_id
        if not security.industry_known or not industry_id:
            rows[sid] = _row(
                snapshot,
                sid,
                "S06",
                eligibility=Eligibility.INPUT_UNKNOWN,
                state=SignalState.INPUT_UNKNOWN,
                reasons=("INDUSTRY_UNKNOWN",),
            )
            continue
        industry = industries.get(industry_id)
        if industry is None:
            rows[sid] = _row(
                snapshot,
                sid,
                "S06",
                eligibility=Eligibility.INPUT_UNKNOWN,
                state=SignalState.INPUT_UNKNOWN,
                reasons=("INDUSTRY_MEMBERSHIP_UNKNOWN",),
            )
            continue
        if industry.status not in ("OK", "EMPTY"):
            rows[sid] = _row(
                snapshot,
                sid,
                "S06",
                eligibility=Eligibility.INPUT_UNKNOWN,
                state=SignalState.INPUT_UNKNOWN,
                reasons=("INDUSTRY_STATS_UNKNOWN",) + industry.reasons,
            )
            continue
        if sid in s01_error:
            blocker = s01_error[sid]
            eligibility = _eligibility_from_blocker(blocker)
            rows[sid] = _row(
                snapshot,
                sid,
                "S06",
                eligibility=eligibility,
                state=_state_from_eligibility(eligibility),
                reasons=(_blocked_reason("S06_BOUND_S01_INPUT", blocker),),
            )
            continue
        metrics = s01_metrics[sid]
        trigger = _s01_trigger(metrics) is ConditionStatus.TRUE
        pool_key = f"{industry_id}:{sid}"
        industry_pool_rank = industry_pool_ranks.get(pool_key)
        industry_trigger_rank = industry_trigger_ranks.get(pool_key)
        formal = (
            trigger
            and industry.strong
            and industry_trigger_rank is not None
            and industry_trigger_rank <= cfg.max_per_industry
        )
        concentration_excluded = (
            trigger
            and industry.strong
            and industry_trigger_rank is not None
            and industry_trigger_rank > cfg.max_per_industry
        )
        row = _row(
            snapshot,
            sid,
            "S06",
            eligibility=Eligibility.SCORABLE,
            state=(
                SignalState.CANDIDATE
                if formal
                else SignalState.CONCENTRATION_EXCLUDED
                if concentration_excluded
                else SignalState.ELIGIBLE_NOT_TRIGGERED
            ),
            signal_status=ConditionStatus.TRUE if formal else ConditionStatus.FALSE,
            observation_status=ConditionStatus.TRUE if trigger else ConditionStatus.FALSE,
            confirmation_status=ConditionStatus.TRUE if industry.strong else ConditionStatus.FALSE,
        )
        row.industry_id = industry_id
        row.industry_pool_rank = industry_pool_rank
        row.industry_trigger_rank = industry_trigger_rank
        row.industry_total_rank = industry.total_rank
        row.formal_candidate = formal
        row.metrics.update(
            {
                "s01_score": s01_score[sid],
                "er20": metrics["er20"],
                "er60": metrics["er60"],
                "price": metrics["price"],
                "ma_short": metrics["ma_short"],
                "ma_long": metrics["ma_long"],
                "industry_breadth": industry.breadth,
                "industry_excess": industry.excess,
                "industry_score": industry.score,
                "industry_total_rank": Decimal(industry.total_rank) if industry.total_rank is not None else None,
                "industry_pool_rank": Decimal(industry_pool_rank) if industry_pool_rank is not None else None,
                "industry_trigger_rank": Decimal(industry_trigger_rank) if industry_trigger_rank is not None else None,
            }
        )
        row.conditions["bound_s01_trigger"] = ConditionStatus.TRUE if trigger else ConditionStatus.FALSE
        row.conditions["strong_industry"] = ConditionStatus.TRUE if industry.strong else ConditionStatus.FALSE
        row.conditions["concentration_slot"] = ConditionStatus.TRUE if formal else ConditionStatus.FALSE
        if concentration_excluded:
            row.reasons = ("CONCENTRATION_EXCLUDED",)
        elif trigger and not industry.strong:
            row.reasons = ("INDUSTRY_NOT_STRONG",)
        if not industry_cross_complete and trigger:
            row.signal_status = ConditionStatus.UNKNOWN
            row.confirmation_status = ConditionStatus.UNKNOWN
            row.signal_state = SignalState.INPUT_UNKNOWN
            row.formal_candidate = False
            row.conditions["strong_industry"] = ConditionStatus.UNKNOWN
            row.reasons = tuple(dict.fromkeys(row.reasons + ("INDUSTRY_CROSS_SECTION_INCOMPLETE",)))
        rows[sid] = row

    replacements_by_industry: dict[str, list[RowResult]] = {}
    for row in rows.values():
        if row.signal_state is SignalState.CONCENTRATION_EXCLUDED and row.industry_id is not None:
            replacements_by_industry.setdefault(row.industry_id, []).append(row)
    for industry_id, replacement_rows in replacements_by_industry.items():
        replacement_rows.sort(
            key=lambda item: (
                item.industry_trigger_rank if item.industry_trigger_rank is not None else 10**9,
                item.security_id,
            )
        )
        for order, row in enumerate(replacement_rows, 1):
            row.execution_replacement_order = order

    def key(row: RowResult) -> tuple:
        return (
            row.industry_total_rank if row.industry_total_rank is not None else 10**9,
            row.industry_pool_rank if row.industry_pool_rank is not None else 10**9,
            row.security_id,
        )

    complete = snapshot.universe_complete and snapshot.industry_mapping_complete
    if any(item.status not in ("OK", "EMPTY") for item in industries.values()):
        complete = False
    complete = complete and _pool_is_complete(snapshot, rows)
    return _finalize(
        snapshot,
        "S06",
        rows,
        key,
        pool_complete=complete,
        config_id=config_id,
        config_version=config_version,
        industries=industries,
        bound_s01_config_version=S01_DEFAULT_CONFIG_VERSION,
        notes=("S06_BINDS_" + S01_DEFAULT_CONFIG_VERSION,),
    )


# ---------------------------------------------------------------------------
# S07
# ---------------------------------------------------------------------------


def _ttm_metrics(fin: FinancialSnapshot) -> tuple[dict[str, Decimal], Numeric | None]:
    if fin.conflict:
        return {}, Numeric(None, ValueStatus.CONFLICT, "FINANCIAL_CONFLICT")
    np_fy = fin.np_ytd
    ocf_fy = fin.ocf_ytd
    if not fin.is_year_end:
        if fin.np_fy_prior is None or fin.np_ytd_prior_same is None:
            return {}, Numeric(None, ValueStatus.MISSING, "PRIOR_NP_MISSING")
        if fin.ocf_fy_prior is None or fin.ocf_ytd_prior_same is None:
            return {}, Numeric(None, ValueStatus.MISSING, "PRIOR_OCF_MISSING")
        if not (np_fy.usable and fin.np_fy_prior.usable and fin.np_ytd_prior_same.usable):
            return {}, next(item for item in (np_fy, fin.np_fy_prior, fin.np_ytd_prior_same) if not item.usable)
        if not (ocf_fy.usable and fin.ocf_fy_prior.usable and fin.ocf_ytd_prior_same.usable):
            return {}, next(item for item in (ocf_fy, fin.ocf_fy_prior, fin.ocf_ytd_prior_same) if not item.usable)
        assert fin.np_fy_prior.value is not None and fin.np_ytd_prior_same.value is not None
        assert fin.ocf_fy_prior.value is not None and fin.ocf_ytd_prior_same.value is not None
        assert np_fy.value is not None and ocf_fy.value is not None
        np_ttm = np_fy.value + fin.np_fy_prior.value - fin.np_ytd_prior_same.value
        ocf_ttm = ocf_fy.value + fin.ocf_fy_prior.value - fin.ocf_ytd_prior_same.value
    else:
        if not np_fy.usable:
            return {}, np_fy
        if not ocf_fy.usable:
            return {}, ocf_fy
        assert np_fy.value is not None and ocf_fy.value is not None
        np_ttm = np_fy.value
        ocf_ttm = ocf_fy.value

    if fin.equity_prior_same is None:
        return {}, Numeric(None, ValueStatus.MISSING, "PRIOR_EQUITY_MISSING")
    if not fin.equity.usable:
        return {}, fin.equity
    if not fin.equity_prior_same.usable:
        return {}, fin.equity_prior_same
    assert fin.equity.value is not None and fin.equity_prior_same.value is not None
    equity_average = (fin.equity.value + fin.equity_prior_same.value) / 2
    if equity_average <= 0:
        return {}, Numeric(None, ValueStatus.NOT_APPLICABLE, "NON_POSITIVE_AVERAGE_EQUITY")
    roe = np_ttm / equity_average
    return {
        "np_ttm": np_ttm,
        "ocf_ttm": ocf_ttm,
        "equity_average": equity_average,
        "roe_ttm": roe,
    }, None


def _financial_available_at(available_at: str, business_date: str) -> bool:
    date_part = available_at[:10]
    if date_part < business_date:
        return True
    if date_part > business_date:
        return False
    if len(available_at) > 10 and ("T" in available_at or " " in available_at):
        time_part = available_at[11:19]
        return time_part <= "15:00:00"
    return True


def _financial_component_blocker(fin: FinancialSnapshot, business_date: str) -> Numeric | None:
    names = ["pe_ttm", "np_ytd", "ocf_ytd", "equity", "equity_prior_same"]
    if not fin.is_year_end:
        names.extend(["np_fy_prior", "ocf_fy_prior", "np_ytd_prior_same", "ocf_ytd_prior_same"])
    for name in names:
        value = getattr(fin, name, None)
        if value is None:
            continue
        checked = _check_available(value, business_date)
        if checked.status is ValueStatus.UNKNOWN and checked.reason == "VALUE_NOT_YET_AVAILABLE":
            return checked
    return None


def _available_ttm_value(
    current: Numeric,
    prior_fy: Numeric | None,
    prior_same: Numeric | None,
    is_year_end: bool,
    business_date: str,
) -> Decimal | None:
    current = _check_available(current, business_date)
    if not current.usable:
        return None
    if is_year_end:
        return current.value
    if prior_fy is None or prior_same is None:
        return None
    prior_fy = _check_available(prior_fy, business_date)
    prior_same = _check_available(prior_same, business_date)
    if not prior_fy.usable or not prior_same.usable:
        return None
    assert current.value is not None and prior_fy.value is not None and prior_same.value is not None
    return current.value + prior_fy.value - prior_same.value


def _s07_known_failure(fin: FinancialSnapshot, threshold: Decimal, business_date: str) -> bool:
    pe = _check_available(fin.pe_ttm, business_date)
    if pe.usable and pe.value is not None and pe.value <= 0:
        return True

    equity = _check_available(fin.equity, business_date)
    prior_equity = (
        _check_available(fin.equity_prior_same, business_date)
        if fin.equity_prior_same is not None
        else None
    )
    equity_average = None
    if equity.usable and prior_equity is not None and prior_equity.usable:
        assert equity.value is not None and prior_equity.value is not None
        equity_average = (equity.value + prior_equity.value) / 2
        if equity_average <= 0:
            return True

    np_ttm = _available_ttm_value(
        fin.np_ytd,
        fin.np_fy_prior,
        fin.np_ytd_prior_same,
        fin.is_year_end,
        business_date,
    )
    if np_ttm is not None and np_ttm <= 0:
        return True
    ocf_ttm = _available_ttm_value(
        fin.ocf_ytd,
        fin.ocf_fy_prior,
        fin.ocf_ytd_prior_same,
        fin.is_year_end,
        business_date,
    )
    if ocf_ttm is not None and ocf_ttm <= 0:
        return True
    if np_ttm is not None and equity_average is not None and equity_average > 0:
        if np_ttm / equity_average < threshold:
            return True
    return False


def _s07_metrics(snapshot: MarketSnapshot, security_id: str) -> tuple[dict[str, Decimal], Numeric | None]:
    fin = snapshot.financials.get(security_id)
    if fin is None:
        return {}, Numeric(None, ValueStatus.MISSING, "FINANCIAL_SNAPSHOT_MISSING")
    if fin.available_at is None:
        return {}, Numeric(None, ValueStatus.UNKNOWN, "FINANCIAL_AVAILABILITY_UNKNOWN")
    if not _financial_available_at(fin.available_at, snapshot.business_date):
        return {}, Numeric(None, ValueStatus.UNKNOWN, "FINANCIAL_NOT_YET_AVAILABLE")
    if fin.is_financial is None:
        return {}, Numeric(None, ValueStatus.UNKNOWN, "FINANCIAL_CLASSIFICATION_UNKNOWN")
    if fin.is_financial:
        return {}, Numeric(None, ValueStatus.NOT_APPLICABLE, "FINANCIAL_TEMPLATE_NOT_APPLICABLE")
    if fin.industry_id is None:
        return {}, Numeric(None, ValueStatus.UNKNOWN, "FINANCIAL_INDUSTRY_UNKNOWN")
    component_blocker = _financial_component_blocker(fin, snapshot.business_date)
    if component_blocker is not None:
        return {}, component_blocker
    if fin.pe_business_date != snapshot.business_date:
        return {}, Numeric(None, ValueStatus.UNKNOWN, "PE_BUSINESS_DATE_NOT_D")
    pe = fin.pe_ttm
    if pe.status is ValueStatus.NOT_APPLICABLE:
        return {}, pe
    if not pe.usable:
        return {}, pe
    assert pe.value is not None
    if pe.value <= 0:
        return {}, Numeric(None, ValueStatus.NOT_APPLICABLE, "NON_POSITIVE_PE")
    metrics, blocker = _ttm_metrics(fin)
    if blocker is not None:
        return {}, blocker
    metrics["pe_ttm"] = pe.value
    return metrics, None


def compute_s07(snapshot: MarketSnapshot, bundle: ConfigBundle) -> StrategyResult:
    cfg = bundle.s07
    config_id, config_version = bundle.effective_identity("S07")
    rows: dict[str, RowResult] = {}
    metrics_by_id: dict[str, dict[str, Decimal]] = {}
    for sid in sorted(snapshot.securities):
        security = snapshot.securities[sid]
        base_eligibility, base_reasons = _base_eligibility(snapshot, security, bundle)
        if base_eligibility is not Eligibility.SCORABLE:
            rows[sid] = _row(
                snapshot,
                sid,
                "S07",
                eligibility=base_eligibility,
                state=_state_from_eligibility(base_eligibility),
                reasons=base_reasons,
            )
            continue
        metrics, blocker = _s07_metrics(snapshot, sid)
        if blocker is not None:
            eligibility = _eligibility_from_blocker(blocker)
            rows[sid] = _row(
                snapshot,
                sid,
                "S07",
                eligibility=eligibility,
                state=_state_from_eligibility(eligibility),
                reasons=(_blocked_reason("S07_INPUT", blocker),),
            )
            continue
        metrics_by_id[sid] = metrics
        rows[sid] = _row(
            snapshot,
            sid,
            "S07",
            eligibility=Eligibility.SCORABLE,
            state=SignalState.ELIGIBLE_NOT_TRIGGERED,
            signal_status=ConditionStatus.UNKNOWN,
            observation_status=ConditionStatus.UNKNOWN,
            confirmation_status=ConditionStatus.UNKNOWN,
        )

    industry_ids = sorted({snapshot.financials[sid].industry_id for sid in metrics_by_id})
    industry_pools: dict[str, list[str]] = {industry_id: [] for industry_id in industry_ids}
    for sid, metrics in metrics_by_id.items():
        industry_id = snapshot.financials[sid].industry_id
        assert industry_id is not None
        industry_pools[industry_id].append(sid)

    for industry_id, members in industry_pools.items():
        pe_population = [metrics_by_id[sid]["pe_ttm"] for sid in members]
        roe_population = [metrics_by_id[sid]["roe_ttm"] for sid in members]
        for sid in members:
            q_pe = percentile_high(metrics_by_id[sid]["pe_ttm"], pe_population)
            q_roe = percentile_high(metrics_by_id[sid]["roe_ttm"], roe_population)
            assert q_pe is not None and q_roe is not None
            score = ((1 - q_pe) + q_roe) / 2
            metrics = metrics_by_id[sid]
            row = rows[sid]
            row.industry_id = industry_id
            row.metrics.update(
                {
                    "pe_ttm": metrics["pe_ttm"],
                    "np_ttm": metrics["np_ttm"],
                    "ocf_ttm": metrics["ocf_ttm"],
                    "equity_average": metrics["equity_average"],
                    "roe_ttm": metrics["roe_ttm"],
                    "q_pe_ttm": 1 - q_pe,
                    "q_roe_ttm": q_roe,
                    "score07": score,
                }
            )
            condition = (
                metrics["np_ttm"] > 0
                and metrics["ocf_ttm"] > 0
                and metrics["roe_ttm"] >= cfg.roe_threshold
            )
            row.signal_status = ConditionStatus.TRUE if condition else ConditionStatus.FALSE
            row.observation_status = row.signal_status
            row.confirmation_status = row.signal_status
            row.conditions["positive_np"] = ConditionStatus.TRUE if metrics["np_ttm"] > 0 else ConditionStatus.FALSE
            row.conditions["positive_ocf"] = ConditionStatus.TRUE if metrics["ocf_ttm"] > 0 else ConditionStatus.FALSE
            row.conditions["roe_threshold"] = (
                ConditionStatus.TRUE if metrics["roe_ttm"] >= cfg.roe_threshold else ConditionStatus.FALSE
            )
            if condition:
                row.formal_candidate = True
                row.signal_state = SignalState.CANDIDATE

    def key(row: RowResult) -> tuple:
        return (
            negative(row.metrics["score07"]),  # type: ignore[arg-type]
            negative(row.metrics["roe_ttm"]),  # type: ignore[arg-type]
            key_decimal(row.metrics["pe_ttm"]),  # type: ignore[arg-type]
            row.security_id,
        )

    pool_complete = _pool_is_complete(snapshot, rows)
    return _finalize(
        snapshot,
        "S07",
        rows,
        key,
        pool_complete=pool_complete,
        config_id=config_id,
        config_version=config_version,
    )


# ---------------------------------------------------------------------------
# S08
# ---------------------------------------------------------------------------


def _s08_metrics(snapshot: MarketSnapshot, security_id: str) -> tuple[dict[str, Decimal], Numeric | None]:
    end_index = _index(snapshot, snapshot.business_date)
    if end_index is None or end_index - 4 < 0:
        return {}, Numeric(None, ValueStatus.MISSING, "INSUFFICIENT_HISTORY")
    dates = snapshot.calendar[end_index - 4 : end_index + 1]
    flows: list[Decimal] = []
    amounts: list[Decimal] = []
    for date in dates:
        flow = snapshot.fund_flows.get(security_id, {}).get(date)
        if flow is None:
            return {}, Numeric(None, ValueStatus.MISSING, "FUND_FLOW_MISSING")
        flow = _check_available(flow, snapshot.business_date)
        if flow.status is ValueStatus.RAW_ZERO_SEMANTICS_UNKNOWN:
            return {}, flow
        if flow.status is ValueStatus.NOT_APPLICABLE:
            return {}, flow
        if not flow.usable:
            return {}, flow
        amount = _value_at(snapshot, security_id, date, "amount")
        if amount.status is ValueStatus.RAW_ZERO_SEMANTICS_UNKNOWN:
            return {}, amount
        if amount.status is ValueStatus.NOT_APPLICABLE:
            return {}, amount
        if not amount.usable:
            return {}, amount
        assert flow.value is not None and amount.value is not None
        flows.append(flow.value)
        amounts.append(amount.value)
    amount_sum = sum(amounts, ZERO)
    if amount_sum <= 0:
        return {}, Numeric(None, ValueStatus.NOT_APPLICABLE, "NOT_APPLICABLE_ZERO_AMOUNT")
    net_sum = sum(flows, ZERO)
    positive_days = sum(1 for value in flows if value > 0)
    return {
        "net_days": flows,  # type: ignore[dict-item]
        "amount_days": amounts,  # type: ignore[dict-item]
        "net_sum": net_sum,
        "amount_sum": amount_sum,
        "positive_days": Decimal(positive_days),
        "flow_ratio": net_sum / amount_sum,
    }, None


def compute_s08(snapshot: MarketSnapshot, bundle: ConfigBundle) -> StrategyResult:
    cfg = bundle.s08
    config_id, config_version = bundle.effective_identity("S08")
    rows: dict[str, RowResult] = {}
    metrics_by_id: dict[str, dict[str, Decimal]] = {}
    for sid in sorted(snapshot.securities):
        security = snapshot.securities[sid]
        base_eligibility, base_reasons = _base_eligibility(snapshot, security, bundle)
        if base_eligibility is not Eligibility.SCORABLE:
            rows[sid] = _row(
                snapshot,
                sid,
                "S08",
                eligibility=base_eligibility,
                state=_state_from_eligibility(base_eligibility),
                reasons=base_reasons,
            )
            continue
        price = _value_at(snapshot, sid, snapshot.business_date, "adjusted_close")
        ma20 = ma_value(snapshot, sid, 20)
        if price.usable and ma20.usable:
            assert price.value is not None and ma20.value is not None
            price_condition = ConditionStatus.TRUE if price.value > ma20.value else ConditionStatus.FALSE
        else:
            price_condition = ConditionStatus.UNKNOWN
        metrics, blocker = _s08_metrics(snapshot, sid)
        if blocker is not None:
            eligibility = _eligibility_from_blocker(blocker)
            row = _row(
                snapshot,
                sid,
                "S08",
                eligibility=eligibility,
                state=_state_from_eligibility(eligibility),
                signal_status=ConditionStatus.FALSE if price_condition is ConditionStatus.FALSE else ConditionStatus.UNKNOWN,
                observation_status=ConditionStatus.UNKNOWN,
                confirmation_status=price_condition,
                reasons=(_blocked_reason("S08_INPUT", blocker),),
            )
            row.metrics["price"] = price.value if price.usable else None
            row.metrics["ma20"] = ma20.value if ma20.usable else None
            row.conditions["price_above_ma20"] = price_condition
            if not price.usable or not ma20.usable:
                price_blocker = price if not price.usable else ma20
                row.reasons = row.reasons + (_blocked_reason("S08_MA20_INPUT", price_blocker),)
            rows[sid] = row
            continue
        metrics_by_id[sid] = metrics
        row = _row(
            snapshot,
            sid,
            "S08",
            eligibility=Eligibility.SCORABLE,
            state=SignalState.ELIGIBLE_NOT_TRIGGERED,
            signal_status=ConditionStatus.UNKNOWN,
            observation_status=ConditionStatus.UNKNOWN,
            confirmation_status=ConditionStatus.UNKNOWN,
        )
        row.metrics.update(metrics)
        row.metrics["price"] = price.value if price.usable else None
        row.metrics["ma20"] = ma20.value if ma20.usable else None
        if not price.usable or not ma20.usable:
            blocker = price if not price.usable else ma20
            row.reasons = (_blocked_reason("S08_MA20_INPUT", blocker),)
        rows[sid] = row

    for sid, metrics in metrics_by_id.items():
        row = rows[sid]
        if row.eligibility is not Eligibility.SCORABLE:
            continue
        price = row.metrics["price"]
        ma20 = row.metrics["ma20"]
        flow_condition = (
            metrics["positive_days"] >= cfg.positive_days_required
            and metrics["net_sum"] > 0
        )
        if price is None or ma20 is None:
            price_condition = ConditionStatus.UNKNOWN
        else:
            price_condition = ConditionStatus.TRUE if price > ma20 else ConditionStatus.FALSE
        if not flow_condition:
            overall = ConditionStatus.FALSE
        elif price_condition is ConditionStatus.TRUE:
            overall = ConditionStatus.TRUE
        elif price_condition is ConditionStatus.FALSE:
            overall = ConditionStatus.FALSE
        else:
            overall = ConditionStatus.UNKNOWN
        row.signal_status = overall
        row.observation_status = ConditionStatus.TRUE if flow_condition else ConditionStatus.FALSE
        row.confirmation_status = price_condition
        row.conditions["positive_days"] = (
            ConditionStatus.TRUE
            if metrics["positive_days"] >= cfg.positive_days_required
            else ConditionStatus.FALSE
        )
        row.conditions["net_sum_positive"] = ConditionStatus.TRUE if metrics["net_sum"] > 0 else ConditionStatus.FALSE
        row.conditions["price_above_ma20"] = price_condition
        if overall is ConditionStatus.TRUE:
            row.formal_candidate = True
            row.signal_state = SignalState.CANDIDATE
        elif overall is ConditionStatus.UNKNOWN:
            row.signal_state = SignalState.INPUT_UNKNOWN
        else:
            row.signal_state = SignalState.ELIGIBLE_NOT_TRIGGERED

    def key(row: RowResult) -> tuple:
        return (
            negative(row.metrics["flow_ratio"]),  # type: ignore[arg-type]
            negative(row.metrics["positive_days"]),  # type: ignore[arg-type]
            negative(row.metrics["net_sum"]),  # type: ignore[arg-type]
            row.security_id,
        )

    pool_complete = _pool_is_complete(snapshot, rows)
    return _finalize(
        snapshot,
        "S08",
        rows,
        key,
        pool_complete=pool_complete,
        config_id=config_id,
        config_version=config_version,
    )


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_COMPUTE = {
    "S01": compute_s01,
    "S02": compute_s02,
    "S03": compute_s03,
    "S04": compute_s04,
    "S05": compute_s05,
    "S06": compute_s06,
    "S07": compute_s07,
    "S08": compute_s08,
}


def compute_strategy(snapshot: MarketSnapshot, strategy_id: str, bundle: ConfigBundle) -> StrategyResult:
    if strategy_id not in _COMPUTE:
        raise ValueError(f"unknown strategy_id {strategy_id!r}; expected one of {STRATEGY_IDS}")
    return _COMPUTE[strategy_id](snapshot, bundle)
