"""Public engine for OD-1 calculations, signal records and exit decisions."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

from .config import ConfigBundle, S01_DEFAULT_CONFIG, default_configs
from .diagnostics import compute_diagnostics as _compute_diagnostics
from .diagnostics import style_view
from .model import (
    ConditionStatus,
    ExitContext,
    ExitDecision,
    MarketSnapshot,
    StrategyResult,
    ValueStatus,
)
from .strategies import (
    STRATEGY_IDS,
    _check_available,
    _index,
    _s01_metrics,
    _s07_metrics,
    _s08_metrics,
    _value_at,
    compute_strategy,
    ma_value,
)

__all__ = [
    "compute_all",
    "compute_diagnostics",
    "compute_strategy",
    "evaluate_exit",
    "signal_records",
    "style_view",
]


def compute_all(snapshot: MarketSnapshot, bundle: ConfigBundle | None = None) -> dict[str, StrategyResult]:
    bundle = bundle or default_configs()
    return {strategy_id: compute_strategy(snapshot, strategy_id, bundle) for strategy_id in STRATEGY_IDS}


def compute_diagnostics(snapshot: MarketSnapshot, bundle: ConfigBundle | None = None):
    return _compute_diagnostics(snapshot, bundle or default_configs())


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, ConditionStatus):
        return value.value
    if isinstance(value, ValueStatus):
        return value.value
    return value


def signal_records(results: Mapping[str, StrategyResult]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for strategy_id in sorted(results):
        result = results[strategy_id]
        for security_id in sorted(result.rows):
            row = result.rows[security_id]
            records.append(
                {
                    "signal_id": f"{row.strategy_id}:{row.security_id}:{row.signal_date}:{row.config_version}",
                    "security_id": row.security_id,
                    "strategy_id": row.strategy_id,
                    "config_id": row.config_id,
                    "config_version": row.config_version,
                    "signal_date": row.signal_date,
                    "input_version": row.input_version,
                    "qualification_status": row.eligibility.value,
                    "signal_state": row.signal_state.value,
                    "signal_status": row.signal_status.value,
                    "observation_status": row.observation_status.value,
                    "confirmation_status": row.confirmation_status.value,
                    "pool_rank": row.pool_rank,
                    "sample_pool_rank": row.sample_pool_rank,
                    "candidate_rank": row.candidate_rank,
                    "sample_candidate_rank": row.sample_candidate_rank,
                    "pool_size": result.pool_size,
                    "candidate_size": result.candidate_size,
                    "pool_complete": result.pool_complete,
                    "industry_id": row.industry_id,
                    "industry_pool_rank": row.industry_pool_rank,
                    "industry_trigger_rank": row.industry_trigger_rank,
                    "industry_total_rank": row.industry_total_rank,
                    "formal_candidate": row.formal_candidate,
                    "replacement_eligible": row.execution_replacement_order is not None,
                    "execution_replacement_order": row.execution_replacement_order,
                    "entry_conflict_exit": row.entry_conflict_exit.value,
                    "entry_platform_upper": _json_value(row.metrics.get("u20")),
                    "available_at": row.available_at or "UNKNOWN",
                    "bound_s01_config_version": result.bound_s01_config_version,
                    "reasons": list(row.reasons),
                    "metrics": _json_value(row.metrics),
                    "conditions": _json_value(row.conditions),
                    "sort_key": list(row.sort_key),
                }
            )
    return records


def _decision(
    reasons: list[str],
    unknown_reasons: list[str],
    *,
    primary_reason: str | None = None,
) -> ExitDecision:
    if reasons:
        order = ("STOP_LOSS", "STRATEGY_EXIT", "MAX_HOLDING")
        priority = {name: index for index, name in enumerate(order)}
        primary = primary_reason or min(reasons, key=lambda item: priority.get(item.split(":")[0], 99))
        return ExitDecision(ConditionStatus.TRUE, tuple(reasons), primary, True)
    if unknown_reasons:
        return ExitDecision(ConditionStatus.UNKNOWN, tuple(unknown_reasons), unknown_reasons[0], False)
    return ExitDecision(ConditionStatus.FALSE, (), None, False)


def evaluate_exit(
    snapshot: MarketSnapshot,
    strategy_id: str,
    security_id: str,
    context: ExitContext,
    bundle: ConfigBundle | None = None,
) -> ExitDecision:
    if not context.has_position:
        return ExitDecision(ConditionStatus.FALSE)
    if strategy_id not in STRATEGY_IDS:
        raise ValueError(f"unknown strategy_id {strategy_id!r}")
    bundle = bundle or default_configs()
    reasons: list[str] = []
    unknown: list[str] = []

    if context.common_stop_triggered:
        reasons.append("STOP_LOSS")
    elif context.common_stop_unknown:
        unknown.append("COMMON_STOP_UNKNOWN")

    cfg = {
        "S01": bundle.s01,
        "S02": bundle.s02,
        "S03": bundle.s03,
        "S04": bundle.s04,
        "S05": bundle.s05,
        "S06": bundle.s06,
        "S07": bundle.s07,
        "S08": bundle.s08,
    }[strategy_id]

    price = _value_at(snapshot, security_id, snapshot.business_date, "adjusted_close")
    if not price.usable and strategy_id not in {"S07"}:
        unknown.append("PRICE_UNKNOWN")

    if strategy_id == "S01":
        ma = ma_value(snapshot, security_id, cfg.ma_short)
        if ma.usable and price.usable and price.value is not None and ma.value is not None:
            if price.value < ma.value:
                reasons.append("STRATEGY_EXIT:S01_BELOW_MA20")
        elif not ma.usable:
            unknown.append("S01_MA20_UNKNOWN")
    elif strategy_id == "S02":
        if context.entry_platform_upper is None:
            unknown.append("S02_PLATFORM_CEILING_UNKNOWN")
        elif price.usable and price.value is not None and price.value < context.entry_platform_upper:
            reasons.append("STRATEGY_EXIT:S02_BELOW_PLATFORM")
    elif strategy_id == "S03":
        ma = ma_value(snapshot, security_id, 60)
        if ma.usable and price.usable and price.value is not None and ma.value is not None:
            if price.value < ma.value:
                reasons.append("STRATEGY_EXIT:S03_BELOW_MA60")
        elif not ma.usable:
            unknown.append("S03_MA60_UNKNOWN")
    elif strategy_id == "S04":
        ma = ma_value(snapshot, security_id, 20)
        if ma.usable and price.usable and price.value is not None and ma.value is not None:
            if price.value >= ma.value:
                reasons.append("STRATEGY_EXIT:S04_REACHED_MA20")
        elif not ma.usable:
            unknown.append("S04_MA20_UNKNOWN")
    elif strategy_id == "S05":
        ma = ma_value(snapshot, security_id, 60)
        if ma.usable and price.usable and price.value is not None and ma.value is not None:
            if price.value < ma.value:
                reasons.append("STRATEGY_EXIT:S05_BELOW_MA60")
        elif not ma.usable:
            unknown.append("S05_MA60_UNKNOWN")
    elif strategy_id == "S06":
        ma = ma_value(snapshot, security_id, S01_DEFAULT_CONFIG.ma_short)
        if ma.usable and price.usable and price.value is not None and ma.value is not None:
            if price.value < ma.value:
                reasons.append("STRATEGY_EXIT:S06_BELOW_BOUND_MA20")
        elif not ma.usable:
            unknown.append("S06_MA20_UNKNOWN")
        history = context.industry_rank_history[-2:]
        if len(history) < 2 or any(item is None for item in history):
            unknown.append("S06_INDUSTRY_RANK_HISTORY_UNKNOWN")
        elif all(item is not None and item > 10 for item in history):
            reasons.append("STRATEGY_EXIT:S06_INDUSTRY_OUT_OF_TOP10_TWO_CLOSES")
    elif strategy_id == "S07":
        metrics, blocker = _s07_metrics(snapshot, security_id)
        if blocker is not None:
            if blocker.status is ValueStatus.NOT_APPLICABLE:
                reasons.append("STRATEGY_EXIT:S07_CONDITION_FAILED")
            else:
                unknown.append("S07_CONDITION_UNKNOWN")
        else:
            condition = metrics["np_ttm"] > 0 and metrics["ocf_ttm"] > 0 and metrics["roe_ttm"] >= cfg.roe_threshold
            if not condition:
                reasons.append("STRATEGY_EXIT:S07_CONDITION_FAILED")
    elif strategy_id == "S08":
        ma = ma_value(snapshot, security_id, 20)
        if ma.usable and price.usable and price.value is not None and ma.value is not None:
            if price.value < ma.value:
                reasons.append("STRATEGY_EXIT:S08_BELOW_MA20")
        elif not ma.usable:
            unknown.append("S08_MA20_UNKNOWN")
        flows = _last_three_flows(snapshot, security_id)
        if flows is None:
            unknown.append("S08_LAST_THREE_FLOWS_UNKNOWN")
        elif all(flow < 0 for flow in flows):
            reasons.append("STRATEGY_EXIT:S08_THREE_DAY_OUTFLOW")

    max_holding = {
        "S01": bundle.s01.max_holding,
        "S02": bundle.s02.max_holding,
        "S03": bundle.s03.max_holding,
        "S04": bundle.s04.max_holding,
        "S05": bundle.s05.max_holding,
        "S06": bundle.s06.max_holding,
        "S07": None,
        "S08": bundle.s08.max_holding,
    }[strategy_id]
    if max_holding is not None and context.holding_days >= max_holding:
        reasons.append("MAX_HOLDING")

    return _decision(reasons, unknown)


def _last_three_flows(snapshot: MarketSnapshot, security_id: str) -> list[Decimal] | None:
    end_index = _index(snapshot, snapshot.business_date)
    if end_index is None or end_index - 2 < 0:
        return None
    values: list[Decimal] = []
    for date in snapshot.calendar[end_index - 2 : end_index + 1]:
        flow = snapshot.fund_flows.get(security_id, {}).get(date)
        if flow is not None:
            flow = _check_available(flow, snapshot.business_date)
        if flow is None or not flow.usable or flow.status is ValueStatus.RAW_ZERO_SEMANTICS_UNKNOWN:
            return None
        assert flow.value is not None
        values.append(flow.value)
    return values
